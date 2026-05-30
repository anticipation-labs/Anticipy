"""Per task cost telemetry and budget enforcement.

Anticipy targets $200/user/year at 100,000 tasks, which means a
$0.002/task ceiling. This module makes that mechanical:

  start_task(task_id)             records start_ts, init cost=0
  record_call(task_id, model, ..) accumulates cost + call counts
  current_task_cost(task_id)      running total used by the gate
  get_per_task_stats(last_n=100)  p50 / median / p95 across recent
                                  finished tasks plus the running
                                  daily and weekly per-user totals
  finish_task(task_id, status)    move from active -> recent so the
                                  next start_task does not collide
  budget_gate(task_id)            string reason to refuse the next
                                  model_call, or None to allow it

The product server wires:
  - cost_telemetry.set_active_for_thread(task_id) at /api/act start
  - platform_adapter.bind_active_task_id(task_id) on the SAME thread
  - platform_adapter.set_telemetry_sink(record_call_from_log_row)
  - platform_adapter.set_budget_gate(budget_gate)
  - finish_task(task_id, status) when the response is sent

Vision call gate is wired separately (record_vision_call). Tasks that
use more than VISION_WARN_COUNT vision calls log a warning; tasks
that use more than VISION_ABORT_COUNT vision calls are aborted by the
gate (the next model_call returns BUDGET_EXCEEDED).

Per-task ceilings:
  PER_TASK_CEILING_USD = 0.002 (the $200/100k math)
  PER_TASK_HARD_CAP_USD = 0.005 (2.5x ceiling, the abort line per spec)
  VISION_WARN_COUNT = 3 (canvas apps are vision-heavy; warn)
  VISION_ABORT_COUNT = 5 (per spec: more than 5 -> abort, follow-up)

Everything is best effort. Storage is an in-memory deque plus the
existing model_calls.jsonl on disk (we do not duplicate logging).
"""

from __future__ import annotations

import collections
import statistics
import threading
import time
from typing import Optional

# ---------------------------------------------------------------------------
# Ceilings
# ---------------------------------------------------------------------------

PER_TASK_CEILING_USD = 0.002
PER_TASK_HARD_CAP_USD = 0.005  # spec: 2.5x ceiling
VISION_WARN_COUNT = 3
VISION_ABORT_COUNT = 5

# Daily / weekly per-user budget guards. $200/year / 365 = ~$0.55/day,
# /52 = ~$3.85/week. We expose these for the /api/cost/stats endpoint
# so the operator (and the gate, later) can see headroom at a glance.
DAILY_BUDGET_USD = 0.55
WEEKLY_BUDGET_USD = 3.85

# How many recent finished tasks we keep for the percentile stats.
_RECENT_TASKS_MAX = 500


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

_lock = threading.RLock()
_active: dict[str, dict] = {}
_recent: collections.deque = collections.deque(maxlen=_RECENT_TASKS_MAX)
# Rolling per-call log for daily / weekly totals. We only keep the
# minimum fields needed to compute the running totals; the full row
# stays in the JSONL on disk.
_call_log: collections.deque = collections.deque(maxlen=20_000)
# Optional per-task thread binding so the gate works for callers that
# do not pass an explicit task_id (legacy onboarding, taxonomy, etc.).
_active_per_thread = threading.local()


def _now() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def start_task(task_id: str) -> None:
    """Begin tracking cost for a new task. Idempotent: a second call
    with the same id is a no-op so retried planners do not zero out
    accumulated cost."""
    if not task_id:
        return
    with _lock:
        if task_id in _active:
            return
        _active[task_id] = {
            "task_id": str(task_id),
            "started_at": _now(),
            "cost_usd": 0.0,
            "call_count": 0,
            "vision_call_count": 0,
            "models": {},
            "first_model": "",
            "warnings": [],
            "aborted": False,
        }


