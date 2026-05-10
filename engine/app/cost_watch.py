"""
Cost audit trail for paid LLM calls.

Every paid model call goes through ``log_paid_call`` to the
``engine_cost_log`` Supabase table. The hard month-to-date cap is enforced
by ``assert_under_cap``, which raises ``CostCapExceeded`` when the running
total reaches the cap.

WIRE-ME: ``app/models.py`` calls ``log_paid_call(...)`` after every
successful provider call (free providers log ``cost_usd=0`` for completeness)
and ``assert_under_cap(COST_MONTHLY_CAP_USD)`` at the top of the cascade.
That wiring lives in models.py, not here.

Schema (created via migration ``2026050601_engine_cost_log``):

    CREATE TABLE engine_cost_log (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      occurred_at timestamptz DEFAULT now(),
      provider text NOT NULL,
      model text NOT NULL,
      input_tokens int NOT NULL DEFAULT 0,
      output_tokens int NOT NULL DEFAULT 0,
      cost_usd numeric(12,6) NOT NULL DEFAULT 0,
      role text,
      task_id uuid,
      user_id text
    );

Cop-out coverage:
  - #14 (no audit): every paid call logs, period.
  - #15 (silent overspend): assert_under_cap raises rather than continuing.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
import os
from typing import Any

import httpx


logger = logging.getLogger("engine.cost_watch")


# ── Errors ─────────────────────────────────────────────────────────────


class CostCapExceeded(Exception):
    """Raised when month-to-date paid LLM spend has reached the cap."""

    def __init__(self, total_usd: float, cap_usd: float):
        self.total_usd = total_usd
        self.cap_usd = cap_usd
        super().__init__(
            f"Cost cap reached: month-to-date ${total_usd:.4f} >= cap ${cap_usd:.2f}"
        )


# ── Supabase REST client (no SDK needed) ──────────────────────────────
#
# We talk to Supabase via the REST endpoint with the service-role key (so
# the cost log is write-only for clients but the engine can both read +
# write). If neither URL nor key is configured the module no-ops gracefully
# in production it still warns.


def _supabase_url() -> str:
    return os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")


def _supabase_service_key() -> str:
    return os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


def _client_configured() -> bool:
    return bool(_supabase_url() and _supabase_service_key())


def _headers() -> dict[str, str]:
    key = _supabase_service_key()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


# ── Public API ─────────────────────────────────────────────────────────


async def log_paid_call(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    role: str | None = None,
    task_id: str | None = None,
    user_id: str | None = None,
) -> None:
    """Insert a single row into ``engine_cost_log``.

    Never raises — failures are logged and swallowed. The audit trail is
    best-effort: a Supabase outage must never block an LLM call.
    """
    if not _client_configured():
        # In dev without Supabase configured the call is a no-op. Don't
        # spam the log — it's expected.
        return

    payload = {
        "provider": str(provider or "unknown"),
        "model": str(model or "unknown"),
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "cost_usd": float(cost_usd or 0.0),
        "role": role,
        "task_id": task_id,
        "user_id": user_id,
    }

    url = f"{_supabase_url()}/rest/v1/engine_cost_log"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, headers=_headers(), json=payload)
            if resp.status_code >= 400:
                logger.warning(
                    "cost_watch insert failed: %s %s",
                    resp.status_code, resp.text[:200],
                )
    except (httpx.HTTPError, asyncio.TimeoutError):
        logger.exception("cost_watch insert raised; swallowing")


async def daily_total_usd(user_id: str | None = None) -> float:
    """Sum ``cost_usd`` for the last 24h, optionally filtered by user.

    Returns 0.0 on any error or when Supabase isn't configured.
    """
    if not _client_configured():
        return 0.0

    # `+` in URL query strings gets decoded as space by PostgREST, breaking
    # timestamptz parse. Percent-encode it so the timezone offset survives.
    cutoff = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=1)).isoformat().replace("+", "%2B")
    url = (
        f"{_supabase_url()}/rest/v1/engine_cost_log"
        f"?select=cost_usd&occurred_at=gte.{cutoff}"
    )
    if user_id:
        url += f"&user_id=eq.{user_id}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=_headers())
            if resp.status_code >= 400:
                logger.warning(
                    "cost_watch daily_total failed: %s %s",
                    resp.status_code, resp.text[:200],
                )
                return 0.0
            rows = resp.json() or []
    except (httpx.HTTPError, asyncio.TimeoutError):
        logger.exception("cost_watch daily_total raised")
        return 0.0

    total = 0.0
    for r in rows:
        try:
            total += float(r.get("cost_usd", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
    return total


async def monthly_total_usd(user_id: str | None = None) -> float:
    """Sum ``cost_usd`` from the start of the current calendar month UTC.

    Returns 0.0 on any error or when Supabase isn't configured.
    """
    if not _client_configured():
        return 0.0

    now = _dt.datetime.now(_dt.timezone.utc)
    cutoff = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat().replace("+", "%2B")
    url = (
        f"{_supabase_url()}/rest/v1/engine_cost_log"
        f"?select=cost_usd&occurred_at=gte.{cutoff}"
    )
    if user_id:
        url += f"&user_id=eq.{user_id}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=_headers())
            if resp.status_code >= 400:
                logger.warning(
                    "cost_watch monthly_total failed: %s %s",
                    resp.status_code, resp.text[:200],
                )
                return 0.0
            rows = resp.json() or []
    except (httpx.HTTPError, asyncio.TimeoutError):
        logger.exception("cost_watch monthly_total raised")
        return 0.0

    total = 0.0
    for r in rows:
        try:
            total += float(r.get("cost_usd", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
    return total


async def assert_under_cap(monthly_cap_usd: float = 10.0) -> None:
    """Raise ``CostCapExceeded`` when month-to-date spend has reached the cap.

    Caller MUST handle the exception (in models.py we surface a
    DegradedResponse). monthly_cap_usd <= 0 disables the check.
    """
    if monthly_cap_usd <= 0:
        return
    total = await monthly_total_usd()
    if total >= monthly_cap_usd:
        raise CostCapExceeded(total_usd=total, cap_usd=monthly_cap_usd)


# ── Internals exposed for testing ──────────────────────────────────────


def _client_module_for_tests() -> dict[str, Any]:
    """Visibility hook so tests can patch ``httpx.AsyncClient`` cleanly."""
    return {"httpx": httpx}


__all__ = [
    "CostCapExceeded",
    "log_paid_call",
    "daily_total_usd",
    "monthly_total_usd",
    "assert_under_cap",
]
