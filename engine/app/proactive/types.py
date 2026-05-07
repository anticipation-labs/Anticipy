"""
Data types for the proactive engine.

These are the contract between phone-side audio capture and server-side action
execution. Audio is *never* present in any of these types — only diarized,
transcribed text from the user's own voice cluster.
"""

from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal


# --- Streaming input -----------------------------------------------------------


@dataclass
class TranscriptChunk:
    """One chunk of transcribed user speech from the phone.

    Phone-side pipeline upstream of this:
      BLE audio → Silero VAD → Sortformer diarization → Parakeet V3 ASR
      → diarization gate (drop any non-user-cluster) → this chunk.

    `chunk_id` is monotonic per session. `session_id` groups chunks
    from the same continuous listening session (e.g., a conversation).
    """

    chunk_id: int
    session_id: str
    user_id: str
    text: str
    start_ts: float  # unix seconds, when speech started on device
    end_ts: float    # unix seconds, when speech ended on device
    confidence: float  # ASR confidence 0..1; below 0.5 we treat as noise

    # Optional environmental hints from the phone (no raw audio):
    is_self_talk: bool = False         # phone-side heuristic: low volume + no bystander cluster
    is_addressed_to_agent: bool = False  # phone heard wake word / direct address

    # Phone-side diarization hint, optional. When the on-device diarizer is
    # confident, it sets "wearer" or "other"; otherwise None / "unknown".
    # The L0 SpeakerIDClassifier reads this as a SOFT prior — the LLM still
    # makes the final call (phone diarization can be wrong, esp. cross-talk).
    diarization_hint: str | None = None

    # Set by the L0 SpeakerIDClassifier after the speaker decision. False
    # means "this chunk is from a non-wearer voice in the room"; the chunk
    # is still kept in the context buffer so the wearer's responses to other
    # people stay grounded, but downstream layers (L1/L2/etc) MUST NOT treat
    # the text as wearer intent. None means "not yet classified" (the field
    # is set in-place by the engine before context append).
    is_wearer: bool | None = None


# --- Intents & Decisions -------------------------------------------------------


class DecisionKind(str, enum.Enum):
    EXECUTE = "execute"  # do it now, tell user after
    ASK = "ask"          # bother user via notifier with this question
    LOG = "log"          # silent, append to "things I noticed"
    REFUSE = "refuse"    # the agent's Donna move: no, you don't actually want this


class Reversibility(str, enum.Enum):
    REVERSIBLE = "reversible"        # search, navigate, read, set reminder, take note
    IRREVERSIBLE = "irreversible"    # send email, pay, book, cancel, delete, contact
    UNKNOWN = "unknown"              # treat as IRREVERSIBLE for safety


@dataclass
class Confidence:
    """LLM-estimated probability the agent understood the user correctly.

    `score` is 0..1. `reasoning` is the LLM's brief justification for the
    score; surfaced in the "Things I noticed" feed so the user can audit.
    """

    score: float
    reasoning: str = ""


@dataclass
class Urgency:
    """How soon this matters. 1 (no rush) through 5 (right now)."""

    level: int  # 1..5
    reasoning: str = ""

    @property
    def channel(self) -> NotificationChannel:
        """Map urgency to the notification channel."""
        if self.level >= 5:
            return NotificationChannel.VOICE
        if self.level >= 4:
            return NotificationChannel.SMS
        if self.level >= 3:
            return NotificationChannel.PUSH
        if self.level >= 2:
            return NotificationChannel.IN_APP
        return NotificationChannel.NOTED


class NotificationChannel(str, enum.Enum):
    """Escalating delivery surfaces, in order of intrusiveness."""

    NOTED = "noted"        # silent — just sits in the "Things I noticed" feed
    IN_APP = "in_app"      # in-app badge
    PUSH = "push"          # push notification
    SMS = "sms"            # text message
    VOICE = "voice"        # voice call


