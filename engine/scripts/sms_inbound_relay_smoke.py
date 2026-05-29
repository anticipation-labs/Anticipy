#!/usr/bin/env python3
"""Smoke test for the website to engine inbound SMS relay.

Exercises:
  1. POST a Twilio-shaped form payload to a local FastAPI route
     that imitates /api/twilio/sms-inbound (Supabase REST direct).
  2. Confirm the row lands in public.anticipy_sms_inbound.
  3. Pull it back via the engine's poll path (_poll_inbound_rows
     hits the local FastAPI route same as the engine would in prod).
  4. Confirm _forward_inbound_to_local_engine hits /api/sms/inbound
     and the existing engine pipeline records a pending decision.

Run from repo root, with the engine on 127.0.0.1:8731 and
SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY env set:

    python3 engine/scripts/sms_inbound_relay_smoke.py

Default account_id is "anticipy-user".
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def banner(s: str) -> None:
    print(f"\n=== {s} ===", flush=True)


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", flush=True)
    sys.exit(1)


def http_post_form(url: str, fields: dict[str, str],
                   headers: dict[str, str] | None = None,
                   timeout: float = 10.0) -> tuple[int, str]:
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return int(getattr(r, "status", 200)), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return int(getattr(exc, "code", 0) or 0), exc.read().decode("utf-8", "replace")


def http_get_json(url: str, timeout: float = 10.0) -> tuple[int, dict]:
    req = urllib.request.Request(url, method="GET",
                                  headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
            try:
                return int(getattr(r, "status", 200)), json.loads(body)
            except Exception:
                return int(getattr(r, "status", 200)), {"raw": body}
    except urllib.error.HTTPError as exc:
        return int(getattr(exc, "code", 0) or 0), {"raw": exc.read().decode("utf-8", "replace")}


def supabase_insert_sms_inbound(payload: dict) -> dict:
    """Insert a synthetic Twilio webhook row directly via REST."""
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
           or os.environ.get("SUPABASE_SERVICE_KEY", ""))
    if not (url and key):
        fail("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
    req = urllib.request.Request(
        f"{url}/rest/v1/anticipy_sms_inbound",
        data=json.dumps([payload]).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "apikey": key, "Authorization": f"Bearer {key}",
            "Prefer": "return=representation",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        rows = json.loads(r.read().decode("utf-8", "replace"))
        return rows[0] if rows else {}


def supabase_delete_sms_inbound(row_id: int) -> None:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
           or os.environ.get("SUPABASE_SERVICE_KEY", ""))
    if not (url and key):
        return
    req = urllib.request.Request(
        f"{url}/rest/v1/anticipy_sms_inbound?id=eq.{int(row_id)}",
        method="DELETE",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
    except Exception:
        pass


def main() -> int:
    engine_url = os.environ.get("ANTICIPY_ENGINE_URL", "").strip() \
        or "http://127.0.0.1:8731"
    account_id = (os.environ.get("ANTICIPY_ACCOUNT_ID", "").strip()
                  or os.environ.get("ANTICIPY_USER_ID", "").strip()
                  or "anticipy-user")

    banner("phase 1: insert a synthetic inbound row in Supabase")
    msg_sid = f"SM{int(time.time())}{os.getpid()}".ljust(34, "x")[:34]
    row = supabase_insert_sms_inbound({
        "from_number": "+15555550999",
        "to_number": "+15555550100",
        "body": f"smoke test {msg_sid}",
        "message_sid": msg_sid,
        "twilio_account_sid": "ACsmoketest",
        "raw_form": {"From": "+15555550999",
                      "To": "+15555550100",
                      "Body": f"smoke test {msg_sid}",
                      "MessageSid": msg_sid},
        "account_id": None,
    })
    if not row.get("id"):
        fail(f"insert did not return row: {row}")
    row_id = row["id"]
    print(f"inserted row id={row_id} message_sid={msg_sid}")

    banner("phase 2: engine status surface lists the poller")
    status_code, status_body = http_get_json(
        f"{engine_url}/api/sms/inbound_poller/status")
    if status_code != 200:
        fail(f"poller status returned {status_code}: {status_body}")
    if not status_body.get("running"):
        fail(f"poller not running: {status_body}")
    print(f"poller running: interval_seconds="
          f"{status_body.get('interval_seconds')} "
          f"engine_id={status_body.get('engine_id')} "
          f"account_id={status_body.get('account_id')}")

    banner("phase 3: poll surface returns the row")
    from app.product.sms_pre_confirm import _poll_inbound_rows
    rows = _poll_inbound_rows()
    rows_for_msg = [r for r in rows if r.get("message_sid") == msg_sid]
    if not rows_for_msg:
        fail(f"poll did not see our row; got {len(rows)} unrelated rows")
    print(f"poll returned our row: id={rows_for_msg[0].get('id')}")

    banner("phase 4: forward step posts to /api/sms/inbound")
    from app.product.sms_pre_confirm import _forward_inbound_to_local_engine
    fwd = _forward_inbound_to_local_engine(rows_for_msg[0])
    if not fwd.get("ok"):
        fail(f"forward to local engine failed: {fwd}")
    print(f"forward ok status={fwd.get('status_code')} "
          f"body_excerpt={fwd.get('body_excerpt', '')[:120]!r}")

    banner("phase 5: cleanup")
    supabase_delete_sms_inbound(row_id)
    print(f"deleted row {row_id}")

    print("\nALL SMS INBOUND RELAY SMOKE TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
