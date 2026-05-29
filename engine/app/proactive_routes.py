"""
HTTP routes that drive the proactive cascade end-to-end.

These are the access surface a wearer-side client (Chrome extension, phone
app, or the Python `access_port.py` test harness) uses to:

  1. Stream transcript chunks into the cascade (POST /proactive/chunk).
  2. Reply yes/no to ASK decisions (POST /proactive/confirm).
  3. Flush pending decisions at end-of-session (POST /proactive/flush).
  4. Drain the per-user event stream (GET /proactive/events).

The cascade itself runs server-side in `engine/app/proactive/engine.py`.
EXECUTE decisions are dispatched through `BrowserAgentExecutor` (in
`engine/app/bridge.py`), which calls the browser agent and end-state verifier.

Design choices:

- Per-user state. A `UserSession` holds one `ProactiveEngine` and one event
  buffer. Conversation context survives across requests so the cascade's
  multi-turn buildup (consolidate, revalidate, dedup) actually works.
- Event buffer bounded to 200 entries. Events are tagged with monotonic
  sequence numbers so a client can long-poll incrementally without
  duplication.
- The factory `_make_user_session` is a module-level hook so tests can
  inject a stub engine without touching real LLMs or browsers.
- Auth: every route requires a Bearer JWT. user_id is taken from the
  token, never the body — defense against id-spoofing.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

import os

from app import auth as auth_module
from app import messages as msg
from app.bridge_extension import RealtimePublishExecutor
from app.memory import make_memory_store
from app.proactive.engine import ProactiveEngine
from app.proactive.llm_adapter import make_json_llm_call
from app.proactive.memory_extractor import MemoryExtractor
from app.proactive.notifier import build_default_routes
from app.proactive.types import Decision, TranscriptChunk
from app.verifier import make_default_verifier

logger = logging.getLogger("engine.proactive_routes")

router = APIRouter(prefix="/proactive", tags=["proactive"])


# ─────────────────────────────────────────────────────────────────
# Per-user session state
# ─────────────────────────────────────────────────────────────────


class UserSession:
    """One ProactiveEngine + one event buffer per wearer.

    The engine carries conversation context (sliding window, pending
    decisions awaiting settle, dispatcher dedup history). The event buffer
    captures whatever the BrowserAgentExecutor reports back to the wearer
    surface so HTTP clients can poll for execution progress.
    """

    EVENT_CAP = 200

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.events: list[dict] = []
        self._seq = 0
        self.lock = asyncio.Lock()
        self.created_at = time.time()
        self.last_used = time.time()

        # RealtimePublishExecutor drives the wearer's actual Chrome via the
        # existing Anticipy extension (Supabase Realtime → background.js →
        # extension's BrowserAgent). No Patchright/Chromium subprocess in the
        # production action path. (Cop-out #25: never spawn a separate browser.)
        executor = RealtimePublishExecutor(
            user_id=user_id,
            verifier=make_default_verifier(),
            on_wearer_message=self._on_wearer_message,
        )
        # Wire real delivery for the cascade. local_notify handles IN_APP
        # and PUSH (macOS notification banner); Twilio handles SMS and
        # VOICE when creds + the contact phone are present. The notifier's
        # ladder falls down through any slot left None, so absent Twilio
        # creds simply route SMS/VOICE traffic into PUSH.
        contact_phone = (
            os.environ.get("ANTICIPY_USER_PHONE")
            or os.environ.get("TWILIO_NOTIFY_TO")
            or os.environ.get("TWILIO_TEST_TO_REAL_NUMBER_E164")
            or None
        )
        delivery_routes = build_default_routes(
            contact_phone=contact_phone,
        )
        self.engine = ProactiveEngine(
            user_id=user_id,
            llm_call=make_json_llm_call(max_tokens=1024),
            executor=executor,
            delivery_routes=delivery_routes,
        )

        # Cross-session memory ("second brain"). Per-chunk extraction runs in
        # parallel with the cascade so durable people / places / preferences
        # / commitments / projects / facts get written without blocking the
        # cascade's decision path.
        self.memory_store = make_memory_store()
        self.memory_extractor = MemoryExtractor(
            llm_call=make_json_llm_call(max_tokens=512),
            store=self.memory_store,
        )

    async def _on_wearer_message(self, message: dict) -> None:
        """Append a wearer-facing message from the browser executor.

        Called from the BrowserAgentExecutor's on_wearer_message hook every
        time the agent emits a status / complete / error message.
        """
        self._seq += 1
        self.events.append({"seq": self._seq, "kind": "agent", **message})
        self._trim()

    def append_decision_event(self, decision: Decision) -> int:
        """Record a Decision the cascade just dispatched. Returns its seq."""
        self._seq += 1
        self.events.append({
            "seq": self._seq,
            "kind": "decision",
            "decision": _decision_to_dict(decision),
        })
        self._trim()
        return self._seq

    def events_after(self, seq: int) -> list[dict]:
        return [e for e in self.events if e.get("seq", 0) > seq]

    def _trim(self) -> None:
        if len(self.events) > self.EVENT_CAP:
            del self.events[: len(self.events) - self.EVENT_CAP]


# Module-level cache, swappable in tests via the factory below.
_user_sessions: dict[str, UserSession] = {}


def _make_user_session(user_id: str) -> UserSession:
    """Factory. Tests monkeypatch this to inject a stub session."""
    return UserSession(user_id)


def _get_or_create_session(user_id: str) -> UserSession:
    session = _user_sessions.get(user_id)
    if session is None:
        session = _make_user_session(user_id)
        _user_sessions[user_id] = session
    session.last_used = time.time()
    return session


def _reset_user_sessions() -> None:
    """Test helper. Production code should not call this."""
    _user_sessions.clear()


# ─────────────────────────────────────────────────────────────────
# Decision serialization
# ─────────────────────────────────────────────────────────────────


def _decision_to_dict(d: Decision) -> dict[str, Any]:
    return {
        "decision_id": d.decision_id,
        "kind": d.kind.value,
        "intent": {
            "intent_id": d.intent.intent_id,
            "text": d.intent.text,
            "action_verb": d.intent.action_verb,
            "parameters": d.intent.parameters,
            "evidence_chunk_ids": d.intent.evidence_chunk_ids,
        },
        "confidence": {
            "score": d.confidence.score,
            "reasoning": d.confidence.reasoning,
        },
        "reversibility": d.reversibility.value,
        "urgency": {
            "level": d.urgency.level,
            "reasoning": d.urgency.reasoning,
        },
        "user_facing_question": d.user_facing_question,
        "completion_message": d.completion_message,
        "refusal_reason": d.refusal_reason,
        "created_at": d.created_at,
    }


# ─────────────────────────────────────────────────────────────────
# Auth helper
# ─────────────────────────────────────────────────────────────────


def _user_from_request(request: Request) -> dict:
    """Bearer JWT → payload. Raises 401 if missing/invalid."""
    auth = request.headers.get("authorization") or ""
    parts = auth.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail=msg.AUTH_REQUIRED)
    payload = auth_module.verify_token(parts[1].strip())
    if not payload:
        raise HTTPException(status_code=401, detail=msg.AUTH_TOKEN_INVALID)
    return payload


# ─────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────


class ChunkRequest(BaseModel):
    session_id: str = "default"
    text: str
    chunk_id: int | None = None
    start_ts: float | None = None
    end_ts: float | None = None
    confidence: float = 0.95
    is_self_talk: bool = False
    diarization_hint: str | None = None


class ConfirmRequest(BaseModel):
    decision_id: str
    response: str = Field(..., description="'yes' or 'no' (anything else is treated as 'no')")


class ChunkResponse(BaseModel):
    decisions: list[dict]
    pending_count: int
    sequence_max: int


class ConfirmResponse(BaseModel):
    ok: bool


class FlushResponse(BaseModel):
    decisions: list[dict]
    sequence_max: int


class EventsResponse(BaseModel):
    events: list[dict]
    sequence_max: int


# ─────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────


@router.post("/chunk", response_model=ChunkResponse)
async def post_chunk(req: ChunkRequest, request: Request) -> ChunkResponse:
    """Feed a transcript chunk into the wearer's proactive cascade."""
    payload = _user_from_request(request)
    user_id = payload["user_id"]

    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    if len(text) > 8000:
        raise HTTPException(status_code=400, detail="text is too long")

    session = _get_or_create_session(user_id)

    now = time.time()
    chunk = TranscriptChunk(
        chunk_id=req.chunk_id if req.chunk_id is not None else int(now * 1000),
        session_id=req.session_id or "default",
        user_id=user_id,
        text=text,
        start_ts=req.start_ts if req.start_ts is not None else now,
        end_ts=req.end_ts if req.end_ts is not None else now,
        confidence=max(0.0, min(1.0, req.confidence)),
        is_self_talk=req.is_self_talk,
        diarization_hint=req.diarization_hint,
    )

    async with session.lock:
        # Run cascade and memory extraction in parallel — both are LLM-bound
        # and mostly orthogonal. Memory failures NEVER block the cascade
        # response; we just log and move on so the wearer gets a Decision
        # back even if the memory side has a hiccup.
        try:
            cascade_task = session.engine.on_transcript_chunk(chunk)
            memory_task = session.memory_extractor.extract_and_write(
                user_id=user_id,
                chunk_text=chunk.text,
                chunk_id=chunk.chunk_id,
            )
            results = await asyncio.gather(
                cascade_task, memory_task, return_exceptions=True,
            )
        except Exception:
            logger.exception("proactive: chunk pipeline raised")
            raise HTTPException(status_code=500, detail=msg.CONNECTION_ERROR)

        cascade_result, memory_result = results
        if isinstance(cascade_result, Exception):
            logger.exception("proactive: cascade raised", exc_info=cascade_result)
            raise HTTPException(status_code=500, detail=msg.CONNECTION_ERROR)
        if isinstance(memory_result, Exception):
            logger.warning("proactive: memory extractor raised: %s", memory_result)

        decisions = cascade_result
        for d in decisions:
            session.append_decision_event(d)

    return ChunkResponse(
        decisions=[_decision_to_dict(d) for d in decisions],
        pending_count=len(session.engine._pending_dispatches),
        sequence_max=session._seq,
    )


