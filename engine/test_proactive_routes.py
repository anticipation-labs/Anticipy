"""Unit tests for app.proactive_routes — the HTTP surface for the cascade."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import auth as auth_module
import app.proactive_routes as pr
from app.proactive.types import (
    Confidence,
    Decision,
    DecisionKind,
    Intent,
    Reversibility,
    Urgency,
)


# ─── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_state():
    """Clean module state before and after every test."""
    pr._reset_user_sessions()
    yield
    pr._reset_user_sessions()


@pytest.fixture
def client():
    # Import here so monkeypatching of pr._make_user_session takes effect
    from app.main import app
    return TestClient(app)


def _auth_headers(user_id: str = "u1", username: str | None = None) -> dict:
    token = auth_module._create_token(user_id, username or user_id)
    return {"Authorization": f"Bearer {token}"}


# ─── Stub session that doesn't use real LLMs or browsers ────────────────


class _StubEngine:
    """Replaces ProactiveEngine for tests."""

    def __init__(self) -> None:
        self.chunks_received: list = []
        self.confirmations_received: list = []
        self.flush_count = 0
        self._pending_dispatches: list = []
        self.next_decisions: list[Decision] = []

    async def on_transcript_chunk(self, chunk):
        self.chunks_received.append(chunk)
        ds = self.next_decisions
        self.next_decisions = []
        return ds

    async def on_confirmation(self, decision_id: str, response: str) -> None:
        self.confirmations_received.append((decision_id, response))

    async def flush_pending(self):
        self.flush_count += 1
        ds = self.next_decisions
        self.next_decisions = []
        return ds


class _NoOpMemoryExtractor:
    async def extract_and_write(self, user_id, chunk_text, chunk_id=0):
        return []


class _StubSession:
    EVENT_CAP = 200

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.events: list[dict] = []
        self._seq = 0
        self.lock = asyncio.Lock()
        self.engine = _StubEngine()
        self.memory_extractor = _NoOpMemoryExtractor()

    async def _on_wearer_message(self, message: dict) -> None:
        self._seq += 1
        self.events.append({"seq": self._seq, "kind": "agent", **message})

    def append_decision_event(self, decision: Decision) -> int:
        self._seq += 1
        self.events.append({
            "seq": self._seq,
            "kind": "decision",
            "decision": pr._decision_to_dict(decision),
        })
        return self._seq

    def events_after(self, seq: int) -> list[dict]:
        return [e for e in self.events if e.get("seq", 0) > seq]


@pytest.fixture
def stub_sessions(monkeypatch):
    sessions: dict[str, _StubSession] = {}

    def factory(user_id: str) -> _StubSession:
        if user_id not in sessions:
            sessions[user_id] = _StubSession(user_id)
        return sessions[user_id]

    monkeypatch.setattr(pr, "_make_user_session", factory)
    return sessions


def _decision(
    kind: DecisionKind = DecisionKind.EXECUTE,
    intent_text: str = "Order paper towels",
    user_facing_question: str | None = None,
) -> Decision:
    intent = Intent.new(user_id="u1", text=intent_text, action_verb="order")
    return Decision.new(
        intent=intent,
        kind=kind,
        confidence=Confidence(score=0.9),
        reversibility=Reversibility.REVERSIBLE,
        urgency=Urgency(level=2),
        user_facing_question=user_facing_question,
        completion_message="Done.",
    )


# ─── Auth tests ─────────────────────────────────────────────────────────


def test_chunk_rejects_missing_auth(client):
    r = client.post("/proactive/chunk", json={"text": "hello"})
    assert r.status_code == 401


def test_chunk_rejects_malformed_auth(client):
    r = client.post(
        "/proactive/chunk",
        json={"text": "hello"},
        headers={"Authorization": "garbage"},
    )
    assert r.status_code == 401


def test_chunk_rejects_invalid_token(client):
    r = client.post(
        "/proactive/chunk",
        json={"text": "hello"},
        headers={"Authorization": "Bearer notavalidjwt"},
    )
    assert r.status_code == 401


def test_chunk_rejects_empty_text(client, stub_sessions):
    r = client.post(
        "/proactive/chunk",
        json={"text": "   "},
        headers=_auth_headers("u1"),
    )
    assert r.status_code == 400


def test_chunk_rejects_too_long_text(client, stub_sessions):
    r = client.post(
        "/proactive/chunk",
        json={"text": "x" * 10_000},
        headers=_auth_headers("u1"),
    )
    assert r.status_code == 400


# ─── /proactive/chunk happy path ────────────────────────────────────────


def test_chunk_creates_session_and_feeds_engine(client, stub_sessions):
    r = client.post(
        "/proactive/chunk",
        json={"session_id": "s1", "text": "let's get dinner Friday"},
        headers=_auth_headers("u1"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "decisions" in body
    assert "pending_count" in body
    assert "sequence_max" in body
    # Stub engine received the chunk
    assert "u1" in stub_sessions
    assert len(stub_sessions["u1"].engine.chunks_received) == 1
    chunk = stub_sessions["u1"].engine.chunks_received[0]
    assert chunk.text == "let's get dinner Friday"
    assert chunk.session_id == "s1"
    assert chunk.user_id == "u1"


def test_chunk_returns_decisions_engine_dispatched(client, stub_sessions):
    # Pre-load the stub to return one decision
    user_id = "u1"
    # We need to create the session first by calling the route once with a no-decision setup
    # ... or seed before first call:
    # Trick: warm up the session, then load the stub
    client.post(
        "/proactive/chunk",
        json={"text": "warmup"},
        headers=_auth_headers(user_id),
    )
    stub_sessions[user_id].engine.next_decisions = [_decision()]

    r = client.post(
        "/proactive/chunk",
        json={"text": "do the thing"},
        headers=_auth_headers(user_id),
    )
    body = r.json()
    assert len(body["decisions"]) == 1
    assert body["decisions"][0]["intent"]["text"] == "Order paper towels"
    assert body["decisions"][0]["kind"] == "execute"
    assert body["sequence_max"] >= 1


def test_chunk_records_decision_event_in_buffer(client, stub_sessions):
    user_id = "u1"
    client.post(
        "/proactive/chunk",
        json={"text": "warmup"},
        headers=_auth_headers(user_id),
    )
    stub_sessions[user_id].engine.next_decisions = [_decision()]
    client.post(
        "/proactive/chunk",
        json={"text": "do it"},
        headers=_auth_headers(user_id),
    )

    events = stub_sessions[user_id].events
    decision_events = [e for e in events if e.get("kind") == "decision"]
    assert len(decision_events) == 1


def test_chunk_user_isolation(client, stub_sessions):
    """A chunk sent by u1 must not appear in u2's session."""
    client.post(
        "/proactive/chunk",
        json={"text": "u1 said this"},
        headers=_auth_headers("u1"),
    )
    client.post(
        "/proactive/chunk",
        json={"text": "u2 said that"},
        headers=_auth_headers("u2"),
    )
    assert stub_sessions["u1"].engine.chunks_received[0].text == "u1 said this"
    assert stub_sessions["u2"].engine.chunks_received[0].text == "u2 said that"
    assert len(stub_sessions["u1"].engine.chunks_received) == 1
    assert len(stub_sessions["u2"].engine.chunks_received) == 1


