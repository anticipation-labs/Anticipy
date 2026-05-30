"""Append-only JSONL journal plus index-file cache for the persistent
task queue.

Storage layout::

    <data_root>/task_queue/queue.jsonl     append-only journal
    <data_root>/task_queue/index.json      current state snapshot

The journal is the source of truth on restart; the index is a fast
read-side cache so callers do not need to fold the journal on every
get / list / claim. If the index is missing or out of date relative to
the journal byte count, the index is rebuilt from the journal.

Threading model:
    A single module-level lock guards journal appends, index writes, and
    in-memory state. Every public function acquires the lock. The lock is
    re-entrant so internal helpers can call each other.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional


# Exponential backoff schedule for retries: 1 minute, 5 minutes, 30
# minutes, 2 hours, 12 hours. After the last entry the task is marked
# failed and the caller is expected to escalate (SMS, banner, etc).
BACKOFF_SCHEDULE_SECONDS: tuple[float, ...] = (
    60.0,
    5 * 60.0,
    30 * 60.0,
    2 * 60 * 60.0,
    12 * 60 * 60.0,
)


# ---------------------------------------------------------------------------
# Status vocabulary (single source of truth)
# ---------------------------------------------------------------------------

STATUS_PENDING = "pending"        # newly enqueued, not yet claimed
STATUS_IN_PROGRESS = "in_progress"  # claimed by an executor
STATUS_WAITING = "waiting"        # paused on external event (reply, time, MFA)
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

_ACTIVE_STATUSES = {STATUS_PENDING, STATUS_IN_PROGRESS, STATUS_WAITING}
_TERMINAL_STATUSES = {STATUS_DONE, STATUS_FAILED, STATUS_CANCELLED}

_VALID_STATUSES = _ACTIVE_STATUSES | _TERMINAL_STATUSES


# ---------------------------------------------------------------------------
# TaskRecord dataclass
# ---------------------------------------------------------------------------

@dataclass
class TaskRecord:
    task_id: str
    created_at: float
    account_id: str
    instruction: str
    status: str = STATUS_PENDING
    wake_at: Optional[float] = None
    retry_count: int = 0
    last_error: str = ""
    owner_session_id: str = ""
    updated_at: float = 0.0
    claimed_at: Optional[float] = None
    completed_at: Optional[float] = None
    last_result: Optional[dict[str, Any]] = None
    waiting_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["created_at_iso"] = _iso(d["created_at"])
        if d.get("wake_at") is not None:
            d["wake_at_iso"] = _iso(d["wake_at"])
        if d.get("updated_at"):
            d["updated_at_iso"] = _iso(d["updated_at"])
        if d.get("claimed_at"):
            d["claimed_at_iso"] = _iso(d["claimed_at"])
        if d.get("completed_at"):
            d["completed_at_iso"] = _iso(d["completed_at"])
        return d


def _iso(epoch_s: float) -> str:
    try:
        return datetime.fromtimestamp(
            float(epoch_s), tz=timezone.utc
        ).isoformat()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_DEFAULT_V7_ROOT = os.path.expanduser("~/.anticipy/v7")


def _data_root() -> Path:
    """Resolve the parent data root. Honors ANTICIPY_DATA_DIR for tests
    and the home-base device, otherwise sits next to the existing v7
    dossier / decision log under ~/.anticipy/v7.
    """
    env = os.environ.get("ANTICIPY_TASK_QUEUE_DIR", "").strip()
    if env:
        return Path(env)
    base = os.environ.get("ANTICIPY_DATA_DIR", "").strip()
    if base:
        return Path(base) / "v7"
    return Path(_DEFAULT_V7_ROOT)


def queue_dir() -> Path:
    d = _data_root() / "task_queue"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _journal_path() -> Path:
    return queue_dir() / "queue.jsonl"


def _index_path() -> Path:
    return queue_dir() / "index.json"


# ---------------------------------------------------------------------------
# In-memory state + lock
# ---------------------------------------------------------------------------

_LOCK = threading.RLock()
_LOADED = False
_TASKS: dict[str, TaskRecord] = {}
# Byte offset of the journal at last index load / write. Lets us detect
# external journal appends (e.g. another process) and rebuild the index
# when those happen.
_INDEX_OFFSET = 0


def _ensure_loaded() -> None:
    global _LOADED, _INDEX_OFFSET, _TASKS
    with _LOCK:
        if _LOADED:
            return
        idx_path = _index_path()
        jrn_path = _journal_path()
        journal_size = jrn_path.stat().st_size if jrn_path.exists() else 0
        loaded_from_index = False
        if idx_path.exists():
            try:
                data = json.loads(idx_path.read_text(encoding="utf-8"))
                offset = int(data.get("journal_offset") or 0)
                tasks_blob = data.get("tasks") or []
                if (offset <= journal_size
                        and isinstance(tasks_blob, list)):
                    _TASKS = {}
                    for row in tasks_blob:
                        try:
                            rec = _coerce_record(row)
                        except Exception:
                            continue
                        _TASKS[rec.task_id] = rec
                    _INDEX_OFFSET = offset
                    loaded_from_index = True
            except Exception:
                loaded_from_index = False
        if not loaded_from_index:
            _TASKS = {}
            _INDEX_OFFSET = 0
        # Replay any journal entries past the loaded offset so we catch
        # external writes plus the case where the index is stale.
        if journal_size > _INDEX_OFFSET:
            _replay_journal_locked()
        _LOADED = True


def _coerce_record(row: dict[str, Any]) -> TaskRecord:
    """Build a TaskRecord from a dict, tolerating missing keys."""
    return TaskRecord(
        task_id=str(row.get("task_id") or ""),
        created_at=float(row.get("created_at") or time.time()),
        account_id=str(row.get("account_id") or ""),
        instruction=str(row.get("instruction") or ""),
        status=str(row.get("status") or STATUS_PENDING),
        wake_at=(float(row["wake_at"])
                 if row.get("wake_at") is not None else None),
        retry_count=int(row.get("retry_count") or 0),
        last_error=str(row.get("last_error") or ""),
        owner_session_id=str(row.get("owner_session_id") or ""),
        updated_at=float(row.get("updated_at") or 0.0),
        claimed_at=(float(row["claimed_at"])
                    if row.get("claimed_at") is not None else None),
        completed_at=(float(row["completed_at"])
                      if row.get("completed_at") is not None else None),
        last_result=(dict(row.get("last_result"))
                     if isinstance(row.get("last_result"), dict) else None),
        waiting_reason=str(row.get("waiting_reason") or ""),
        metadata=(dict(row.get("metadata"))
                  if isinstance(row.get("metadata"), dict) else {}),
    )


def _replay_journal_locked() -> None:
    """Read every journal line and reduce it onto _TASKS. Called when
    the index is missing or when a startup detects extra bytes past the
    loaded offset.
    """
    global _INDEX_OFFSET
    jrn_path = _journal_path()
    if not jrn_path.exists():
        _INDEX_OFFSET = 0
        return
    size = jrn_path.stat().st_size
    if size == 0:
        _INDEX_OFFSET = 0
        return
    with jrn_path.open("r", encoding="utf-8") as fh:
        if _INDEX_OFFSET > 0 and _INDEX_OFFSET <= size:
            try:
                fh.seek(_INDEX_OFFSET)
            except Exception:
                fh.seek(0)
                _INDEX_OFFSET = 0
                _TASKS.clear()
        else:
            _INDEX_OFFSET = 0
            _TASKS.clear()
        for raw in fh:
            line = raw.rstrip("\n")
            if not line:
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue
            if not isinstance(entry, dict):
                continue
            _apply_journal_entry_locked(entry)
    _INDEX_OFFSET = size


def _apply_journal_entry_locked(entry: dict[str, Any]) -> None:
    task = entry.get("task")
    if not isinstance(task, dict):
        return
    try:
        rec = _coerce_record(task)
    except Exception:
        return
    if not rec.task_id:
        return
    _TASKS[rec.task_id] = rec


# ---------------------------------------------------------------------------
# Journal + index writers
# ---------------------------------------------------------------------------

def _append_journal_locked(event: str, rec: TaskRecord,
                            extra: Optional[dict[str, Any]] = None) -> None:
    """Append one event line to the journal AND keep the in-memory map
    coherent. Callers must hold _LOCK.
    """
    global _INDEX_OFFSET
    payload: dict[str, Any] = {
        "event": event,
        "ts": time.time(),
        "ts_iso": _iso(time.time()),
        "task": asdict(rec),
    }
    if extra:
        payload["extra"] = extra
    line = json.dumps(payload, default=str, ensure_ascii=False) + "\n"
    jrn_path = _journal_path()
    jrn_path.parent.mkdir(parents=True, exist_ok=True)
    with jrn_path.open("a", encoding="utf-8") as fh:
        fh.write(line)
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except Exception:
            pass
    _TASKS[rec.task_id] = rec
    try:
        _INDEX_OFFSET = jrn_path.stat().st_size
    except Exception:
        pass
    _write_index_locked()


def _write_index_locked() -> None:
    """Snapshot the in-memory map atomically. Best effort; the journal
    is the source of truth so a torn write here is recoverable on next
    boot via _replay_journal_locked.
    """
    idx_path = _index_path()
    tmp_path = idx_path.with_suffix(idx_path.suffix + ".tmp")
    payload = {
        "schema": 1,
        "written_at": time.time(),
        "written_at_iso": _iso(time.time()),
        "journal_offset": _INDEX_OFFSET,
        "tasks": [asdict(rec) for rec in _TASKS.values()],
    }
    try:
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_text(
            json.dumps(payload, default=str, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp_path, idx_path)
    except Exception:
        # Index is a cache; if we cannot write, the next read will rebuild
        # from the journal. Do not raise.
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enqueue(instruction: str, *,
            account_id: str = "anticipy-user",
            wake_at: Optional[float] = None,
            owner_session_id: str = "",
            metadata: Optional[dict[str, Any]] = None) -> TaskRecord:
    """Persist a new task. Returns the TaskRecord."""
    text = (instruction or "").strip()
    if not text:
        raise ValueError("task instruction must be non-empty")
    now = time.time()
    rec = TaskRecord(
        task_id=f"task-{uuid.uuid4().hex[:16]}",
        created_at=now,
        account_id=(account_id or "anticipy-user").strip() or "anticipy-user",
        instruction=text,
        status=STATUS_PENDING,
        wake_at=float(wake_at) if wake_at is not None else None,
        owner_session_id=str(owner_session_id or ""),
        updated_at=now,
        metadata=dict(metadata or {}),
    )
    with _LOCK:
        _ensure_loaded()
        _append_journal_locked("enqueue", rec)
    return rec


def claim_next(*, owner_session_id: str = "") -> Optional[TaskRecord]:
    """Atomically claim the next runnable pending task.

    A task is runnable when status == pending AND wake_at is null or
    in the past. Returns None if nothing is runnable.
    """
    now = time.time()
    with _LOCK:
        _ensure_loaded()
        candidates = [
            rec for rec in _TASKS.values()
            if rec.status == STATUS_PENDING
            and (rec.wake_at is None or rec.wake_at <= now)
        ]
        if not candidates:
            return None
        # Oldest created_at wins so multi-day queues drain FIFO.
        candidates.sort(key=lambda r: (r.wake_at or 0.0, r.created_at))
        rec = candidates[0]
        rec.status = STATUS_IN_PROGRESS
        rec.claimed_at = now
        rec.updated_at = now
        if owner_session_id:
            rec.owner_session_id = owner_session_id
        _append_journal_locked("claim", rec)
        return rec


def complete(task_id: str, result: Optional[dict[str, Any]] = None) -> Optional[TaskRecord]:
    """Mark a task done. Idempotent on already-done tasks."""
    with _LOCK:
        _ensure_loaded()
        rec = _TASKS.get(task_id)
        if rec is None:
            return None
        if rec.status == STATUS_DONE:
            return rec
        now = time.time()
        rec.status = STATUS_DONE
        rec.completed_at = now
        rec.updated_at = now
        rec.last_result = dict(result) if isinstance(result, dict) else (
            {"value": result} if result is not None else None)
        rec.last_error = ""
        _append_journal_locked("complete", rec)
        return rec


def fail(task_id: str, error: str,
         *, allow_retry: bool = True) -> Optional[TaskRecord]:
    """Mark a task failed. Schedules a retry with exponential backoff
    if attempts remain on the schedule.
    """
    with _LOCK:
        _ensure_loaded()
        rec = _TASKS.get(task_id)
        if rec is None:
            return None
        now = time.time()
        rec.last_error = (error or "")[:1024]
        rec.retry_count = int(rec.retry_count or 0) + 1
        if allow_retry and rec.retry_count <= len(BACKOFF_SCHEDULE_SECONDS):
            delay = BACKOFF_SCHEDULE_SECONDS[rec.retry_count - 1]
            rec.status = STATUS_PENDING
            rec.wake_at = now + delay
            rec.claimed_at = None
            rec.updated_at = now
            _append_journal_locked("retry_scheduled", rec, {
                "delay_seconds": delay,
                "next_attempt": rec.retry_count + 1,
            })
        else:
            rec.status = STATUS_FAILED
            rec.completed_at = now
            rec.updated_at = now
            _append_journal_locked("fail", rec, {
                "escalate": True,
                "attempt_count": rec.retry_count,
            })
        return rec


def reschedule(task_id: str, wake_at: float) -> Optional[TaskRecord]:
    """Update wake_at on a pending or waiting task; reset to pending so
    the scheduler picks it up at the new time.
    """
    with _LOCK:
        _ensure_loaded()
        rec = _TASKS.get(task_id)
        if rec is None:
            return None
        if rec.status in _TERMINAL_STATUSES:
            return rec
        now = time.time()
        rec.wake_at = float(wake_at)
        rec.status = STATUS_PENDING
        rec.updated_at = now
        _append_journal_locked("reschedule", rec)
        return rec


def wait_for(task_id: str, reason: str,
             *, wake_at: Optional[float] = None) -> Optional[TaskRecord]:
    """Park a task in the waiting status while it depends on an external
    signal (an inbound email, an MFA prompt, etc). wake_at is an
    optional safety net so the task does not block forever.
    """
    with _LOCK:
        _ensure_loaded()
        rec = _TASKS.get(task_id)
        if rec is None:
            return None
        if rec.status in _TERMINAL_STATUSES:
            return rec
        now = time.time()
        rec.status = STATUS_WAITING
        rec.waiting_reason = str(reason or "")[:512]
        rec.updated_at = now
        if wake_at is not None:
            rec.wake_at = float(wake_at)
        _append_journal_locked("wait_for", rec)
        return rec


def cancel(task_id: str, reason: str = "") -> Optional[TaskRecord]:
    with _LOCK:
        _ensure_loaded()
        rec = _TASKS.get(task_id)
        if rec is None:
            return None
        if rec.status in _TERMINAL_STATUSES:
            return rec
        now = time.time()
        rec.status = STATUS_CANCELLED
        rec.completed_at = now
        rec.updated_at = now
        rec.last_error = str(reason or "")[:512]
        _append_journal_locked("cancel", rec)
        return rec


def get(task_id: str) -> Optional[TaskRecord]:
    with _LOCK:
        _ensure_loaded()
        return _TASKS.get(task_id)


def list_tasks(status: Optional[str | Iterable[str]] = None,
                limit: int = 200) -> list[TaskRecord]:
    """Return tasks, newest first. status may be a single string or
    iterable; None returns everything.
    """
    with _LOCK:
        _ensure_loaded()
        if status is None:
            allowed: Optional[set[str]] = None
        elif isinstance(status, str):
            allowed = {status}
        else:
            allowed = {str(s) for s in status}
        out = [r for r in _TASKS.values()
               if allowed is None or r.status in allowed]
        out.sort(key=lambda r: r.updated_at or r.created_at, reverse=True)
        if limit > 0:
            out = out[:limit]
        return out


def scan_due(now: Optional[float] = None) -> list[TaskRecord]:
    """Return tasks that are PENDING with wake_at <= now. The caller
    decides what to do with them (typically: hand to the dispatcher
    that will then call claim_next).
    """
    t = float(now if now is not None else time.time())
    with _LOCK:
        _ensure_loaded()
        return [r for r in _TASKS.values()
                if r.status == STATUS_PENDING
                and (r.wake_at is not None and r.wake_at <= t)]


def resume_after_restart() -> list[TaskRecord]:
    """Engine startup hook. Resets any task left in_progress (a crash
    boundary) back to pending so the dispatcher can re-claim it, then
    returns every task that needs attention right now (pending without
    wake_at, pending with wake_at <= now, and the freshly-reset
    in_progress tasks).
    """
    now = time.time()
    with _LOCK:
        # Force a journal replay on startup. This avoids trusting a
        # potentially stale index.
        global _LOADED
        _LOADED = False
        _ensure_loaded()
        recovered: list[TaskRecord] = []
        for rec in list(_TASKS.values()):
            if rec.status == STATUS_IN_PROGRESS:
                rec.status = STATUS_PENDING
                rec.updated_at = now
                rec.last_error = (
                    (rec.last_error + "; " if rec.last_error else "")
                    + "engine_restart_recovery"
                )[:1024]
                _append_journal_locked("recover_in_progress", rec)
                recovered.append(rec)
        runnable = [
            r for r in _TASKS.values()
            if r.status == STATUS_PENDING
            and (r.wake_at is None or r.wake_at <= now)
        ]
        # Deduplicate while preserving recovered tasks first.
        seen: set[str] = set()
        out: list[TaskRecord] = []
        for r in recovered + runnable:
            if r.task_id in seen:
                continue
            seen.add(r.task_id)
            out.append(r)
        out.sort(key=lambda r: (r.created_at, r.task_id))
        return out


# ---------------------------------------------------------------------------
# Cleanup policy (auto-expire stale waiting tasks)
# ---------------------------------------------------------------------------

# Default age threshold for sweeping a stale `needs_user_clarification`
# task whose instruction looks like trivia. One hour matches the spec.
STALE_TRIVIA_AGE_SECONDS = 3600.0

# Maximum waiting tasks the popover should ever render. Anything past
# this gets folded behind a "show more" affordance so the user does
# not see "you have 22 tasks waiting" on the front of the device.
DEFAULT_MAX_VISIBLE_IN_UI = 5

# How many retries a recovery task may accumulate before the cleanup
# rolls the rest up into a single SMS and cancels the older siblings.
RECOVERY_RETRY_ROLLUP_THRESHOLD = 3

# Lexical openers that mark an instruction as trivia the agent should
# never have queued. Conservative on purpose: we only sweep things
# that read like questions, not anything that looks like an action.
_TRIVIA_OPENER_RE = re.compile(
    r"^\s*(?:wait[,\s]+)?(?:"
    r"when did|when was|when is|when's|whens|"
    r"what is|what was|what's|whats|what does|what are|"
    r"who is|who was|who's|whos|"
    r"where is|where was|"
    r"how many|how much|how do|how does|how did|"
    r"why did|why is|why was|why are|why do|why does|"
    r"tell me about|"
    r"define|"
    r"explain"
    r")\b",
    re.IGNORECASE,
)

# Synthetic recipients that escaped from dev / test runs. These are
# safe to purge because they cannot resolve to a real human.
_DEV_TEST_RECIPIENT_RE = re.compile(
    r"(?:"
    r"omarkebrahim\+anticipy-|"
    r"@anticipy-test\.local|"
    r"@example\.com|"
    r"Anticipy plus Anticipipeline|"
    r"Anticipipeline at gmail|"
    r"Anticipipeline"
    r")",
    re.IGNORECASE,
)


def max_visible_in_ui() -> int:
    """Read the popover cap from env so the desktop shell can tune it
    without a rebuild. Falls back to DEFAULT_MAX_VISIBLE_IN_UI.
    """
    raw = (os.environ.get("ANTICIPY_TASK_QUEUE_MAX_VISIBLE_IN_UI") or "").strip()
    if not raw:
        return DEFAULT_MAX_VISIBLE_IN_UI
    try:
        n = int(raw)
        if n > 0:
            return n
    except Exception:
        pass
    return DEFAULT_MAX_VISIBLE_IN_UI


def _looks_like_trivia(instruction: str) -> bool:
    return bool(_TRIVIA_OPENER_RE.match(instruction or ""))


def _looks_like_dev_test_leak(instruction: str) -> bool:
    return bool(_DEV_TEST_RECIPIENT_RE.search(instruction or ""))


def cleanup_expired_tasks(
    *,
    now: Optional[float] = None,
    stale_trivia_age_seconds: float = STALE_TRIVIA_AGE_SECONDS,
    recovery_retry_threshold: int = RECOVERY_RETRY_ROLLUP_THRESHOLD,
    escalator: Optional[Callable[[TaskRecord], dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Apply the popover cleanup policy. Returns a summary dict.

    Policy (see planning/00-handoff/QUEUE_AUDIT.md):

    1. `status=waiting`, `waiting_reason=needs_user_clarification`,
       `age > stale_trivia_age_seconds`, and the instruction matches a
       trivia opener (lexical: "wait, when did", "what is", etc.) ->
       cancel with `reason=stale_trivia_swept`.

    2. `status=waiting`, instruction contains a known dev-test
       recipient pattern -> cancel with `reason=dev_test_leak_purged`.

    3. `status=waiting`, `waiting_reason` starts with `recovery:`,
       grouped by the same `recovery_failure_kind` per account. If the
       total retry_count across the group exceeds the threshold OR the
       group has more than `recovery_retry_threshold + 1` siblings,
       call the escalator on the newest sibling (the caller wires this
       to `failure_recovery.route_recovery` so the user gets ONE SMS),
       then cancel the older siblings with `reason=rolled_up`.

    The function never deletes journal entries; it only appends cancel
    events so the audit trail stays intact.
    """
    t = float(now if now is not None else time.time())
    summary = {
        "cancelled": 0,
        "escalated": 0,
        "kept": 0,
        "stale_trivia_swept": 0,
        "dev_test_leak_purged": 0,
        "rolled_up": 0,
        "real_kept": 0,
        "recovery_kept": 0,
        "examples": {
            "stale_trivia_swept": [],
            "dev_test_leak_purged": [],
            "rolled_up": [],
            "real_kept": [],
            "recovery_kept": [],
        },
    }

    with _LOCK:
        _ensure_loaded()
        waiting = [r for r in _TASKS.values() if r.status == STATUS_WAITING]

        # Group recovery tasks so we can roll up by (account, kind).
        recovery_groups: dict[tuple[str, str], list[TaskRecord]] = {}
        for rec in waiting:
            wr = rec.waiting_reason or ""
            if not wr.startswith("recovery:"):
                continue
            kind = (rec.metadata or {}).get("recovery_failure_kind") or wr
            key = (rec.account_id or "", str(kind))
            recovery_groups.setdefault(key, []).append(rec)

        # Pass 1: stale trivia + dev_test_leak.
        for rec in waiting:
            wr = rec.waiting_reason or ""
            if wr.startswith("recovery:"):
                continue  # handled in pass 2
            age = t - (rec.created_at or t)
            instr = rec.instruction or ""
            if (wr == "needs_user_clarification"
                    and age > stale_trivia_age_seconds
                    and _looks_like_trivia(instr)):
                _cancel_internal_locked(
                    rec.task_id, reason="stale_trivia_swept",
                )
                summary["cancelled"] += 1
                summary["stale_trivia_swept"] += 1
                if len(summary["examples"]["stale_trivia_swept"]) < 5:
                    summary["examples"]["stale_trivia_swept"].append(
                        rec.task_id
                    )
                continue
            if _looks_like_dev_test_leak(instr):
                _cancel_internal_locked(
                    rec.task_id, reason="dev_test_leak_purged",
                )
                summary["cancelled"] += 1
                summary["dev_test_leak_purged"] += 1
                if len(summary["examples"]["dev_test_leak_purged"]) < 5:
                    summary["examples"]["dev_test_leak_purged"].append(
                        rec.task_id
                    )
                continue
            # Surviving non-recovery waiting tasks are "real": user
            # genuinely needs to clarify. Keep them.
            summary["kept"] += 1
            summary["real_kept"] += 1
            if len(summary["examples"]["real_kept"]) < 5:
                summary["examples"]["real_kept"].append(rec.task_id)

        # Pass 2: recovery rollup. Group by (account, failure_kind);
        # if the group's retries are over budget OR there are more
        # than threshold+1 siblings, escalate the newest and roll
        # everything else up.
        for (account, kind), group in recovery_groups.items():
            group.sort(key=lambda r: r.created_at or 0.0)
            total_retries = sum(int(r.retry_count or 0) for r in group)
            over_retries = total_retries > recovery_retry_threshold
            too_many_siblings = len(group) > (recovery_retry_threshold + 1)
            keep = group[-1]  # newest
            if over_retries or too_many_siblings:
                # Escalate the newest task via the supplied callback.
                escalated_ok = False
                if escalator is not None:
                    try:
                        res = escalator(keep) or {}
                        escalated_ok = bool(res.get("ok"))
                    except Exception:
                        escalated_ok = False
                if escalated_ok:
                    summary["escalated"] += 1
                # Roll up older siblings even if the escalator failed:
                # the user already has 20 cards in the popover, we are
                # not going to keep them just because Twilio is down.
                for sib in group[:-1]:
                    _cancel_internal_locked(
                        sib.task_id, reason="rolled_up",
                    )
                    summary["cancelled"] += 1
                    summary["rolled_up"] += 1
                    if len(summary["examples"]["rolled_up"]) < 5:
                        summary["examples"]["rolled_up"].append(sib.task_id)
                summary["kept"] += 1
                summary["recovery_kept"] += 1
                if len(summary["examples"]["recovery_kept"]) < 5:
                    summary["examples"]["recovery_kept"].append(keep.task_id)
            else:
                # Under budget: keep every recovery sibling.
                for sib in group:
                    summary["kept"] += 1
                    summary["recovery_kept"] += 1
                    if len(summary["examples"]["recovery_kept"]) < 5:
                        summary["examples"]["recovery_kept"].append(
                            sib.task_id
                        )

    summary["max_visible_in_ui"] = max_visible_in_ui()
    return summary


def _cancel_internal_locked(task_id: str, *, reason: str) -> Optional[TaskRecord]:
    """Internal cancel that assumes the caller holds _LOCK already and
    appends an audit-friendly cancel event. Mirrors `cancel()` but
    skips the lock reentry to keep the cleanup pass atomic.
    """
    rec = _TASKS.get(task_id)
    if rec is None:
        return None
    if rec.status in _TERMINAL_STATUSES:
        return rec
    now = time.time()
    rec.status = STATUS_CANCELLED
    rec.completed_at = now
    rec.updated_at = now
    rec.last_error = str(reason or "")[:512]
    _append_journal_locked("cancel", rec, {"reason": reason})
    return rec


def rebuild_index_from_journal() -> dict[str, Any]:
    """Diagnostic / repair helper. Drops the in-memory state, replays
    the journal, writes a fresh index. Returns a summary.
    """
    with _LOCK:
        global _LOADED, _TASKS, _INDEX_OFFSET
        _LOADED = False
        _TASKS = {}
        _INDEX_OFFSET = 0
        _ensure_loaded()
        return {
            "tasks": len(_TASKS),
            "journal_offset": _INDEX_OFFSET,
            "journal_path": str(_journal_path()),
            "index_path": str(_index_path()),
        }
