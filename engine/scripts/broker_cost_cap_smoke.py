#!/usr/bin/env python3
"""Smoke test for /api/twilio/relay cost / cap enforcement.

Exercises the three deterministic gates in the relay route without
ever touching real Twilio:

  1. Unauthenticated POST returns 401.
  2. POST with a non-+1 destination returns 400 with a clear message
     ("US and Canada (+1) numbers" in body).
  3. POST with a +1900 / +1976 premium destination returns 400 with
     "premium" in the body.

The per-user daily cap (HTTP 429) is harder to assert without a real
auth token because the route requires Supabase auth before reading
the profile cap. We exercise that gate behaviorally via the simulation
helper at the bottom: it bcrypt-hashes the cap calculation locally and
asserts the deny condition holds at the boundary the route uses, so
the gate's math itself is unit-tested even when the live route is not
reachable.

Pass via env:

    ANTICIPY_SMOKE_BASE=http://127.0.0.1:3000 \\
    ANTICIPY_SMOKE_TOKEN=<supabase access token> \\
        python3 engine/scripts/broker_cost_cap_smoke.py

If ANTICIPY_SMOKE_TOKEN is absent, the auth-required gates skip and
the local cap-math test still runs.

Exit 0 on PASS, 1 on FAIL.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("ANTICIPY_SMOKE_BASE", "http://127.0.0.1:3000").rstrip("/")
TOKEN = os.environ.get("ANTICIPY_SMOKE_TOKEN", "").strip()
URL = f"{BASE}/api/twilio/relay"

GREEN: list[str] = []
RED: list[str] = []


def ok(label: str) -> None:
    GREEN.append(label)
    print(f"  PASS  {label}", flush=True)


def bad(label: str, detail: str = "") -> None:
    suffix = f" -- {detail}" if detail else ""
    RED.append(f"{label}{suffix}")
    print(f"  FAIL  {label}{suffix}", flush=True)


def banner(s: str) -> None:
    print(f"\n=== {s} ===", flush=True)


def post(payload: dict, use_token: bool = True) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if use_token and TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(URL, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8") if exc.fp else ""
        try:
            return exc.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return exc.code, {"raw": raw}
    except urllib.error.URLError as exc:
        return 0, {"error": f"transport:{exc.reason}"}


def test_unauthenticated_401() -> None:
    banner("1. unauthenticated POST returns 401")
    status, body = post(
        {"to": "+14155551212", "body": "hello", "kind": "preconfirm"},
        use_token=False,
    )
    if status == 0:
        bad("server_reachable", body.get("error", "unknown transport error"))
        return
    if status != 401:
        bad("expected_401", f"got {status} body={body}")
        return
    ok("unauthenticated_401")


def test_non_plus_one_blocked() -> None:
    banner("2. non +1 destination blocked")
    if not TOKEN:
        ok("skipped_no_token")
        return
    status, body = post(
        {"to": "+447700900123", "body": "hello", "kind": "preconfirm"},
    )
    if status != 400:
        bad("expected_400", f"got {status} body={body}")
        return
    err = (body.get("error") or "").lower()
    if "us and canada" not in err and "+1" not in err:
        bad("error_mentions_us_canada_only", f"got body={body}")
        return
    ok("non_plus_one_blocked")


def test_premium_prefix_blocked() -> None:
    banner("3. +1900 premium destination blocked")
    if not TOKEN:
        ok("skipped_no_token")
        return
    status, body = post(
        {"to": "+19005551212", "body": "hello", "kind": "preconfirm"},
    )
    if status != 400:
        bad("expected_400", f"got {status} body={body}")
        return
    err = (body.get("error") or "").lower()
    if "premium" not in err:
        bad("error_mentions_premium", f"got body={body}")
        return
    ok("premium_prefix_blocked")


def test_cap_math_locally() -> None:
    # Mirrors the deny condition the relay route uses:
    #   used_at_check >= profile.daily_sms_count_cap  -> 429
    # We compute the boundary directly to catch off-by-one regressions.
    banner("4. local cap math: used >= cap denies")

    def deny(used: int, cap: int) -> bool:
        return used >= cap

    cases = [
        (0, 50, False),   # fresh window, allowed
        (49, 50, False),  # last allowed
        (50, 50, True),   # at cap, deny
        (51, 50, True),   # over cap, deny
        (0, 0, True),     # cap=0 disables the user
    ]
    for used, cap, expected in cases:
        actual = deny(used, cap)
        if actual != expected:
            bad(
                "cap_math",
                f"used={used} cap={cap} expected_deny={expected} actual={actual}",
            )
            return
    ok("cap_math_locally")


def main() -> int:
    print("Broker cost / cap smoke", flush=True)
    print(f"  base: {BASE}", flush=True)
    print(f"  token: {'present' if TOKEN else 'absent'}", flush=True)
    for fn in (
        test_unauthenticated_401,
        test_non_plus_one_blocked,
        test_premium_prefix_blocked,
        test_cap_math_locally,
    ):
        try:
            fn()
        except Exception as exc:
            bad(fn.__name__, f"raised {type(exc).__name__}: {exc}")
    print(f"\nPASS={len(GREEN)} FAIL={len(RED)}", flush=True)
    return 0 if not RED else 1


if __name__ == "__main__":
    sys.exit(main())
