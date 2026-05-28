"""Tests for app.cost_watch — paid LLM call audit trail and cap check."""

from __future__ import annotations

import datetime as _dt
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app import cost_watch
from app.cost_watch import (
    CostCapExceeded,
    assert_under_cap,
    daily_total_usd,
    log_paid_call,
    monthly_total_usd,
)


# ─────────────────────────────────────────────────────────────────────────
# Helper: stub Supabase config + AsyncClient for the duration of a test
# ─────────────────────────────────────────────────────────────────────────


class _MockResponse:
    def __init__(self, status_code: int = 201, json_data=None, text: str = ""):
        self.status_code = status_code
        self._json = json_data if json_data is not None else []
        self.text = text

    def json(self):
        return self._json


class _RecordingClient:
    """AsyncClient stand-in that records every call and returns scripted
    responses keyed by URL substring.

    Use as: ``_RecordingClient(post_response=..., get_response=...)``.
    """

    def __init__(
        self,
        post_response: _MockResponse | None = None,
        get_response: _MockResponse | None = None,
        raise_on: str | None = None,
    ):
        self.post_response = post_response or _MockResponse(201)
        self.get_response = get_response or _MockResponse(200, [])
        self.raise_on = raise_on  # "post" | "get" | None
        self.posts: list[dict] = []
        self.gets: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        if self.raise_on == "post":
            raise httpx.HTTPError("simulated post failure")
        self.posts.append({"url": url, "headers": headers, "json": json})
        return self.post_response

    async def get(self, url, headers=None):
        if self.raise_on == "get":
            raise httpx.HTTPError("simulated get failure")
        self.gets.append(url)
        return self.get_response


@pytest.fixture
def supabase_env(monkeypatch):
    """Configure NEXT_PUBLIC_SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY for the
    duration of the test so cost_watch's _client_configured() is True."""
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-svc-key")
    yield


