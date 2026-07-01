"""Shared data language (Python mirror of shared/SCHEMA.md).

Three shapes, decided once, used by every room:
  - MemoryItem    (profile_fact | open_loop | history)
  - CaptureEvent  (mac_mic | pendant_phone)
  - ActionRequest (risk gate + connector/browser path)

Keep this boring and identical to the canonical spec.
"""
from __future__ import annotations

import time
import uuid
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# The fourth drawer "derived" (inferred facts w/ confidence) joins the original
# three. `kind` IS the item's type; kept named `kind` for back-compat with the
# scaffold + tests.
MemoryKind = Literal["profile_fact", "open_loop", "history", "derived"]
CaptureSourceName = Literal["mac_mic", "pendant_phone"]
ActionRisk = Literal["low", "needs_confirm", "ask_human"]
ActionPath = Literal["connector", "browser"]


def new_id() -> str:
    """Opaque unique id."""
    return uuid.uuid4().hex


def now_ts() -> float:
    """Epoch seconds."""
    return time.time()


class MemoryItem(BaseModel):
    # The full item shape. `timestamp` is the created-at; embeddings are NOT stored
    # on the item (they live in the local vector index keyed by id). provenance +
    # confidence are mandatory-by-default so stated facts (1.0) outrank guesses.
    id: str = Field(default_factory=new_id)
    kind: MemoryKind                                    # the type
    text: str
    fields: Dict[str, object] = Field(default_factory=dict)   # structured fields (due, task, ...)
    people: List[str] = Field(default_factory=list)
    timestamp: float = Field(default_factory=now_ts)    # created_at (INGEST time)
    updated_at: float = Field(default_factory=now_ts)
    # BI-TEMPORAL validity (M3). `timestamp` is when we HEARD it (ingest time); `event_time`
    # is when the fact/event is ABOUT (valid-time). `valid_from`/`valid_to` bound the window
    # a fact is TRUE — an ephemeral fact ("pickup moved to 3 TODAY") gets a valid_to at the
    # end of that day so retrieval stops surfacing it tomorrow. None = always valid (durable).
    event_time: Optional[float] = None
    valid_from: Optional[float] = None
    valid_to: Optional[float] = None
    provenance: str = "stated"                          # stated | inferred | <capture source>
    confidence: float = 1.0                             # stated = 1.0; derived < 1.0
    importance: float = 0.5
    status: str = "open"                                # state: open|waiting|done (loops); active|superseded|archived

    def is_valid_at(self, ts: float) -> bool:
        """True if this item's validity window contains `ts`. Durable facts (no bounds)
        are always valid; an ephemeral fact is invalid once `ts` passes its `valid_to`."""
        if self.valid_from is not None and ts < self.valid_from:
            return False
        if self.valid_to is not None and ts > self.valid_to:
            return False
        return True


class CaptureEvent(BaseModel):
    id: str = Field(default_factory=new_id)
    source: CaptureSourceName
    text: str
    timestamp: float = Field(default_factory=now_ts)


class ActionRequest(BaseModel):
    id: str = Field(default_factory=new_id)
    intent: str
    risk: ActionRisk
    path: ActionPath
    payload: dict = Field(default_factory=dict)


# The purpose a context is assembled FOR. Same source of truth, different budget/shape:
#   decide -> tight + always-complete (all open loops); cheap, low-latency for the harm-line.
#   act    -> drill-down; the hands get richer relevant detail to execute.
#   speak  -> facts/preferences the voice/text follow-up should honor.
ContextPurpose = Literal["decide", "act", "speak"]


class ContextPack(BaseModel):
    """The ONE assembled model-context, built by live_memory.context_builder and used by
    EVERY consumer (decider, browser/API hands, voice). Typed so the pieces provably share
    one context instead of three parallel pipes. Carries provenance + abstain so the
    harm-line and the hands apply the right guard. `text` is the budget-fit prompt block."""
    purpose: ContextPurpose = "decide"
    about: str = ""
    text: str = ""                                  # budget-fit prompt block (loops first)
    open_loops: List[str] = Field(default_factory=list)   # ALWAYS all active (never dropped)
    profile: List[str] = Field(default_factory=list)
    history: List[str] = Field(default_factory=list)
    derived: List[str] = Field(default_factory=list)
    top_relevance: float = 0.0                      # semantic confidence of the best match
    abstain: bool = True                            # below floor -> don't fabricate
    provenance: Dict[str, str] = Field(default_factory=dict)  # item text -> stated|inferred|source
    budget_used: int = 0
    item_count: int = 0

    def as_ctx_dict(self) -> Dict[str, object]:
        """Back-compat shape the orchestrator/worker already consume (notes + drawers)."""
        return {
            "notes": self.text,
            "open_loops": list(self.open_loops),
            "profile": list(self.profile),
            "history": list(self.history),
            "derived": list(self.derived),
        }