@router.post("/confirm", response_model=ConfirmResponse)
async def post_confirm(req: ConfirmRequest, request: Request) -> ConfirmResponse:
    """Forward a wearer's yes/no reply to an ASK decision."""
    payload = _user_from_request(request)
    user_id = payload["user_id"]

    if not req.decision_id or not req.decision_id.strip():
        raise HTTPException(status_code=400, detail="decision_id is required")

    response = (req.response or "").strip().lower()
    if response not in ("yes", "no"):
        raise HTTPException(status_code=400, detail="response must be 'yes' or 'no'")

    session = _user_sessions.get(user_id)
    if session is None:
        raise HTTPException(status_code=404, detail="no active proactive session")

    try:
        await session.engine.on_confirmation(req.decision_id, response)
    except Exception:
        logger.exception("proactive: on_confirmation raised")
        raise HTTPException(status_code=500, detail=msg.CONNECTION_ERROR)

    return ConfirmResponse(ok=True)


@router.post("/flush", response_model=FlushResponse)
async def post_flush(request: Request) -> FlushResponse:
    """Force-settle pending decisions (e.g. at end-of-session or on silence)."""
    payload = _user_from_request(request)
    user_id = payload["user_id"]

    session = _user_sessions.get(user_id)
    if session is None:
        return FlushResponse(decisions=[], sequence_max=0)

    async with session.lock:
        try:
            decisions = await session.engine.flush_pending()
        except Exception:
            logger.exception("proactive: flush_pending raised")
            raise HTTPException(status_code=500, detail=msg.CONNECTION_ERROR)

        for d in decisions:
            session.append_decision_event(d)

    return FlushResponse(
        decisions=[_decision_to_dict(d) for d in decisions],
        sequence_max=session._seq,
    )


@router.get("/events", response_model=EventsResponse)
async def get_events(request: Request, after_seq: int = 0) -> EventsResponse:
    """Drain the wearer's event buffer for events with seq > after_seq."""
    payload = _user_from_request(request)
    user_id = payload["user_id"]

    session = _user_sessions.get(user_id)
    if session is None:
        return EventsResponse(events=[], sequence_max=0)

    return EventsResponse(
        events=session.events_after(after_seq),
        sequence_max=session._seq,
    )
