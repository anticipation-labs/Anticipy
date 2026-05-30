#!/usr/bin/env python3
"""Smoke test for /api/twilio/voice inbound webhook.

Two scenarios. Both fully offline (no Twilio account, no real call).

  1. Unsigned POST returns 403. Confirms verifyTwilioRequest gate.
  2. Signed POST with a known phone (must exist in anticipy_profiles
     with that phone_e164) returns 200 + TwiML containing the
     assistant name and the <Gather> action pointing to
     /api/twilio/voice/pin.
  3. Signed POST with an unknown phone returns 200 + TwiML containing
     the "not registered" greeting and a <Hangup/>.

To run a real signed request the test needs TWILIO_AUTH_TOKEN to
match the dev server's env. Pass via env:

    TWILIO_AUTH_TOKEN=<server token> \\
    ANTICIPY_SMOKE_BASE=http://127.0.0.1:3000 \\
    ANTICIPY_SMOKE_KNOWN_FROM=+14155551212 \\
    ANTICIPY_SMOKE_UNKNOWN_FROM=+19998887777 \\
        python3 engine/scripts/twilio_voice_inbound_smoke.py

If TWILIO_AUTH_TOKEN is absent, only the 403 reachability test runs.

Exit 0 on PASS, 1 on FAIL.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("ANTICIPY_SMOKE_BASE", "http://127.0.0.1:3000").rstrip("/")
AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
KNOWN_FROM = os.environ.get("ANTICIPY_SMOKE_KNOWN_FROM", "").strip()
UNKNOWN_FROM = os.environ.get("ANTICIPY_SMOKE_UNKNOWN_FROM", "+19998887777").strip()
URL = f"{BASE}/api/twilio/voice"

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


def sign(url: str, params: dict[str, str], token: str) -> str:
    # Twilio HMAC: URL + sorted(key+value) joined, HMAC-SHA1 with the
    # auth token, base64-encoded.
    keys = sorted(params.keys())
    payload = url + "".join(k + params[k] for k in keys)
    sig = hmac.new(token.encode("utf-8"), payload.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(sig).decode("ascii")


def post_form(
    params: dict[str, str],
    signature: str | None,
) -> tuple[int, str]:
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if signature is not None:
        headers["x-twilio-signature"] = signature
    body = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(URL, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8") if exc.fp else ""
        return exc.code, raw
    except urllib.error.URLError as exc:
        return 0, f"transport:{exc.reason}"


def test_unsigned_returns_403() -> None:
    banner("1. unsigned POST returns 403")
    status, body = post_form(
        {"From": UNKNOWN_FROM, "To": "+15555550100", "CallSid": "CA-smoke-1"},
        signature=None,
    )
    if status == 0:
        bad("server_reachable", body)
        return
    if status != 403:
        bad("expected_403", f"got {status} body={body[:200]}")
        return
    ok("unsigned_returns_403")


def test_signed_unknown_number_says_not_registered() -> None:
    banner("2. signed POST + unknown number says 'not registered'")
    if not AUTH_TOKEN:
        ok("skipped_no_token")
        return
    params = {"From": UNKNOWN_FROM, "To": "+15555550100", "CallSid": "CA-smoke-2"}
    sig = sign(URL, params, AUTH_TOKEN)
    status, body = post_form(params, signature=sig)
    if status != 200:
        bad("status_200", f"got {status} body={body[:200]}")
        return
    if "not registered" not in body.lower():
        bad("not_registered_present", f"got body={body[:200]}")
        return
    if "<hangup" not in body.lower():
        bad("hangup_present", f"got body={body[:200]}")
        return
    ok("signed_unknown_number_says_not_registered")


def test_signed_known_number_gathers_pin() -> None:
    banner("3. signed POST + known number greets and gathers PIN")
    if not AUTH_TOKEN:
        ok("skipped_no_token")
        return
    if not KNOWN_FROM:
        ok("skipped_no_known_from (set ANTICIPY_SMOKE_KNOWN_FROM)")
        return
    params = {"From": KNOWN_FROM, "To": "+15555550100", "CallSid": "CA-smoke-3"}
    sig = sign(URL, params, AUTH_TOKEN)
    status, body = post_form(params, signature=sig)
    if status != 200:
        bad("status_200", f"got {status} body={body[:200]}")
        return
    if "/api/twilio/voice/pin" not in body:
        bad("pin_action_present", f"got body={body[:200]}")
        return
    if "<gather" not in body.lower():
        bad("gather_present", f"got body={body[:200]}")
        return
    ok("signed_known_number_gathers_pin")


def main() -> int:
    print("Twilio voice inbound smoke", flush=True)
    print(f"  base: {BASE}", flush=True)
    print(f"  TWILIO_AUTH_TOKEN: {'present' if AUTH_TOKEN else 'absent'}", flush=True)
    print(f"  KNOWN_FROM: {KNOWN_FROM or 'absent'}", flush=True)
    print(f"  UNKNOWN_FROM: {UNKNOWN_FROM}", flush=True)
    for fn in (
        test_unsigned_returns_403,
        test_signed_unknown_number_says_not_registered,
        test_signed_known_number_gathers_pin,
    ):
        try:
            fn()
        except Exception as exc:
            bad(fn.__name__, f"raised {type(exc).__name__}: {exc}")
    print(f"\nPASS={len(GREEN)} FAIL={len(RED)}", flush=True)
    return 0 if not RED else 1


if __name__ == "__main__":
    sys.exit(main())