def record_call(
    task_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    is_vision: bool = False,
) -> None:
    """Accumulate one model call into the per-task ledger."""
    if not task_id:
        return
    with _lock:
        rec = _active.get(task_id)
        if rec is None:
            # Task started outside the wrapped path. Create it on the
            # fly so the call still gets counted; this is the only
            # branch that lets a caller mint a task id without start.
            start_task(task_id)
            rec = _active.get(task_id)
            if rec is None:
                return
        rec["call_count"] = int(rec.get("call_count", 0)) + 1
        rec["cost_usd"] = float(rec.get("cost_usd", 0.0)) + float(cost_usd or 0.0)
        if is_vision:
            rec["vision_call_count"] = int(rec.get("vision_call_count", 0)) + 1
        models = rec.setdefault("models", {})
        m_key = str(model or "unknown")
        m_stat = models.setdefault(m_key, {
            "calls": 0, "cost_usd": 0.0,
            "input_tokens": 0, "output_tokens": 0,
            "vision_calls": 0,
        })
        m_stat["calls"] += 1
        m_stat["cost_usd"] = float(m_stat.get("cost_usd", 0.0)) + float(cost_usd or 0.0)
        m_stat["input_tokens"] = int(m_stat.get("input_tokens", 0)) + int(input_tokens or 0)
        m_stat["output_tokens"] = int(m_stat.get("output_tokens", 0)) + int(output_tokens or 0)
        if is_vision:
            m_stat["vision_calls"] = int(m_stat.get("vision_calls", 0)) + 1
        if not rec.get("first_model"):
            rec["first_model"] = m_key
        # Vision warning: log once when we cross the warn line. The
        # abort line is enforced by budget_gate; we still note it here
        # so the per-task stats reflect the count.
        if is_vision:
            cnt = rec["vision_call_count"]
            if cnt == VISION_WARN_COUNT:
                rec.setdefault("warnings", []).append(
                    f"vision_count_warn:{cnt}"
                )
            elif cnt >= VISION_ABORT_COUNT:
                rec.setdefault("warnings", []).append(
                    f"vision_count_abort:{cnt}"
                )
    # Rolling daily / weekly log lives outside the per-task lock so
    # the long deque does not block per-task readers.
    _call_log.append({
        "ts": _now(),
        "task_id": str(task_id),
        "cost_usd": float(cost_usd or 0.0),
        "model": str(model or "unknown"),
        "is_vision": bool(is_vision),
    })


def record_call_from_log_row(row: dict) -> None:
    """Sink wired to platform_adapter.set_telemetry_sink. Every model
    call goes through here. We only record rows that succeeded or that
    have a usage block; refused / budget_exceeded rows are aggregated
    by the abort path and would otherwise inflate the call count."""
    if not isinstance(row, dict):
        return
    if row.get("budget_exceeded"):
        return
    task_id = row.get("task_id") or get_active_task_id_for_thread()
    if not task_id:
        return
    cost = float(row.get("cost_usd") or 0.0)
    p_tok = int(row.get("prompt_tokens") or 0)
    c_tok = int(row.get("completion_tokens") or 0)
    if not row.get("ok") and cost == 0.0 and p_tok == 0 and c_tok == 0:
        # purely transport/HTTP failures: nothing to bill, but still
        # count the call so an OpenRouter outage cannot mask spend.
        cost = 0.0
    record_call(
        str(task_id), str(row.get("model") or "unknown"),
        p_tok, c_tok, cost,
        is_vision=bool(row.get("is_vision")),
    )


def record_vision_call(task_id: str, model: str, input_tokens: int,
                       output_tokens: int, cost_usd: float) -> None:
    """Explicit vision call recorder. The Kimi K2.6 vision path bypasses
    platform_adapter.model_call (it uses its own urllib POST in
    surface_runtime_vision.VisionSurface._post_chat), so we expose this
    helper for that adapter to call directly."""
    record_call(task_id, model, input_tokens, output_tokens, cost_usd, is_vision=True)


def current_task_cost(task_id: str) -> float:
    """Running total cost for an active task. Returns 0 for unknown."""
    if not task_id:
        return 0.0
    with _lock:
        rec = _active.get(task_id)
        if rec is None:
            return 0.0
        return float(rec.get("cost_usd", 0.0))


def current_task_record(task_id: str) -> dict:
    """Read-only snapshot of the active task's ledger."""
    if not task_id:
        return {}
    with _lock:
        rec = _active.get(task_id)
        if rec is None:
            return {}
        return dict(rec)


