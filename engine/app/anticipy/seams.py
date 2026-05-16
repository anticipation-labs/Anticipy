"""Typed seam interfaces cut in P0, before anything uses them.

These dataclasses are the contract between the engine core and the
identity, profile, and two way comms layers that are implemented later
(P7, P8). The core consumes these shapes from P2 onward, so the later
phases fill them in without touching core logic. This is the structural
rule that keeps the build a dependency chain and not a rewrite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

Decision = Literal["ACT", "STORE_AS_LATENT", "ASK", "IGNORE"]
InboundKind = Literal["ambient", "direct", "reply"]
Channel = Literal["text", "email", "call"]


@dataclass
class UserProfile:
    """The warm start that fixes cold start. Produced by onboarding
    intake (P7), read by the core for reference resolution from day one
    so a new user is not an empty memory agent guessing. Every field is
    per user and RLS protected once the spine exists.
    """

    user_id: str
    # identity
    name: str = ""
    role_title: str = ""
    what_they_do: str = ""
    timezone: str = "UTC"
    working_hours: str = ""
    # people: relation label -> resolved description. The "the boss" and
    # "us" anchors live here so those references resolve on day one.
    people: dict[str, str] = field(default_factory=dict)
    # the systems they live in, each with a connected flag
    critical_software: dict[str, bool] = field(default_factory=dict)
    # per account opaque vault key, scope, read only context use flag
    connected_accounts: dict[str, dict] = field(default_factory=dict)
    # what the user wants Anticipy to do, and the explicit do not touch list
    mandate: str = ""
    do_not_touch: list[str] = field(default_factory=list)
    # progressive autonomy state
    autonomy_level: float = 0.92
    days_since_onboard: int = 0
    trajectory_confidence: float = 0.0
    # how to reach them
    comms_prefs: dict[str, str] = field(default_factory=dict)
    quiet_hours: str = ""
    # placeholder reference for the future voiceprint, seam only
    voice_anchor: Optional[str] = None

    def is_populated(self) -> bool:
        return bool(self.name and self.role_title and (self.people or self.mandate))


@dataclass
class UserContext:
    """Passed into every decision. Carries identity, the progressive
    autonomy operating point, and opaque connected account references.
    """

    user_id: str
    profile: Optional[UserProfile] = None
    autonomy_level: float = 0.92
    connected_account_refs: dict[str, str] = field(default_factory=dict)
    timezone: str = "UTC"
    # monotonic simulated clock seconds, used by the 3 hour rule tests so
    # timing is deterministic and not wall clock dependent
    now_s: Optional[float] = None

    @classmethod
    def cold_start(cls, user_id: str) -> "UserContext":
        """A brand new user with no profile yet. The most conservative
        autonomy operating point: ask more, act less.
        """
        return cls(user_id=user_id, profile=None, autonomy_level=0.97)

    @classmethod
    def from_profile(cls, profile: UserProfile) -> "UserContext":
        return cls(
            user_id=profile.user_id,
            profile=profile,
            autonomy_level=profile.autonomy_level,
            connected_account_refs={k: v.get("vault_key", "") for k, v in profile.connected_accounts.items()},
            timezone=profile.timezone,
        )


@dataclass
class InboundMessage:
    """One inbound unit on any of the three paths. Tagged by source so
    the router sends it down the one pipeline correctly. A direct user
    command is highest authority and lowest uncertainty: the user
    addressed it deliberately, so addressee detection is bypassed.
    """

    source: InboundKind
    text: str
    user_id: str
    speaker_id: str = "WEARER"
    ts: float = 0.0
    channel: Optional[Channel] = None
    in_reply_to: Optional[str] = None  # task_id when source == "reply"
    raw: Any = None


@dataclass
class OutboundMessage:
    """One outbound unit to the user. comms_send records this in test
    mode. The real Telnyx and SES adapter consumes this exact shape.
    """

    task_id: str
    user_id: str
    channel: Channel
    body: str
    criticality: str = "non_critical"  # non_critical | critical
    options: list[str] = field(default_factory=list)
    expected_answer_shape: str = "freeform"
    ts: float = 0.0

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "channel": self.channel,
            "body": self.body,
            "criticality": self.criticality,
            "options": list(self.options),
            "expected_answer_shape": self.expected_answer_shape,
            "ts": self.ts,
        }


@dataclass
class TranscriptLine:
    """One diarized line. speaker_id is an opaque label. Exactly one
    speaker per transcript is the enrolled wearer, marked WEARER. The
    engine treats WEARER identification as an input it is given, not
    something it computes, so the real diarizer slots in at the adapter
    boundary later with zero engine change.
    """

    speaker_id: str
    text: str
    ts: float


@dataclass
class EngineDecision:
    """The one typed output of the proactive engine for one
    conversational unit.
    """

    decision: Decision
    confidence: float
    evidence: str
    unit_text: str
    user_id: str
    intent: Optional[dict] = None
    memory_op: Optional[dict] = None  # ADD | UPDATE | DELETE | NOOP record
    ask_question: Optional[str] = None
    source: InboundKind = "ambient"

    def to_dict(self) -> dict:
        return {
            "decision": self.decision,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "unit_text": self.unit_text,
            "user_id": self.user_id,
            "intent": self.intent,
            "memory_op": self.memory_op,
            "ask_question": self.ask_question,
            "source": self.source,
        }
