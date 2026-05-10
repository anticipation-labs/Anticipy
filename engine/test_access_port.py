"""Unit tests for engine/access_port.py — the wearer-side Python client."""

from __future__ import annotations

import asyncio

import httpx
import pytest
import pytest_asyncio

import app.proactive_routes as pr
from access_port import AccessPort, AccessPortError, TranscriptUtterance
from app import auth as auth_module
from app.proactive.types import (
    Confidence,
    Decision,
    DecisionKind,
    Intent,
    Reversibility,
    Urgency,
)


# ─── Stub session reused from test_proactive_routes ─────────────────────


class _StubEngine:
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

    async def on_confirmation(self, decision_id, response):
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

    async def _on_wearer_message(self, message):
        self._seq += 1
        self.events.append({"seq": self._seq, "kind": "agent", **message})

    def append_decision_event(self, decision):
        self._seq += 1
        self.events.append({
            "seq": self._seq,
            "kind": "decision",
            "decision": pr._decision_to_dict(decision),
        })
        return self._seq

    def events_after(self, seq):
        return [e for e in self.events if e.get("seq", 0) > seq]


def _decision(kind=DecisionKind.EXECUTE, intent_text="Order paper towels"):
    intent = Intent.new(user_id="u1", text=intent_text, action_verb="order")
    return Decision.new(
        intent=intent, kind=kind,
        confidence=Confidence(score=0.9),
        reversibility=Reversibility.REVERSIBLE,
        urgency=Urgency(level=2),
        completion_message="Done.",
    )


@pytest.fixture(autouse=True)
def _reset_state():
    pr._reset_user_sessions()
    yield
    pr._reset_user_sessions()


@pytest.fixture
def stub_sessions(monkeypatch):
    sessions: dict[str, _StubSession] = {}

    def factory(user_id: str) -> _StubSession:
        if user_id not in sessions:
            sessions[user_id] = _StubSession(user_id)
        return sessions[user_id]

    monkeypatch.setattr(pr, "_make_user_session", factory)
    return sessions


@pytest_asyncio.fixture
async def app_client():
    """An httpx.AsyncClient mounted on the ASGI app for in-process testing."""
    from app.main import app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _token(user_id: str = "u1", username: str | None = None) -> str:
    return auth_module._create_token(user_id, username or user_id)


# ─── AccessPort construction ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_access_port_unauthenticated_initially():
    ap = AccessPort(base_url="http://test", client=httpx.AsyncClient())
    try:
        assert not ap.authenticated
        assert ap.user_id is None
    finally:
        await ap._client.aclose()


@pytest.mark.asyncio
async def test_access_port_set_token():
    ap = AccessPort(base_url="http://test", client=httpx.AsyncClient())
    try:
        ap.set_token("tok", user_id="u1", username="u1")
        assert ap.authenticated
        assert ap.user_id == "u1"
        assert ap.username == "u1"
    finally:
        await ap._client.aclose()


@pytest.mark.asyncio
async def test_send_chunk_requires_auth(app_client):
    ap = AccessPort(base_url="http://test", client=app_client)
    with pytest.raises(RuntimeError, match="not authenticated"):
        await ap.send_chunk("hello")


@pytest.mark.asyncio
async def test_send_chunk_succeeds(app_client, stub_sessions):
    ap = AccessPort(base_url="http://test", client=app_client)
    ap.set_token(_token("u1"), user_id="u1", username="u1")

    resp = await ap.send_chunk("Let's get dinner Friday")
    assert "decisions" in resp
    assert "pending_count" in resp
    assert "sequence_max" in resp
    chunks = stub_sessions["u1"].engine.chunks_received
    assert len(chunks) == 1
    assert chunks[0].text == "Let's get dinner Friday"


