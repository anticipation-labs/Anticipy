"""Event sourced durable workflow runtime, cut in P0 before anything
uses it.

Every task that can outlive a single decision (a suspended intent
waiting on a user reply, a multi step compound task, a handoff awaiting
clarification) is a durable workflow from the moment it is created. A
crash, sleep, app close, or restart resumes exactly where it left off
without re executing completed steps. The product property this
guarantees: the user tells it something, the laptop sleeps, nothing is
forgotten.

The model is deterministic replay, the same pattern Temporal uses,
implemented in process and backed by SQLite under the adapter data dir
at single user scale. The same event sourced journal scales to the multi
tenant Postgres form with no interface change, so the storage is reached
only through this module.

Determinism contract for workflow functions:

  - All side effects and all nondeterminism go through ctx.journal_step.
  - On resume the function runs again from the top. Each journal_step
    whose result is already in the journal returns that stored result
    without calling the function body (replay). Steps not yet journaled
    execute for real (at least once with idempotent steps).
  - ctx.await_external suspends the workflow until an external event with
    the given key is delivered, or its deadline passes. Suspension
    survives a process kill.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from app.anticipy import platform_adapter

WorkflowFn = Callable[["WorkflowContext"], Awaitable[Any]]

_registry: dict[str, WorkflowFn] = {}
_db_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is not None:
        return _conn
    path = platform_adapter.data_dir() / "durable.sqlite3"
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS workflows (
            workflow_id TEXT PRIMARY KEY,
            wf_type     TEXT NOT NULL,
            input_json  TEXT NOT NULL,
            status      TEXT NOT NULL,
            result_json TEXT,
            await_key   TEXT,
            await_deadline REAL,
            created_ts  REAL NOT NULL,
            updated_ts  REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS journal (
            workflow_id TEXT NOT NULL,
            idem_key    TEXT NOT NULL,
            step_name   TEXT NOT NULL,
            result_json TEXT NOT NULL,
            ts          REAL NOT NULL,
            PRIMARY KEY (workflow_id, idem_key)
        );
        CREATE TABLE IF NOT EXISTS events (
            workflow_id TEXT NOT NULL,
            event_key   TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            delivered_ts REAL NOT NULL,
            consumed    INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (workflow_id, event_key)
        );
        """
    )
    conn.commit()
    _conn = conn
    return conn


def reset_runtime_for_tests() -> None:
    """Drop the in process connection handle so a fresh process or a
    test with a different ANTICIPY_DATA_DIR rebinds cleanly. Does not
    delete data.
    """
    global _conn
    with _db_lock:
        if _conn is not None:
            _conn.close()
            _conn = None


def register_workflow(wf_type: str, fn: WorkflowFn) -> None:
    _registry[wf_type] = fn


class _Suspend(Exception):
    """Raised inside a workflow when it must wait for an external event.
    Unwinds to the runtime, which persists the suspension and returns.
    """

    def __init__(self, event_key: str, deadline: Optional[float]) -> None:
        self.event_key = event_key
        self.deadline = deadline


@dataclass
class WorkflowContext:
    workflow_id: str
    wf_type: str
    input: dict
    _step_counts: dict[str, int]

    async def journal_step(self, name: str, fn: Callable[[], Any]) -> Any:
        """Run fn exactly once across the whole life of the workflow.
        On replay the journaled result is returned without calling fn.
        fn may be sync or return an awaitable.
        """
        self._step_counts[name] = self._step_counts.get(name, 0) + 1
        idem_key = f"{name}#{self._step_counts[name]}"
        with _db_lock:
            row = _db().execute(
                "SELECT result_json FROM journal WHERE workflow_id=? AND idem_key=?",
                (self.workflow_id, idem_key),
            ).fetchone()
        if row is not None:
            return json.loads(row[0])
        result = fn()
        if asyncio.iscoroutine(result) or isinstance(result, Awaitable):
            result = await result
        with _db_lock:
            _db().execute(
                "INSERT OR REPLACE INTO journal VALUES (?,?,?,?,?)",
                (self.workflow_id, idem_key, name, json.dumps(result), time.time()),
            )
            _db().commit()
        return result

    async def await_external(self, event_key: str, timeout_s: Optional[float] = None) -> Any:
        """Suspend until an event with event_key is delivered or the
        deadline passes. The deadline is recorded so the 3 hour rule can
        act on silence. Survives a process kill.
        """
        with _db_lock:
            row = _db().execute(
                "SELECT payload_json FROM events WHERE workflow_id=? AND event_key=?",
                (self.workflow_id, event_key),
            ).fetchone()
        if row is not None:
            return json.loads(row[0])
        deadline = None
        if timeout_s is not None:
            base = self.input.get("_clock_base_s")
            now = base if base is not None else time.time()
            deadline = now + timeout_s
        raise _Suspend(event_key, deadline)


