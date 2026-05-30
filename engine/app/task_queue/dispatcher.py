"""Background dispatcher that wakes up persistent tasks.

The store module is the durable layer. This module is the runtime layer:
it pulls due tasks off the queue every ~60 seconds, hands them to a
caller-supplied execution callback, and reports completion / failure
back to the store with retry semantics.

Wiring: ``app.product.server`` registers an executor callback at
startup, calls ``schedule_engine_restart_recovery`` to re-fire any
in-flight task left by a prior process, and starts the periodic
scanner. The dispatcher is intentionally agnostic about HOW a task
runs; the server registers a callback that re-issues the same logic
``/api/act`` would have run for a brand-new utterance.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Optional

from . import store
from .store import TaskRecord


LOGGER = logging.getLogger("engine.task_queue.dispatcher")


# Type of the execution callback the server registers. Returns a dict
# with at least the keys ``ok`` (bool) and optionally ``waiting`` (bool,
# meaning "park the task in waiting status, do not retry"),
# ``waiting_reason``, ``wake_at`` (new wake time), ``error`` (str), and
# ``result`` (any JSON-serialisable artifact to attach to the journal
# entry on success).
Executor = Callable[[TaskRecord], dict[str, Any]]


_LOCK = threading.RLock()
_EXECUTOR: Optional[Executor] = None
_THREAD: Optional[threading.Thread] = None
_STOP_EVENT = threading.Event()
_SCAN_INTERVAL_SECONDS = 60.0


def register_executor(executor: Executor) -> None:
    """The server passes its execution callback here at startup."""
    global _EXECUTOR
    with _LOCK:
        _EXECUTOR = executor


def is_running() -> bool:
    with _LOCK:
        t = _THREAD
        return bool(t and t.is_alive())


def stop() -> None:
    """Signal the scanner thread to exit. Used by tests and shutdown."""
    _STOP_EVENT.set()
    with _LOCK:
        t = _THREAD
    if t is not None and t.is_alive():
        t.join(timeout=5.0)


def schedule_engine_restart_recovery() -> list[TaskRecord]:
    """Engine startup hook. Resets any task left in_progress and
    re-fires every currently-runnable task on a background thread so
    the FastAPI startup callback returns immediately.
    """
    recovered = store.resume_after_restart()
    if not recovered:
        LOGGER.info("task_queue_restart_recovery_empty")
        return recovered
    LOGGER.info(
        "task_queue_restart_recovery_count=%d", len(recovered)
    )
    # Fire each recovered task on a separate thread so a slow executor
    # does not block startup.
    for rec in recovered:
        threading.Thread(
            target=_run_one,
            args=(rec,),
            daemon=True,
            name=f"taskq-resume-{rec.task_id[:8]}",
        ).start()
    return recovered


def start_scanner(*, interval_seconds: Optional[float] = None) -> bool:
    """Start the background scanner thread if not already running."""
    global _THREAD, _SCAN_INTERVAL_SECONDS
    with _LOCK:
        if interval_seconds and interval_seconds > 0:
            _SCAN_INTERVAL_SECONDS = float(interval_seconds)
        if _THREAD is not None and _THREAD.is_alive():
            return False
        _STOP_EVENT.clear()
        t = threading.Thread(
            target=_scan_loop,
            daemon=True,
            name="taskq-scanner",
        )
        _THREAD = t
        t.start()
        LOGGER.info(
            "task_queue_scanner_started interval_seconds=%.1f",
            _SCAN_INTERVAL_SECONDS,
        )
        return True


def _scan_loop() -> None:
    """Periodic loop: every interval_seconds, look at the queue, fire
    any due tasks, sleep again. Exits when _STOP_EVENT is set.
    """
    while not _STOP_EVENT.is_set():
        try:
            fired = scan_once()
            if fired:
                LOGGER.info("task_queue_scan_fired=%d", len(fired))
        except Exception:
            LOGGER.exception("task_queue_scan_loop_error")
        # Sleep in 1-second steps so stop() unblocks quickly.
        for _ in range(int(_SCAN_INTERVAL_SECONDS)):
            if _STOP_EVENT.is_set():
                return
            time.sleep(1.0)


def scan_once(*, now: Optional[float] = None) -> list[TaskRecord]:
    """Pull every due task off the queue and dispatch it. Public so
    tests and the server's /api/task_queue/scan endpoint can call it.
    Returns the list of records that were dispatched (for visibility).
    """
    t = float(now if now is not None else time.time())
    due = store.scan_due(t)
    fired: list[TaskRecord] = []
    for rec in due:
        # Re-check status by claiming so two concurrent scans do not
        # fire the same task twice. claim_next is FIFO; we directly
        # re-fetch by id and only fire if our claim went through.
        claimed = store.claim_next()
        if claimed is None:
            continue
        fired.append(claimed)
        threading.Thread(
            target=_run_one,
            args=(claimed,),
            daemon=True,
            name=f"taskq-fire-{claimed.task_id[:8]}",
        ).start()
    # Plus any pending tasks with no wake_at that were never claimed.
    # claim_next gives them to us; if there is no executor we leave them.
    while True:
        c = store.claim_next()
        if c is None:
            break
        fired.append(c)
        threading.Thread(
            target=_run_one,
            args=(c,),
            daemon=True,
            name=f"taskq-fire-{c.task_id[:8]}",
        ).start()
    return fired


def _run_one(rec: TaskRecord) -> None:
    """Execute one claimed task via the registered callback. Handles
    completion / waiting / failure based on the callback's result.
    """
    executor = _EXECUTOR
    if executor is None:
        LOGGER.warning(
            "task_queue_no_executor task_id=%s parking_waiting",
            rec.task_id,
        )
        store.wait_for(rec.task_id, "no_executor_registered")
        return
    try:
        result = executor(rec) or {}
    except Exception as exc:
        LOGGER.exception(
            "task_queue_executor_raised task_id=%s", rec.task_id
        )
        store.fail(rec.task_id, f"{type(exc).__name__}: {exc}")
        return
    if not isinstance(result, dict):
        store.fail(rec.task_id,
                    f"executor returned non-dict: {type(result).__name__}")
        return
    if result.get("waiting"):
        store.wait_for(
            rec.task_id,
            str(result.get("waiting_reason") or "external_dependency"),
            wake_at=result.get("wake_at"),
        )
        return
    if result.get("ok"):
        store.complete(rec.task_id, result.get("result") or result)
        return
    if result.get("reschedule_at") is not None:
        store.reschedule(rec.task_id, float(result["reschedule_at"]))
        return
    err = str(result.get("error") or "executor returned ok=false")
    store.fail(rec.task_id, err)