def finish_task(task_id: str, status: str = "ok") -> dict:
    """Move task from active -> recent. Returns the finalised record."""
    if not task_id:
        return {}
    with _lock:
        rec = _active.pop(task_id, None)
        if rec is None:
            return {}
        rec["finished_at"] = _now()
        rec["status"] = str(status or "ok")
        rec["duration_s"] = round(
            rec["finished_at"] - float(rec.get("started_at") or rec["finished_at"]), 3)
        rec["cost_usd"] = round(float(rec.get("cost_usd", 0.0)), 6)
        # Trim to scalar copies for the recent deque so callers cannot
        # mutate the snapshot.
        snapshot = {
            "task_id": str(rec.get("task_id", "")),
            "started_at": float(rec.get("started_at", 0.0)),
            "finished_at": float(rec.get("finished_at", 0.0)),
            "duration_s": float(rec.get("duration_s", 0.0)),
            "cost_usd": float(rec.get("cost_usd", 0.0)),
            "call_count": int(rec.get("call_count", 0)),
            "vision_call_count": int(rec.get("vision_call_count", 0)),
            "first_model": str(rec.get("first_model") or ""),
            "status": str(rec.get("status") or "ok"),
            "aborted": bool(rec.get("aborted")),
            "warnings": list(rec.get("warnings") or []),
            "models": {k: dict(v) for k, v in (rec.get("models") or {}).items()},
        }
        _recent.append(snapshot)
        return snapshot


def get_per_task_stats(last_n: int = 100) -> dict:
    """p50 / median / p95 across the most recent `last_n` finished
    tasks, plus the running daily and weekly per-user totals.

    Per the cost-ceiling memo: $200/user/year at 100k tasks => $0.002
    per task. The p50 line should sit well below that. The p95 line
    should sit below the $0.005 hard cap. If either drifts up, the
    vision call rate or planner cascade depth needs to come down."""
    with _lock:
        recent_snapshot = list(_recent)
        active_snapshot = [
            {
                "task_id": str(v.get("task_id", "")),
                "cost_usd": float(v.get("cost_usd", 0.0)),
                "call_count": int(v.get("call_count", 0)),
                "vision_call_count": int(v.get("vision_call_count", 0)),
                "started_at": float(v.get("started_at", 0.0)),
            }
            for v in _active.values()
        ]
    last_n = max(1, int(last_n or 100))
    window = recent_snapshot[-last_n:] if recent_snapshot else []
    costs = sorted([float(t.get("cost_usd", 0.0)) for t in window])
    call_counts = [int(t.get("call_count", 0)) for t in window]
    vision_counts = [int(t.get("vision_call_count", 0)) for t in window]

    def _pct(values: list[float], pct: float) -> float:
        if not values:
            return 0.0
        if len(values) == 1:
            return float(values[0])
        # Linear interp percentile, deterministic and dependency-free.
        idx = (len(values) - 1) * (pct / 100.0)
        lo = int(idx)
        hi = min(lo + 1, len(values) - 1)
        frac = idx - lo
        return float(values[lo]) + (float(values[hi]) - float(values[lo])) * frac

    median_cost = statistics.median(costs) if costs else 0.0
    mean_cost = statistics.fmean(costs) if costs else 0.0

    # Daily / weekly totals from the rolling per-call log. We snapshot
    # outside the lock so the long deque does not block writers.
    now = _now()
    day_cutoff = now - 24 * 3600.0
    week_cutoff = now - 7 * 24 * 3600.0
    daily_total = 0.0
    weekly_total = 0.0
    daily_calls = 0
    weekly_calls = 0
    for row in list(_call_log):
        ts = float(row.get("ts") or 0.0)
        cost = float(row.get("cost_usd") or 0.0)
        if ts >= week_cutoff:
            weekly_total += cost
            weekly_calls += 1
            if ts >= day_cutoff:
                daily_total += cost
                daily_calls += 1

    return {
        "window_size": len(window),
        "last_n_requested": last_n,
        "per_task_ceiling_usd": PER_TASK_CEILING_USD,
        "per_task_hard_cap_usd": PER_TASK_HARD_CAP_USD,
        "p50_cost_usd": round(_pct(costs, 50), 6),
        "median_cost_usd": round(float(median_cost), 6),
        "mean_cost_usd": round(float(mean_cost), 6),
        "p95_cost_usd": round(_pct(costs, 95), 6),
        "max_cost_usd": round(max(costs) if costs else 0.0, 6),
        "min_cost_usd": round(min(costs) if costs else 0.0, 6),
        "above_ceiling_count": sum(1 for c in costs if c > PER_TASK_CEILING_USD),
        "above_hard_cap_count": sum(1 for c in costs if c > PER_TASK_HARD_CAP_USD),
        "median_calls_per_task": (
            round(float(statistics.median(call_counts)), 3) if call_counts else 0.0
        ),
        "median_vision_calls_per_task": (
            round(float(statistics.median(vision_counts)), 3) if vision_counts else 0.0
        ),
        "max_vision_calls_per_task": (
            int(max(vision_counts)) if vision_counts else 0
        ),
        "running_daily_total_usd": round(daily_total, 6),
        "running_weekly_total_usd": round(weekly_total, 6),
        "daily_budget_usd": DAILY_BUDGET_USD,
        "weekly_budget_usd": WEEKLY_BUDGET_USD,
        "daily_calls": int(daily_calls),
        "weekly_calls": int(weekly_calls),
        "active_tasks": active_snapshot,
        "recent_tasks": list(reversed(window))[:100],
    }


