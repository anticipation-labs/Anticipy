"""
Phase 7 tests for the cost-efficient LLM router.

All tests use a mock HTTP hook (no real provider calls). Each test uses an
isolated SQLite cache file via tmp_path so they can run in parallel.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.llm_router import budget, cache, router  # noqa: E402
from app.llm_router import providers  # noqa: E402
from app.llm_router.budget import BudgetExceeded  # noqa: E402
from app.llm_router.providers import sanitize_text  # noqa: E402


# --- Test fixtures ----------------------------------------------------------


@pytest.fixture(autouse=True)
def isolate_cache(tmp_path: Path, monkeypatch):
    """Each test gets its own SQLite cache, its own caps, and a clean hook."""
    db = tmp_path / "llm_cache.db"
    cache.set_db_path(db)
    cache.cache_reset()
    budget.clear_caps_override()
    providers.clear_http_hook()
    # Provide dummy keys so providers don't refuse based on env.
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-deepseek")
    monkeypatch.setenv("GOOGLE_API_KEY", "sk-test-gemini")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-or")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    yield
    providers.clear_http_hook()
    cache.set_db_path(None)
    budget.clear_caps_override()


# --- Mock helpers -----------------------------------------------------------


def _make_deepseek_response(content: str = "ok", in_tok: int = 100, out_tok: int = 20):
    """Shape mimics DeepSeek's chat completions JSON."""
    return {
        "model": "deepseek-chat",
        "choices": [{
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": in_tok,
            "completion_tokens": out_tok,
            "prompt_cache_hit_tokens": 0,
        },
    }


def _make_gemini_response(content: str = "ok", in_tok: int = 100, out_tok: int = 20):
    return {
        "candidates": [{
            "content": {"parts": [{"text": content}]},
            "finishReason": "STOP",
        }],
        "usageMetadata": {
            "promptTokenCount": in_tok,
            "candidatesTokenCount": out_tok,
            "cachedContentTokenCount": 0,
        },
    }


def _make_perplexity_response(content: str = "facts", in_tok: int = 50, out_tok: int = 100):
    return {
        "model": "perplexity/sonar",
        "choices": [{
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": in_tok,
            "completion_tokens": out_tok,
        },
    }


def _make_openai_response(content: str = "ok", in_tok: int = 100, out_tok: int = 20):
    return {
        "choices": [{
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": in_tok,
            "completion_tokens": out_tok,
            "prompt_tokens_details": {"cached_tokens": 0},
        },
    }


class _HookRecorder:
    """Captures every (method, url, payload) call so tests can assert routing."""

    def __init__(self, responder):
        self.calls: list[dict] = []
        self.responder = responder

    async def __call__(self, method, url, headers, payload):
        self.calls.append({"method": method, "url": url, "payload": payload})
        return self.responder(url, payload)


def _install_hook(responder):
    """Convenience: wrap a sync responder and install as the HTTP hook."""
    recorder = _HookRecorder(responder)
    providers.set_http_hook(recorder)
    return recorder


# --- Tests ------------------------------------------------------------------


def test_intent_classify_routes_to_deepseek():
    def responder(url, payload):
        assert "deepseek.com" in url, f"intent_classify must use DeepSeek; got {url}"
        return _make_deepseek_response(content="ACTION")
    rec = _install_hook(responder)

    resp = asyncio.run(router.route(
        task_type="intent_classify",
        messages=[{"role": "user", "content": "remind me to call mom"}],
        user_id="u-test",
    ))

    assert resp["content"] == "ACTION"
    assert resp["model_used"] == "deepseek-v4-flash"
    assert resp["cache_hit"] is False
    assert len(rec.calls) == 1


def test_vision_dom_routes_to_gemini_flash():
    def responder(url, payload):
        assert "gemini-2.5-flash" in url, f"vision_dom must use Gemini Flash; got {url}"
        return _make_gemini_response(content="login button at x=100 y=200")
    rec = _install_hook(responder)

    resp = asyncio.run(router.route(
        task_type="vision_dom",
        messages=[{"role": "user", "content": "where is the login button?"}],
        user_id="u-test",
    ))

    assert resp["model_used"] == "gemini-2.5-flash"
    assert "login button" in resp["content"]
    assert len(rec.calls) == 1


def test_trivia_lookup_routes_to_sonar():
    def responder(url, payload):
        # Perplexity goes via OpenRouter; the model name is in the payload.
        assert payload["model"] == "perplexity/sonar", (
            f"trivia_lookup must request perplexity/sonar; got {payload['model']}"
        )
        return _make_perplexity_response(content="The capital of France is Paris.")
    rec = _install_hook(responder)

    # Trivia per-call cap default is $0.01 (search fee adds ~$0.005 above
    # the global $0.005 cap, per spec). No test override needed.

    resp = asyncio.run(router.route(
        task_type="trivia_lookup",
        messages=[{"role": "user", "content": "what's the capital of france"}],
        user_id="u-test",
    ))

    assert resp["model_used"] == "perplexity/sonar"
    assert "Paris" in resp["content"]


def test_escalation_routes_to_gemini_pro():
    def responder(url, payload):
        assert "gemini-2.5-pro" in url, f"escalation must use Gemini Pro; got {url}"
        return _make_gemini_response(content="deep reasoning result", in_tok=8000, out_tok=800)
    rec = _install_hook(responder)

    # Escalation has its own per-call cap ($0.02) in budget.py to allow
    # Gemini 2.5 Pro's higher token price (rare, gated by upstream confidence).

    resp = asyncio.run(router.route(
        task_type="escalation",
        messages=[{"role": "user", "content": "this is really hard"}],
        user_id="u-test",
    ))

    assert resp["model_used"] == "gemini-2.5-pro"
    assert "deep reasoning" in resp["content"]


def test_override_model_kwarg_respected():
    def responder(url, payload):
        assert "openai.com" in url, f"override should hit OpenAI; got {url}"
        return _make_openai_response(content="forced via override")
    rec = _install_hook(responder)

    resp = asyncio.run(router.route(
        task_type="planner",
        messages=[{"role": "user", "content": "plan it"}],
        user_id="u-test",
        override_model="gpt-4.1-nano",
    ))

    assert resp["model_used"] == "gpt-4.1-nano"
    assert resp["content"] == "forced via override"
    assert len(rec.calls) == 1


def test_provider_error_falls_through_to_backup():
    call_index = {"n": 0}

    def responder(url, payload):
        call_index["n"] += 1
        if call_index["n"] == 1:
            # First call (DeepSeek primary) errors out.
            raise providers.ProviderError("deepseek", 500, "synthetic upstream failure")
        # Second call (Gemini fallback) succeeds.
        if "gemini" in url:
            return _make_gemini_response(content="fallback worked")
        return _make_openai_response(content="fallback worked")
    rec = _install_hook(responder)

    resp = asyncio.run(router.route(
        task_type="planner",
        messages=[{"role": "user", "content": "plan it"}],
        user_id="u-test",
    ))

    assert resp["content"] == "fallback worked"
    # Primary deepseek failed; fallback (gemini-2.5-flash per matrix) won.
    assert resp["model_used"] == "gemini-2.5-flash"
    assert len(rec.calls) == 2


def test_cache_hit_skips_provider_call():
    call_count = {"n": 0}

    def responder(url, payload):
        call_count["n"] += 1
        return _make_deepseek_response(content="cached-able answer")
    _install_hook(responder)

    msgs = [{"role": "user", "content": "deterministic input for cache key"}]

    # First call: provider fires, cache_hit=False.
    r1 = asyncio.run(router.route(task_type="planner", messages=msgs, user_id="u-test"))
    assert r1["cache_hit"] is False
    assert call_count["n"] == 1

    # Second call: SAME input -> cache_hit=True, provider NOT called.
    r2 = asyncio.run(router.route(task_type="planner", messages=msgs, user_id="u-test"))
    assert r2["cache_hit"] is True
    assert r2["cost_usd"] == 0.0
    assert call_count["n"] == 1, "provider was called on cache hit"


def test_cache_miss_then_hit():
    """Two distinct prompts: each miss-then-hit independently."""
    call_count = {"n": 0}

    def responder(url, payload):
        call_count["n"] += 1
        return _make_deepseek_response(content="distinct answer")
    _install_hook(responder)

    a = [{"role": "user", "content": "prompt A"}]
    b = [{"role": "user", "content": "prompt B"}]

    asyncio.run(router.route(task_type="planner", messages=a, user_id="u-test"))
    asyncio.run(router.route(task_type="planner", messages=b, user_id="u-test"))
    assert call_count["n"] == 2

    # Now both should hit.
    rA = asyncio.run(router.route(task_type="planner", messages=a, user_id="u-test"))
    rB = asyncio.run(router.route(task_type="planner", messages=b, user_id="u-test"))
    assert rA["cache_hit"] is True
    assert rB["cache_hit"] is True
    assert call_count["n"] == 2, "cache hits triggered extra provider calls"

    stats = cache.cache_stats()
    assert stats["hit"] >= 2
    assert stats["miss"] >= 2


def test_budget_per_call_cap_enforced():
    """A call whose ESTIMATED cost exceeds the per-call cap is rejected."""
    # Set per-call cap absurdly low so any normal call trips.
    budget.set_caps_for_tests(per_call=0.0000001)

    def responder(url, payload):
        return _make_deepseek_response()
    _install_hook(responder)

    with pytest.raises(BudgetExceeded) as exc_info:
        asyncio.run(router.route(
            task_type="planner",
            messages=[{"role": "user", "content": "plan something cheap"}],
            user_id="u-test-per-call-cap",
        ))

    assert exc_info.value.scope == "per_call"


def test_budget_daily_cap_enforced():
    """When cumulative daily spend would exceed cap, BudgetExceeded fires.

    We pre-load the budget log with 100 calls at $0.003 each = $0.30,
    matching the spec's daily cap exactly, then attempt one more call.
    The next planner call's estimate (~$0.001) tips the user over.
    """
    user = "u-test-daily-cap"
    # Pre-fill 100 calls totalling exactly $0.30 (matches spec cap)
    for _ in range(100):
        budget.record_cost("planner", "deepseek-v4-flash", 0.003, user_id=user)

    budget.set_caps_for_tests(per_call=1.0, daily=0.30, monthly=999.0)

    def responder(url, payload):
        return _make_deepseek_response()
    _install_hook(responder)

    with pytest.raises(BudgetExceeded) as exc_info:
        asyncio.run(router.route(
            task_type="planner",
            messages=[{"role": "user", "content": "another call"}],
            user_id=user,
        ))

    assert exc_info.value.scope == "daily"
    # We loaded $0.30; cap is $0.30; one more call tips over.
    assert exc_info.value.cap_usd == pytest.approx(0.30)
    assert exc_info.value.spent_usd >= 0.30


def test_em_dash_stripped_from_response():
    """Em-dashes and citation markers MUST be scrubbed from every response."""
    raw = "Anticipy is great—really great[1]. Also good–ish[2]."
    def responder(url, payload):
        return _make_deepseek_response(content=raw)
    _install_hook(responder)

    resp = asyncio.run(router.route(
        task_type="planner",
        messages=[{"role": "user", "content": "talk about anticipy"}],
        user_id="u-test",
    ))

    assert "—" not in resp["content"], "em-dash leaked through"
    assert "–" not in resp["content"], "en-dash leaked through"
    assert "[1]" not in resp["content"], "citation marker leaked through"
    assert "[2]" not in resp["content"], "citation marker leaked through"
    # Verify the rest of the text survived.
    assert "Anticipy" in resp["content"]
    assert "great" in resp["content"]


def test_unknown_task_type_raises():
    """Defensive: callers must use a valid task type."""
    with pytest.raises(ValueError):
        asyncio.run(router.route(
            task_type="not_a_real_task",
            messages=[{"role": "user", "content": "x"}],
            user_id="u-test",
        ))


def test_sanitize_text_helper_is_idempotent():
    """sanitize_text is safe to call twice on its own output."""
    raw = "hello—world[3]"
    once = sanitize_text(raw)
    twice = sanitize_text(once)
    assert once == twice
    assert "—" not in once
    assert "[3]" not in once


def test_route_response_shape_is_complete():
    """Every successful route() call returns the full key set."""
    def responder(url, payload):
        return _make_deepseek_response(content="x")
    _install_hook(responder)

    r = asyncio.run(router.route(
        task_type="intent_classify",
        messages=[{"role": "user", "content": "x"}],
        user_id="u-test",
    ))
    required = {
        "content", "model_used", "cost_usd", "latency_ms",
        "cache_hit", "input_tokens", "output_tokens", "cached_tokens",
    }
    missing = required - set(r.keys())
    assert not missing, f"route() response missing keys: {missing}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
