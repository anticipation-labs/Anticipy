"""
Cascade-resilience tests for the 4-tier MODEL_CHAIN (gemini → groq → mistral → deepseek).

These tests stub `_call_gemini` and `_call_openai_compatible` in `app.models` so
no real API traffic is generated, then verify the high-level
`llm_call` / `llm_call_json` / `llm_call_text` / `llm_call_json_str` surfaces
behave correctly under partial-degradation conditions:

  - Gemini 429 → fall over to Groq
  - Gemini 429 + Groq 503 → fall over to Mistral
  - All providers down → DegradedResponse() (falsy)
  - Broken JSON on first provider → succeed on second
  - tracker.exceeded → no provider called, returns DegradedResponse
  - llm_call_json_str forwards json_mode=True
  - provider_slot serializes same-provider, parallelizes different
  - _await_throttle no-blocks on a fresh provider
  - effective_layer_timeout_seconds math when MODEL_CHAIN[0].min_interval > 0

Pattern: stubs return the same `(text, in_tokens, out_tokens)` tuple shape
that the real backends do; httpx.HTTPStatusError raised with a real Request +
Response so the cascade's `e.response.status_code` access works. We also
monkeypatch `app.models.asyncio.sleep` to a no-op so the cascade's between-
attempt backoff (0.5–4s) doesn't make tests slow — except in the throttle
spacing test, where real-time behavior is what we're verifying.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

# Test env must be set before importing app.config (which validates the
# Fernet key on import). Static dev-only fixed values matching test_models.py.
os.environ.setdefault("JWT_SECRET", "x" * 48)
os.environ.setdefault(
    "PROFILE_ENCRYPTION_KEY",
    "RoUzc1lJ3gkPkHrxoYQzv1trmEJSQbgo6mNhlQYgfJk=",
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import httpx  # noqa: E402

from app import models  # noqa: E402
from app.models import (  # noqa: E402
    CostTracker,
    DegradedResponse,
    effective_layer_timeout_seconds,
    llm_call,
    llm_call_json,
    llm_call_json_str,
    llm_call_text,
    provider_slot,
)


# ─────────────────────────────────────────────────────────────────────────────
# Test scaffolding — chain installer + stub helpers
# ─────────────────────────────────────────────────────────────────────────────


# A fixed 4-tier chain with all four providers present, regardless of what the
# real environment looks like. Tests are deterministic.
_FIXED_CHAIN: list[dict] = [
    {
        "name": "gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "api_key": "fake-gemini",
        "model": "gemini-2.5-flash",
        "cost_input": 0.0001,
        "cost_output": 0.0004,
        "min_interval_seconds": 0.0,
    },
    {
        "name": "groq",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key": "fake-groq",
        "model": "llama-3.3-70b-versatile",
        "cost_input": 0.00059,
        "cost_output": 0.00079,
        "min_interval_seconds": 0.0,
    },
    {
        "name": "mistral",
        "base_url": "https://api.mistral.ai/v1",
        "api_key": "fake-mistral",
        "model": "mistral-large-latest",
        "cost_input": 0.0006,
        "cost_output": 0.0024,
        "min_interval_seconds": 0.0,
    },
    {
        "name": "deepseek",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "fake-deepseek",
        "model": "deepseek-chat",
        "cost_input": 0.00014,
        "cost_output": 0.00028,
        "min_interval_seconds": 0.0,
    },
]


def _install_fixed_chain() -> list[dict]:
    """Replace MODEL_CHAIN in-place; return the saved original for restore.
    Also clears the per-provider quota tracking added in models.py so test
    state from a prior cascade test (where a provider got marked 429)
    doesn't leak into this one. Cop-out #18 fix: quota state is module-level
    in production, but tests need a clean slate."""
    saved = list(models.MODEL_CHAIN)
    models.MODEL_CHAIN.clear()
    models.MODEL_CHAIN.extend(_FIXED_CHAIN)
    # Reset quota-tracking state so prior tests' 429s don't pre-block providers.
    if hasattr(models, "_reset_provider_quotas"):
        models._reset_provider_quotas()
    return saved


def _restore_chain(saved: list[dict]) -> None:
    models.MODEL_CHAIN.clear()
    models.MODEL_CHAIN.extend(saved)


def _reset_throttle_state() -> None:
    models._throttle_locks.clear()
    models._throttle_last_call.clear()
    models._provider_semaphores.clear()


def _make_http_error(status: int) -> httpx.HTTPStatusError:
    """Build a real HTTPStatusError so e.response.status_code works."""
    req = httpx.Request("POST", "https://example.invalid/x")
    resp = httpx.Response(status, request=req)
    return httpx.HTTPStatusError(f"HTTP {status}", request=req, response=resp)


async def _no_sleep(_seconds: float) -> None:
    """Replacement for asyncio.sleep that doesn't actually sleep —
    keeps the cascade's between-attempt backoff from making tests slow."""
    return None


