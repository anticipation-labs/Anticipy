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
from typing import List, Literal

from pydantic import BaseModel, Field

MemoryKind = Literal["profile_fact", "open_loop", "history"]
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
    id: str = Field(default_factory=new_id)
    kind: MemoryKind
    text: str
    people: List[str] = Field(default_factory=list)
    timestamp: float = Field(default_factory=now_ts)
    status: str = "open"


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