def budget_gate(task_id: Optional[str]) -> Optional[str]:
    """Per-task budget gate. Wired into platform_adapter.set_budget_gate.
    Returns a non-empty reason string if the next model_call should be
    refused; None lets it proceed.

    Refusal conditions:
      1. Cumulative task cost has already crossed the hard cap.
      2. The task has already hit the vision abort count and the
         next call would either be a vision call or another planner
         iteration on a task we already flagged.
    """
    if not task_id:
        return None
    with _lock:
        rec = _active.get(task_id)
        if rec is None:
            return None
        if rec.get("aborted"):
            return "task already aborted"
        cost = float(rec.get("cost_usd", 0.0))
        if cost > PER_TASK_HARD_CAP_USD:
            rec["aborted"] = True
            rec.setdefault("warnings", []).append(
                f"hard_cap_exceeded:{cost:.6f}>{PER_TASK_HARD_CAP_USD}"
            )
            return (
                f"task cost ${cost:.6f} exceeds hard cap "
                f"${PER_TASK_HARD_CAP_USD:.4f} (2.5x ceiling); escalate to user"
            )
        if int(rec.get("vision_call_count", 0)) >= VISION_ABORT_COUNT:
            rec["aborted"] = True
            rec.setdefault("warnings", []).append(
                f"vision_abort:{rec['vision_call_count']}"
            )
            return (
                f"vision call count {rec['vision_call_count']} hit abort "
                f"threshold {VISION_ABORT_COUNT}; canvas app, escalate "
                "to user"
            )
    return None


# ---------------------------------------------------------------------------
# Per-thread active task helpers (mirror of the adapter's thread-local
# so callers that import only the telemetry can still read the active
# id without reaching into the adapter)
# ---------------------------------------------------------------------------


def set_active_for_thread(task_id: Optional[str]) -> None:
    if task_id:
        _active_per_thread.task_id = str(task_id)
    else:
        if hasattr(_active_per_thread, "task_id"):
            try:
                del _active_per_thread.task_id
            except Exception:
                pass


def get_active_task_id_for_thread() -> Optional[str]:
    return getattr(_active_per_thread, "task_id", None)


# ---------------------------------------------------------------------------
# Vision specific helpers
# ---------------------------------------------------------------------------


def vision_call_count(task_id: str) -> int:
    """Return how many vision calls the active task has logged."""
    if not task_id:
        return 0
    with _lock:
        rec = _active.get(task_id)
        if rec is None:
            return 0
        return int(rec.get("vision_call_count", 0))


def vision_gate(task_id: Optional[str]) -> Optional[str]:
    """Block a NEW vision call when the abort threshold is hit. Used by
    surface_runtime_vision before it dispatches to Kimi K2.6 so we do
    not silently drift past 5 vision calls per task."""
    if not task_id:
        return None
    cnt = vision_call_count(task_id)
    if cnt >= VISION_ABORT_COUNT:
        return (
            f"vision call count {cnt} reached abort threshold "
            f"{VISION_ABORT_COUNT}; canvas-only app, escalate to user "
            "follow-up"
        )
    return None


__all__ = [
    "PER_TASK_CEILING_USD",
    "PER_TASK_HARD_CAP_USD",
    "VISION_WARN_COUNT",
    "VISION_ABORT_COUNT",
    "DAILY_BUDGET_USD",
    "WEEKLY_BUDGET_USD",
    "start_task",
    "record_call",
    "record_call_from_log_row",
    "record_vision_call",
    "current_task_cost",
    "current_task_record",
    "finish_task",
    "get_per_task_stats",
    "budget_gate",
    "vision_call_count",
    "vision_gate",
    "set_active_for_thread",
    "get_active_task_id_for_thread",
]
