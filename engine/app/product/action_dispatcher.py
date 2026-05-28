"""ActionDispatcher: drive an intent to terminal state via planner + runtime.

Loop contract: read -> plan -> act -> verify, bounded by MAX_STEPS=20.
Never returns "declined". Terminal outcomes are exactly four:
  - success: planner emitted done, OR a verify primitive returned ok
  - ask_user: planner emitted ask_user, OR we hit retry-saturation, OR we hit
    the step ceiling
  - notify: planner emitted notify_user (Anticipy informed the user)
  - in_progress: only when run_step() is called externally with no terminal
    step yet (not returned by execute())

Same-primitive retry cap: 3. After three consecutive failed primitives of the
same kind we ask the user to clarify rather than loop forever.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.product.action_planner import ActionPlanner, PlannerStep
from app.product.universal_surface_runtime import (
    PrimitiveResult, UniversalSurfaceRuntime,
)


MAX_STEPS = 20
SAME_PRIMITIVE_RETRY_CAP = 3
EVENT_LOG_DIR = Path(os.environ.get(
    "ANTICIPY_DISPATCHER_LOG",
    str(Path.home() / ".anticipy" / "dispatcher"),
))


@dataclass
class DispatchOutcome:
    status: str  # "success" | "ask_user" | "notify" | "in_progress"
    intent: str = ""
    steps: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)
    question: str = ""
    options: list[str] = field(default_factory=list)
    message: str = ""
    proof: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "intent": self.intent,
            "steps": self.steps,
            "history": list(self.history),
            "question": self.question,
            "options": list(self.options),
            "message": self.message,
            "proof": dict(self.proof),
            "error": self.error or "",
        }


class ActionDispatcher:
    """Drive an intent to terminal state. Never declines."""

    def __init__(
        self,
        *,
        runtime: UniversalSurfaceRuntime | None = None,
        planner: ActionPlanner | None = None,
        max_steps: int = MAX_STEPS,
        retry_cap: int = SAME_PRIMITIVE_RETRY_CAP,
        log_dir: Path = EVENT_LOG_DIR,
    ) -> None:
        self.runtime = runtime or UniversalSurfaceRuntime()
        self.planner = planner or ActionPlanner()
        self.max_steps = int(max_steps)
        self.retry_cap = int(retry_cap)
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def execute(
        self,
        intent: str,
        *,
        account_id: str = "",
        device_id: str = "",
        memory_context: dict[str, Any] | None = None,
    ) -> DispatchOutcome:
        intent = (intent or "").strip()
        if not intent:
            return DispatchOutcome(
                status="ask_user", intent="",
                question="What would you like me to do?",
                options=[],
            )
        history: list[dict[str, Any]] = []
        recent_primitives: list[str] = []
        last_surface: dict[str, Any] = {}
        run_id = time.strftime("%Y%m%dT%H%M%SZ_run", time.gmtime())
        run_log = self.log_dir / f"{run_id}.jsonl"

        for step in range(self.max_steps):
            surface_receipt = self.runtime.read()
            last_surface = surface_receipt.proof or {}
            self._log(run_log, {
                "step": step, "phase": "read", "intent": intent,
                "account_id": account_id, "device_id": device_id,
                "ok": surface_receipt.ok,
                "url": last_surface.get("url", ""),
                "title": last_surface.get("title", ""),
            })

            plan = self.planner.plan_next_primitive(
                intent, last_surface, history, memory_context or {},
            )
            self._log(run_log, {
                "step": step, "phase": "plan",
                "primitive": plan.primitive, "why": plan.why,
                "model": plan.model, "args": plan.args,
            })

            if plan.primitive == "done":
                outcome = DispatchOutcome(
                    status="success", intent=intent, steps=step + 1,
                    history=history, proof={"surface": last_surface,
                                              "why": plan.why},
                )
                self._log(run_log, {"step": step, "phase": "terminal",
                                     "status": "success"})
                return outcome

            if plan.primitive == "ask_user":
                question = str((plan.args or {}).get("question") or
                                "I need clarification to continue.")
                options = list((plan.args or {}).get("options") or [])
                outcome = DispatchOutcome(
                    status="ask_user", intent=intent, steps=step + 1,
                    history=history, question=question, options=options,
                    proof={"surface": last_surface, "why": plan.why},
                )
                self._log(run_log, {"step": step, "phase": "terminal",
                                     "status": "ask_user",
                                     "question": question})
                return outcome

            if plan.primitive == "notify_user":
                msg = str((plan.args or {}).get("message") or "")
                self.runtime.notify_user(msg)
                outcome = DispatchOutcome(
                    status="notify", intent=intent, steps=step + 1,
                    history=history, message=msg,
                    proof={"surface": last_surface, "why": plan.why},
                )
                self._log(run_log, {"step": step, "phase": "terminal",
                                     "status": "notify", "message": msg})
                return outcome

            result = self.runtime.execute(plan.to_dict())
            history.append(self._history_entry(plan, result))
            self._log(run_log, {
                "step": step, "phase": "act",
                "primitive": plan.primitive, "ok": result.ok,
                "error": result.error,
            })

            if plan.primitive == "verify" and result.ok:
                outcome = DispatchOutcome(
                    status="success", intent=intent, steps=step + 1,
                    history=history, proof={"surface": last_surface,
                                              "verify": result.to_dict()},
                )
                self._log(run_log, {"step": step, "phase": "terminal",
                                     "status": "success_via_verify"})
                return outcome

            recent_primitives.append(plan.primitive)
            recent_primitives = recent_primitives[-self.retry_cap:]
            saturated = (
                len(recent_primitives) >= self.retry_cap
                and len(set(recent_primitives)) == 1
                and not result.ok
            )
            if saturated:
                outcome = DispatchOutcome(
                    status="ask_user", intent=intent, steps=step + 1,
                    history=history,
                    question=(
                        f"I tried {plan.primitive} {self.retry_cap} times "
                        f"and it keeps failing ({result.error[:120]}). "
                        "How would you like me to proceed?"),
                    options=["retry", "skip", "cancel"],
                    proof={"surface": last_surface,
                           "last_attempt": result.to_dict()},
                )
                self._log(run_log, {"step": step, "phase": "terminal",
                                     "status": "ask_user_retry_saturation"})
                return outcome

        outcome = DispatchOutcome(
            status="ask_user", intent=intent, steps=self.max_steps,
            history=history,
            question=(
                f"I've tried {self.max_steps} steps toward \"{intent[:80]}\" "
                "and haven't succeeded yet. Help me succeed?"),
            options=["keep_going", "show_me_what_you_did", "cancel"],
            proof={"surface": last_surface},
        )
        self._log(run_log, {"step": self.max_steps, "phase": "terminal",
                             "status": "ask_user_step_ceiling"})
        return outcome

    # ----------------------------------------------------------- internals

    def _history_entry(self, plan: PlannerStep,
                        result: PrimitiveResult) -> dict[str, Any]:
        return {
            "primitive": plan.primitive,
            "args": dict(plan.args),
            "why": plan.why,
            "model": plan.model,
            "ok": bool(result.ok),
            "error": result.error or "",
            "proof_summary": self._summarize_proof(result.proof),
        }

    def _summarize_proof(self, proof: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(proof, dict):
            return {}
        keep = {}
        for key in ("url", "title", "via", "key", "label", "selector",
                    "navigated_to", "chars", "stdout"):
            if key in proof:
                value = proof[key]
                if isinstance(value, str):
                    value = value[:240]
                keep[key] = value
        return keep

    def _log(self, path: Path, event: dict[str, Any]) -> None:
        try:
            event = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                     **event}
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, default=str) + "\n")
        except Exception:
            pass


__all__ = ["ActionDispatcher", "DispatchOutcome"]