def _patch_no_sleep_in_models() -> object:
    """Patch the `asyncio` reference inside app.models so its calls to
    asyncio.sleep are no-ops, but the global asyncio module still works
    everywhere else (including our own asyncio.run wrapper)."""
    saved = models.asyncio.sleep
    models.asyncio.sleep = _no_sleep  # type: ignore[assignment]
    return saved


def _restore_sleep(saved) -> None:
    models.asyncio.sleep = saved  # type: ignore[assignment]


# ─────────────────────────────────────────────────────────────────────────────
# 1. Gemini 429 → Groq returns valid JSON
# ─────────────────────────────────────────────────────────────────────────────


def test_gemini_429_falls_over_to_groq() -> None:
    saved_chain = _install_fixed_chain()
    saved_sleep = _patch_no_sleep_in_models()
    calls: dict[str, int] = {"gemini": 0, "openai_compat": 0}

    async def stub_gemini(*_a, **_kw):
        calls["gemini"] += 1
        raise _make_http_error(429)

    async def stub_openai(base_url, *_a, **_kw):
        calls["openai_compat"] += 1
        # First openai-compat call must be groq (Plan B).
        assert "groq" in base_url, f"expected groq base_url, got {base_url}"
        return ('{"answer": "from-groq", "ok": true}', 12, 8)

    saved_g = models._call_gemini
    saved_o = models._call_openai_compatible
    models._call_gemini = stub_gemini  # type: ignore[assignment]
    models._call_openai_compatible = stub_openai  # type: ignore[assignment]

    try:
        async def go():
            t = CostTracker()
            result = await llm_call_json([{"role": "user", "content": "x"}], t)
            assert isinstance(result, dict), f"expected dict, got {type(result)}"
            assert result.get("answer") == "from-groq"
            # Gemini was tried (with retry-on-429 → 2 attempts), Groq was tried once.
            assert calls["gemini"] >= 1
            assert calls["openai_compat"] == 1
            # Cost was attributed to groq.
            assert t.calls == 1
            assert t.total_usd > 0.0

        asyncio.run(go())
    finally:
        models._call_gemini = saved_g  # type: ignore[assignment]
        models._call_openai_compatible = saved_o  # type: ignore[assignment]
        _restore_sleep(saved_sleep)
        _restore_chain(saved_chain)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Gemini 429 + Groq 503 → Mistral succeeds
# ─────────────────────────────────────────────────────────────────────────────


def test_two_providers_down_mistral_works() -> None:
    saved_chain = _install_fixed_chain()
    saved_sleep = _patch_no_sleep_in_models()
    seen_providers: list[str] = []

    async def stub_gemini(*_a, **_kw):
        seen_providers.append("gemini")
        raise _make_http_error(429)

    async def stub_openai(base_url, *_a, **_kw):
        if "groq" in base_url:
            seen_providers.append("groq")
            raise _make_http_error(503)
        if "api.mistral.ai" in base_url:
            seen_providers.append("mistral")
            return ('{"src": "mistral"}', 5, 3)
        if "deepseek" in base_url:
            seen_providers.append("deepseek")
            return ('{"src": "deepseek"}', 5, 3)
        raise AssertionError(f"unexpected base_url {base_url}")

    saved_g = models._call_gemini
    saved_o = models._call_openai_compatible
    models._call_gemini = stub_gemini  # type: ignore[assignment]
    models._call_openai_compatible = stub_openai  # type: ignore[assignment]

    try:
        async def go():
            t = CostTracker()
            result = await llm_call_json([{"role": "user", "content": "x"}], t)
            assert isinstance(result, dict), f"expected dict, got {type(result)}"
            assert result.get("src") == "mistral"
            # Order of providers tried: gemini (≥1), groq (≥1), mistral (1).
            # Deepseek must NOT have been called — mistral short-circuited.
            assert "deepseek" not in seen_providers, f"deepseek leaked: {seen_providers}"
            assert "mistral" in seen_providers
            assert seen_providers.index("mistral") > seen_providers.index("groq")

        asyncio.run(go())
    finally:
        models._call_gemini = saved_g  # type: ignore[assignment]
        models._call_openai_compatible = saved_o  # type: ignore[assignment]
        _restore_sleep(saved_sleep)
        _restore_chain(saved_chain)


