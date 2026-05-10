"""Unit tests for app.bridge_extension — drive Decisions through the
Chrome extension via Supabase Realtime, never spawn a separate browser."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

import app.bridge_extension as be
from app.bridge_extension import (
    RealtimePublishExecutor,
    broadcast_to_realtime,
    decision_to_intent_row,
)
from app.proactive.types import (
    Confidence,
    Decision,
    DecisionKind,
    Intent,
    Reversibility,
    Urgency,
)
from app.verifier import Verdict


def _decision(
    kind: DecisionKind = DecisionKind.EXECUTE,
    intent_text: str = "Order paper towels",
    action_verb: str = "order_supplies",
    parameters: dict | None = None,
    confidence_score: float = 0.9,
    urgency_level: int = 2,
) -> Decision:
    intent = Intent.new(
        user_id="u1",
        text=intent_text,
        action_verb=action_verb,
        parameters=parameters or {"brand": "Bounty"},
    )
    return Decision.new(
        intent=intent,
        kind=kind,
        confidence=Confidence(score=confidence_score),
        reversibility=Reversibility.REVERSIBLE,
        urgency=Urgency(level=urgency_level),
        completion_message="Done.",
    )


# ─── decision_to_intent_row ─────────────────────────────────────────────


def test_decision_to_intent_row_maps_basic_fields():
    d = _decision()
    row = decision_to_intent_row(d, user_id="omar")
    assert row["id"] == d.decision_id
    assert row["user_id"] == "omar"
    assert row["action_type"] == "order_supplies"
    assert row["summary_for_user"] == "Order paper towels"
    assert row["status"] == "confirmed"
    assert row["importance"] == "standard"  # urgency level 2
    assert row["parameters"] == {"brand": "Bounty"}
    assert "created_at" in row
    assert row["created_at"].endswith("Z")


def test_decision_to_intent_row_critical_importance():
    d = _decision(urgency_level=5)
    row = decision_to_intent_row(d, "u")
    assert row["importance"] == "critical"


def test_decision_to_intent_row_important():
    d = _decision(urgency_level=3)
    row = decision_to_intent_row(d, "u")
    assert row["importance"] == "important"


def test_decision_to_intent_row_low_urgency():
    d = _decision(urgency_level=1)
    row = decision_to_intent_row(d, "u")
    assert row["importance"] == "low"


def test_decision_to_intent_row_ask_kind_status_pending():
    d = _decision(kind=DecisionKind.ASK)
    row = decision_to_intent_row(d, "u")
    assert row["status"] == "pending"


def test_decision_to_intent_row_handles_empty_action_verb():
    intent = Intent.new(user_id="u", text="x", action_verb="")
    d = Decision.new(
        intent=intent, kind=DecisionKind.EXECUTE,
        confidence=Confidence(score=0.9),
        reversibility=Reversibility.REVERSIBLE,
        urgency=Urgency(level=2),
    )
    row = decision_to_intent_row(d, "u")
    assert row["action_type"] == "general_action"


# ─── broadcast_to_realtime ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_broadcast_returns_true_on_2xx(monkeypatch):
    captured = {}

    class _Resp:
        def __init__(self, status):
            self.status_code = status
            self.text = "ok"

    class _Client:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["body"] = json
            return _Resp(204)

    monkeypatch.setattr(be.httpx, "AsyncClient", _Client)
    ok = await broadcast_to_realtime("topic-x", "event-y", {"hello": "world"})
    assert ok is True
    assert "/realtime/v1/api/broadcast" in captured["url"]
    assert captured["body"]["messages"][0]["topic"] == "topic-x"
    assert captured["body"]["messages"][0]["event"] == "event-y"
    assert captured["body"]["messages"][0]["payload"] == {"hello": "world"}


@pytest.mark.asyncio
async def test_broadcast_returns_false_on_non_2xx(monkeypatch):
    class _Resp:
        status_code = 500
        text = "internal error"

    class _Client:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, *a, **kw): return _Resp()

    monkeypatch.setattr(be.httpx, "AsyncClient", _Client)
    ok = await broadcast_to_realtime("t", "e", {})
    assert ok is False


@pytest.mark.asyncio
async def test_broadcast_returns_false_on_exception(monkeypatch):
    class _Client:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, *a, **kw): raise RuntimeError("network down")

    monkeypatch.setattr(be.httpx, "AsyncClient", _Client)
    ok = await broadcast_to_realtime("t", "e", {})
    assert ok is False


@pytest.mark.asyncio
async def test_broadcast_returns_false_when_supabase_url_unset(monkeypatch):
    monkeypatch.setattr(be, "SUPABASE_URL", "")
    ok = await broadcast_to_realtime("t", "e", {})
    assert ok is False


# ─── RealtimePublishExecutor.execute ────────────────────────────────────


@pytest.fixture
def patched_supabase(monkeypatch):
    """Replaces the supabase / broadcast surface with controllable stubs.
    Returns a state dict tests can read/write to direct behavior."""
    state = {
        "upserts": [],
        "broadcasts": [],
        "rows_to_return": [],   # list of row dicts to return on each select_rows call
        "select_calls": 0,
        "broadcast_returns": True,
    }

    async def fake_upsert(table, data):
        state["upserts"].append((table, data))
        return data

    async def fake_select(table, filters=None, columns="*", limit=100):
        state["select_calls"] += 1
        if state["rows_to_return"]:
            return state["rows_to_return"].pop(0)
        return []

    async def fake_broadcast(topic, event, payload, *, timeout=10.0):
        state["broadcasts"].append((topic, event, payload))
        return state["broadcast_returns"]

    monkeypatch.setattr(be.supabase_client, "upsert_row", fake_upsert)
    monkeypatch.setattr(be.supabase_client, "select_rows", fake_select)
    monkeypatch.setattr(be, "broadcast_to_realtime", fake_broadcast)
    return state


@pytest.mark.asyncio
async def test_executor_refuses_non_execute(patched_supabase):
    ex = RealtimePublishExecutor(user_id="u1", verifier=None)
    ev = await ex.execute(_decision(kind=DecisionKind.LOG))
    assert ev.stage == "error"
    assert patched_supabase["broadcasts"] == []


@pytest.mark.asyncio
async def test_executor_inserts_and_broadcasts(patched_supabase):
    # Extension says executed on first poll
    patched_supabase["rows_to_return"] = [
        [{"id": "x", "status": "executed", "execution_result": "Order placed. Confirmation #ABC."}]
    ]
    ex = RealtimePublishExecutor(
        user_id="omar",
        verifier=None,
        poll_timeout_s=2.0,
        poll_interval_s=0.05,
    )
    d = _decision()
    ev = await ex.execute(d)

    assert ev.stage == "completed"
    assert "Confirmation #ABC" in ev.message
    assert len(patched_supabase["upserts"]) == 1
    assert patched_supabase["upserts"][0][0] == "anticipy_intents"
    assert patched_supabase["upserts"][0][1]["user_id"] == "omar"
    assert len(patched_supabase["broadcasts"]) == 1
    topic, event, payload = patched_supabase["broadcasts"][0]
    assert topic == "anticipy-intents"
    assert event == "confirmed_intent"
    assert payload["user_id"] == "omar"
    assert payload["intent"]["id"] == d.decision_id


@pytest.mark.asyncio
async def test_executor_surfaces_extension_failure(patched_supabase):
    patched_supabase["rows_to_return"] = [
        [{"id": "x", "status": "failed", "execution_result": "Couldn't find the booking page."}]
    ]
    ex = RealtimePublishExecutor(
        user_id="omar", verifier=None,
        poll_timeout_s=2.0, poll_interval_s=0.05,
    )
    ev = await ex.execute(_decision())
    assert ev.stage == "error"
    assert "Couldn't" in ev.message or "couldn't" in ev.message.lower()


@pytest.mark.asyncio
async def test_executor_polls_until_timeout(patched_supabase):
    # Always return status=confirmed, never moves to executed/failed
    async def always_confirmed(table, filters=None, columns="*", limit=100):
        return [{"id": filters["id"], "status": "confirmed"}]
    import app.bridge_extension as be_mod
    be_mod.supabase_client.select_rows = always_confirmed  # type: ignore

    ex = RealtimePublishExecutor(
        user_id="omar", verifier=None,
        poll_timeout_s=0.4, poll_interval_s=0.05,
    )
    ev = await ex.execute(_decision())
    assert ev.stage == "error"
    assert (
        "didn't get back" in ev.message.lower()
        or "try again" in ev.message.lower()
    )


@pytest.mark.asyncio
async def test_executor_errors_when_broadcast_fails(patched_supabase):
    patched_supabase["broadcast_returns"] = False
    ex = RealtimePublishExecutor(
        user_id="omar", verifier=None,
        poll_timeout_s=0.5, poll_interval_s=0.05,
    )
    ev = await ex.execute(_decision())
    assert ev.stage == "error"
    assert "browser" in ev.message.lower() or "extension" in ev.message.lower()
    # Should NOT have polled if broadcast failed
    assert patched_supabase["select_calls"] == 0


@pytest.mark.asyncio
async def test_executor_runs_verifier_on_executed(patched_supabase):
    patched_supabase["rows_to_return"] = [
        [{"id": "x", "status": "executed", "execution_result": "I clicked some stuff."}]
    ]

    class _PassingVerifier:
        async def verify(self, goal, final_state=None, history_summary=""):
            return Verdict(passed=True, evidence="ok", confidence=0.9)

    ex = RealtimePublishExecutor(
        user_id="omar", verifier=_PassingVerifier(),
        poll_timeout_s=2.0, poll_interval_s=0.05,
    )
    ev = await ex.execute(_decision())
    assert ev.stage == "completed"


@pytest.mark.asyncio
async def test_verifier_overrides_extension_self_report_on_fail(patched_supabase):
    patched_supabase["rows_to_return"] = [
        [{"id": "x", "status": "executed", "execution_result": "I clicked some stuff."}]
    ]

    class _FailingVerifier:
        async def verify(self, goal, final_state=None, history_summary=""):
            return Verdict(passed=False, honest_message_for_wearer="Can't see the confirmation.")

    ex = RealtimePublishExecutor(
        user_id="omar", verifier=_FailingVerifier(),
        poll_timeout_s=2.0, poll_interval_s=0.05,
    )
    ev = await ex.execute(_decision())
    assert ev.stage == "error"
    assert "Can't see" in ev.message or "can't see" in ev.message.lower()


@pytest.mark.asyncio
async def test_verifier_raise_fails_closed(patched_supabase):
    patched_supabase["rows_to_return"] = [
        [{"id": "x", "status": "executed", "execution_result": "ok"}]
    ]

    class _RaisingVerifier:
        async def verify(self, goal, final_state=None, history_summary=""):
            raise RuntimeError("verifier broken")

    ex = RealtimePublishExecutor(
        user_id="omar", verifier=_RaisingVerifier(),
        poll_timeout_s=2.0, poll_interval_s=0.05,
    )
    ev = await ex.execute(_decision())
    assert ev.stage == "error"


# ─── on_wearer_message integration ──────────────────────────────────────


@pytest.mark.asyncio
async def test_on_wearer_message_called_on_send_and_during_poll(patched_supabase):
    received = []

    async def cb(m):
        received.append(m)

    # First poll: still confirmed; second: executed
    patched_supabase["rows_to_return"] = [
        [{"id": "x", "status": "confirmed"}],
        [{"id": "x", "status": "executed", "execution_result": "Done."}],
    ]
    ex = RealtimePublishExecutor(
        user_id="omar", verifier=None,
        on_wearer_message=cb,
        poll_timeout_s=2.0, poll_interval_s=0.05,
    )
    await ex.execute(_decision())
    types = [m.get("type") for m in received]
    assert "status" in types  # at least the "Sent to your browser" status


@pytest.mark.asyncio
async def test_on_wearer_message_failure_does_not_abort(patched_supabase):
    patched_supabase["rows_to_return"] = [
        [{"id": "x", "status": "executed", "execution_result": "ok"}]
    ]

    async def angry(m):
        raise RuntimeError("ui crashed")

    ex = RealtimePublishExecutor(
        user_id="omar", verifier=None,
        on_wearer_message=angry,
        poll_timeout_s=2.0, poll_interval_s=0.05,
    )
    ev = await ex.execute(_decision())
    assert ev.stage == "completed"