def _set_status(wf_id: str, status: str, result: Any = None, await_key: Optional[str] = None, deadline: Optional[float] = None) -> None:
    with _db_lock:
        _db().execute(
            "UPDATE workflows SET status=?, result_json=?, await_key=?, await_deadline=?, updated_ts=? WHERE workflow_id=?",
            (status, json.dumps(result) if result is not None else None, await_key, deadline, time.time(), wf_id),
        )
        _db().commit()


async def _drive(wf_id: str) -> dict:
    with _db_lock:
        row = _db().execute(
            "SELECT wf_type, input_json FROM workflows WHERE workflow_id=?", (wf_id,)
        ).fetchone()
    if row is None:
        return {"status": "missing"}
    wf_type, input_json = row
    fn = _registry.get(wf_type)
    if fn is None:
        return {"status": "unregistered", "wf_type": wf_type}
    ctx = WorkflowContext(wf_id, wf_type, json.loads(input_json), {})
    try:
        result = await fn(ctx)
    except _Suspend as s:
        _set_status(wf_id, "suspended", await_key=s.event_key, deadline=s.deadline)
        return {"status": "suspended", "await_key": s.event_key, "deadline": s.deadline}
    _set_status(wf_id, "completed", result=result)
    return {"status": "completed", "result": result}


def start_workflow(wf_type: str, wf_id: str, input: dict) -> dict:
    with _db_lock:
        existing = _db().execute(
            "SELECT status FROM workflows WHERE workflow_id=?", (wf_id,)
        ).fetchone()
        if existing is None:
            now = time.time()
            _db().execute(
                "INSERT INTO workflows (workflow_id, wf_type, input_json, status, created_ts, updated_ts) VALUES (?,?,?,?,?,?)",
                (wf_id, wf_type, json.dumps(input), "running", now, now),
            )
            _db().commit()
    return asyncio.run(_drive(wf_id))


def deliver_event(wf_id: str, event_key: str, payload: Any) -> dict:
    """Record an external event and resume the workflow. The resumed run
    replays the journal, so completed steps are not re executed.
    """
    with _db_lock:
        _db().execute(
            "INSERT OR REPLACE INTO events VALUES (?,?,?,?,0)",
            (wf_id, event_key, json.dumps(payload), time.time()),
        )
        _db().commit()
    return asyncio.run(_drive(wf_id))


def fire_timeout(wf_id: str) -> dict:
    """The 3 hour rule delivers silence as a synthetic timeout event for
    a suspended workflow whose deadline has passed. Returns the workflow
    outcome. Carve out enforcement (money, ultra high risk comms) lives
    in the comms layer, which decides whether to call this at all.
    """
    with _db_lock:
        row = _db().execute(
            "SELECT await_key FROM workflows WHERE workflow_id=? AND status='suspended'",
            (wf_id,),
        ).fetchone()
    if row is None:
        return {"status": "not_suspended"}
    return deliver_event(wf_id, row[0], {"_timeout": True})


def resume_all() -> list[dict]:
    """Called on startup. Replays every workflow that was running or
    suspended. A workflow killed mid step had not journaled that step,
    so the step re executes (at least once, steps are idempotent). A
    suspended workflow re suspends unless its event already arrived.
    """
    with _db_lock:
        rows = _db().execute(
            "SELECT workflow_id FROM workflows WHERE status IN ('running','suspended')"
        ).fetchall()
    out = []
    for (wf_id,) in rows:
        out.append({"workflow_id": wf_id, **asyncio.run(_drive(wf_id))})
    return out


def get_workflow(wf_id: str) -> Optional[dict]:
    with _db_lock:
        row = _db().execute(
            "SELECT wf_type, status, result_json, await_key, await_deadline FROM workflows WHERE workflow_id=?",
            (wf_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "workflow_id": wf_id,
        "wf_type": row[0],
        "status": row[1],
        "result": json.loads(row[2]) if row[2] else None,
        "await_key": row[3],
        "await_deadline": row[4],
    }


def list_suspended() -> list[dict]:
    with _db_lock:
        rows = _db().execute(
            "SELECT workflow_id, await_key, await_deadline FROM workflows WHERE status='suspended'"
        ).fetchall()
    return [{"workflow_id": r[0], "await_key": r[1], "await_deadline": r[2]} for r in rows]
