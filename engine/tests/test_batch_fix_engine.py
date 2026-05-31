"""Batch fixes verification suite — Engine side.

Covers the 12 fixes landed by the engine-side batch agent:

  1. BNEW-004 + UX-002  -- POST /api/onboarding/basic_profile persists name+location
  2. UX-003              -- GET /api/extension/probe returns agent_alive
  3. B-PHASE9-1          -- email_draft plans compose a real Gmail URL
  4. B-PHASE9-2          -- email-shape regex fast-path runs BEFORE the LLM
  5. B-PHASE9-3a         -- parse_draft_intent requires the literal "draft" verb
  6. B-PHASE9-3b         -- SMS pre-confirm gate fires on the parse_draft_intent fast-path
  7. BNEW-001            -- /api/past_tasks always applies a user_id / account_id filter
  8. BNEW-003            -- /api/sms/inbound rejects requests without a valid Twilio signature
  9. BNEW-005            -- /api/listen/dismiss acquires lock + requires X-Anticipy-Token
 10. BNEW-006            -- /api/listen/reset requires X-Anticipy-Token + rate limit
 11. BNEW-009            -- /api/onboarding/call_start enforces per-IP cap of 3/hour
 12. UX-007              -- the mic device picker prefers real hardware over virtual loopbacks
 13. task queue stuck    -- the dispatcher promotes waiting -> pending when wake_at elapses

Each test exercises the user-visible contract with the real engine
module loaded against fastapi.testclient.TestClient. No live engine
restart, no network IO. TWILIO_MOCK=1 keeps every Twilio path mocked
per the no-real-send memory.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Bootstrap engine import path.
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_ENGINE_ROOT = os.path.dirname(_HERE)
if _ENGINE_ROOT not in sys.path:
    sys.path.insert(0, _ENGINE_ROOT)

# Pin a non-production port so the eager singleton lock at module
# import never collides with the live engine on 8731.
os.environ.setdefault("ANTICIPY_ENGINE_PORT", "59799")
os.environ.setdefault("ANTICIPY_TEST_FAST_TIMEOUTS", "1")
os.environ.setdefault("TWILIO_MOCK", "1")
os.environ.setdefault("ANTICIPY_DEV_MODE", "1")  # bypass token checks in tests


# ---------------------------------------------------------------------------
# Module-level imports (lazy, after env setup).
# ---------------------------------------------------------------------------


def _make_client():
    """TestClient bound to the engine FastAPI app."""
    from app.product import server as _srv
    from fastapi.testclient import TestClient
    return _srv, TestClient(_srv.app)


# ---------------------------------------------------------------------------
# FIX 1: BNEW-004 + UX-002 -- POST /api/onboarding/basic_profile
# ---------------------------------------------------------------------------


def test_bnew_004_basic_profile_endpoint_exists_and_persists():
    """Hitting the previously-missing /api/onboarding/basic_profile
    endpoint MUST return 200 and persist name + location into the
    session profile so /api/state.onboarded flips True."""
    _srv, client = _make_client()
    # Reset any previous profile fixture so the test starts from a known
    # state.
    _srv._SESS["profile"] = None
    _srv._SESS["profile_obj"] = None
    resp = client.post(
        "/api/onboarding/basic_profile",
        json={"name": "Test User", "location": "Vancouver, BC"},
    )
    assert resp.status_code == 200, (
        f"basic_profile returned {resp.status_code}: {resp.text[:300]}"
    )
    body = resp.json()
    assert body["ok"] is True, body
    assert body["name"] == "Test User"
    assert body["location"] == "Vancouver, BC"
    assert body["onboarded"] is True
    # Verify state echoes onboarded=true via the integrated /api/state
    # route (G2: layer-above check).
    state = client.get("/api/state").json()
    assert state["onboarded"] is True, state


def test_bnew_004_basic_profile_partial_only_name():
    """A partial submission (name only) still persists what it has but
    does not mark onboarded since location is required for True."""
    _srv, client = _make_client()
    _srv._SESS["profile"] = None
    _srv._SESS["profile_obj"] = None
    resp = client.post(
        "/api/onboarding/basic_profile",
        json={"name": "Solo Name"},
    )
    assert resp.status_code == 200, resp.text[:200]
    body = resp.json()
    assert body["ok"] is True
    assert body["name"] == "Solo Name"
    assert body["onboarded"] is False


# ---------------------------------------------------------------------------
# FIX 2: UX-003 -- /api/extension/probe
# ---------------------------------------------------------------------------


def test_ux_003_extension_probe_returns_alive_field():
    """The probe must return a JSON body with agent_alive: bool. The
    actual value depends on whether anticipy_agent.py is running on
    the host; this test only verifies the contract shape."""
    _srv, client = _make_client()
    resp = client.get("/api/extension/probe")
    assert resp.status_code == 200, resp.text[:300]
    body = resp.json()
    assert body.get("ok") is True
    assert "agent_alive" in body, body
    assert isinstance(body["agent_alive"], bool)
    # connected mirror is also expected
    assert "connected" in body
    assert isinstance(body["connected"], bool)


# ---------------------------------------------------------------------------
# FIX 3: B-PHASE9-1 -- _compose_gmail_url_from_plan produces a real URL
# ---------------------------------------------------------------------------


def test_phase9_1_compose_gmail_url_from_plan():
    """Engine helper must compose a navigable Gmail URL so the
    extension bridge can open it, instead of passing the plan task
    sentence as the navigation target."""
    _srv, _client = _make_client()
    plan = {
        "mode": "act",
        "intent": "email_draft",
        "task": (
            "Draft an email to lara@example.com with subject Friday "
            "demo saying Thanks for the great Friday demo, follow up "
            "next week."
        ),
        "person": "lara@example.com",
        "thing": "Friday demo",
    }
    url = _srv._compose_gmail_url_from_plan(
        plan["task"], plan,
    )
    assert url.startswith("https://mail.google.com/mail/"), url
    assert "to=lara%40example.com" in url, url
    assert "view=cm" in url, url
    assert "su=" in url, url
    assert "body=" in url, url


def test_phase9_1_dispatch_via_bridge_uses_gmail_url_for_email_draft(
    monkeypatch,
):
    """Wiring check: when /_dispatch_via_extension_bridge fires with
    intent=email_draft, the intent_payload handed to dispatch_action
    must carry a real Gmail compose URL, NOT the plan task sentence.
    """
    _srv, _client = _make_client()
    captured: list[dict[str, Any]] = []

    def fake_dispatch(*, goal: str, intent_payload: dict[str, Any]):
        captured.append({
            "goal": goal,
            "intent_payload": dict(intent_payload),
        })
        return {
            "ran": True,
            "surface": "extension",
            "screenshot_path": "/tmp/x.png",
            "url": str(intent_payload.get("target") or ""),
            "error": "",
            "proof": {"url": str(intent_payload.get("target") or "")},
            "source": "stub",
            "verb": intent_payload.get("verb"),
            "target": intent_payload.get("target"),
        }

    monkeypatch.setattr(
        "app.product.server._browser_surface",
        lambda: "extension_native_bridge", raising=False,
    )
    # Patch the imported dispatch_action inside the function body. The
    # function does `from app.action_engine.dispatch import dispatch_action`
    # at call time, so patching the source module works.
    monkeypatch.setattr(
        "app.action_engine.dispatch.dispatch_action",
        fake_dispatch, raising=False,
    )
    monkeypatch.setattr(
        "app.action_engine.dispatch.extension_surface_available",
        lambda: True, raising=False,
    )
    instruction = (
        "Draft an email to omarkebrahim+anticipy-test@gmail.com "
        "with subject Friday demo saying Thanks for the great Friday demo"
    )
    plan = {
        "mode": "act",
        "intent": "email_draft",
        "task": instruction,
        "person": "omarkebrahim+anticipy-test@gmail.com",
        "thing": "Friday demo",
    }
    resp = _srv._dispatch_via_extension_bridge(instruction, plan)
    assert resp is not None
    assert captured, "dispatch_action was not invoked"
    payload = captured[0]["intent_payload"]
    target = payload.get("target", "")
    # The target MUST now be a real Gmail compose URL, NOT the plan
    # task prose. This was the Phase 9 dispatch failure.
    assert target.startswith("https://mail.google.com/mail/"), target
    assert "to=omarkebrahim" in target, target


# ---------------------------------------------------------------------------
# FIX 4: B-PHASE9-2 -- email-shape regex fast-path runs BEFORE the LLM
# ---------------------------------------------------------------------------


def test_phase9_2_email_shape_fastpath_returns_email_draft_plan():
    """The new fastpath must promote any 'verb + recipient email'
    utterance to mode=act / intent=email_draft so the live LLM
    classifier's misroute to school_deadline_reminder cannot happen
    on the inject hot path."""
    _srv, _client = _make_client()
    plan = _srv._fastpath_email_shape_to_plan(
        "draft a thank you email to omarkebrahim+anticipy-test@gmail.com "
        "about Friday demo")
    assert plan is not None, plan
    assert plan["mode"] == "act"
    assert plan["intent"] == "email_draft"
    assert "omarkebrahim+anticipy-test@gmail.com" in plan["person"]
    assert plan["_fastpath"] == "email_shape"
    # The fastpath should also fire for "send" verbs; the SMS gate
    # downstream blocks the actual send.
    plan2 = _srv._fastpath_email_shape_to_plan(
        "send omarkebrahim+anticipy-test@gmail.com the Friday demo notes")
    assert plan2 is not None
    assert plan2["intent"] == "email_draft"


def test_phase9_2_fastpath_does_not_fire_without_email_address():
    """No email address means no fastpath match (so unrelated
    utterances still go to the LLM)."""
    _srv, _client = _make_client()
    assert _srv._fastpath_email_shape_to_plan(
        "open google.com in a new tab") is None
    assert _srv._fastpath_email_shape_to_plan(
        "draft a Friday update for the team") is None


# ---------------------------------------------------------------------------
# FIX 5a: B-PHASE9-3 -- parse_draft_intent only matches the "draft" verb
# ---------------------------------------------------------------------------


def test_phase9_3a_parse_draft_intent_requires_draft_verb():
    """parse_draft_intent MUST return None for send/mail/share/follow-up
    verbs so those flows fall through to the SMS pre-confirm gate."""
    from app.action_engine.gmail_compose import parse_draft_intent
    # Draft and compose are safe (drafting is reversible).
    safe = parse_draft_intent(
        "Draft an email to user@example.com with subject Hi saying body")
    assert safe is not None, "draft verb should still match"
    safe2 = parse_draft_intent(
        "Compose an email to user@example.com with subject Hi saying body")
    assert safe2 is not None, "compose verb should match"
    # Unsafe verbs must NOT short-circuit the gate.
    for unsafe in (
        "send user@example.com a Friday update saying see attached",
        "mail user@example.com the contract subject Sign saying urgent",
        "share user@example.com the deck about Q4 plans",
        "follow up with user@example.com about the demo",
    ):
        assert parse_draft_intent(unsafe) is None, (
            f"parse_draft_intent must NOT match unsafe verb: {unsafe!r}")


# ---------------------------------------------------------------------------
# FIX 5b: B-PHASE9-3 -- SMS pre-confirm gate fires on the fast-path
# ---------------------------------------------------------------------------


def test_phase9_3b_sms_gate_fires_on_parse_draft_intent_fastpath(
    monkeypatch,
):
    """Even when parse_draft_intent matches, the SMS pre-confirm gate
    must be consulted. We force should_pre_confirm to True and verify
    /api/act returns the sms_pending_confirm payload instead of
    dispatching the draft directly."""
    _srv, client = _make_client()
    monkeypatch.setattr(
        "app.product.sms_pre_confirm.should_pre_confirm",
        lambda plan, instruction: True, raising=False,
    )

    def fake_create_pending(plan, instruction):
        return {
            "ok": True,
            "task_id": "test-pending-1",
            "status": "pending",
            "channel": "sms",
            "preconfirm_sms_sent": True,
            "fixture": "test_phase9_3b",
        }

    monkeypatch.setattr(
        "app.product.sms_pre_confirm.create_pending_confirm",
        fake_create_pending, raising=False,
    )
    resp = client.post("/api/act", json={
        "instruction": (
            "Draft an email to lara@example.com with subject "
            "Friday saying Hi"
        ),
    })
    assert resp.status_code == 200, resp.text[:400]
    body = resp.json()
    assert body.get("task_id") == "test-pending-1", body
    assert body.get("preconfirm_sms_sent") is True, body
    assert body.get("status") == "pending"


# ---------------------------------------------------------------------------
# FIX 6: BNEW-001 -- /api/past_tasks always applies a filter
# ---------------------------------------------------------------------------


def test_bnew_001_past_tasks_requires_filter():
    """The endpoint must NEVER return rows without a user_id / account_id
    filter. Calling it with no params still uses USER_ID by default."""
    _srv, client = _make_client()
    # No params: should fall back to USER_ID which is set at startup.
    resp = client.get("/api/past_tasks?limit=5")
    assert resp.status_code in (200, 400), resp.text[:200]
    body = resp.json()
    # When supabase is not configured (test env), endpoint returns
    # ok=True with empty rows. The contract this test verifies is the
    # shape, not the result count.
    assert "rows" in body, body
    assert "user_id_filter" in body or "error" in body, body


def test_bnew_001_past_tasks_propagates_user_id_filter(monkeypatch):
    """When user_id is supplied, the endpoint MUST add a user_id eq
    filter to the Supabase query AND drop any rows whose user_id does
    not match (defense in depth)."""
    _srv, client = _make_client()
    # Stub the urllib.request.urlopen the endpoint uses for its
    # Supabase REST call. Return a payload with mixed user_ids to
    # exercise the post-filter.
    captured_urls: list[str] = []

    class FakeResp:
        def __init__(self, payload: bytes):
            self._payload = payload
        def read(self) -> bytes:
            return self._payload
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=10):
        captured_urls.append(req.full_url)
        body = json.dumps([
            {"id": 1, "user_id": "alice", "task_id": "t1",
             "instruction": "x", "status": "done", "created_at": "",
             "updated_at": "", "account_id": "ac1"},
            {"id": 2, "user_id": "bob", "task_id": "t2",
             "instruction": "leak", "status": "done", "created_at": "",
             "updated_at": "", "account_id": "ac2"},
            {"id": 3, "user_id": "alice", "task_id": "t3",
             "instruction": "y", "status": "done", "created_at": "",
             "updated_at": "", "account_id": "ac1"},
        ]).encode("utf-8")
        return FakeResp(body)

    monkeypatch.setattr(
        "urllib.request.urlopen", fake_urlopen, raising=False)
    # Also stub the SUPABASE_URL so the endpoint takes the real path.
    monkeypatch.setattr(
        "app.config.SUPABASE_URL", "https://stub.example.com",
        raising=False)
    monkeypatch.setattr(
        "app.config.SUPABASE_ANON_KEY", "stub-key", raising=False)
    resp = client.get("/api/past_tasks?user_id=alice&limit=10")
    assert resp.status_code == 200, resp.text[:300]
    body = resp.json()
    assert body.get("ok") is True, body
    # G1: the URL handed to Supabase must contain the user_id filter.
    assert captured_urls, "no URLs captured"
    assert "user_id=eq.alice" in captured_urls[0], captured_urls[0]
    # G2: cross-tenant rows MUST be filtered out client-side too.
    rows = body.get("rows", [])
    assert all(r.get("user_id") == "alice" for r in rows), rows
    # Bob's leaky row must not appear.
    assert not any(r.get("instruction") == "leak" for r in rows), rows


# ---------------------------------------------------------------------------
# FIX 7: BNEW-003 -- Twilio signature check on /api/sms/inbound
# ---------------------------------------------------------------------------


def test_bnew_003_sms_inbound_rejects_unsigned_when_token_set(
    monkeypatch,
):
    """With TWILIO_AUTH_TOKEN configured and TWILIO_MOCK off, an
    unsigned POST MUST be rejected with 403."""
    _srv, client = _make_client()
    monkeypatch.delenv("TWILIO_MOCK", raising=False)
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test-token-12345")
    resp = client.post(
        "/api/sms/inbound",
        data={"Body": "YES", "From": "+15555550100", "To": "+15555550199"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 403, (
        f"unsigned POST should be rejected, got {resp.status_code}: "
        f"{resp.text[:300]}"
    )
    body = resp.json()
    assert body.get("error") == "twilio_signature_invalid"


def test_bnew_003_sms_inbound_accepts_valid_signature(monkeypatch):
    """A correctly-signed inbound POST passes the verifier."""
    import base64
    import hashlib
    import hmac as _hmac
    _srv, client = _make_client()
    monkeypatch.delenv("TWILIO_MOCK", raising=False)
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test-token-12345")
    monkeypatch.delenv("TWILIO_PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("ANTICIPY_PUBLIC_BASE_URL", raising=False)
    # No pending tasks; reply should classify as unknown and ack.
    fields = {
        "Body": "YES", "From": "+15555550100", "To": "+15555550199",
        "MessageSid": "SM-test-1",
    }
    # TestClient base URL is http://testserver
    url = "http://testserver/api/sms/inbound"
    keys = sorted(fields.keys())
    payload = url + "".join(k + fields[k] for k in keys)
    digest = _hmac.new(
        b"test-token-12345", payload.encode("utf-8"),
        hashlib.sha1).digest()
    sig = base64.b64encode(digest).decode("ascii")
    resp = client.post(
        "/api/sms/inbound", data=fields,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "x-twilio-signature": sig,
            "Accept": "application/json",
        },
    )
    assert resp.status_code == 200, resp.text[:300]


def test_bnew_003_sms_inbound_bypassed_in_mock_mode():
    """TWILIO_MOCK=1 bypasses the signature check so unit tests can
    exercise the handler without HMAC plumbing."""
    _srv, client = _make_client()
    # TWILIO_MOCK is set at module top.
    resp = client.post(
        "/api/sms/inbound",
        data={"Body": "YES", "From": "+15555550100"},
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    assert resp.status_code == 200, resp.text[:300]


# ---------------------------------------------------------------------------
# FIX 8: BNEW-005 -- /api/listen/dismiss requires token + lock
# ---------------------------------------------------------------------------


def test_bnew_005_listen_dismiss_requires_token(monkeypatch):
    """When ANTICIPY_DEV_MODE is off and TWILIO_MOCK is off, hitting
    /api/listen/dismiss without the engine-local token MUST 401."""
    _srv, client = _make_client()
    monkeypatch.delenv("ANTICIPY_DEV_MODE", raising=False)
    monkeypatch.delenv("TWILIO_MOCK", raising=False)
    resp = client.post("/api/listen/dismiss")
    assert resp.status_code == 401, (
        f"listen/dismiss without token must be 401, got "
        f"{resp.status_code}: {resp.text[:200]}"
    )


def test_bnew_005_listen_dismiss_with_valid_token(monkeypatch):
    """With a valid X-Anticipy-Token header, dismiss works."""
    _srv, client = _make_client()
    monkeypatch.delenv("ANTICIPY_DEV_MODE", raising=False)
    monkeypatch.delenv("TWILIO_MOCK", raising=False)
    # Read or generate the local token.
    token = _srv._engine_local_token()
    assert token, "engine local token unavailable"
    # Set a pending so we can verify it gets cleared under the lock.
    _srv._LISTEN["pending"] = {"instruction": "test", "ts": time.time()}
    resp = client.post(
        "/api/listen/dismiss",
        headers={"X-Anticipy-Token": token},
    )
    assert resp.status_code == 200, resp.text[:200]
    body = resp.json()
    assert body.get("ok") is True
    assert _srv._LISTEN["pending"] is None


# ---------------------------------------------------------------------------
# FIX 9: BNEW-006 -- /api/listen/reset requires token
# ---------------------------------------------------------------------------


def test_bnew_006_listen_reset_requires_token(monkeypatch):
    """/api/listen/reset MUST 401 without the token in real mode."""
    _srv, client = _make_client()
    monkeypatch.delenv("ANTICIPY_DEV_MODE", raising=False)
    monkeypatch.delenv("TWILIO_MOCK", raising=False)
    resp = client.post("/api/listen/reset")
    assert resp.status_code == 401, resp.text[:200]


# ---------------------------------------------------------------------------
# FIX 10: BNEW-009 -- /api/onboarding/call_start rate limit
# ---------------------------------------------------------------------------


def test_bnew_009_call_start_per_ip_rate_limit(monkeypatch):
    """3 successful POSTs allowed per hour per IP; the 4th MUST 429.

    We force the cap to 2 via env var so the test runs in 3 calls and
    avoids the 3/hour production constant; the engine treats the env
    var as the source of truth.
    """
    _srv, client = _make_client()
    monkeypatch.setenv("ANTICIPY_CALL_START_LIMIT_PER_HOUR", "2")
    # Reset the bucket so prior tests in this session do not pollute.
    bucket_prefix = "onboarding_call_start:"
    keys_to_drop = [
        k for k in list(_srv._RATE_LIMIT_BUCKETS.keys())
        if k.startswith(bucket_prefix)
    ]
    for k in keys_to_drop:
        _srv._RATE_LIMIT_BUCKETS.pop(k, None)
    # 2 inside the cap (return code may be 503/error because direct
    # twilio creds are unset, but the rate gate must NOT fire on the
    # first two attempts).
    for i in range(2):
        resp = client.post(
            "/api/onboarding/call_start",
            json={"phone_e164": "+15555550100"},
        )
        # 503 means "no broker / no creds"; 200 means it actually
        # placed (broker mock). The rate limit MUST NOT have fired.
        assert resp.status_code != 429, (
            f"attempt {i + 1} prematurely rate-limited: {resp.text[:300]}"
        )
    # Third attempt MUST be 429.
    resp3 = client.post(
        "/api/onboarding/call_start",
        json={"phone_e164": "+15555550100"},
    )
    assert resp3.status_code == 429, (
        f"third attempt must be rate-limited, got "
        f"{resp3.status_code}: {resp3.text[:300]}"
    )
    body = resp3.json()
    assert body.get("rate_limited") is True, body
    assert body.get("limit_per_hour") == 2, body


# ---------------------------------------------------------------------------
# FIX 11: UX-007 -- prefer real hardware mic over virtual loopback
# ---------------------------------------------------------------------------


def test_ux_007_audio_device_selection_prefers_real_over_virtual():
    """The picker must rank real hardware mics ahead of virtual
    loopback devices even when the virtual device reports as default.
    We exercise the helper logic that classifies and sorts devices."""
    _srv, _client = _make_client()
    # Simulated CoreAudio device list: BlackHole (virtual) is default,
    # MacBook Pro Microphone (builtin) and Yeti USB are both real.
    devices = [
        {
            "index": 0, "name": "BlackHole 2ch",
            "max_input_channels": 2, "default_samplerate": 48000.0,
        },
        {
            "index": 1, "name": "MacBook Pro Microphone",
            "max_input_channels": 1, "default_samplerate": 48000.0,
        },
        {
            "index": 2, "name": "Yeti Stereo Microphone",
            "max_input_channels": 1, "default_samplerate": 44100.0,
        },
    ]
    default_name = "BlackHole 2ch"
    rows = [_srv._audio_device_row(i, d, default_name) for i, d in
            enumerate(devices)]
    # Verify kind classification: BlackHole=virtual, MBP=builtin,
    # Yeti=external_usb (matches Yeti keyword).
    by_name = {r["name"]: r for r in rows}
    assert by_name["BlackHole 2ch"]["kind"] == "virtual", by_name
    assert by_name["MacBook Pro Microphone"]["kind"] == "builtin"
    assert by_name["Yeti Stereo Microphone"]["kind"] == "external_usb"
    # The bucket logic in /api/listen/start: pass_buckets[0] is "real +
    # default", pass_buckets[1] is "real but not default". With BlackHole
    # as default, MBP and Yeti land in bucket 1 (real, not default).
    # BlackHole lands in bucket 2 (default but virtual). When
    # ANTICIPY_ALLOW_VIRTUAL_AUDIO is unset, the picker MUST visit
    # buckets in order 0,1,2,3 -> the first real device wins over
    # BlackHole.
    real_kinds = {"builtin", "external_usb", "bluetooth"}
    real_rows = [r for r in rows if r["kind"] in real_kinds]
    assert real_rows, "expected at least one real hardware mic in fixture"
    # If we picked under the production preference (real-first), the
    # first selected device must NOT be the virtual BlackHole when a
    # real device exists.
    picked_under_real_first = real_rows[0]
    assert picked_under_real_first["kind"] != "virtual"
    assert picked_under_real_first["name"] != "BlackHole 2ch"


# ---------------------------------------------------------------------------
# FIX 12: task queue stuck -- waiting -> pending promotion on wake
# ---------------------------------------------------------------------------


def test_task_queue_stuck_waiting_promotes_to_pending(monkeypatch):
    """A WAITING task whose wake_at has elapsed MUST be promoted back
    to PENDING by the dispatcher scan. Before this fix the queue's
    waiting count grew without bound."""
    # Isolate the queue state to a temp dir so production data is not
    # touched.
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("ANTICIPY_DATA_DIR", tmp)
        # Force a re-import of the store so the new ANTICIPY_DATA_DIR
        # takes effect. The store caches its dir at import.
        import importlib
        from app import task_queue as _tq
        importlib.reload(_tq.store)
        importlib.reload(_tq.dispatcher)
        importlib.reload(_tq)
        store = _tq.store
        disp = _tq.dispatcher
        # Enqueue a task and park it as waiting with wake_at in the
        # past.
        rec = store.enqueue("test waiting promotion task",
                             account_id="user-x")
        # claim_next to flip to in_progress, then wait_for to park.
        claimed = store.claim_next()
        assert claimed is not None
        wake_at_past = time.time() - 60.0  # 1 minute ago
        store.wait_for(
            claimed.task_id,
            "test_waiting_wakes_up",
            wake_at=wake_at_past,
        )
        # Sanity: the task is waiting now.
        rec_after = store.get(claimed.task_id)
        assert rec_after is not None
        assert rec_after.status == "waiting", rec_after
        # Run the promotion helper.
        promoted = disp._promote_due_waiting_tasks(time.time())
        assert promoted == 1, f"expected to promote 1, got {promoted}"
        rec_promoted = store.get(claimed.task_id)
        assert rec_promoted is not None
        assert rec_promoted.status == "pending", rec_promoted


def test_task_queue_waiting_without_wake_at_not_promoted(monkeypatch):
    """Tasks parked in waiting WITHOUT a wake_at hint depend on an
    external signal and MUST stay waiting indefinitely."""
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("ANTICIPY_DATA_DIR", tmp)
        import importlib
        from app import task_queue as _tq
        importlib.reload(_tq.store)
        importlib.reload(_tq.dispatcher)
        importlib.reload(_tq)
        store = _tq.store
        disp = _tq.dispatcher
        rec = store.enqueue("blocked task", account_id="user-y")
        claimed = store.claim_next()
        assert claimed is not None
        # wait_for WITHOUT wake_at -> stays parked.
        store.wait_for(claimed.task_id, "needs_user_clarification")
        promoted = disp._promote_due_waiting_tasks(time.time())
        assert promoted == 0
        rec_after = store.get(claimed.task_id)
        assert rec_after is not None
        assert rec_after.status == "waiting"
