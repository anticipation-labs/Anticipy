"""Ralph loop persistence layer.

Implements the SQLite-backed state machine described in
planning/00-handoff/RALPH_LOOP.md. Replaces the unbounded memory.jsonl
log (bug-hunter B477) with bounded, indexed storage.

This package owns Phase 4-1 only (tables + CRUD wrapper). Failure
classification, retry dispatch, wake-up polling, and verification
layers ship in later P4 phases and import from here.
"""

from app.ralph.store import (
    CostCapExceeded,
    DEFAULT_DB_PATH,
    Goal,
    GoalStep,
    RalphStore,
)

__all__ = [
    "CostCapExceeded",
    "DEFAULT_DB_PATH",
    "Goal",
    "GoalStep",
    "RalphStore",
]
