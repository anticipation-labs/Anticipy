"""Persistent task queue with wake-up scheduling.

Once Anticipy starts handling a task, it owns that task to completion
even across restarts, days, or weeks. Sleeps and re-wakes as needed.

Public API surface:
    enqueue(instruction, *, account_id=None, wake_at=None, owner_session_id=None, metadata=None) -> TaskRecord
    claim_next() -> Optional[TaskRecord]
    complete(task_id, result) -> Optional[TaskRecord]
    fail(task_id, error) -> Optional[TaskRecord]
    reschedule(task_id, wake_at) -> Optional[TaskRecord]
    wait_for(task_id, reason, wake_at=None) -> Optional[TaskRecord]
    cancel(task_id, reason="") -> Optional[TaskRecord]
    list_tasks(status=None, limit=200) -> list[TaskRecord]
    resume_after_restart() -> list[TaskRecord]
    get(task_id) -> Optional[TaskRecord]

Storage layout (under ANTICIPY_DATA_DIR or ~/.anticipy/v7):
    task_queue/queue.jsonl   append-only journal of every state transition
    task_queue/index.json    current state for every active and recent task

The journal is the source of truth across restarts; the index file is a
cache of the current state so callers do not need to fold the journal on
every read. Both are rebuilt on demand if the index is missing or stale.
"""

from __future__ import annotations

from .store import (
    BACKOFF_SCHEDULE_SECONDS,
    DEFAULT_MAX_VISIBLE_IN_UI,
    RECOVERY_RETRY_ROLLUP_THRESHOLD,
    STALE_TRIVIA_AGE_SECONDS,
    TaskRecord,
    cancel,
    claim_next,
    cleanup_expired_tasks,
    complete,
    enqueue,
    fail,
    get,
    list_tasks,
    max_visible_in_ui,
    queue_dir,
    rebuild_index_from_journal,
    reschedule,
    resume_after_restart,
    scan_due,
    wait_for,
)
from . import dispatcher

__all__ = [
    "BACKOFF_SCHEDULE_SECONDS",
    "DEFAULT_MAX_VISIBLE_IN_UI",
    "RECOVERY_RETRY_ROLLUP_THRESHOLD",
    "STALE_TRIVIA_AGE_SECONDS",
    "TaskRecord",
    "cancel",
    "claim_next",
    "cleanup_expired_tasks",
    "complete",
    "dispatcher",
    "enqueue",
    "fail",
    "get",
    "list_tasks",
    "max_visible_in_ui",
    "queue_dir",
    "rebuild_index_from_journal",
    "reschedule",
    "resume_after_restart",
    "scan_due",
    "wait_for",
]