def test_chunk_clamps_confidence(client, stub_sessions):
    client.post(
        "/proactive/chunk",
        json={"text": "x", "confidence": 5.0},
        headers=_auth_headers("u1"),
    )
    chunk = stub_sessions["u1"].engine.chunks_received[0]
    assert chunk.confidence == 1.0

    client.post(
        "/proactive/chunk",
        json={"text": "y", "confidence": -1.0},
        headers=_auth_headers("u1"),
    )
    chunk = stub_sessions["u1"].engine.chunks_received[1]
    assert chunk.confidence == 0.0


def test_chunk_handles_engine_exception(client, stub_sessions, monkeypatch):
    """An engine failure surfaces as 500, not a crash."""
    # Warm up so a session exists
    client.post("/proactive/chunk", json={"text": "x"}, headers=_auth_headers("u1"))

    async def boom(chunk):
        raise RuntimeError("engine exploded")

    stub_sessions["u1"].engine.on_transcript_chunk = boom

    r = client.post(
        "/proactive/chunk",
        json={"text": "y"},
        headers=_auth_headers("u1"),
    )
    assert r.status_code == 500


# ─── /proactive/confirm ─────────────────────────────────────────────────


def test_confirm_forwards_to_engine(client, stub_sessions):
    # Establish session
    client.post("/proactive/chunk", json={"text": "x"}, headers=_auth_headers("u1"))

    r = client.post(
        "/proactive/confirm",
        json={"decision_id": "abc-123", "response": "yes"},
        headers=_auth_headers("u1"),
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert stub_sessions["u1"].engine.confirmations_received == [("abc-123", "yes")]


def test_confirm_normalizes_response_case(client, stub_sessions):
    client.post("/proactive/chunk", json={"text": "x"}, headers=_auth_headers("u1"))
    r = client.post(
        "/proactive/confirm",
        json={"decision_id": "x", "response": "  YES  "},
        headers=_auth_headers("u1"),
    )
    assert r.status_code == 200
    assert stub_sessions["u1"].engine.confirmations_received[0][1] == "yes"


def test_confirm_rejects_invalid_response(client, stub_sessions):
    client.post("/proactive/chunk", json={"text": "x"}, headers=_auth_headers("u1"))
    r = client.post(
        "/proactive/confirm",
        json={"decision_id": "x", "response": "maybe"},
        headers=_auth_headers("u1"),
    )
    assert r.status_code == 400


def test_confirm_rejects_empty_decision_id(client, stub_sessions):
    client.post("/proactive/chunk", json={"text": "x"}, headers=_auth_headers("u1"))
    r = client.post(
        "/proactive/confirm",
        json={"decision_id": "  ", "response": "yes"},
        headers=_auth_headers("u1"),
    )
    assert r.status_code == 400


def test_confirm_rejects_unknown_user(client, stub_sessions):
    """No session ever existed for this user."""
    r = client.post(
        "/proactive/confirm",
        json={"decision_id": "x", "response": "yes"},
        headers=_auth_headers("never_seen_user"),
    )
    assert r.status_code == 404


def test_confirm_requires_auth(client):
    r = client.post("/proactive/confirm", json={"decision_id": "x", "response": "yes"})
    assert r.status_code == 401


# ─── /proactive/flush ───────────────────────────────────────────────────


def test_flush_returns_empty_for_unknown_user(client, stub_sessions):
    r = client.post("/proactive/flush", headers=_auth_headers("nobody"))
    assert r.status_code == 200
    assert r.json() == {"decisions": [], "sequence_max": 0}


def test_flush_calls_engine_flush(client, stub_sessions):
    client.post("/proactive/chunk", json={"text": "x"}, headers=_auth_headers("u1"))
    stub_sessions["u1"].engine.next_decisions = [_decision()]

    r = client.post("/proactive/flush", headers=_auth_headers("u1"))
    assert r.status_code == 200
    body = r.json()
    assert len(body["decisions"]) == 1
    assert stub_sessions["u1"].engine.flush_count == 1


def test_flush_requires_auth(client):
    r = client.post("/proactive/flush")
    assert r.status_code == 401


# ─── /proactive/events ──────────────────────────────────────────────────


def test_events_returns_empty_for_unknown_user(client, stub_sessions):
    r = client.get("/proactive/events", headers=_auth_headers("nobody"))
    assert r.status_code == 200
    assert r.json() == {"events": [], "sequence_max": 0}


def test_events_drains_decisions_and_agent_messages(client, stub_sessions):
    user_id = "u1"
    client.post(
        "/proactive/chunk",
        json={"text": "warmup"},
        headers=_auth_headers(user_id),
    )
    stub_sessions[user_id].engine.next_decisions = [_decision()]
    client.post("/proactive/chunk", json={"text": "do it"}, headers=_auth_headers(user_id))

    # Inject a fake wearer-agent message
    asyncio.run(stub_sessions[user_id]._on_wearer_message({"type": "status", "message": "Working..."}))

    r = client.get("/proactive/events", headers=_auth_headers(user_id))
    body = r.json()
    assert body["sequence_max"] >= 2
    kinds = [e["kind"] for e in body["events"]]
    assert "decision" in kinds
    assert "agent" in kinds


def test_events_respects_after_seq(client, stub_sessions):
    user_id = "u1"
    client.post("/proactive/chunk", json={"text": "x"}, headers=_auth_headers(user_id))

    asyncio.run(stub_sessions[user_id]._on_wearer_message({"type": "status", "message": "1"}))
    asyncio.run(stub_sessions[user_id]._on_wearer_message({"type": "status", "message": "2"}))
    asyncio.run(stub_sessions[user_id]._on_wearer_message({"type": "status", "message": "3"}))

    r = client.get("/proactive/events?after_seq=2", headers=_auth_headers(user_id))
    body = r.json()
    seqs = [e["seq"] for e in body["events"]]
    assert all(s > 2 for s in seqs)
    # Sanity: at least one event was emitted past seq 2
    assert len(seqs) >= 1


# ─── _decision_to_dict round-trip ───────────────────────────────────────


def test_decision_to_dict_serializes_all_fields():
    d = _decision(kind=DecisionKind.ASK, user_facing_question="OK?")
    serialized = pr._decision_to_dict(d)
    assert serialized["kind"] == "ask"
    assert serialized["user_facing_question"] == "OK?"
    assert serialized["intent"]["action_verb"] == "order"
    assert "confidence" in serialized
    assert "score" in serialized["confidence"]
    assert "reversibility" in serialized
    assert serialized["reversibility"] == "reversible"
    assert serialized["urgency"]["level"] == 2
