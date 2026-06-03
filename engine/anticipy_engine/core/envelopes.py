"""The shapes that flow through the bus, and the Goal the orchestrator owns.

FROZEN contract surface — every worker, real or stub, speaks these. Three
messages share a base envelope; a Goal is persisted (not a transient message).
"""
from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


def new_id() -> str:
    return uuid.uuid4().hex


def now_ts() -> float:
    return time.time()


class MessageType(str, Enum):
    EVENT = "event"
    JOB = "job"
    RESULT = "result"


class EventSource(str, Enum):
    mac_mic = "mac_mic"
    pendant_phone = "pendant_phone"
    app = "app"
    system = "system"


class Risk(str, Enum):
    low = "low"
    needs_confirm = "needs_confirm"
    ask_human = "ask_human"


class JobStatus(str, Enum):
    success = "success"
    failed = "failed"
    needs_human = "needs_human"


class GoalState(str, Enum):
    planning = "planning"
    running = "running"
    waiting = "waiting"
    done = "done"
    failed = "failed"


class StepState(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    needs_human = "needs_human"
    failed = "failed"


# ---- bus messages ----
class Envelope(BaseModel):
    id: str = Field(default_factory=new_id)
    timestamp: float = Field(default_factory=now_ts)


class Event(Envelope):
    type: MessageType = MessageType.EVENT
    source: EventSource
    text: str
    meta: dict = Field(default_factory=dict)


class Job(Envelope):
    type: MessageType = MessageType.JOB
    intent: str
    args: dict = Field(default_factory=dict)
    risk: Risk = Risk.low
    goal_id: Optional[str] = None


class Result(Envelope):
    type: MessageType = MessageType.RESULT
    job_id: str
    status: JobStatus
    output: dict = Field(default_factory=dict)
    # On success this MUST be present and truthy — the orchestrator refuses to
    # mark a step done without it.
    proof: Optional[dict] = None
    cost: float = 0.0
    error: Optional[str] = None


# ---- the orchestrator's unit of work (persisted) ----
class Step(BaseModel):
    intent: str
    args: dict = Field(default_factory=dict)
    risk: Risk = Risk.low
    state: StepState = StepState.pending
    attempts: int = 0
    result: Optional[Result] = None


class Goal(BaseModel):
    id: str = Field(default_factory=new_id)
    intent: str
    description: str = ""
    steps: List[Step] = Field(default_factory=list)
    state: GoalState = GoalState.planning
    proof: dict = Field(default_factory=dict)
    created_at: float = Field(default_factory=now_ts)
    updated_at: float = Field(default_factory=now_ts)

    def touch(self) -> None:
        self.updated_at = now_ts()