# ─────────────────────────────────────────────────────────────────────────────
# 3. All four providers down → DegradedResponse (falsy) for both
#    llm_call_json and llm_call_text
# ─────────────────────────────────────────────────────────────────────────────


def test_all_providers_down_returns_degraded() -> None:
    saved_chain = _install_fixed_chain()
    saved_sleep = _patch_no_sleep_in_models()
    call_count = {"n": 0}

    async def stub_gemini(*_a, **_kw):
        call_count["n"] += 1
        raise _make_http_error(500)

    async def stub_openai(*_a, **_kw):
        call_count["n"] += 1
        raise _make_http_error(500)

    saved_g = models._call_gemini
    saved_o = models._call_openai_compatible
    models._call_gemini = stub_gemini  # type: ignore[assignment]
    models._call_openai_compatible = stub_openai  # type: ignore[assignment]

    try:
        async def go():
            # llm_call_json
            t1 = CostTracker()
            r1 = await llm_call_json([{"role": "user", "content": "x"}], t1)
            assert isinstance(r1, DegradedResponse)
            assert not r1, "DegradedResponse must be falsy"
            assert not isinstance(r1, dict), "must NOT be a dict (callers branch on isinstance)"

            # llm_call_text
            t2 = CostTracker()
            r2 = await llm_call_text([{"role": "user", "content": "x"}], t2)
            assert isinstance(r2, DegradedResponse)
            assert not r2

            # All four providers must have been tried at least once.
            # (Each may have been retried up to 2x for 5xx, but the cascade
            # treats non-429 5xx as terminal-this-model after 1 attempt
            # because it's an unrecognized HTTPStatusError branch.)
            assert call_count["n"] >= 4, f"only {call_count['n']} provider calls"

        asyncio.run(go())
    finally:
        models._call_gemini = saved_g  # type: ignore[assignment]
        models._call_openai_compatible = saved_o  # type: ignore[assignment]
        _restore_sleep(saved_sleep)
        _restore_chain(saved_chain)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Broken/truncated JSON on Gemini → recover on Groq
# ─────────────────────────────────────────────────────────────────────────────


def test_broken_json_first_provider_recovers_on_second() -> None:
    saved_chain = _install_fixed_chain()
    saved_sleep = _patch_no_sleep_in_models()

    async def stub_gemini(*_a, **_kw):
        # Truly garbled — none of the 5 strategies should recover anything.
        return ("@@@ not even close to json zzz", 4, 2)

    async def stub_openai(base_url, *_a, **_kw):
        assert "groq" in base_url, f"second hop must be groq, got {base_url}"
        return ('{"answer": "valid-from-groq"}', 6, 4)

    saved_g = models._call_gemini
    saved_o = models._call_openai_compatible
    models._call_gemini = stub_gemini  # type: ignore[assignment]
    models._call_openai_compatible = stub_openai  # type: ignore[assignment]

    try:
        async def go():
            t = CostTracker()
            result = await llm_call_json([{"role": "user", "content": "x"}], t)
            assert isinstance(result, dict)
            assert result.get("answer") == "valid-from-groq"

        asyncio.run(go())
    finally:
        models._call_gemini = saved_g  # type: ignore[assignment]
        models._call_openai_compatible = saved_o  # type: ignore[assignment]
        _restore_sleep(saved_sleep)
        _restore_chain(saved_chain)


