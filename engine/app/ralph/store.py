"""SQLite-backed persistence for the Ralph loop.

Implements the goals + goal_steps tables described in
planning/00-handoff/RALPH_LOOP.md (Phase 4-1). Stdlib sqlite3 only,
WAL mode, thread-safe via a per-instance RLock.

This module owns CRUD only. Failure classification, recovery dispatch,
wake-up polling, and verification layers live in sibling modules added
in later P4 phases (P4-2 ... P4-8) and import Goal / GoalStep / RalphStore
from here.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

# Goal status enum values per RALPH_LOOP.md.
VALID_STATUSES: frozenset[str] = frozenset(
    {
        "pending",
        "running",
        "wait_user",
        "wait_retry",
        "done",
        "failed",
        "cancelled",
    }
)

VALID_STEP_RESULTS: frozenset[str] = frozenset({"pass", "fail"})

# Columns that update_goal_status accepts as keyword overrides. Anything
# outside this set raises ValueError to keep the schema honest.
GOAL_UPDATABLE_COLUMNS: frozenset[str] = frozenset(
    {
        "cost_usd",
        "cost_cap_usd",
        "consecutive_failures",
        "next_attempt_at",
        "surface",
        "channel_payload",
        "final_artifact_path",
    }
)

DEFAULT_DB_PATH: Path = (
    Path(os.environ.get("ANTICIPY_RALPH_DB", "")).expanduser()
    if os.environ.get("ANTICIPY_RALPH_DB")
    else Path.home() / ".anticipy" / "v7" / "ralph.db"
)

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class CostCapExceeded(Exception):
    """Raised by bump_cost when a goal's cumulative spend exceeds its cap."""

    def __init__(self, goal_id: str, cost_usd: float, cost_cap_usd: float):
        self.goal_id = goal_id
        self.cost_usd = cost_usd
        self.cost_cap_usd = cost_cap_usd
        super().__init__(
            f"goal {goal_id} cost ${cost_usd:.4f} exceeds cap ${cost_cap_usd:.4f}"
        )


@dataclass
class Goal:
    """Mirrors a row in the goals table."""

    goal_id: str
    user_id: str
    goal_text: str
    origin: Optional[str]
    status: str
    cost_usd: float
    cost_cap_usd: float
    consecutive_failures: int
    next_attempt_at: Optional[int]
    created_at: int
    updated_at: int
    surface: Optional[str]
    channel_payload: Optional[str]
    final_artifact_path: Optional[str]

    def channel_payload_dict(self) -> Optional[dict[str, Any]]:
        """Parse channel_payload JSON if present, else None."""
        if not self.channel_payload:
            return None
        try:
            return json.loads(self.channel_payload)
        except (ValueError, TypeError):
            return None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GoalStep:
    """Mirrors a row in the goal_steps table."""

    step_id: str
    goal_id: str
    step_index: int
    action: str
    action_payload: Optional[str]
    pre_state_hash: Optional[str]
    post_state_hash: Optional[str]
    result: Optional[str]
    failure_class: Optional[str]
    failure_detail: Optional[str]
    retry_count: int
    cost_usd: float
    duration_ms: Optional[int]
    started_at: int
    ended_at: Optional[int]

    def action_payload_dict(self) -> Optional[dict[str, Any]]:
        """Parse action_payload JSON if present, else None."""
        if not self.action_payload:
            return None
        try:
            return json.loads(self.action_payload)
        except (ValueError, TypeError):
            return None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_ts() -> int:
    """Unix seconds, integer. Matches RALPH_LOOP.md's wake-up SELECT."""
    return int(time.time())


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _row_to_goal(row: sqlite3.Row) -> Goal:
    return Goal(
        goal_id=row["goal_id"],
        user_id=row["user_id"],
        goal_text=row["goal_text"],
        origin=row["origin"],
        status=row["status"],
        cost_usd=float(row["cost_usd"]),
        cost_cap_usd=float(row["cost_cap_usd"]),
        consecutive_failures=int(row["consecutive_failures"]),
        next_attempt_at=row["next_attempt_at"],
        created_at=int(row["created_at"]),
        updated_at=int(row["updated_at"]),
        surface=row["surface"],
        channel_payload=row["channel_payload"],
        final_artifact_path=row["final_artifact_path"],
    )


