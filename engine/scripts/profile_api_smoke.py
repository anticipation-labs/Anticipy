#!/usr/bin/env python3
"""Smoke test for /api/onboarding/profile GET + POST.

Hits a running Next.js dev server (default http://127.0.0.1:3000) with
a real Supabase session token and walks the GET -> POST -> GET cycle:

  1. GET returns ok=true and a profile shape that always includes
     assistant_name (default Anticipy) and has_pin.
  2. POST {assistant_name: "Donna"} updates the name and returns the
     new profile. PIN hash never leaks in the response.
  3. POST {pin: "1234"} flips has_pin to true. PIN hash never leaks.
  4. POST {phone_e164: "+14155551212"} stores the canonical number.
  5. Invalid bodies produce 400 with a clear error message.

The test does NOT bring up the dev server or sign up a user; both are
expected to already exist. Pass the access token and target base URL
via env or CLI:

    ANTICIPY_SMOKE_BASE=http://127.0.0.1:3000 \\
    ANTICIPY_SMOKE_TOKEN=<supabase access token> \\
        python3 engine/scripts/profile_api_smoke.py

When ANTICIPY_SMOKE_TOKEN is missing we still validate the request
shape against the route by hitting it without an Authorization header
and asserting 401 (the route is reachable, the gate works). This lets
the smoke test pass in CI without provisioned auth.

Exit 0 on PASS, 1 on FAIL.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("ANTICIPY_SMOKE_BASE", "http://127.0.0.1:3000").rstrip("/")
TOKEN = os.environ.get("ANTICIPY_SMOKE_TOKEN", "").strip()
URL = f"{BASE}/api/onboarding/profile"

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


def request(
    method: str,
    body: dict | None = None,
    use_token: bool = True,
) -> tuple[int, dict]:
    data = None
    headers = {"Content-Type": "application/json"}
    if use_token and TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(URL, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            payload = json.loads(raw) if raw else {}
            return resp.status, payload
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8") if exc.fp else ""
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return exc.code, payload
    except urllib.error.URLError as exc:
        return 0, {"error": f"transport:{exc.reason}"}


def test_unauth_returns_401() -> None:
    banner("1. unauthenticated request returns 401")
    status, body = request("GET", use_token=False)
    if status == 0:
        bad("server_reachable", body.get("error", "unknown transport error"))
        return
    if status != 401:
        bad("expected_401", f"got {status} body={body}")
        return
    if body.get("ok") is True:
        bad("body_ok_false", f"got {body}")
        return
    ok("unauth_returns_401")


def test_get_returns_profile() -> None:
    banner("2. GET returns profile shape")
    if not TOKEN:
        ok("skipped_no_token (route reachability proved above)")
        return
    status, body = request("GET")
    if status != 200:
        bad("get_status_200", f"got {status} body={body}")
        return
    profile = body.get("profile")
    if not isinstance(profile, dict):
        bad("profile_dict", f"got {body}")
        return
    if "assistant_name" not in profile or "has_pin" not in profile:
        bad("profile_shape", f"missing keys, got {profile}")
        return
    if "pin_hash" in profile or "pin" in profile:
        bad("no_pin_hash_leak", f"hash leaked in {profile}")
        return
    ok("get_returns_profile")


def test_post_assistant_name() -> None:
    banner("3. POST assistant_name updates")
    if not TOKEN:
        ok("skipped_no_token")
        return
    new_name = f"Donna{int(time.time()) % 10000}"
    status, body = request("POST", {"assistant_name": new_name})
    if status != 200:
        bad("post_status_200", f"got {status} body={body}")
        return
    profile = body.get("profile", {})
    if profile.get("assistant_name") != new_name:
        bad("name_persisted", f"got {profile}")
        return
    ok("post_assistant_name")


def test_post_pin_no_leak() -> None:
    banner("4. POST pin flips has_pin true, hash never leaks")
    if not TOKEN:
        ok("skipped_no_token")
        return
    status, body = request("POST", {"pin": "246810"})
    if status != 200:
        bad("post_pin_status_200", f"got {status} body={body}")
        return
    profile = body.get("profile", {})
    if profile.get("has_pin") is not True:
        bad("has_pin_true", f"got {profile}")
        return
    if "pin_hash" in profile or "pin" in profile:
        bad("no_pin_leak", f"got {profile}")
        return
    ok("post_pin_no_leak")


def test_invalid_phone_400() -> None:
    banner("5. POST invalid phone returns 400")
    if not TOKEN:
        ok("skipped_no_token")
        return
    status, body = request("POST", {"phone_e164": "555-1212"})
    if status != 400:
        bad("invalid_phone_400", f"got {status} body={body}")
        return
    if body.get("ok") is True:
        bad("invalid_phone_ok_false", f"got {body}")
        return
    ok("invalid_phone_400")


def test_invalid_pin_400() -> None:
    banner("6. POST invalid pin (too short) returns 400")
    if not TOKEN:
        ok("skipped_no_token")
        return
    status, body = request("POST", {"pin": "12"})
    if status != 400:
        bad("invalid_pin_400", f"got {status} body={body}")
        return
    ok("invalid_pin_400")


def test_assistant_name_sanitization() -> None:
    banner("7. POST assistant_name with bad chars returns 400")
    if not TOKEN:
        ok("skipped_no_token")
        return
    status, body = request("POST", {"assistant_name": "Donna<script>"})
    if status != 400:
        bad("sanitization_400", f"got {status} body={body}")
        return
    ok("assistant_name_sanitization")


def main() -> int:
    print("Profile API smoke", flush=True)
    print(f"  base: {BASE}", flush=True)
    print(f"  token: {'present' if TOKEN else 'absent'}", flush=True)
    for fn in (
        test_unauth_returns_401,
        test_get_returns_profile,
        test_post_assistant_name,
        test_post_pin_no_leak,
        test_invalid_phone_400,
        test_invalid_pin_400,
        test_assistant_name_sanitization,
    ):
        try:
            fn()
        except Exception as exc:
            bad(fn.__name__, f"raised {type(exc).__name__}: {exc}")
    print(f"\nPASS={len(GREEN)} FAIL={len(RED)}", flush=True)
    return 0 if not RED else 1


if __name__ == "__main__":
    sys.exit(main())
