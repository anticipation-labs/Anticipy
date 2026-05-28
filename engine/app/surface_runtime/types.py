from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import time
from typing import Any


class SurfaceKind(str, Enum):
    BROWSER_DOM = "browser_dom"
    BROWSER_CANVAS = "browser_canvas"
    NATIVE_AX = "native_ax"
    TERMINAL = "terminal"
    FILE_SYSTEM = "file_system"
    NOTIFICATION = "notification"
    UNKNOWN = "unknown"


class EvidenceKind(str, Enum):
    DOM_SNAPSHOT = "dom_snapshot"
    CDP_TARGET = "cdp_target"
    AX_TREE = "ax_tree"
    SCREENSHOT = "screenshot"
    VISION_ANSWER = "vision_answer"
    TERMINAL_BUFFER = "terminal_buffer"
    FILE_STATE = "file_state"
    NOTIFICATION_RECORD = "notification_record"
    PROVIDER_CALLBACK = "provider_callback"
    ENGINE_LOG = "engine_log"


class PrimitiveKind(str, Enum):
    READ = "read"
    OPEN = "open"
    CLICK = "click"
    TYPE = "type"
    SHORTCUT = "shortcut"
    WAIT = "wait"
    VERIFY = "verify"
    ASK = "ask"
    DECLINE = "decline"
    NOTIFY = "notify"


class RiskMode(str, Enum):
    SILENT_EXECUTE = "silent_execute"
    EXECUTE_NOTIFY = "execute_notify"
    ASK_FIRST = "ask_first"
    DECLINE = "decline"


@dataclass(frozen=True)
class SurfaceObservation:
    surface_kind: SurfaceKind
    target: str
    evidence_kind: EvidenceKind
    summary: str
    confidence: float
    artifact_path: str | None = None
    observed_state: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_json(self) -> dict[str, Any]:
        return _enum_safe(asdict(self))


@dataclass(frozen=True)
class ActionPrimitive:
    primitive: PrimitiveKind
    surface_kind: SurfaceKind
    target: str
    args: dict[str, Any] = field(default_factory=dict)
    max_wait_seconds: float = 30.0
    risk_mode: RiskMode = RiskMode.ASK_FIRST

    def to_json(self) -> dict[str, Any]:
        return _enum_safe(asdict(self))


@dataclass(frozen=True)
class ProofReceipt:
    evidence_kind: EvidenceKind
    surface_kind: SurfaceKind
    target: str
    summary: str
    confidence: float = 1.0
    artifact_path: str | None = None
    observed_state: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_json(self) -> dict[str, Any]:
        return _enum_safe(asdict(self))


@dataclass(frozen=True)
class RuntimeDecision:
    mode: RiskMode
    reason: str
    primitives: list[ActionPrimitive] = field(default_factory=list)
    required_receipts: list[EvidenceKind] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return _enum_safe(asdict(self))


@dataclass(frozen=True)
class LearnedRecipe:
    user_id: str
    surface_kind: SurfaceKind
    category: str
    title: str
    primitives: list[ActionPrimitive]
    receipt: ProofReceipt
    confidence: float
    updated_at: float = field(default_factory=time.time)

    def to_json(self) -> dict[str, Any]:
        return _enum_safe(asdict(self))


def _enum_safe(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [_enum_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _enum_safe(v) for k, v in value.items()}
    return value
