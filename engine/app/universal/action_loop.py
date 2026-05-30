"""Universal action loop orchestrator.

Public surface: ``run_until_done(intent, surface_hint, deadline_sec)``.

Internals:

  1. Resolve (or create) an Anticipy-owned background tab via the
     existing DSv4SkillRunner ``_ensure_agent_window`` helper. This
     guarantees the loop never hijacks one of the user's foreground
     tabs (the same ownership rule the bridge enforces; see
     ``scripts/v7/anticipy_bridge_fallback_cdp.py``: only target_ids
     that the bridge / runner explicitly created are considered
     Anticipy-owned and reusable).
  2. If ``surface_hint`` is a URL, navigate the owned tab there. Else
     leave the tab on ``about:blank`` so the loop's first decide step
     can pick the destination from the intent.
  3. Hand the typed intent to the same Ralph Loop the rest of the
     product already uses: per iteration capture screenshot + DOM
     accessibility tree + page text, ask the vision model (Kimi K2.6)
     for ONE concrete next action, dispatch over CDP, observe, check
     completion via the vision auditor on the real after-screenshot.
  4. Hard wall-clock deadline. The runner already has a max-iteration
     cap; we wrap with an outer deadline so the endpoint never blocks
     a request past the caller-supplied budget.

The loop does NOT contain any per-app code. The intent is data; the
DOM and the screenshot are data; the model decides. The same orchestrator
that drives Gmail compose drives Google Calendar event creation drives
a Salesforce opportunity update.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

from app.action_engine.cdp_dispatcher import navigate
from app.action_engine.dsv4_skill_runner import (
    DSv4SkillRunner,
    TaskResult,
    _connect_session_keepalive,
)


_logger = logging.getLogger("anticipy.universal.action_loop")


DEFAULT_CDP_PORT = int(os.environ.get("ANTICIPY_CDP_PORT", "9222"))


def _result_to_dict(result: TaskResult, *, elapsed_s: float,
                    deadline_sec: float, intent: str,
                    surface_hint: str, deadline_hit: bool) -> dict:
    """Coerce a runner TaskResult into a JSON-safe dict.

    Mirrors the shape of the runner's own manifest plus the universal
    wrapper metadata (the intent, the surface hint, wall-clock spent,
    whether the outer deadline tripped).
    """
    return {
        "intent": intent,
        "surface_hint": surface_hint,
        "status": result.status,
        "answer": str(result.answer or "")[:600],
        "evidence": str(result.evidence or "")[:600],
        "n_iterations": int(result.n_iterations or 0),
        "subtasks": list(result.subtasks or []),
        "trajectory_dir": result.trajectory_dir or "",
        "error": result.error,
        "elapsed_sec": round(float(elapsed_s), 3),
        "deadline_sec": float(deadline_sec),
        "deadline_hit": bool(deadline_hit),
    }


def run_until_done(intent: str,
                   surface_hint: str = "",
                   deadline_sec: float = 60.0,
                   *,
                   cdp_port: int = DEFAULT_CDP_PORT,
                   max_iters: int = 30) -> dict:
    """Run the universal action loop until done or deadline.

    Parameters
    ----------
    intent
        Plain-English description of what the user wants. The model
        reads this verbatim as the sub-goal each iteration.
    surface_hint
        Optional URL or domain. If it parses as a URL (starts with
        ``http://`` or ``https://``) the owned tab navigates there
        first. Otherwise it is passed through as a free-text hint
        appended to the intent so the model can decide where to go.
        Empty means leave the destination up to the model.
    deadline_sec
        Wall-clock budget. The inner Ralph Loop also has its own
        max-iteration cap; whichever trips first wins.
    cdp_port
        Chrome DevTools Protocol port. Defaults to the engine-wide
        ``ANTICIPY_CDP_PORT`` env (9222 in the shipping config).
    max_iters
        Per-subtask iteration cap for the inner runner. 30 is the
        runner's default and what every shipping path uses.

    Returns
    -------
    dict
        JSON-safe result. Keys: ``intent``, ``surface_hint``,
        ``status`` (one of SUCCESS, ITERATION_EXHAUSTED, HARD_FAIL,
        ERROR, ASK, DEADLINE_EXCEEDED), ``answer``, ``evidence``,
        ``n_iterations``, ``subtasks``, ``trajectory_dir``,
        ``error``, ``elapsed_sec``, ``deadline_sec``,
        ``deadline_hit``.
    """
    intent = (intent or "").strip()
    surface_hint = (surface_hint or "").strip()
    if not intent:
        return {
            "intent": intent,
            "surface_hint": surface_hint,
            "status": "ERROR",
            "answer": "",
            "evidence": "",
            "n_iterations": 0,
            "subtasks": [],
            "trajectory_dir": "",
            "error": "empty intent",
            "elapsed_sec": 0.0,
            "deadline_sec": float(deadline_sec),
            "deadline_hit": False,
        }

    deadline_sec = float(deadline_sec) if deadline_sec else 60.0
    start = time.monotonic()

    # The runner already encapsulates Anticipy-owned tab ownership
    # via _ensure_agent_window: it calls Target.createTarget with
    # newWindow=True, background=True and persists the resulting
    # targetId in ~/.anticipy/v4_agent_window.json. Subsequent runs
    # reuse the same window. The user's foreground tabs are never
    # touched. We piggy-back on that by handing surface_hint to the
    # runner's existing starting_url path so the owned tab navigates
    # before the first decide step.
    is_url = surface_hint.startswith(("http://", "https://"))
    starting_url = surface_hint if is_url else None
    if not is_url and surface_hint:
        # Free-text hint; the model decides the destination. Append
        # to the intent so the decider sees it as a constraint.
        task = f"{intent} (start on: {surface_hint})"
    else:
        task = intent

    runner = DSv4SkillRunner(cdp_port=cdp_port, max_iters=max_iters)

    # Run the inner loop on a worker thread so the outer deadline can
    # trip without leaving the request blocked indefinitely. The
    # underlying runner cooperatively returns on iteration exhaustion
    # / hard fail / success; the deadline thread simply checks the
    # wall-clock between iterations by relying on the runner's
    # per-iteration overhead. If the deadline trips before the runner
    # returns we synthesize a DEADLINE_EXCEEDED result and let the
    # runner's own thread finish writing its trajectory in the
    # background (the manifest still lands).
    box: dict[str, Any] = {"result": None, "error": None}

    # Snapshot the active task id from the calling thread so the worker
    # can rebind it. Without this rebind, every LLM call inside the
    # runner sees task_id=None and the budget gate has no record to
    # consult. Best-effort import: if cost telemetry is unavailable the
    # worker still runs.
    _active_task_id = None
    _ct = None
    try:
        from app.product import cost_telemetry as _ct  # type: ignore
        _active_task_id = _ct.get_active_task_id_for_thread()
    except Exception:
        _ct = None  # type: ignore

    def _worker() -> None:
        # Rebind the snapshotted task id on this worker thread so
        # OpenRouterClient.chat and platform_adapter.model_call both see
        # the same active task and the per-task budget gate / cost
        # ledger work end-to-end across the thread boundary.
        if _active_task_id:
            try:
                if _ct is not None:
                    _ct.set_active_for_thread(_active_task_id)
                from app.anticipy import platform_adapter as _pa  # type: ignore
                _pa.bind_active_task_id(_active_task_id)
            except Exception:
                pass
        try:
            tr = runner.run(task, starting_url=starting_url)
            box["result"] = tr
        except Exception as exc:  # noqa: BLE001
            box["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                if _ct is not None:
                    _ct.set_active_for_thread(None)
                from app.anticipy import platform_adapter as _pa  # type: ignore
                _pa.bind_active_task_id(None)
            except Exception:
                pass

    th = threading.Thread(target=_worker, daemon=True,
                          name="anticipy-universal-loop")
    th.start()
    th.join(timeout=deadline_sec)

    elapsed = time.monotonic() - start
    if th.is_alive():
        # Deadline exceeded. The runner thread keeps going (Python
        # has no safe thread kill) but the request returns. The
        # trajectory dir captured below is None because the runner
        # has not returned its TaskResult yet; we report what we know.
        return {
            "intent": intent,
            "surface_hint": surface_hint,
            "status": "DEADLINE_EXCEEDED",
            "answer": "",
            "evidence": (f"wall-clock {deadline_sec:.1f}s exceeded "
                          "before the loop returned"),
            "n_iterations": 0,
            "subtasks": [],
            "trajectory_dir": "",
            "error": "deadline_exceeded",
            "elapsed_sec": round(elapsed, 3),
            "deadline_sec": deadline_sec,
            "deadline_hit": True,
        }

    if box["error"]:
        return {
            "intent": intent,
            "surface_hint": surface_hint,
            "status": "ERROR",
            "answer": "",
            "evidence": "",
            "n_iterations": 0,
            "subtasks": [],
            "trajectory_dir": "",
            "error": box["error"],
            "elapsed_sec": round(elapsed, 3),
            "deadline_sec": deadline_sec,
            "deadline_hit": False,
        }

    tr: TaskResult = box["result"]
    return _result_to_dict(tr, elapsed_s=elapsed, deadline_sec=deadline_sec,
                           intent=intent, surface_hint=surface_hint,
                           deadline_hit=False)