def _row_to_step(row: sqlite3.Row) -> GoalStep:
    return GoalStep(
        step_id=row["step_id"],
        goal_id=row["goal_id"],
        step_index=int(row["step_index"]),
        action=row["action"],
        action_payload=row["action_payload"],
        pre_state_hash=row["pre_state_hash"],
        post_state_hash=row["post_state_hash"],
        result=row["result"],
        failure_class=row["failure_class"],
        failure_detail=row["failure_detail"],
        retry_count=int(row["retry_count"]),
        cost_usd=float(row["cost_usd"]),
        duration_ms=row["duration_ms"],
        started_at=int(row["started_at"]),
        ended_at=row["ended_at"],
    )


class RalphStore:
    """SQLite wrapper for the Ralph loop persistence layer.

    Thread-safe: a single connection is shared across threads with
    check_same_thread=False and serialized behind a per-instance RLock.
    Foreign keys are enabled. WAL mode is set at first open.
    """

    def __init__(self, db_path: Optional[Path | str] = None):
        path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
        path = Path(path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            isolation_level=None,  # autocommit so PRAGMAs and DDL apply immediately
            timeout=30.0,
        )
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    # --- lifecycle -------------------------------------------------------

    def _init_db(self) -> None:
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.execute("PRAGMA busy_timeout=30000")
            schema = _SCHEMA_PATH.read_text(encoding="utf-8")
            self._conn.executescript(schema)

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass

    def __enter__(self) -> "RalphStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # --- goals -----------------------------------------------------------

    def create_goal(
        self,
        user_id: str,
        goal_text: str,
        origin: Optional[str] = None,
        cost_cap_usd: float = 0.05,
        *,
        status: str = "pending",
        surface: Optional[str] = None,
        channel_payload: Optional[dict[str, Any] | str] = None,
    ) -> str:
        """Create a goal row, return its goal_id."""
        if status not in VALID_STATUSES:
            raise ValueError(f"invalid status {status!r}")
        goal_id = _new_id("g")
        now = _now_ts()
        payload_text = _payload_to_text(channel_payload)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO goals (
                    goal_id, user_id, goal_text, origin, status,
                    cost_usd, cost_cap_usd, consecutive_failures,
                    next_attempt_at, created_at, updated_at,
                    surface, channel_payload, final_artifact_path
                ) VALUES (?, ?, ?, ?, ?, 0, ?, 0, NULL, ?, ?, ?, ?, NULL)
                """,
                (
                    goal_id,
                    user_id,
                    goal_text,
                    origin,
                    status,
                    float(cost_cap_usd),
                    now,
                    now,
                    surface,
                    payload_text,
                ),
            )
        return goal_id

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM goals WHERE goal_id = ?", (goal_id,)
            ).fetchone()
        return _row_to_goal(row) if row else None

    def update_goal_status(self, goal_id: str, status: str, **kwargs: Any) -> None:
        """Update status (and optional columns) atomically.

        kwargs may include any column in GOAL_UPDATABLE_COLUMNS. updated_at
        is always bumped.
        """
        if status not in VALID_STATUSES:
            raise ValueError(f"invalid status {status!r}")
        sets = ["status = ?", "updated_at = ?"]
        values: list[Any] = [status, _now_ts()]
        for key, value in kwargs.items():
            if key not in GOAL_UPDATABLE_COLUMNS:
                raise ValueError(f"column {key!r} not updatable via update_goal_status")
            if key == "channel_payload":
                value = _payload_to_text(value)
            sets.append(f"{key} = ?")
            values.append(value)
        values.append(goal_id)
        sql = f"UPDATE goals SET {', '.join(sets)} WHERE goal_id = ?"
        with self._lock:
            cur = self._conn.execute(sql, values)
            if cur.rowcount == 0:
                raise KeyError(f"goal {goal_id!r} not found")

    def bump_cost(self, goal_id: str, usd: float) -> float:
        """Atomically add `usd` to goal.cost_usd.

        Raises CostCapExceeded if the new total exceeds cost_cap_usd. The
        increment IS applied even when the cap is breached (so callers see
        the actual spend that pushed them over), but the exception fires
        so the caller can pause the goal.

        Returns the new cumulative cost_usd.
        """
        if usd < 0:
            raise ValueError("bump_cost expects non-negative usd")
        now = _now_ts()
        with self._lock:
            row = self._conn.execute(
                "SELECT cost_usd, cost_cap_usd FROM goals WHERE goal_id = ?",
                (goal_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"goal {goal_id!r} not found")
            new_cost = float(row["cost_usd"]) + float(usd)
            cap = float(row["cost_cap_usd"])
            self._conn.execute(
                "UPDATE goals SET cost_usd = ?, updated_at = ? WHERE goal_id = ?",
                (new_cost, now, goal_id),
            )
            if new_cost > cap:
                raise CostCapExceeded(goal_id, new_cost, cap)
        return new_cost

    def schedule_retry(self, goal_id: str, next_attempt_at: int) -> None:
        """Mark goal wait_retry and set next_attempt_at unix ts."""
        self.update_goal_status(
            goal_id,
            "wait_retry",
            next_attempt_at=int(next_attempt_at),
        )

    def due_for_retry(self, limit: int = 10) -> list[Goal]:
        """Goals ready to wake up. Matches the wake-up SELECT in RALPH_LOOP.md.

        SELECT goals where status='wait_retry' AND next_attempt_at <= now,
        ordered by next_attempt_at ASC, limited.
        """
        now = _now_ts()
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM goals
                 WHERE status = 'wait_retry'
                   AND next_attempt_at IS NOT NULL
                   AND next_attempt_at <= ?
                 ORDER BY next_attempt_at ASC
                 LIMIT ?
                """,
                (now, int(limit)),
            ).fetchall()
        return [_row_to_goal(r) for r in rows]

    # --- steps -----------------------------------------------------------

    def add_step(
        self,
        goal_id: str,
        action: str,
        action_payload: Optional[dict[str, Any] | str] = None,
        pre_state_hash: Optional[str] = None,
    ) -> str:
        """Append a step. step_index auto-increments per goal."""
        step_id = _new_id("s")
        now = _now_ts()
        payload_text = _payload_to_text(action_payload)
        with self._lock:
            # Verify FK target exists explicitly (clearer error than the FK trigger).
            row = self._conn.execute(
                "SELECT 1 FROM goals WHERE goal_id = ?", (goal_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"goal {goal_id!r} not found")
            next_index_row = self._conn.execute(
                "SELECT COALESCE(MAX(step_index), -1) + 1 AS next_idx FROM goal_steps WHERE goal_id = ?",
                (goal_id,),
            ).fetchone()
            step_index = int(next_index_row["next_idx"])
            self._conn.execute(
                """
                INSERT INTO goal_steps (
                    step_id, goal_id, step_index, action, action_payload,
                    pre_state_hash, post_state_hash, result,
                    failure_class, failure_detail, retry_count,
                    cost_usd, duration_ms, started_at, ended_at
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, 0, 0, NULL, ?, NULL)
                """,
                (
                    step_id,
                    goal_id,
                    step_index,
                    action,
                    payload_text,
                    pre_state_hash,
                    now,
                ),
            )
        return step_id

    def complete_step(
        self,
        step_id: str,
        post_state_hash: Optional[str],
        result: str,
        failure_class: Optional[str] = None,
        failure_detail: Optional[str] = None,
        cost_usd: float = 0.0,
        duration_ms: Optional[int] = None,
    ) -> None:
        """Mark a step finished. result must be 'pass' or 'fail'."""
        if result not in VALID_STEP_RESULTS:
            raise ValueError(f"invalid result {result!r}")
        now = _now_ts()
        with self._lock:
            cur = self._conn.execute(
                """
                UPDATE goal_steps SET
                    post_state_hash = ?,
                    result = ?,
                    failure_class = ?,
                    failure_detail = ?,
                    cost_usd = ?,
                    duration_ms = ?,
                    ended_at = ?
                 WHERE step_id = ?
                """,
                (
                    post_state_hash,
                    result,
                    failure_class,
                    failure_detail,
                    float(cost_usd),
                    duration_ms,
                    now,
                    step_id,
                ),
            )
            if cur.rowcount == 0:
                raise KeyError(f"step {step_id!r} not found")

    def goal_steps(self, goal_id: str) -> list[GoalStep]:
        """All steps for a goal, ordered by step_index ASC."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM goal_steps WHERE goal_id = ? ORDER BY step_index ASC",
                (goal_id,),
            ).fetchall()
        return [_row_to_step(r) for r in rows]

    # --- introspection ---------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """Counts by status + cost rollups (last 24h, current calendar day, month).

        Returns a dict shaped:
          {
            "by_status": {status: count, ...},
            "total_goals": int,
            "cost_last_24h_usd": float,
            "cost_today_usd": float,
            "cost_month_usd": float,
          }

        Day/month boundaries are derived from server-local time so they
        line up with how user-facing receipts read.
        """
        now = _now_ts()
        day_start = now - 86_400
        # Calendar-day and calendar-month boundaries (local time).
        local_now = time.localtime(now)
        cal_day_start = int(
            time.mktime(
                (
                    local_now.tm_year,
                    local_now.tm_mon,
                    local_now.tm_mday,
                    0,
                    0,
                    0,
                    0,
                    0,
                    -1,
                )
            )
        )
        cal_month_start = int(
            time.mktime(
                (
                    local_now.tm_year,
                    local_now.tm_mon,
                    1,
                    0,
                    0,
                    0,
                    0,
                    0,
                    -1,
                )
            )
        )
        with self._lock:
            by_status: dict[str, int] = {}
            for row in self._conn.execute(
                "SELECT status, COUNT(*) AS n FROM goals GROUP BY status"
            ):
                by_status[row["status"]] = int(row["n"])
            total = int(
                self._conn.execute("SELECT COUNT(*) AS n FROM goals").fetchone()["n"]
            )
            cost_24h = float(
                self._conn.execute(
                    "SELECT COALESCE(SUM(cost_usd), 0.0) AS s FROM goals WHERE updated_at >= ?",
                    (day_start,),
                ).fetchone()["s"]
            )
            cost_today = float(
                self._conn.execute(
                    "SELECT COALESCE(SUM(cost_usd), 0.0) AS s FROM goals WHERE updated_at >= ?",
                    (cal_day_start,),
                ).fetchone()["s"]
            )
            cost_month = float(
                self._conn.execute(
                    "SELECT COALESCE(SUM(cost_usd), 0.0) AS s FROM goals WHERE updated_at >= ?",
                    (cal_month_start,),
                ).fetchone()["s"]
            )
        return {
            "by_status": by_status,
            "total_goals": total,
            "cost_last_24h_usd": cost_24h,
            "cost_today_usd": cost_today,
            "cost_month_usd": cost_month,
        }


# --- helpers ------------------------------------------------------------


def _payload_to_text(payload: Optional[dict[str, Any] | str]) -> Optional[str]:
    """Accept dict (JSON-encoded) or already-encoded string. None -> None."""
    if payload is None:
        return None
    if isinstance(payload, str):
        return payload
    if isinstance(payload, (dict, list)):
        return json.dumps(payload, separators=(",", ":"))
    raise TypeError(
        f"channel_payload / action_payload must be dict, list, str, or None; got {type(payload).__name__}"
    )
