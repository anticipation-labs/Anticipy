"""
Lightweight Supabase REST client using httpx.
Handles engine_users, browser_profiles, and engine_tasks tables.

All public functions degrade gracefully on transient failures: select returns
[], inserts/upserts return None.  This keeps the engine responsive when the
database is briefly unavailable.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.config import SUPABASE_URL, SUPABASE_ANON_KEY


logger = logging.getLogger("engine")


def _headers(extra: dict | None = None) -> dict:
    h = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    if extra:
        h.update(extra)
    return h


def _rest_url(table: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"


# A status is "transient" if a quick retry could plausibly succeed.
_TRANSIENT_STATUSES = {408, 429, 500, 502, 503, 504}
_DEFAULT_RETRIES = 2


async def _request_with_retry(
    method: str,
    url: str,
    *,
    headers: dict,
    params: dict | None = None,
    json: dict | None = None,
    retries: int = _DEFAULT_RETRIES,
) -> httpx.Response | None:
    """Run an HTTP request with simple retry on transient failures."""
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.request(method, url, headers=headers, params=params, json=json)
                if resp.status_code in _TRANSIENT_STATUSES and attempt < retries:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                return resp
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            last_exc = e
            if attempt < retries:
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
        except Exception as e:
            last_exc = e
            break
    if last_exc is not None:
        logger.debug("supabase request failed: %s %s", method, url, exc_info=True)
    return None


async def insert_row(table: str, data: dict) -> dict | None:
    """Insert a single row and return the created record."""
    resp = await _request_with_retry(
        "POST", _rest_url(table), headers=_headers(), json=data
    )
    if resp is not None and resp.status_code in (200, 201):
        try:
            rows = resp.json()
            return rows[0] if rows else data
        except Exception:
            return data
    return None


async def select_rows(
    table: str,
    filters: dict | None = None,
    columns: str = "*",
    limit: int = 100,
) -> list[dict]:
    """Select rows with optional eq-filters."""
    params: dict = {"select": columns, "limit": str(int(limit))}
    if filters:
        for key, value in filters.items():
            params[key] = f"eq.{value}"
    resp = await _request_with_retry(
        "GET", _rest_url(table), headers=_headers(), params=params
    )
    if resp is not None and resp.status_code == 200:
        try:
            data = resp.json()
            return data if isinstance(data, list) else []
        except Exception:
            return []
    return []


async def update_rows(table: str, filters: dict, data: dict) -> list[dict]:
    """Update rows matching eq-filters."""
    params: dict = {}
    if filters:
        for key, value in filters.items():
            params[key] = f"eq.{value}"
    resp = await _request_with_retry(
        "PATCH", _rest_url(table), headers=_headers(), params=params, json=data
    )
    if resp is not None and resp.status_code == 200:
        try:
            out = resp.json()
            return out if isinstance(out, list) else []
        except Exception:
            return []
    return []


async def upsert_row(table: str, data: dict) -> dict | None:
    """Upsert a single row (insert or update on conflict)."""
    resp = await _request_with_retry(
        "POST",
        _rest_url(table),
        headers=_headers({"Prefer": "return=representation,resolution=merge-duplicates"}),
        json=data,
    )
    if resp is not None and resp.status_code in (200, 201):
        try:
            rows = resp.json()
            return rows[0] if rows else data
        except Exception:
            return data
    return None


async def call_rpc(name: str, args: dict) -> list[dict]:
    """Invoke a Postgres function exposed via PostgREST.

    Used for similarity search RPCs (anticipy_memory_topk,
    engine_trajectories_topk). Returns [] on any error so callers can
    degrade gracefully — same contract as select_rows.
    """
    url = f"{SUPABASE_URL}/rest/v1/rpc/{name}"
    resp = await _request_with_retry("POST", url, headers=_headers(), json=args)
    if resp is not None and resp.status_code in (200, 201):
        try:
            data = resp.json()
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return [data]
            return []
        except Exception:
            return []
    return []