# ─────────────────────────────────────────────────────────────────────────────
# 5. tracker.exceeded short-circuits — no provider call at all
# ─────────────────────────────────────────────────────────────────────────────


def test_tracker_exceeded_short_circuits() -> None:
    saved_chain = _install_fixed_chain()
    called = {"n": 0}

    async def stub_gemini(*_a, **_kw):
        called["n"] += 1
        return ('{"x": 1}', 1, 1)

    async def stub_openai(*_a, **_kw):
        called["n"] += 1
        return ('{"x": 1}', 1, 1)

    saved_g = models._call_gemini
    saved_o = models._call_openai_compatible
    models._call_gemini = stub_gemini  # type: ignore[assignment]
    models._call_openai_compatible = stub_openai  # type: ignore[assignment]

    try:
        async def go():
            from app.config import MAX_COST_USD
            t = CostTracker()
            t.total_usd = MAX_COST_USD + 1.0  # already over the cap
            assert t.exceeded

            r1 = await llm_call([{"role": "user", "content": "x"}], t, require_json=True)
            assert isinstance(r1, DegradedResponse)
            assert not r1

            r2 = await llm_call_text([{"role": "user", "content": "x"}], t)
            assert isinstance(r2, DegradedResponse)

            r3 = await llm_call_json([{"role": "user", "content": "x"}], t)
            assert isinstance(r3, DegradedResponse)

            # No provider was ever invoked.
            assert called["n"] == 0, f"providers called {called['n']} times despite tracker.exceeded"

        asyncio.run(go())
    finally:
        models._call_gemini = saved_g  # type: ignore[assignment]
        models._call_openai_compatible = saved_o  # type: ignore[assignment]
        _restore_chain(saved_chain)


# ─────────────────────────────────────────────────────────────────────────────
# 6. llm_call_json_str forwards json_mode=True via _call_model
# ─────────────────────────────────────────────────────────────────────────────


def test_llm_call_json_str_forwards_json_mode() -> None:
    saved_chain = _install_fixed_chain()
    captured: dict = {}

    async def stub_call_model(model_cfg, messages, temperature=0.0, max_tokens=256, json_mode=False):
        captured["json_mode"] = json_mode
        captured["provider"] = model_cfg["name"]
        # Return clean parseable JSON so json_str validates.
        return ('{"k": "v"}', 3, 2)

    saved = models._call_model
    models._call_model = stub_call_model  # type: ignore[assignment]
    try:
        async def go():
            t = CostTracker()
            result = await llm_call_json_str([{"role": "user", "content": "x"}], t)
            assert result == '{"k": "v"}'
            assert captured["json_mode"] is True, "json_mode must be forwarded as True"
            assert captured["provider"] == "gemini", "first attempt should target Plan A"

        asyncio.run(go())
    finally:
        models._call_model = saved  # type: ignore[assignment]
        _restore_chain(saved_chain)


# ─────────────────────────────────────────────────────────────────────────────
# 7. provider_slot serializes same-provider, parallelizes different providers
# ─────────────────────────────────────────────────────────────────────────────


def test_provider_slot_serializes_same_parallelizes_different() -> None:
    """3 concurrent slot acquires on `mistral` with min_interval=1.0 finish at
    ~0s/~1s/~2s; 3 acquires on different providers all finish near-zero."""
    _reset_throttle_state()

    async def go():
        finishes: list[float] = []
        start = time.monotonic()

        async def acquire_mistral() -> None:
            async with provider_slot("mistral", 1.0):
                finishes.append(time.monotonic() - start)

        await asyncio.gather(acquire_mistral(), acquire_mistral(), acquire_mistral())
        finishes.sort()
        assert len(finishes) == 3
        assert finishes[0] < 0.1, f"first mistral finish {finishes[0]:.3f}s should be ~0"
        assert 0.95 <= finishes[1] <= 1.3, f"second mistral finish {finishes[1]:.3f}s, expected ~1s"
        assert 1.95 <= finishes[2] <= 2.4, f"third mistral finish {finishes[2]:.3f}s, expected ~2s"

        # Now reset and verify different-provider acquires run in parallel.
        _reset_throttle_state()
        diff_finishes: list[float] = []
        start2 = time.monotonic()

        async def acquire(p: str) -> None:
            async with provider_slot(p, 1.0):
                diff_finishes.append(time.monotonic() - start2)

        await asyncio.gather(acquire("p1"), acquire("p2"), acquire("p3"))
        for t in diff_finishes:
            assert t < 0.15, f"different-provider acquire took {t:.3f}s, expected near-zero"

    asyncio.run(go())


