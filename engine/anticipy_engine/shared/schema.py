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
from typing import Dict, List, Literal

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
    timestamp: float = Field(default_factory=now_ts)    # created_at
    updated_at: float = Field(default_factory=now_ts)
    provenance: str = "stated"                          # stated | inferred | <capture source>
    confidence: float = 1.0                             # stated = 1.0; derived < 1.0
    importance: float = 0.5
    status: str = "open"                                # state: open|waiting|done (loops); active|superseded|archived


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
