"""Shared proactive contracts.

These are the typed shapes that future listening, browser handoff, UI cards,
phone/pendant input, and evals should converge on. They are adapted from the
older V7 proactive engine contracts, but live in the current package so new
work does not have to reach into the disabled `.anticipy` system.

Important boundary: server contracts carry transcribed, diarized text only.
They must not carry raw audio.
"""
from __future__ import annotations

import enum
import time
import uuid
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def _new_id() -> str:
    return uuid.uuid4().hex


def _to_wire(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return value.value
    if is_dataclass(value):
        return {k: _to_wire(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _to_wire(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_wire(v) for v in value]
    return value


class WireMixin:
    """Small dataclass helper for JSON-safe API/test payloads."""

    def to_wire(self) -> dict[str, Any]:
        return _to_wire(self)


class DecisionKind(str, enum.Enum):
    ACT = "act"
    ASK = "ask"
    SILENT = "silent"
    BLOCKED = "blocked"
    NOTIFY = "notify"
    DEFERRED = "deferred"


class Reversibility(str, enum.Enum):
    REVERSIBLE = "reversible"
    IRREVERSIBLE = "irreversible"
    UNKNOWN = "unknown"


class NotificationChannel(str, enum.Enum):
    NOTED = "noted"
    IN_APP = "in_app"
    PUSH = "push"
    SMS = "sms"
    VOICE = "voice"


@dataclass
class TranscriptChunk(WireMixin):
    """One diarized text chunk from a listening session.

    Upstream audio capture, VAD, diarization, and ASR happen before this type.
    This contract intentionally starts after transcription.
    """

    user_id: str
    session_id: str
    text: str
    chunk_id: str = field(default_factory=_new_id)
    sequence: int = 0
    start_ts: float = 0.0
    end_ts: float = 0.0
    confidence: float = 1.0
    source: Literal["typed", "transcript", "mp3", "browser_mic", "mac_mic", "phone", "pendant"] = "typed"
    is_self_talk: bool = False
    is_addressed_to_agent: bool = False
    diarization_hint: Literal["wearer", "other", "unknown"] = "unknown"
    is_wearer: bool | None = None
    source_anchors: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


@dataclass
class Confidence(WireMixin):
    score: float
    reasoning: str = ""


@dataclass
class Urgency(WireMixin):
    level: int
    reasoning: str = ""

    @property
    def channel(self) -> NotificationChannel:
        if self.level >= 5:
            return NotificationChannel.VOICE
        if self.level >= 4:
            return NotificationChannel.SMS
        if self.level >= 3:
            return NotificationChannel.PUSH
        if self.level >= 2:
            return NotificationChannel.IN_APP
        return NotificationChannel.NOTED


@dataclass
class Intent(WireMixin):
    """A candidate task or memory extracted from one or more transcript chunks."""

    user_id: str
    text: str
    action_verb: str
    intent_id: str = field(default_factory=_new_id)
    parameters: dict[str, Any] = field(default_factory=dict)
    evidence_chunk_ids: list[str] = field(default_factory=list)
    source_anchors: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


@dataclass
class Decision(WireMixin):
    """The proactive engine's judgment for one intent.

    `confirmation_token` is optional and should be scoped to the exact risky
    action when the browser/runtime eventually executes a final step.
    """

    intent: Intent
    kind: DecisionKind
    confidence: Confidence
    reversibility: Reversibility
    urgency: Urgency
    decision_id: str = field(default_factory=_new_id)
    reason: str = ""
    user_facing_question: str | None = None
    completion_message: str | None = None
    refusal_reason: str | None = None
    proof_scope: str = ""
    confirmation_token: str | None = None
    created_at: float = field(default_factory=time.time)


@dataclass
class IntentPayload(WireMixin):
    type: Literal["intent"] = "intent"
    intent: Intent | None = None
    context_snippet: str = ""


@dataclass
class ConfirmationResponse(WireMixin):
    type: Literal["confirmation"] = "confirmation"
    decision_id: str = ""
    response: Literal["yes", "no"] = "yes"
    user_id: str = ""


@dataclass
class EngineStatusEvent(WireMixin):
    type: Literal["status"] = "status"
    decision_id: str = ""
    stage: Literal["queued", "executing", "waiting", "completed", "error", "degraded"] = "queued"
    message: str = ""
    source_anchors: list[str] = field(default_factory=list)


@dataclass
class Note(WireMixin):
    note_id: str
    user_id: str
    session_id: str
    body: str
    kind: Literal["highlight", "todo", "name", "date", "decision", "quote"] = "highlight"
    source_chunk_ids: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


GatewaySource = Literal[
    "browser",
    "mic",
    "upload",
    "sms",
    "call",
    "app",
    "extension",
    "manual",
    "voice",
    "text",
    "memory",
    "brain",
    "system",
]

GatewayStatus = Literal[
    "observed",
    "listening",
    "understood",
    "needs_approval",
    "working",
    "done",
    "remembered",
    "following_up",
    "blocked",
    "failed",
    "ignored",
    "stopped",
    "unavailable",
]


class GatewayBaseModel(BaseModel):
    """Pydantic base for the gateway's API and JSONL ledger records."""

    model_config = ConfigDict(extra="forbid")

    def to_wire(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class GatewayMemoryMutation(GatewayBaseModel):
    mutation_id: str = Field(default_factory=_new_id)
    drawer: Literal["profile", "open_loops", "history", "derived", "remembered", "unknown"] = "unknown"
    operation: Literal["proposed", "written", "read_back", "updated", "resolved", "ignored"] = "proposed"
    text: str = ""
    memory_id: str | None = None
    confidence: float = 1.0
    proof: dict[str, Any] = Field(default_factory=dict)


class GatewayActionPlan(GatewayBaseModel):
    action_id: str = Field(default_factory=_new_id)
    route: str = ""
    action: str = ""
    title: str = ""
    status: str = "observed"
    approval_required: bool = False
    card_id: str | None = None
    ask_id: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)


class GatewayChannelMirror(GatewayBaseModel):
    channel: Literal["app", "text", "voice", "browser", "memory"] = "app"
    status: Literal["notified", "available", "queued", "sent", "delivered", "failed", "not_configured"] = "available"
    target_ref: str | None = None
    message: str = ""


class GatewayBrowserRun(GatewayBaseModel):
    run_id: str = Field(default_factory=_new_id)
    task: str = ""
    start_url: str | None = None
    final_url: str | None = None
    success: bool = False
    answer: str = ""
    screenshot: bool = False
    screenshot_path: str | None = None
    blocked_reason: str | None = None
    trace: dict[str, Any] = Field(default_factory=dict)


class GatewayBrainAssessment(GatewayBaseModel):
    """Structured judgment for why an input did or did not become work.

    This is intentionally product-level, not model-provider-specific. The same
    shape can be produced by deterministic guards, a structured model call, or
    an imported older proactive engine during differential eval.
    """

    classification: Literal[
        "actionable",
        "memory",
        "mixed",
        "ignored",
        "blocked",
        "unavailable",
        "unknown",
    ] = "unknown"
    realness: Literal[
        "real",
        "vent",
        "sarcasm",
        "hypothetical",
        "third_party",
        "retracted",
        "ambient",
        "ambiguous",
        "mixed",
        "unknown",
    ] = "unknown"
    should_act: bool = False
    should_ask: bool = False
    should_remember: bool = False
    should_ignore: bool = False
    ignored_reasons: list[str] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    reuse_refs: list[str] = Field(default_factory=list)


class GatewayFollowUp(GatewayBaseModel):
    status: Literal["none", "scheduled", "recorded", "due", "completed", "blocked"] = "none"
    at: float | None = None
    reason: str = ""
    source_ref: str | None = None


class GatewayProof(GatewayBaseModel):
    proof_id: str = Field(default_factory=_new_id)
    type: str = ""
    scope: str = ""
    summary: str = ""
    ref: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class ProactiveGatewayEnvelope(GatewayBaseModel):
    """Canonical gateway record for Plan Baby Steps.

    Every source lane should be able to emit this shape before it mutates memory,
    browser state, voice/text, cards, proof, or follow-up.
    """

    event_id: str = Field(default_factory=_new_id)
    created_at: float = Field(default_factory=time.time)
    user_id: str = "default"
    source: GatewaySource = "manual"
    source_label: str = ""
    raw_input_ref: dict[str, Any] = Field(default_factory=dict)
    structured_summary: str = ""
    facts: list[dict[str, Any]] = Field(default_factory=list)
    open_loops: list[dict[str, Any]] = Field(default_factory=list)
    possible_tasks: list[dict[str, Any]] = Field(default_factory=list)
    brain_assessment: GatewayBrainAssessment = Field(default_factory=GatewayBrainAssessment)
    suggested_actions: list[GatewayActionPlan] = Field(default_factory=list)
    memory_mutations: list[GatewayMemoryMutation] = Field(default_factory=list)
    approval_required: bool = False
    channel_mirrors: list[GatewayChannelMirror] = Field(default_factory=list)
    browser_run: GatewayBrowserRun | None = None
    proof: list[GatewayProof] = Field(default_factory=list)
    follow_up: GatewayFollowUp = Field(default_factory=GatewayFollowUp)
    follow_up_at: float | None = None
    source_of_truth_tags: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    status: GatewayStatus = "observed"


RAW_AUDIO_FIELD_NAMES = {
    "audio",
    "raw_audio",
    "audio_bytes",
    "pcm",
    "waveform",
    "wav",
    "mp3_bytes",
    "media_blob",
    "recording",
}


__all__ = [
    "ConfirmationResponse",
    "Confidence",
    "Decision",
    "DecisionKind",
    "EngineStatusEvent",
    "GatewayActionPlan",
    "GatewayBaseModel",
    "GatewayBrainAssessment",
    "GatewayBrowserRun",
    "GatewayChannelMirror",
    "GatewayFollowUp",
    "GatewayMemoryMutation",
    "GatewayProof",
    "GatewaySource",
    "GatewayStatus",
    "Intent",
    "IntentPayload",
    "Note",
    "NotificationChannel",
    "ProactiveGatewayEnvelope",
    "RAW_AUDIO_FIELD_NAMES",
    "Reversibility",
    "TranscriptChunk",
    "Urgency",
]