@pytest.fixture
def no_supabase_env(monkeypatch):
    """Clear Supabase env so _client_configured() is False."""
    monkeypatch.delenv("NEXT_PUBLIC_SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    yield


# ─────────────────────────────────────────────────────────────────────────
# log_paid_call
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_paid_call_inserts_row(supabase_env):
    client = _RecordingClient(post_response=_MockResponse(201))
    with patch.object(httpx, "AsyncClient", return_value=client):
        await log_paid_call(
            provider="gemini",
            model="gemini-2.5-flash",
            input_tokens=120,
            output_tokens=40,
            cost_usd=0.000528,
            role="planner",
            task_id="task-uuid-1",
            user_id="user-1",
        )

    assert len(client.posts) == 1
    body = client.posts[0]["json"]
    assert body["provider"] == "gemini"
    assert body["model"] == "gemini-2.5-flash"
    assert body["input_tokens"] == 120
    assert body["output_tokens"] == 40
    assert body["cost_usd"] == pytest.approx(0.000528)
    assert body["role"] == "planner"
    assert body["task_id"] == "task-uuid-1"
    assert body["user_id"] == "user-1"
    # URL points at the cost log table
    assert "/rest/v1/engine_cost_log" in client.posts[0]["url"]


@pytest.mark.asyncio
async def test_log_paid_call_noop_without_config(no_supabase_env):
    """When Supabase isn't configured, log_paid_call quietly no-ops."""
    client = _RecordingClient()
    with patch.object(httpx, "AsyncClient", return_value=client):
        await log_paid_call(
            provider="gemini",
            model="x",
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.0001,
        )
    assert client.posts == []


@pytest.mark.asyncio
async def test_log_paid_call_swallows_http_errors(supabase_env):
    """An outage on Supabase MUST NOT abort an LLM call."""
    client = _RecordingClient(raise_on="post")
    with patch.object(httpx, "AsyncClient", return_value=client):
        # Should not raise.
        await log_paid_call(
            provider="x", model="x",
            input_tokens=1, output_tokens=1, cost_usd=0.0,
        )


@pytest.mark.asyncio
async def test_log_paid_call_swallows_4xx_response(supabase_env):
    """Non-2xx response is logged but doesn't propagate."""
    client = _RecordingClient(post_response=_MockResponse(400, text="bad request"))
    with patch.object(httpx, "AsyncClient", return_value=client):
        await log_paid_call(
            provider="x", model="x",
            input_tokens=1, output_tokens=1, cost_usd=0.0,
        )


@pytest.mark.asyncio
async def test_log_paid_call_normalises_negative_or_none(supabase_env):
    """Defensively normalise None / negative numerics so the DB doesn't
    reject a row over a defaulted field."""
    client = _RecordingClient(post_response=_MockResponse(201))
    with patch.object(httpx, "AsyncClient", return_value=client):
        await log_paid_call(
            provider=None,    # type: ignore[arg-type]
            model=None,       # type: ignore[arg-type]
            input_tokens=None,  # type: ignore[arg-type]
            output_tokens=None,  # type: ignore[arg-type]
            cost_usd=None,    # type: ignore[arg-type]
        )
    body = client.posts[0]["json"]
    assert body["provider"] == "unknown"
    assert body["model"] == "unknown"
    assert body["input_tokens"] == 0
    assert body["output_tokens"] == 0
    assert body["cost_usd"] == 0.0


# ─────────────────────────────────────────────────────────────────────────
# daily_total_usd / monthly_total_usd
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_daily_total_usd_sums_rows(supabase_env):
    rows = [
        {"cost_usd": 0.001},
        {"cost_usd": 0.002},
        {"cost_usd": 0.005},
    ]
    client = _RecordingClient(get_response=_MockResponse(200, rows))
    with patch.object(httpx, "AsyncClient", return_value=client):
        total = await daily_total_usd()
    assert total == pytest.approx(0.008)


@pytest.mark.asyncio
async def test_daily_total_usd_filters_by_user(supabase_env):
    rows = [{"cost_usd": 0.5}]
    client = _RecordingClient(get_response=_MockResponse(200, rows))
    with patch.object(httpx, "AsyncClient", return_value=client):
        total = await daily_total_usd(user_id="alice")
    assert total == pytest.approx(0.5)
    assert any("user_id=eq.alice" in u for u in client.gets)


@pytest.mark.asyncio
async def test_daily_total_zero_when_unconfigured(no_supabase_env):
    total = await daily_total_usd()
    assert total == 0.0


@pytest.mark.asyncio
async def test_daily_total_zero_on_http_error(supabase_env):
    client = _RecordingClient(raise_on="get")
    with patch.object(httpx, "AsyncClient", return_value=client):
        total = await daily_total_usd()
    assert total == 0.0


@pytest.mark.asyncio
async def test_daily_total_zero_on_4xx(supabase_env):
    client = _RecordingClient(get_response=_MockResponse(400, text="bad"))
    with patch.object(httpx, "AsyncClient", return_value=client):
        total = await daily_total_usd()
    assert total == 0.0


@pytest.mark.asyncio
async def test_daily_total_skips_nonnumeric_rows(supabase_env):
    rows = [
        {"cost_usd": 0.5},
        {"cost_usd": "junk"},
        {"cost_usd": None},
        {"cost_usd": 1.5},
    ]
    client = _RecordingClient(get_response=_MockResponse(200, rows))
    with patch.object(httpx, "AsyncClient", return_value=client):
        total = await daily_total_usd()
    assert total == pytest.approx(2.0)


@pytest.mark.asyncio
async def test_monthly_total_uses_first_of_month_cutoff(supabase_env):
    rows = [{"cost_usd": 7.5}]
    client = _RecordingClient(get_response=_MockResponse(200, rows))
    with patch.object(httpx, "AsyncClient", return_value=client):
        total = await monthly_total_usd()
    assert total == pytest.approx(7.5)
    # The cutoff is the 1st-of-month at 00:00 UTC for the current month.
    now = _dt.datetime.now(_dt.timezone.utc)
    cutoff_iso = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    assert any(cutoff_iso in u for u in client.gets)


# ─────────────────────────────────────────────────────────────────────────
# assert_under_cap
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_assert_under_cap_under_threshold(supabase_env):
    rows = [{"cost_usd": 1.0}, {"cost_usd": 2.0}]  # total $3
    client = _RecordingClient(get_response=_MockResponse(200, rows))
    with patch.object(httpx, "AsyncClient", return_value=client):
        await assert_under_cap(monthly_cap_usd=10.0)  # no raise


@pytest.mark.asyncio
async def test_assert_under_cap_at_cap_raises(supabase_env):
    rows = [{"cost_usd": 5.0}, {"cost_usd": 5.0}]
    client = _RecordingClient(get_response=_MockResponse(200, rows))
    with patch.object(httpx, "AsyncClient", return_value=client):
        with pytest.raises(CostCapExceeded) as exc:
            await assert_under_cap(monthly_cap_usd=10.0)
    assert exc.value.cap_usd == 10.0
    assert exc.value.total_usd == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_assert_under_cap_over_cap_raises(supabase_env):
    rows = [{"cost_usd": 12.5}]
    client = _RecordingClient(get_response=_MockResponse(200, rows))
    with patch.object(httpx, "AsyncClient", return_value=client):
        with pytest.raises(CostCapExceeded):
            await assert_under_cap(monthly_cap_usd=10.0)


@pytest.mark.asyncio
async def test_assert_under_cap_zero_disables_check(supabase_env):
    """Cap of 0 short-circuits → no Supabase round-trip, never raises."""
    client = _RecordingClient(raise_on="get")  # would explode if called
    with patch.object(httpx, "AsyncClient", return_value=client):
        await assert_under_cap(monthly_cap_usd=0.0)
    assert client.gets == []


@pytest.mark.asyncio
async def test_assert_under_cap_negative_disables_check(supabase_env):
    client = _RecordingClient(raise_on="get")
    with patch.object(httpx, "AsyncClient", return_value=client):
        await assert_under_cap(monthly_cap_usd=-1.0)
    assert client.gets == []


@pytest.mark.asyncio
async def test_cost_cap_exception_carries_context():
    e = CostCapExceeded(total_usd=15.5, cap_usd=10.0)
    assert e.total_usd == 15.5
    assert e.cap_usd == 10.0
    s = str(e)
    assert "$15.5" in s or "15.5000" in s
    assert "$10" in s


# ─────────────────────────────────────────────────────────────────────────
# Headers carry the service-role key
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_uses_service_role_key_in_headers(supabase_env):
    client = _RecordingClient()
    with patch.object(httpx, "AsyncClient", return_value=client):
        await log_paid_call(
            provider="gemini", model="x",
            input_tokens=1, output_tokens=1, cost_usd=0.0,
        )
    headers = client.posts[0]["headers"]
    assert headers["apikey"] == "test-svc-key"
    assert headers["Authorization"] == "Bearer test-svc-key"
    assert headers["Content-Type"] == "application/json"