@pytest.mark.asyncio
async def test_send_chunk_with_full_metadata(app_client, stub_sessions):
    ap = AccessPort(base_url="http://test", client=app_client)
    ap.set_token(_token("u1"), user_id="u1", username="u1")

    await ap.send_chunk(
        "background tv noise — yeah do it",
        session_id="convo-2",
        chunk_id=42,
        start_ts=1000.0,
        end_ts=1003.5,
        confidence=0.7,
        is_self_talk=False,
        diarization_hint="wearer",
    )
    chunk = stub_sessions["u1"].engine.chunks_received[0]
    assert chunk.session_id == "convo-2"
    assert chunk.chunk_id == 42
    assert chunk.start_ts == 1000.0
    assert chunk.end_ts == 1003.5
    assert chunk.confidence == 0.7
    assert chunk.diarization_hint == "wearer"


# ─── confirm / flush / events ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_confirm_forwards_to_engine(app_client, stub_sessions):
    ap = AccessPort(base_url="http://test", client=app_client)
    ap.set_token(_token("u1"), user_id="u1", username="u1")

    await ap.send_chunk("warmup")
    resp = await ap.confirm("decision-abc", "yes")
    assert resp == {"ok": True}
    assert stub_sessions["u1"].engine.confirmations_received == [("decision-abc", "yes")]


@pytest.mark.asyncio
async def test_confirm_rejects_invalid_response(app_client, stub_sessions):
    ap = AccessPort(base_url="http://test", client=app_client)
    ap.set_token(_token("u1"), user_id="u1", username="u1")
    await ap.send_chunk("warmup")
    with pytest.raises(AccessPortError) as excinfo:
        await ap.confirm("d1", "maybe")
    assert excinfo.value.status == 400


@pytest.mark.asyncio
async def test_flush_calls_engine(app_client, stub_sessions):
    ap = AccessPort(base_url="http://test", client=app_client)
    ap.set_token(_token("u1"), user_id="u1", username="u1")
    await ap.send_chunk("warmup")
    stub_sessions["u1"].engine.next_decisions = [_decision()]
    resp = await ap.flush()
    assert "decisions" in resp
    assert len(resp["decisions"]) == 1
    assert stub_sessions["u1"].engine.flush_count == 1


@pytest.mark.asyncio
async def test_get_events_returns_decision_and_agent_events(app_client, stub_sessions):
    ap = AccessPort(base_url="http://test", client=app_client)
    ap.set_token(_token("u1"), user_id="u1", username="u1")

    await ap.send_chunk("warmup")
    stub_sessions["u1"].engine.next_decisions = [_decision()]
    await ap.send_chunk("do it")
    await stub_sessions["u1"]._on_wearer_message({"type": "status", "message": "Working..."})

    events = await ap.get_events()
    kinds = [e["kind"] for e in events["events"]]
    assert "decision" in kinds
    assert "agent" in kinds


# ─── drive_transcript ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_drive_transcript_sends_each_line(app_client, stub_sessions):
    ap = AccessPort(base_url="http://test", client=app_client)
    ap.set_token(_token("u1"), user_id="u1", username="u1")

    result = await ap.drive_transcript(
        ["line one", "line two", "line three"],
        session_id="conv-x",
    )
    chunks = stub_sessions["u1"].engine.chunks_received
    assert [c.text for c in chunks] == ["line one", "line two", "line three"]
    assert all(c.session_id == "conv-x" for c in chunks)
    # All chunks have monotonic ids 1..3
    assert [c.chunk_id for c in chunks] == [1, 2, 3]
    # Flush was called
    assert stub_sessions["u1"].engine.flush_count == 1
    assert "decisions" in result
    assert "events" in result


