"""Integration tests for unified-timeline wiring (Phase 2 follow-on).

Every action Anticipy completes (SMS, voice, email draft, web action,
note, user reply) appends one row to ~/.anticipy/v7/timeline.jsonl via
engine.app.timeline.append(). These tests mock the SMS / voice / email
/ action-engine call sites and assert the corresponding timeline rows
land with the correct kind, channel, and status.

Each test points the timeline at a fresh per-test JSONL path via the
ANTICIPY_TIMELINE_PATH env var so the suite never touches the real
~/.anticipy/v7/timeline.jsonl.

Mocking strategy:
    - SMS / voice: monkeypatch send_sms_sync, _twilio_sms, _twilio_voice
      so no real Twilio HTTP traffic happens.
    - Email: monkeypatch create_gmail_draft so no CDP traffic happens.
    - Web action: drive _run_action_engine via make_real_action_engine
      monkeypatch so no Chrome traffic happens.
    - Notifier note: build a real Decision with kind=LOG and call
      _record_to_feed directly via asyncio.

Reads back via app.timeline.reader.tail so we exercise the same read
path the popover uses.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.timeline import reader  # noqa: E402


# Engine startup runs an aggressive port reclaim that prints a noisy
# message about /tmp/anticipy_product_8731.lock. We pin a high port so
# that path never collides with the live dev engine.
os.environ.setdefault("ANTICIPY_ENGINE_PORT", "59732")


@pytest.fixture
def tmp_timeline(tmp_path, monkeypatch):
    """Point the timeline writer / reader at a fresh JSONL file."""
    path = tmp_path / "timeline.jsonl"
    monkeypatch.setenv("ANTICIPY_TIMELINE_PATH", str(path))
    return path


def _read_lines(path: Path) -> list[dict]:
    """Read every JSONL line from path into dicts."""
    if not path.exists():
        return []
    rows: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if raw:
                rows.append(json.loads(raw))
    return rows


# ---------------------------------------------------------------------------
# 1. server._send_receipt_sms_sync (broker path)
# ---------------------------------------------------------------------------


def test_receipt_sms_broker_success_emits_done(tmp_timeline, monkeypatch):
    """Broker SMS succeeds -> timeline gets a done sms_sent row."""
    from app.product import server

    # Force broker path and supply destination phone.
    monkeypatch.setenv("ANTICIPY_TWILIO_BROKER", "1")
    monkeypatch.setenv("TWILIO_NOTIFY_TO", "+15551234567")
    monkeypatch.delenv("TWILIO_MOCK", raising=False)

    # Mock the broker call so no real Twilio traffic happens.
    fake_module = types.SimpleNamespace(
        send_sms_sync=lambda phone, body, category: {
            "ok": True, "twilio_sid": "SM_broker_123",
            "mock": False,
        }
    )
    monkeypatch.setitem(
        sys.modules, "app.product.sms_pre_confirm", fake_module
    )

    out = server._send_receipt_sms_sync("Sent the email to alice. ")
    assert out["ok"] is True
    assert out["source"] == "broker"

    rows = _read_lines(tmp_timeline)
    assert len(rows) == 1
    row = rows[0]
    assert row["kind"] == "sms_sent"
    assert row["channel"] == "twilio_sms"
    assert row["status"] == "done"
    assert row["summary"].startswith("SMS receipt to ")
    assert row["payload"]["to"] == "+15551234567"
    assert row["payload"]["twilio_sid"] == "SM_broker_123"
    assert row["payload"]["source"] == "broker"


def test_receipt_sms_broker_failure_emits_failed(tmp_timeline, monkeypatch):
    """Broker SMS raises -> timeline gets a failed sms_sent row."""
    from app.product import server

    monkeypatch.setenv("ANTICIPY_TWILIO_BROKER", "1")
    monkeypatch.setenv("TWILIO_NOTIFY_TO", "+15551234567")
    monkeypatch.delenv("TWILIO_MOCK", raising=False)

    def _boom(*args, **kwargs):
        raise RuntimeError("broker is on fire")

    fake_module = types.SimpleNamespace(send_sms_sync=_boom)
    monkeypatch.setitem(
        sys.modules, "app.product.sms_pre_confirm", fake_module
    )

    out = server._send_receipt_sms_sync("Sent the email to alice. ")
    assert out["ok"] is False

    rows = _read_lines(tmp_timeline)
    assert len(rows) == 1
    assert rows[0]["kind"] == "sms_sent"
    assert rows[0]["status"] == "failed"
    assert "broker is on fire" in rows[0]["payload"]["error"]


# ---------------------------------------------------------------------------
# 2. server._send_receipt_email_via_cdp (Gmail CDP draft path)
# ---------------------------------------------------------------------------


def test_receipt_email_draft_success_emits_done(tmp_timeline, monkeypatch):
    """Gmail draft via CDP succeeds -> timeline gets a done email_sent row."""
    from app.product import server

    monkeypatch.setenv("ANTICIPY_USER_EMAIL", "user@example.com")
    # Make sure CDP_PORT looks enabled to the helper.
    monkeypatch.setattr(server, "CDP_PORT", 9222, raising=False)

    # Stub the Gmail-compose module out before _send_receipt_email_via_cdp
    # imports it. Returns a DraftRequest-style result object with ok=True.
    class _StubResult:
        ok = True
        compose_url = "https://mail.google.com/compose/123"
        error = None

    fake_module = types.SimpleNamespace(
        DraftRequest=lambda **kw: kw,
        create_gmail_draft=lambda req, cdp_port, marker: _StubResult(),
    )
    monkeypatch.setitem(
        sys.modules, "app.action_engine.gmail_compose", fake_module
    )
    # Avoid the post-draft typing-evidence path that wants real CDP. The
    # only blocker is _gmail_find_compose_target reaching out via WS; we
    # short-circuit it to return "" so the typing helper is skipped.
    monkeypatch.setattr(
        server, "_gmail_find_compose_target",
        lambda *a, **kw: "", raising=False,
    )

    out = server._send_receipt_email_via_cdp(
        "Demo subject", "body text",
        sent_link="https://mail.google.com/#sent/xyz",
        screenshot_path="/tmp/anticipy/receipt.png",
        message_id="<abc@mail.gmail.com>",
    )
    assert out["ok"] is True

    rows = _read_lines(tmp_timeline)
    assert len(rows) == 1
    row = rows[0]
    assert row["kind"] == "email_sent"
    assert row["channel"] == "chrome"
    assert row["status"] == "done"
    assert row["payload"]["to"] == "user@example.com"
    assert row["payload"]["draft_only"] is True
    assert row["payload"]["message_id"] == "<abc@mail.gmail.com>"
    assert row["payload"]["sent_link"] == (
        "https://mail.google.com/#sent/xyz"
    )


# ---------------------------------------------------------------------------
# 3. server._run_action_engine (web action dispatcher)
# ---------------------------------------------------------------------------


def test_run_action_engine_success_emits_web_action_done(
        tmp_timeline, monkeypatch):
    """Action engine returns SUCCESS -> timeline gets a done web_action row."""
    from app.product import server

    # Short-circuit the direct-browser-action and structured-gmail-draft
    # paths so the test exercises the main DSv4SkillRunner emit point.
    monkeypatch.setattr(
        server, "_try_direct_browser_action",
        lambda *a, **kw: None, raising=False,
    )
    monkeypatch.setattr(
        server, "_try_direct_gmail_draft",
        lambda *a, **kw: None, raising=False,
    )
    monkeypatch.setattr(
        server, "_try_structured_gmail_draft",
        lambda *a, **kw: None, raising=False,
    )
    monkeypatch.setattr(
        server, "_ensure_cdp_chrome", lambda: True, raising=False,
    )
    monkeypatch.setattr(
        server, "_ensure_clean_gmail_compose",
        lambda: True, raising=False,
    )

    # Stub make_real_action_engine to return a fake runner.
    def _fake_engine(cdp_port, max_iters):
        def _runner(_task_dict):
            return {
                "status": "SUCCESS",
                "answer": "ok",
                "evidence": "did it",
                "trajectory_dir": "/tmp/trajectory/abc",
                "error": None,
            }
        return _runner

    fake_module = types.SimpleNamespace(
        make_real_action_engine=_fake_engine,
    )
    monkeypatch.setitem(
        sys.modules, "app.anticipy.action_handoff", fake_module
    )

    plan = {"intent": "browse", "person": "", "thing": "",
            "task": "search openai blog",
            "__sms_confirmed": True}
    resp = server._run_action_engine(
        "search openai blog", plan)
    assert resp.status_code == 200

    rows = _read_lines(tmp_timeline)
    # exactly one web_action row from this dispatcher invocation
    web_rows = [r for r in rows if r["kind"] == "web_action"]
    assert len(web_rows) == 1
    row = web_rows[0]
    assert row["channel"] == "chrome"
    assert row["status"] == "done"
    assert row["summary"] == "search openai blog"
    assert row["payload"]["engine_status"] == "SUCCESS"
    assert row["payload"]["plan"]["intent"] == "browse"


def test_run_action_engine_exception_emits_web_action_failed(
        tmp_timeline, monkeypatch):
    """Action engine raises -> timeline gets a failed web_action row."""
    from app.product import server

    monkeypatch.setattr(
        server, "_try_direct_browser_action",
        lambda *a, **kw: None, raising=False,
    )
    monkeypatch.setattr(
        server, "_try_direct_gmail_draft",
        lambda *a, **kw: None, raising=False,
    )
    monkeypatch.setattr(
        server, "_try_structured_gmail_draft",
        lambda *a, **kw: None, raising=False,
    )
    monkeypatch.setattr(
        server, "_ensure_cdp_chrome", lambda: True, raising=False,
    )
    monkeypatch.setattr(
        server, "_ensure_clean_gmail_compose",
        lambda: True, raising=False,
    )

    def _bad_engine(cdp_port, max_iters):
        def _runner(_task_dict):
            raise RuntimeError("chromium crashed")
        return _runner

    fake_module = types.SimpleNamespace(
        make_real_action_engine=_bad_engine,
    )
    monkeypatch.setitem(
        sys.modules, "app.anticipy.action_handoff", fake_module
    )

    plan = {"intent": "browse", "person": "", "thing": "",
            "task": "open google.com",
            "__sms_confirmed": True}
    resp = server._run_action_engine("open google.com", plan)
    assert resp.status_code == 500

    rows = _read_lines(tmp_timeline)
    web_rows = [r for r in rows if r["kind"] == "web_action"]
    assert len(web_rows) == 1
    assert web_rows[0]["status"] == "failed"
    assert "chromium crashed" in web_rows[0]["payload"]["error"]


# ---------------------------------------------------------------------------
# 4. server.sms_inbound (user reply)
# ---------------------------------------------------------------------------


def test_sms_inbound_emits_user_reply(tmp_timeline, monkeypatch):
    """Inbound SMS webhook always emits a user_reply row even when the
    resolve fails (no pending task)."""
    from app.product import server

    # Force resolve_inbound to return "no pending" so we exercise the
    # path where the timeline emit must still fire BEFORE resolution.
    fake_pre = types.SimpleNamespace(
        resolve_inbound=lambda body, task_id="": {
            "ok": False, "reply_class": "unknown",
            "task_id": "", "previous_status": "",
            "new_status": "", "action_payload": None,
            "error": "no pending task",
        }
    )
    monkeypatch.setitem(
        sys.modules, "app.product.sms_pre_confirm", fake_pre
    )

    # Hit the route via the FastAPI test client so we exercise the full
    # request path including form parsing.
    from fastapi.testclient import TestClient
    client = TestClient(server.app)
    resp = client.post(
        "/api/sms/inbound",
        data={
            "Body": "YES go ahead",
            "From": "+15558675309",
            "MessageSid": "SM_inbound_999",
        },
        headers={"accept": "application/json"},
    )
    assert resp.status_code == 200

    rows = _read_lines(tmp_timeline)
    reply_rows = [r for r in rows if r["kind"] == "user_reply"]
    assert len(reply_rows) == 1
    row = reply_rows[0]
    assert row["channel"] == "twilio_sms"
    assert row["status"] == "done"
    assert row["summary"] == "YES go ahead"
    assert row["payload"]["from"] == "+15558675309"
    assert row["payload"]["message_sid"] == "SM_inbound_999"
    assert row["payload"]["speech"] is False


# ---------------------------------------------------------------------------
# 5. sms_pre_confirm.send_sms_sync (every SMS funnels here)
# ---------------------------------------------------------------------------


def test_send_sms_sync_preconfirm_emits_wait_user(tmp_timeline, monkeypatch):
    """preconfirm-category send waits on user reply -> wait_user row."""
    from app.product import sms_pre_confirm

    # Force the mock path so no real Twilio traffic happens AND ok=True
    # with mock=True is returned so we exercise the success branch.
    monkeypatch.setenv("TWILIO_MOCK", "1")
    monkeypatch.delenv("ANTICIPY_TWILIO_BROKER", raising=False)

    result = sms_pre_confirm.send_sms_sync(
        "+15551112222", "Send the email to alice? Reply YES/NO/EDIT.",
        kind="preconfirm",
    )
    assert result["ok"] is True
    assert result["mock"] is True

    rows = _read_lines(tmp_timeline)
    assert len(rows) == 1
    row = rows[0]
    assert row["kind"] == "sms_sent"
    assert row["channel"] == "twilio_sms"
    assert row["status"] == "wait_user"
    assert row["payload"]["to"] == "+15551112222"
    assert row["payload"]["category"] == "preconfirm"
    assert row["payload"]["mock"] is True


def test_send_sms_sync_receipt_emits_done(tmp_timeline, monkeypatch):
    """receipt-category send is terminal -> done row."""
    from app.product import sms_pre_confirm

    monkeypatch.setenv("TWILIO_MOCK", "1")
    monkeypatch.delenv("ANTICIPY_TWILIO_BROKER", raising=False)

    result = sms_pre_confirm.send_sms_sync(
        "+15551112222", "Sent the email. Open it here: ...",
        kind="receipt",
    )
    assert result["ok"] is True

    rows = _read_lines(tmp_timeline)
    assert len(rows) == 1
    assert rows[0]["status"] == "done"
    assert rows[0]["payload"]["category"] == "receipt"


def test_send_sms_sync_followup_emits_done(tmp_timeline, monkeypatch):
    """followup-category send (from expiry sweeper) is terminal -> done."""
    from app.product import sms_pre_confirm

    monkeypatch.setenv("TWILIO_MOCK", "1")
    monkeypatch.delenv("ANTICIPY_TWILIO_BROKER", raising=False)

    result = sms_pre_confirm.send_sms_sync(
        "+15551112222",
        "No reply, so I saved it as a Gmail draft.",
        kind="followup",
    )
    assert result["ok"] is True

    rows = _read_lines(tmp_timeline)
    assert len(rows) == 1
    assert rows[0]["status"] == "done"
    assert rows[0]["payload"]["category"] == "followup"


def test_send_sms_sync_failure_emits_failed(tmp_timeline, monkeypatch):
    """Missing destination phone returns ok=False -> failed row."""
    from app.product import sms_pre_confirm

    monkeypatch.setenv("TWILIO_MOCK", "1")

    result = sms_pre_confirm.send_sms_sync(
        "", "no recipient", kind="preconfirm")
    assert result["ok"] is False

    rows = _read_lines(tmp_timeline)
    assert len(rows) == 1
    assert rows[0]["status"] == "failed"
    assert rows[0]["payload"]["category"] == "preconfirm"


# ---------------------------------------------------------------------------
# 6. notifier._record_to_feed (LOG / NOTED decisions land as notes)
# ---------------------------------------------------------------------------


def test_notifier_log_decision_emits_note(tmp_timeline):
    """Decision kind=LOG -> timeline gets a note row."""
    from app.proactive.notifier import Notifier
    from app.proactive.types import (
        Confidence, Decision, DecisionKind, Intent, Reversibility, Urgency,
    )

    intent = Intent.new(
        user_id="test-user",
        text="user mumbled something",
        action_verb="note",
    )
    decision = Decision.new(
        intent=intent,
        kind=DecisionKind.LOG,
        confidence=Confidence(score=0.5, reasoning="meh"),
        reversibility=Reversibility.REVERSIBLE,
        urgency=Urgency(level=1, reasoning="no rush"),
    )
    n = Notifier()
    asyncio.run(n.announce(decision))

    rows = _read_lines(tmp_timeline)
    note_rows = [r for r in rows if r["kind"] == "note"]
    assert len(note_rows) == 1
    row = note_rows[0]
    assert row["channel"] == "popover"
    assert row["status"] == "done"
    assert row["summary"] == "user mumbled something"
    assert row["payload"]["intent_id"] == intent.intent_id
    assert row["payload"]["decision_id"] == decision.decision_id
    assert row["payload"]["urgency"] == 1
    assert row["payload"]["kind"] == "log"


def test_notifier_noted_channel_emits_note(tmp_timeline):
    """Decision routed to NOTED channel (urgency=1) emits a note even
    when kind != LOG, because the channel is what determines whether
    it appears in the silent feed."""
    from app.proactive.notifier import Notifier
    from app.proactive.types import (
        Confidence, Decision, DecisionKind, Intent, Reversibility, Urgency,
    )

    intent = Intent.new(
        user_id="test-user",
        text="background fact",
        action_verb="recall",
    )
    decision = Decision.new(
        intent=intent,
        kind=DecisionKind.EXECUTE,
        confidence=Confidence(score=0.9, reasoning="confident"),
        reversibility=Reversibility.REVERSIBLE,
        urgency=Urgency(level=1, reasoning="silent"),
        completion_message="Filed that for later.",
    )
    n = Notifier()
    asyncio.run(n.announce(decision))

    rows = _read_lines(tmp_timeline)
    note_rows = [r for r in rows if r["kind"] == "note"]
    assert len(note_rows) == 1
    assert note_rows[0]["summary"] == "Filed that for later."


def test_notifier_high_urgency_skips_note(tmp_timeline):
    """A decision routed to SMS / VOICE / PUSH / IN_APP does NOT land in
    the note feed (those get their own timeline rows from the delivery
    path)."""
    from app.proactive.notifier import Notifier
    from app.proactive.types import (
        Confidence, Decision, DecisionKind, Intent, Reversibility, Urgency,
    )

    intent = Intent.new(
        user_id="test-user",
        text="urgent question",
        action_verb="ask",
    )
    decision = Decision.new(
        intent=intent,
        kind=DecisionKind.ASK,
        confidence=Confidence(score=0.9, reasoning="urgent"),
        reversibility=Reversibility.IRREVERSIBLE,
        urgency=Urgency(level=5, reasoning="right now"),
        user_facing_question="Should I cancel the meeting?",
    )
    n = Notifier()
    asyncio.run(n.announce(decision))

    rows = _read_lines(tmp_timeline)
    note_rows = [r for r in rows if r["kind"] == "note"]
    assert note_rows == []
