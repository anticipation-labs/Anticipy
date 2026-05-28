"""Tests for app.models per-provider quota tracking.

The cascade should:
  - Skip a provider that returned 429 until its cooldown expires
  - Increase cooldown exponentially on consecutive 429s (5s, 10s, 20s, …, capped at 60s)
  - Reset cooldown on a successful call
  - Sleep until the earliest unblock when ALL providers are blocked
  - Treat 402 (payment required) as a long-cooldown block
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import httpx
import pytest

import app.models as models
from app.models import (
    CostTracker,
    DegradedResponse,
    _earliest_unblock_time,
    _is_provider_quota_blocked,
    _mark_provider_429,
    _mark_provider_ok,
    _provider_failure_count,
    _provider_quota_until,
    _reset_provider_quotas,
    llm_call,
)


@pytest.fixture(autouse=True)
def _reset():
    _reset_provider_quotas()
    yield
    _reset_provider_quotas()


# ─── Quota helpers ──────────────────────────────────────────────────────


def test_provider_starts_unblocked():
    blocked, _ = _is_provider_quota_blocked("gemini")
    assert not blocked


def test_429_blocks_for_5s():
    _mark_provider_429("gemini")
    blocked, until = _is_provider_quota_blocked("gemini")
    assert blocked
    delta = until - time.monotonic()
    assert 4.0 < delta <= 5.5


def test_consecutive_429s_double_cooldown():
    _mark_provider_429("gemini")  # 5s
    delta1 = _provider_quota_until["gemini"] - time.monotonic()
    _mark_provider_429("gemini")  # 10s
    delta2 = _provider_quota_until["gemini"] - time.monotonic()
    _mark_provider_429("gemini")  # 20s
    delta3 = _provider_quota_until["gemini"] - time.monotonic()
    assert delta1 < delta2 < delta3
    assert 19.0 < delta3 <= 20.5


def test_cooldown_capped_at_60s():
    for _ in range(20):
        _mark_provider_429("gemini")
    delta = _provider_quota_until["gemini"] - time.monotonic()
    assert delta <= 60.5
    assert delta >= 59.0


def test_mark_ok_clears_block():
    _mark_provider_429("gemini")
    assert _is_provider_quota_blocked("gemini")[0]
    _mark_provider_ok("gemini")
    assert not _is_provider_quota_blocked("gemini")[0]
    assert "gemini" not in _provider_quota_until
    assert _provider_failure_count.get("gemini", 0) == 0


def test_mark_ok_resets_failure_count_for_next_429():
    _mark_provider_429("gemini")  # 5s
    _mark_provider_429("gemini")  # 10s
    _mark_provider_ok("gemini")
    _mark_provider_429("gemini")  # back to 5s
    delta = _provider_quota_until["gemini"] - time.monotonic()
    assert 4.0 < delta <= 5.5


def test_earliest_unblock_returns_none_when_nothing_blocked():
    assert _earliest_unblock_time() is None


def test_earliest_unblock_returns_earliest():
    _mark_provider_429("gemini")
    time.sleep(0.05)
    _mark_provider_429("groq")
    earliest = _earliest_unblock_time()
    assert earliest is not None
    # gemini was marked first, so it unblocks first
    assert earliest <= _provider_quota_until["groq"]


# ─── llm_call cascade behavior ──────────────────────────────────────────


@pytest.fixture
def two_provider_chain(monkeypatch):
    """Patch MODEL_CHAIN to a two-provider stub. Returns the list so tests
    can inspect call counts via stubbed `_call_model`."""
    chain = [
        {"name": "gemini", "model": "g", "base_url": "http://g", "api_key": "k",
         "cost_input": 0.0, "cost_output": 0.0, "min_interval_seconds": 0.0},
        {"name": "groq", "model": "gr", "base_url": "http://gr", "api_key": "k",
         "cost_input": 0.0, "cost_output": 0.0, "min_interval_seconds": 0.0},
    ]
    monkeypatch.setattr(models, "MODEL_CHAIN", chain)
    return chain


def _make_429_response():
    """Construct an httpx HTTPStatusError equivalent to a 429."""
    req = httpx.Request("POST", "http://x")
    resp = httpx.Response(status_code=429, request=req)
    return httpx.HTTPStatusError("rate limited", request=req, response=resp)


def _make_402_response():
    req = httpx.Request("POST", "http://x")
    resp = httpx.Response(status_code=402, request=req)
    return httpx.HTTPStatusError("payment required", request=req, response=resp)


@pytest.mark.asyncio
async def test_429_marks_provider_blocked(monkeypatch, two_provider_chain):
    calls = []

    async def stub(model_cfg, messages, temperature, max_tokens, json_mode=False):
        calls.append(model_cfg["name"])
        if model_cfg["name"] == "gemini":
            raise _make_429_response()
        return ("groq result", 1, 1)

    monkeypatch.setattr(models, "_call_model", stub)

    tracker = CostTracker()
    result = await llm_call([{"role": "user", "content": "hi"}], tracker)
    assert result == "groq result"
    # gemini should be blocked
    assert _is_provider_quota_blocked("gemini")[0]
    # groq should be ok
    assert not _is_provider_quota_blocked("groq")[0]


@pytest.mark.asyncio
async def test_blocked_provider_skipped_on_subsequent_call(monkeypatch, two_provider_chain):
    """Once a provider is blocked, the cascade should skip it without trying."""
    _mark_provider_429("gemini")  # pre-block

    calls = []

    async def stub(model_cfg, messages, temperature, max_tokens, json_mode=False):
        calls.append(model_cfg["name"])
        return ("ok", 1, 1)

    monkeypatch.setattr(models, "_call_model", stub)

    tracker = CostTracker()
    result = await llm_call([{"role": "user", "content": "hi"}], tracker)
    assert result == "ok"
    # gemini was skipped; only groq was attempted
    assert calls == ["groq"]


@pytest.mark.asyncio
async def test_all_blocked_sleeps_until_earliest_unblock(monkeypatch, two_provider_chain):
    """When every provider is blocked, the cascade sleeps until the first
    one unblocks, then retries."""
    # Block both providers, but gemini's cooldown is short
    _provider_quota_until["gemini"] = time.monotonic() + 0.15
    _provider_quota_until["groq"] = time.monotonic() + 5.0

    call_log: list[tuple[str, float]] = []

    async def stub(model_cfg, messages, temperature, max_tokens, json_mode=False):
        call_log.append((model_cfg["name"], time.monotonic()))
        return ("late ok", 1, 1)

    monkeypatch.setattr(models, "_call_model", stub)

    tracker = CostTracker()
    t0 = time.monotonic()
    result = await llm_call([{"role": "user", "content": "hi"}], tracker)
    elapsed = time.monotonic() - t0

    assert result == "late ok"
    # Slept ~0.15s for gemini, then called gemini
    assert call_log[0][0] == "gemini"
    assert elapsed >= 0.10
    assert elapsed < 1.0  # we did NOT wait for groq's 5s cooldown


@pytest.mark.asyncio
async def test_402_blocks_long(monkeypatch, two_provider_chain):
    """402 Payment Required → block for max cooldown."""
    async def stub(model_cfg, messages, temperature, max_tokens, json_mode=False):
        if model_cfg["name"] == "gemini":
            raise _make_402_response()
        return ("groq saved us", 1, 1)

    monkeypatch.setattr(models, "_call_model", stub)
    tracker = CostTracker()
    result = await llm_call([{"role": "user", "content": "hi"}], tracker)
    assert result == "groq saved us"
    blocked, until = _is_provider_quota_blocked("gemini")
    assert blocked
    delta = until - time.monotonic()
    assert delta >= 55.0  # close to MAX 60s


@pytest.mark.asyncio
async def test_success_clears_prior_failure(monkeypatch, two_provider_chain):
    # Pre-mark gemini with 2 failures
    _mark_provider_429("gemini")
    _mark_provider_429("gemini")
    # Manually unblock so the test can call gemini
    _provider_quota_until["gemini"] = 0.0

    async def stub(model_cfg, messages, temperature, max_tokens, json_mode=False):
        return ("ok", 1, 1)

    monkeypatch.setattr(models, "_call_model", stub)
    tracker = CostTracker()
    await llm_call([{"role": "user", "content": "hi"}], tracker)
    # Failure count should reset; next 429 should be 5s, not 20s
    assert _provider_failure_count.get("gemini", 0) == 0


@pytest.mark.asyncio
async def test_all_providers_429_returns_degraded_after_one_retry(
    monkeypatch, two_provider_chain
):
    """If both providers 429, the cascade marks both, sleeps for the earliest
    cooldown to expire, then both are still 429 → returns DegradedResponse
    without infinite loop."""
    async def always_429(model_cfg, messages, temperature, max_tokens, json_mode=False):
        raise _make_429_response()

    monkeypatch.setattr(models, "_call_model", always_429)

    # Patch sleep to be fast so the test doesn't actually wait 5+ seconds
    real_sleep = asyncio.sleep
    async def fast_sleep(t):
        await real_sleep(min(t, 0.05))

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)

    tracker = CostTracker()
    result = await llm_call([{"role": "user", "content": "hi"}], tracker)
    assert isinstance(result, DegradedResponse)
    # Both providers should be marked blocked
    assert _is_provider_quota_blocked("gemini")[0]
    assert _is_provider_quota_blocked("groq")[0]


@pytest.mark.asyncio
async def test_blocked_provider_unblocks_after_cooldown(monkeypatch, two_provider_chain):
    """After cooldown elapses, the provider is callable again."""
    _provider_quota_until["gemini"] = time.monotonic() - 1.0  # already expired
    _provider_quota_until["groq"] = time.monotonic() - 1.0

    async def stub(model_cfg, messages, temperature, max_tokens, json_mode=False):
        return ("back online", 1, 1)

    monkeypatch.setattr(models, "_call_model", stub)
    tracker = CostTracker()
    result = await llm_call([{"role": "user", "content": "hi"}], tracker)
    assert result == "back online"


@pytest.mark.asyncio
async def test_quota_state_isolated_between_providers(monkeypatch, two_provider_chain):
    """Blocking gemini should NOT affect groq."""
    _mark_provider_429("gemini")
    assert _is_provider_quota_blocked("gemini")[0]
    assert not _is_provider_quota_blocked("groq")[0]
    assert _provider_failure_count.get("groq", 0) == 0