# ─────────────────────────────────────────────────────────────────────────────
# 8. _await_throttle on a fresh provider returns immediately
# ─────────────────────────────────────────────────────────────────────────────


def test_await_throttle_first_call_no_block() -> None:
    _reset_throttle_state()

    async def go():
        start = time.monotonic()
        await models._await_throttle("test_xyz_fresh", 1.0)
        elapsed = time.monotonic() - start
        assert elapsed < 0.05, f"fresh-provider throttle delayed {elapsed:.3f}s"

        # Zero-interval is also a no-op even with state.
        await models._await_throttle("test_xyz_fresh", 0.0)
        # ...followed by another call: still no-op for zero interval.
        start2 = time.monotonic()
        await models._await_throttle("brand_new_provider", 0.0)
        assert (time.monotonic() - start2) < 0.05

    asyncio.run(go())


# ─────────────────────────────────────────────────────────────────────────────
# 9. effective_layer_timeout_seconds(base, N) math when MODEL_CHAIN[0]
#    has min_interval > 0
# ─────────────────────────────────────────────────────────────────────────────


def test_effective_layer_timeout_with_throttled_primary() -> None:
    saved_chain = list(models.MODEL_CHAIN)
    try:
        models.MODEL_CHAIN.clear()
        models.MODEL_CHAIN.append({
            "name": "mistral",
            "min_interval_seconds": 1.5,
            "base_url": "x", "api_key": "x", "model": "x",
            "cost_input": 0.0, "cost_output": 0.0,
        })
        # base + (N-1) * 1.5
        assert effective_layer_timeout_seconds(10.0, expected_concurrent_calls=1) == 10.0
        assert abs(effective_layer_timeout_seconds(10.0, expected_concurrent_calls=2) - 11.5) < 1e-9
        assert abs(effective_layer_timeout_seconds(10.0, expected_concurrent_calls=4) - 14.5) < 1e-9
        # N=0 / N=1 path: base unchanged
        assert effective_layer_timeout_seconds(7.0, expected_concurrent_calls=0) == 7.0

        # When primary's interval == 0, base stays unchanged.
        models.MODEL_CHAIN.clear()
        models.MODEL_CHAIN.append({
            "name": "gemini",
            "min_interval_seconds": 0.0,
            "base_url": "x", "api_key": "x", "model": "x",
            "cost_input": 0.0, "cost_output": 0.0,
        })
        assert effective_layer_timeout_seconds(10.0, expected_concurrent_calls=5) == 10.0
    finally:
        _restore_chain(saved_chain)


# ─────────────────────────────────────────────────────────────────────────────
# 10. llm_call_json_str returns "" when every provider fails (NOT
#     DegradedResponse — the json_str surface predates the sentinel)
# ─────────────────────────────────────────────────────────────────────────────


def test_llm_call_json_str_returns_empty_on_full_failure() -> None:
    saved_chain = _install_fixed_chain()
    saved_sleep = _patch_no_sleep_in_models()

    async def stub_call_model(*_a, **_kw):
        raise _make_http_error(500)

    saved = models._call_model
    models._call_model = stub_call_model  # type: ignore[assignment]
    try:
        async def go():
            t = CostTracker()
            result = await llm_call_json_str([{"role": "user", "content": "x"}], t)
            assert result == "", f"expected '', got {result!r}"

        asyncio.run(go())
    finally:
        models._call_model = saved  # type: ignore[assignment]
        _restore_sleep(saved_sleep)
        _restore_chain(saved_chain)


# ─────────────────────────────────────────────────────────────────────────────
# 11. llm_call (require_json=False) returns text from first provider that
#     answers — and no further providers are queried
# ─────────────────────────────────────────────────────────────────────────────