@pytest.mark.asyncio
async def test_drive_transcript_with_explicit_utterances(app_client, stub_sessions):
    ap = AccessPort(base_url="http://test", client=app_client)
    ap.set_token(_token("u1"), user_id="u1", username="u1")

    await ap.drive_transcript([
        TranscriptUtterance(text="hi", chunk_id=10, confidence=0.5, diarization_hint="wearer"),
        TranscriptUtterance(text="bye", chunk_id=20, is_self_talk=True),
    ])
    chunks = stub_sessions["u1"].engine.chunks_received
    assert chunks[0].chunk_id == 10
    assert chunks[0].confidence == 0.5
    assert chunks[0].diarization_hint == "wearer"
    assert chunks[1].chunk_id == 20
    assert chunks[1].is_self_talk is True


@pytest.mark.asyncio
async def test_drive_transcript_no_flush_skips_flush(app_client, stub_sessions):
    ap = AccessPort(base_url="http://test", client=app_client)
    ap.set_token(_token("u1"), user_id="u1", username="u1")

    await ap.drive_transcript(["a"], flush_at_end=False)
    assert stub_sessions["u1"].engine.flush_count == 0


@pytest.mark.asyncio
async def test_drive_transcript_aggregates_decisions(app_client, stub_sessions):
    ap = AccessPort(base_url="http://test", client=app_client)
    ap.set_token(_token("u1"), user_id="u1", username="u1")
    # Warm session
    await ap.send_chunk("warmup")
    stub_sessions["u1"].engine.next_decisions = [_decision(intent_text="from chunk 1")]

    result = await ap.drive_transcript(
        ["x"],
        flush_at_end=False,
    )
    decision_texts = [d["intent"]["text"] for d in result["decisions"]]
    assert "from chunk 1" in decision_texts


# ─── wait_for_event ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_wait_for_event_returns_matching_event(app_client, stub_sessions):
    ap = AccessPort(base_url="http://test", client=app_client)
    ap.set_token(_token("u1"), user_id="u1", username="u1")

    await ap.send_chunk("warmup")
    # Inject an event
    await stub_sessions["u1"]._on_wearer_message({"type": "complete", "message": "All done."})

    found = await ap.wait_for_event(
        lambda e: e.get("kind") == "agent" and e.get("type") == "complete",
        timeout=2.0,
        poll_interval=0.05,
    )
    assert found is not None
    assert found["message"] == "All done."


@pytest.mark.asyncio
async def test_wait_for_event_returns_none_on_timeout(app_client, stub_sessions):
    ap = AccessPort(base_url="http://test", client=app_client)
    ap.set_token(_token("u1"), user_id="u1", username="u1")
    await ap.send_chunk("warmup")

    found = await ap.wait_for_event(
        lambda e: False,  # never match
        timeout=0.3,
        poll_interval=0.05,
    )
    assert found is None


# ─── Error path: engine 500 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_chunk_raises_on_500(app_client, stub_sessions, monkeypatch):
    ap = AccessPort(base_url="http://test", client=app_client)
    ap.set_token(_token("u1"), user_id="u1", username="u1")
    await ap.send_chunk("warmup")  # session created

    async def boom(chunk):
        raise RuntimeError("engine crashed")

    stub_sessions["u1"].engine.on_transcript_chunk = boom

    with pytest.raises(AccessPortError) as excinfo:
        await ap.send_chunk("trigger")
    assert excinfo.value.status == 500


@pytest.mark.asyncio
async def test_login_records_token_on_success(app_client, monkeypatch):
    """When the engine returns success+token, AccessPort caches it."""
    async def fake_login(req, request):
        from app.main import AuthResponse
        return AuthResponse(success=True, token=_token("u9", "u9"), user_id="u9", message="ok")
    # Monkeypatch the route handler is hard via TestClient; instead, exercise the
    # actual login route logic by setting up auth_module bypass:
    async def ok(*args, **kwargs):
        return {"success": True, "token": _token("u9", "u9"), "user_id": "u9"}
    monkeypatch.setattr("app.auth.login", ok)

    ap = AccessPort(base_url="http://test", client=app_client)
    data = await ap.login("u9", "averylongpassword12345")
    assert data["success"]
    assert ap.authenticated
    assert ap.user_id == "u9"
    assert ap.username == "u9"
