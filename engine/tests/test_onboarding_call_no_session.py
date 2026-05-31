"""Tests for /api/onboarding/call_start dispatch fallback.

Background: before this fix, the handler returned 401 "no Supabase
session" when the engine could not resolve a Supabase token. On a local
Mac install (owner running his own engine with TWILIO creds in
.env.local) there is no Supabase session to inherit, so the popover
"Have Anticipy call you" card always showed "Call failed".

The handler now has two dispatch paths:

  1. Supabase session present -> POST to the website broker
     (/api/twilio/voice-relay). This is the multi-tenant shipping path
     for strangers who downloaded the DMG.
  2. Direct-Twilio creds present in env -> POST directly to the Twilio
     REST API (Calls.json) with the website-hosted TwiML URL. This is
     the owner-on-own-Mac path.
  3. Neither -> 503 with a clear error explaining BOTH remediations.

These tests exercise all three paths via FastAPI's TestClient. Neither
real Twilio nor the real website is contacted: the broker call goes
through a monkeypatched _place_voice_call_via_broker, and the direct
Twilio path is short-circuited with TWILIO_MOCK=1 which returns a
synthetic ok payload without any network call.

The owner's real phone number (+16047245161 per memory) is never used
in these tests; +13128675309 is the canonical safe test number used
elsewhere in the repo (see scripts/v7/twilio_onboarding_call.py).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Pin the engine port high before importing server so the startup port
# reclaim cannot collide with a live dev engine on 8731.
os.environ.setdefault("ANTICIPY_ENGINE_PORT", "59745")
os.environ.setdefault("ANTICIPY_PORT", "59745")


SAFE_TEST_PHONE = "+13128675309"


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """Strip every env var that influences dispatch picking + force the
    audit log + timeline to per-test tmp paths so nothing leaks into
    ~/.anticipy and tests do not see each other's state.
    """
    for key in (
        "ANTICIPY_CLOUD_AUTH_TOKEN",
        "TWILIO_BROKER_ACCOUNT_SID",
        "TWILIO_BROKER_SID",
        "TWILIO_BROKER_TOKEN",
        "TWILIO_BROKER_FROM",
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
        "TWILIO_PHONE_NUMBER",
        "TWILIO_API_KEY_SID",
        "TWILIO_API_KEY_SECRET",
        "TWILIO_MOCK",
        "ANTICIPY_WEBSITE_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    # Point the on-disk session lookup at a tmp file that does not
    # exist, so _voice_broker_supabase_token returns "" by default.
    monkeypatch.setenv(
        "ANTICIPY_SESSION_FILE", str(tmp_path / "session_missing.json"),
    )
    # Redirect the voice-call audit log + timeline writes.
    monkeypatch.setenv(
        "ANTICIPY_TIMELINE_PATH", str(tmp_path / "timeline.jsonl"),
    )
    return tmp_path


@pytest.fixture
def client(isolated_env, monkeypatch):
    """A FastAPI TestClient bound to server.app, with the voice-call
    log path redirected through monkeypatching of the path helper.
    """
    from fastapi.testclient import TestClient
    from app.product import server

    log_path = isolated_env / "voice_onboarding_calls.jsonl"
    monkeypatch.setattr(server, "_voice_call_log_path", lambda: log_path)
    return TestClient(server.app)


def test_no_session_and_no_creds_returns_503_with_clear_error(client):
    """When NEITHER a Supabase session NOR direct Twilio creds are
    available, the handler must return a 503 with an actionable error
    naming both remediation paths. This is the bug-fix surface: before
    the fix this case returned 401 "no Supabase session", which left
    owners on their own Mac with no path forward.
    """
    resp = client.post(
        "/api/onboarding/call_start",
        json={"phone_e164": SAFE_TEST_PHONE},
    )
    assert resp.status_code == 503, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert body["dispatch_source"] == "none"
    # The error must point at BOTH remediations so the user knows what
    # to do without reading the source.
    err = (body.get("error") or "").lower()
    assert "supabase" in err or "sign in" in err
    assert "twilio_broker_" in err or "twilio_account_sid" in err


def test_direct_twilio_creds_skip_session_check_via_mock(client, monkeypatch):
    """When TWILIO_BROKER_* env is set AND TWILIO_MOCK=1, the handler
    must use the direct-Twilio path and return ok=true with a synthetic
    SID. No Supabase session is required.

    This is the happy path for the owner-on-own-Mac case: the engine
    has Twilio creds locally, the popover "Call me" card works without
    needing to sign in on the website.
    """
    monkeypatch.setenv("TWILIO_BROKER_ACCOUNT_SID", "AC" + "x" * 32)
    monkeypatch.setenv("TWILIO_BROKER_SID", "AC" + "x" * 32)
    monkeypatch.setenv("TWILIO_BROKER_TOKEN", "y" * 32)
    monkeypatch.setenv("TWILIO_BROKER_FROM", "+16196584447")
    monkeypatch.setenv("TWILIO_MOCK", "1")

    resp = client.post(
        "/api/onboarding/call_start",
        json={"phone_e164": SAFE_TEST_PHONE},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["dispatch_source"] == "direct_twilio"
    assert body["call_sid"].startswith("CA_mock_")
    assert body["to"] == SAFE_TEST_PHONE
    assert body["from"] == "+16196584447"


def test_legacy_twilio_account_sid_creds_also_work(client, monkeypatch):
    """Same as the above but with the LEGACY env var names
    (TWILIO_ACCOUNT_SID + TWILIO_AUTH_TOKEN + TWILIO_PHONE_NUMBER) that
    Omar already has in .env.local. The handler must accept either
    naming so devs do not have to dual-write env vars.
    """
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC" + "x" * 32)
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "y" * 32)
    monkeypatch.setenv("TWILIO_PHONE_NUMBER", "+16196584447")
    monkeypatch.setenv("TWILIO_MOCK", "1")

    resp = client.post(
        "/api/onboarding/call_start",
        json={"phone_e164": SAFE_TEST_PHONE},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["dispatch_source"] == "direct_twilio"
    assert body["call_sid"].startswith("CA_mock_")


def test_supabase_session_still_routes_through_broker(client, monkeypatch):
    """When a Supabase session IS present, the broker path remains the
    preferred dispatch. This guards against accidentally regressing the
    multi-tenant shipping path while fixing the local case.
    """
    from app.product import server

    monkeypatch.setenv("ANTICIPY_CLOUD_AUTH_TOKEN", "fake_session_token")
    # Also set direct creds. The broker path must STILL win when the
    # session token is present.
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC" + "x" * 32)
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "y" * 32)
    monkeypatch.setenv("TWILIO_PHONE_NUMBER", "+16196584447")
    monkeypatch.setenv("TWILIO_MOCK", "1")

    captured: dict = {}

    def fake_broker(phone, account_id, token):
        captured["phone"] = phone
        captured["account_id"] = account_id
        captured["token"] = token
        return 200, {
            "ok": True,
            "call_sid": "CA_broker_fake",
            "status": "queued",
            "to": phone,
            "from": "+16196584447",
        }

    monkeypatch.setattr(
        server, "_place_voice_call_via_broker", fake_broker,
    )

    resp = client.post(
        "/api/onboarding/call_start",
        json={"phone_e164": SAFE_TEST_PHONE, "account_id": "acct-broker"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["dispatch_source"] == "broker"
    assert body["call_sid"] == "CA_broker_fake"
    assert captured["token"] == "fake_session_token"
    assert captured["phone"] == SAFE_TEST_PHONE
    assert captured["account_id"] == "acct-broker"


def test_phone_validation_runs_before_dispatch(client, monkeypatch):
    """Premium prefixes and bad phones must still 400 even when the
    direct path could otherwise succeed. The validation guard is a
    pre-condition independent of which dispatch path is chosen.
    """
    monkeypatch.setenv("TWILIO_BROKER_ACCOUNT_SID", "AC" + "x" * 32)
    monkeypatch.setenv("TWILIO_BROKER_TOKEN", "y" * 32)
    monkeypatch.setenv("TWILIO_BROKER_FROM", "+16196584447")
    monkeypatch.setenv("TWILIO_MOCK", "1")

    # Premium 1-900 prefix must be rejected.
    resp = client.post(
        "/api/onboarding/call_start",
        json={"phone_e164": "+19005551212"},
    )
    assert resp.status_code == 400
    err = (resp.json().get("error") or "").lower()
    assert "premium" in err

    # Non-US/CA must also be rejected (UK +44).
    resp = client.post(
        "/api/onboarding/call_start",
        json={"phone_e164": "+447911123456"},
    )
    assert resp.status_code == 400


def test_direct_twilio_writes_audit_row(client, monkeypatch, isolated_env):
    """Verify the local audit JSONL captures the placement so the
    /api/onboarding/voice_status poll has a primary local record.
    """
    import json

    monkeypatch.setenv("TWILIO_BROKER_ACCOUNT_SID", "AC" + "x" * 32)
    monkeypatch.setenv("TWILIO_BROKER_TOKEN", "y" * 32)
    monkeypatch.setenv("TWILIO_BROKER_FROM", "+16196584447")
    monkeypatch.setenv("TWILIO_MOCK", "1")

    resp = client.post(
        "/api/onboarding/call_start",
        json={"phone_e164": SAFE_TEST_PHONE, "account_id": "acct-direct"},
    )
    assert resp.status_code == 200, resp.text

    log_path = isolated_env / "voice_onboarding_calls.jsonl"
    assert log_path.exists(), "audit log was not written"
    rows = [
        json.loads(ln) for ln in log_path.read_text().splitlines() if ln
    ]
    assert any(
        r.get("account_id") == "acct-direct"
        and r.get("dispatch_source") == "direct_twilio"
        and r.get("ok") is True
        and (r.get("call_sid") or "").startswith("CA_mock_")
        for r in rows
    ), rows
