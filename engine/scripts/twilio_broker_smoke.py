#!/usr/bin/env python3
"""Smoke test for the website-side Twilio broker integration.

Verifies the engine half of the broker handoff without touching the
real Twilio API or the deployed website:

  1. With ANTICIPY_TWILIO_BROKER=0 and TWILIO_MOCK=1 (default), the
     existing send_sms_sync mock path returns ok=True with mock=True.
     Confirms we did not accidentally break the historical behaviour.

  2. With ANTICIPY_TWILIO_BROKER=1 and NO session.json / no
     ANTICIPY_CLOUD_AUTH_TOKEN, _send_via_broker returns
     {ok: False, error: "missing_session"}.

  3. With ANTICIPY_TWILIO_BROKER=1 and a junk session token, the
     stubbed broker endpoint returns 401 and send_sms_sync degrades to
     the existing direct-Twilio path (which lands in the
     TWILIO_MOCK=1 branch and returns ok=True with mock=True).

The broker HTTP call is stubbed via monkeypatch on httpx.Client so the
script can run in CI with zero network.

Run from repo root:

    python3 engine/scripts/twilio_broker_smoke.py

Exits 0 on PASS, 1 on FAIL.
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "engine"))


GREEN_CHECKS: list[str] = []
RED_CHECKS: list[str] = []


def ok(name: str) -> None:
    print(f"  PASS  {name}", flush=True)
    GREEN_CHECKS.append(name)


def bad(name: str, detail: str = "") -> None:
    suffix = f" -- {detail}" if detail else ""
    print(f"  FAIL  {name}{suffix}", flush=True)
    RED_CHECKS.append(f"{name}{suffix}")


def banner(s: str) -> None:
    print(f"\n=== {s} ===", flush=True)


def _clear_broker_env() -> None:
    for var in (
        "ANTICIPY_TWILIO_BROKER",
        "ANTICIPY_WEBSITE_URL",
        "ANTICIPY_CLOUD_AUTH_TOKEN",
        "ANTICIPY_SESSION_FILE",
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
        "TWILIO_PHONE_NUMBER",
        "TWILIO_TEST_TO_REAL_NUMBER",
        "TWILIO_MOCK",
    ):
        os.environ.pop(var, None)


def test_broker_disabled_mock_path() -> None:
    banner("1. broker disabled, TWILIO_MOCK=1 returns mock")
    _clear_broker_env()
    os.environ["TWILIO_MOCK"] = "1"

    # Re-import fresh after env reset.
    if "app.product.sms_pre_confirm" in sys.modules:
        del sys.modules["app.product.sms_pre_confirm"]
    from app.product import sms_pre_confirm  # type: ignore

    if sms_pre_confirm._twilio_broker_enabled():
        bad("broker_disabled", "ANTICIPY_TWILIO_BROKER unexpectedly enabled")
        return
    result = sms_pre_confirm.send_sms_sync(
        "+15555550100", "smoke test body", kind="preconfirm")
    if not result.get("ok"):
        bad("mock_returns_ok", f"got {result}")
        return
    if not result.get("mock"):
        bad("mock_flag_true", f"got {result}")
        return
    if result.get("source") == "broker":
        bad("not_via_broker", f"got {result}")
        return
    ok("broker_disabled_mock_path")


def test_broker_enabled_missing_session() -> None:
    banner("2. broker enabled, no session token returns missing_session")
    _clear_broker_env()
    os.environ["ANTICIPY_TWILIO_BROKER"] = "1"
    # Force the on-disk session lookup to a path that does not exist.
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["ANTICIPY_SESSION_FILE"] = str(
            Path(tmp) / "no-session-here.json")

        if "app.product.sms_pre_confirm" in sys.modules:
            del sys.modules["app.product.sms_pre_confirm"]
        from app.product import sms_pre_confirm  # type: ignore

        if not sms_pre_confirm._twilio_broker_enabled():
            bad("broker_enabled", "flag not honoured")
            return
        broker_result = sms_pre_confirm._send_via_broker(
            "smoke body", "+15555550100", "preconfirm")
        if broker_result.get("ok"):
            bad("missing_session_not_ok", f"got {broker_result}")
            return
        if broker_result.get("error") != "missing_session":
            bad("missing_session_error",
                f"expected error=missing_session got {broker_result}")
            return
        if broker_result.get("source") != "broker":
            bad("missing_session_source",
                f"expected source=broker got {broker_result}")
            return
    ok("broker_enabled_missing_session")


def test_broker_enabled_junk_token_degrades_to_direct() -> None:
    banner("3. broker enabled, junk token 401 falls back to direct mock")
    _clear_broker_env()
    os.environ["ANTICIPY_TWILIO_BROKER"] = "1"
    os.environ["ANTICIPY_CLOUD_AUTH_TOKEN"] = "junk-token-not-a-real-jwt"
    os.environ["TWILIO_MOCK"] = "1"

    if "app.product.sms_pre_confirm" in sys.modules:
        del sys.modules["app.product.sms_pre_confirm"]
    from app.product import sms_pre_confirm  # type: ignore

    # Stub httpx.Client so we do not actually hit the network. The stub
    # returns 401 to simulate the website-side broker rejecting an
    # invalid Supabase token.
    import httpx  # type: ignore

    class _FakeResponse:
        status_code = 401

        def json(self) -> dict:
            return {"ok": False, "error": "Unauthorized"}

        @property
        def text(self) -> str:
            return "{\"ok\":false,\"error\":\"Unauthorized\"}"

    class _FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.calls: list[tuple[str, dict, dict]] = []

        def __enter__(self) -> "_FakeClient":
            return self

        def __exit__(self, *exc_info: object) -> None:  # noqa: D401
            return None

        def post(self, url: str, *, json: dict | None = None,
                 headers: dict | None = None) -> _FakeResponse:
            self.calls.append((url, json or {}, headers or {}))
            return _FakeResponse()

    original_client = httpx.Client
    httpx.Client = _FakeClient  # type: ignore[assignment]
    try:
        broker_result = sms_pre_confirm._send_via_broker(
            "smoke body", "+15555550100", "preconfirm")
        if broker_result.get("ok"):
            bad("junk_token_not_ok", f"got {broker_result}")
            return
        if broker_result.get("status") != 401:
            bad("junk_token_status_401",
                f"expected 401 got {broker_result}")
            return
        # Full send_sms_sync should fall through to the direct path,
        # which under TWILIO_MOCK=1 returns ok with mock=True.
        full_result = sms_pre_confirm.send_sms_sync(
            "+15555550100", "smoke test body", kind="preconfirm")
        if not full_result.get("ok"):
            bad("degraded_to_mock_ok", f"got {full_result}")
            return
        if not full_result.get("mock"):
            bad("degraded_to_mock_flag", f"got {full_result}")
            return
        if full_result.get("source") == "broker":
            bad("degraded_not_via_broker", f"got {full_result}")
            return
    finally:
        httpx.Client = original_client  # type: ignore[assignment]
    ok("broker_enabled_junk_token_degrades_to_direct")


def main() -> int:
    print("Twilio broker smoke test", flush=True)
    print(f"  repo root: {ROOT}", flush=True)
    for fn in (
        test_broker_disabled_mock_path,
        test_broker_enabled_missing_session,
        test_broker_enabled_junk_token_degrades_to_direct,
    ):
        try:
            fn()
        except Exception as exc:
            bad(fn.__name__, f"raised {type(exc).__name__}: {exc}")
            traceback.print_exc()
    print(
        f"\nPASS={len(GREEN_CHECKS)} FAIL={len(RED_CHECKS)}",
        flush=True,
    )
    return 0 if not RED_CHECKS else 1


if __name__ == "__main__":
    sys.exit(main())
