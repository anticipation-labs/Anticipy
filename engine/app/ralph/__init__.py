"""Ralph loop persistence + recovery layer.

Implements the SQLite-backed state machine described in
planning/00-handoff/RALPH_LOOP.md. Replaces the unbounded memory.jsonl
log (bug-hunter B477) with bounded, indexed storage.

P4-1 landed the SQLite store. P4-2 / P4-4 add the failure classifier,
recovery dispatcher, two-layer verifier, and the run_goal orchestrator.
"""

from app.ralph.classifier import VALID_CLASSES, classify
from app.ralph.recovery import (
    ACTION_CANCEL,
    ACTION_ESCALATE_MODEL,
    ACTION_NOTIFY_USER,
    ACTION_RETRY_LATER,
    ACTION_RETRY_NOW,
    RecoveryPlan,
    VALID_ACTIONS,
    recover,
)
from app.ralph.store import (
    CostCapExceeded,
    DEFAULT_DB_PATH,
    Goal,
    GoalStep,
    RalphStore,
)
from app.ralph.verifier import (
    JudgeResult,
    VALID_VERDICTS,
    judge_goal,
    verify_step,
)
from app.ralph.loop import RunOutcome, StepResult, run_goal

__all__ = [
    "ACTION_CANCEL",
    "ACTION_ESCALATE_MODEL",
    "ACTION_NOTIFY_USER",
    "ACTION_RETRY_LATER",
    "ACTION_RETRY_NOW",
    "CostCapExceeded",
    "DEFAULT_DB_PATH",
    "Goal",
    "GoalStep",
    "JudgeResult",
    "RalphStore",
    "RecoveryPlan",
    "RunOutcome",
    "StepResult",
    "VALID_ACTIONS",
    "VALID_CLASSES",
    "VALID_VERDICTS",
    "classify",
    "judge_goal",
    "recover",
    "run_goal",
    "verify_step",
]