def test_text_mode_first_success_short_circuits() -> None:
    saved_chain = _install_fixed_chain()
    seen: list[str] = []

    async def stub_gemini(*_a, **_kw):
        seen.append("gemini")
        return ("hello world", 3, 2)

    async def stub_openai(*_a, **_kw):
        seen.append("openai_compat")
        return ("should-not-reach", 0, 0)

    saved_g = models._call_gemini
    saved_o = models._call_openai_compatible
    models._call_gemini = stub_gemini  # type: ignore[assignment]
    models._call_openai_compatible = stub_openai  # type: ignore[assignment]
    try:
        async def go():
            t = CostTracker()
            r = await llm_call_text([{"role": "user", "content": "x"}], t)
            assert r == "hello world"
            assert seen == ["gemini"], f"unexpected fallover: {seen}"
            # Cost was tracked exactly once.
            assert t.calls == 1
        asyncio.run(go())
    finally:
        models._call_gemini = saved_g  # type: ignore[assignment]
        models._call_openai_compatible = saved_o  # type: ignore[assignment]
        _restore_chain(saved_chain)


# ─────────────────────────────────────────────────────────────────────────────
# 12. Empty MODEL_CHAIN → DegradedResponse without ever calling a stub
# ─────────────────────────────────────────────────────────────────────────────


def test_empty_chain_returns_degraded() -> None:
    saved_chain = list(models.MODEL_CHAIN)
    called = {"n": 0}

    async def stub_gemini(*_a, **_kw):
        called["n"] += 1
        return ('{"x": 1}', 1, 1)

    async def stub_openai(*_a, **_kw):
        called["n"] += 1
        return ('{"x": 1}', 1, 1)

    saved_g = models._call_gemini
    saved_o = models._call_openai_compatible
    models._call_gemini = stub_gemini  # type: ignore[assignment]
    models._call_openai_compatible = stub_openai  # type: ignore[assignment]
    try:
        models.MODEL_CHAIN.clear()
        async def go():
            t = CostTracker()
            r1 = await llm_call_json([{"role": "user", "content": "x"}], t)
            assert isinstance(r1, DegradedResponse)
            r2 = await llm_call_text([{"role": "user", "content": "x"}], t)
            assert isinstance(r2, DegradedResponse)
            r3 = await llm_call_json_str([{"role": "user", "content": "x"}], t)
            assert r3 == ""
            assert called["n"] == 0
        asyncio.run(go())
    finally:
        models._call_gemini = saved_g  # type: ignore[assignment]
        models._call_openai_compatible = saved_o  # type: ignore[assignment]
        _restore_chain(saved_chain)


if __name__ == "__main__":
    # Allow `python test_cascade_resilience.py` for quick local runs.
    test_gemini_429_falls_over_to_groq()
    print("PASS test_gemini_429_falls_over_to_groq")
    test_two_providers_down_mistral_works()
    print("PASS test_two_providers_down_mistral_works")
    test_all_providers_down_returns_degraded()
    print("PASS test_all_providers_down_returns_degraded")
    test_broken_json_first_provider_recovers_on_second()
    print("PASS test_broken_json_first_provider_recovers_on_second")
    test_tracker_exceeded_short_circuits()
    print("PASS test_tracker_exceeded_short_circuits")
    test_llm_call_json_str_forwards_json_mode()
    print("PASS test_llm_call_json_str_forwards_json_mode")
    test_provider_slot_serializes_same_parallelizes_different()
    print("PASS test_provider_slot_serializes_same_parallelizes_different")
    test_await_throttle_first_call_no_block()
    print("PASS test_await_throttle_first_call_no_block")
    test_effective_layer_timeout_with_throttled_primary()
    print("PASS test_effective_layer_timeout_with_throttled_primary")
    test_llm_call_json_str_returns_empty_on_full_failure()
    print("PASS test_llm_call_json_str_returns_empty_on_full_failure")
    test_text_mode_first_success_short_circuits()
    print("PASS test_text_mode_first_success_short_circuits")
    test_empty_chain_returns_degraded()
    print("PASS test_empty_chain_returns_degraded")
    print("\nAll cascade-resilience tests passed.")