@dataclass
class Intent:
    """An intent extracted from a salient utterance + context.

    The `action_verb` is what reversibility.py looks up. It must be
    one of the canonical verbs the LLM was prompted to choose from
    (see interpreter.py CANONICAL_ACTION_VERBS).

    `parameters` are the slot fillings: target site / person / amount /
    date / etc. They are LLM-extracted free-form; downstream consumers
    (decider, browser agent) interpret them.

    `evidence_chunk_ids` are the transcript chunks the LLM cited for
    this intent. Surfaced in the "Things I noticed" feed.
    """

    intent_id: str
    user_id: str
    text: str           # one-sentence rephrasing of the user's intent
    action_verb: str    # canonical verb; reversibility.py is the source of truth
    parameters: dict[str, Any] = field(default_factory=dict)
    evidence_chunk_ids: list[int] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    @staticmethod
    def new(user_id: str, text: str, action_verb: str, **kw: Any) -> Intent:
        return Intent(
            intent_id=uuid.uuid4().hex,
            user_id=user_id,
            text=text,
            action_verb=action_verb,
            **kw,
        )


@dataclass
class Decision:
    """The decider's verdict on a single intent.

    `confirmation_token` is set when kind == ASK and the user has
    confirmed; otherwise None. It is a JWT signed by the engine's
    JWT_SECRET, used to authorize execution.
    """

    decision_id: str
    intent: Intent
    kind: DecisionKind
    confidence: Confidence
    reversibility: Reversibility
    urgency: Urgency
    user_facing_question: str | None = None  # populated when kind == ASK
    completion_message: str | None = None    # populated when kind == EXECUTE
    refusal_reason: str | None = None        # populated when kind == REFUSE
    confirmation_token: str | None = None
    created_at: float = field(default_factory=time.time)

    @staticmethod
    def new(
        intent: Intent,
        kind: DecisionKind,
        confidence: Confidence,
        reversibility: Reversibility,
        urgency: Urgency,
        **kw: Any,
    ) -> Decision:
        return Decision(
            decision_id=uuid.uuid4().hex,
            intent=intent,
            kind=kind,
            confidence=confidence,
            reversibility=reversibility,
            urgency=urgency,
            **kw,
        )


# --- Phone↔engine wire payloads ------------------------------------------------


@dataclass
class IntentPayload:
    """The wire format from phone → engine. Used in WebSocket messages.

    The phone sends a fully-formed intent (it has done the salience filter +
    extraction locally on the on-device LLM). The engine validates,
    re-decides if needed, and executes.

    For the v1 deployment where the proactive engine runs server-side, this
    payload is constructed inside the engine and never crosses a network
    boundary. The structure is the same so the on-device port is straightforward.
    """

    type: Literal["intent"] = "intent"
    intent: Intent | None = None
    context_snippet: str = ""  # ~last 2 minutes of user-voice transcript


@dataclass
class ConfirmationResponse:
    """User said yes/no to an ASK on the phone."""

    type: Literal["confirmation"] = "confirmation"
    decision_id: str = ""
    response: Literal["yes", "no"] = "yes"
    user_id: str = ""


@dataclass
class EngineStatusEvent:
    """Engine → phone status updates while an intent is being executed."""

    type: Literal["status"] = "status"
    decision_id: str = ""
    stage: Literal["queued", "executing", "completed", "error", "degraded"] = "queued"
    message: str = ""  # user-facing copy, already sanitized & in the agent's voice


# --- Notes (recorder mode) -----------------------------------------------------


@dataclass
class Note:
    """A single note. Notes are an always-on side-effect of listening.

    Notes are *summaries* of recent transcript, not raw transcript. The
    phone-side notes recorder collapses repeated/redundant content and
    extracts structured items (todos, names, dates).
    """

    note_id: str
    user_id: str
    session_id: str
    body: str  # user-readable note text
    kind: Literal["highlight", "todo", "name", "date", "decision", "quote"] = "highlight"
    source_chunk_ids: list[int] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


# --- "Things I noticed" feed entry ---------------------------------------------


@dataclass
class NoticedItem:
    """An entry in the user-visible feed of intents the agent considered but
    didn't auto-execute (low confidence) or surfaced post-hoc.

    Each item is one tap → execute, ignore, or remind-later.
    """

    item_id: str
    user_id: str
    session_id: str
    body: str  # user-readable summary
    decision: Decision
    status: Literal["new", "executed", "ignored", "snoozed"] = "new"
    snoozed_until: float | None = None
    created_at: float = field(default_factory=time.time)
