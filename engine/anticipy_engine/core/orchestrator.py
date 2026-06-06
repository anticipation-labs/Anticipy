"""The orchestrator — the boss.

Control loop over a Goal: plan (one smart call), then for each step build a Job,
gate irreversible/external steps through the human path, dispatch on the bus,
verify the Result's proof, retry on failure, reroute to an alternate intent, and
persist after every step so a restart can resume. NEVER marks a goal done
without proof for every step; never silently drops a step.
"""
from __future__ import annotations

import json
import re
from typing import Dict, Optional

from .bus import Bus
from .envelopes import Goal, GoalState, Job, JobStatus, Result, Risk, Step, StepState
from .gateway import SMART, ModelGateway
from .store import GoalStore


USER_TASK_INTENTS = (
    "send_email",
    "send_email_draft",
    "create_event",
    "message",
    "post_to_x",
    "browse_task",
)


class Approver:
    async def approve(self, goal: Goal, step: Step) -> bool:  # pragma: no cover - interface
        raise NotImplementedError


class AutoApprover(Approver):
    """Human-path stub: a test can auto-approve or auto-deny."""

    def __init__(self, approve: bool = True) -> None:
        self._approve = approve

    async def approve(self, goal: Goal, step: Step) -> bool:
        return self._approve


def _robust_json(raw):
    """Resilient extraction of a JSON object/array from a model reply that may be fenced,
    prose-wrapped, or slightly off (the browser-agent pattern, reused): strip fences, try the
    whole string, then a balanced-brace/bracket scan. Returns the parsed value or None."""
    if not raw:
        return None
    s = re.sub(r"```(json)?", "", raw).strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    for op, cl in (("{", "}"), ("[", "]")):
        start = s.find(op)
        if start < 0:
            continue
        depth = 0
        for i in range(start, len(s)):
            if s[i] == op:
                depth += 1
            elif s[i] == cl:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(s[start:i + 1])
                    except Exception:
                        break
    return None


class Orchestrator:
    def __init__(
        self,
        bus: Bus,
        gateway: ModelGateway,
        store: GoalStore,
        glassbox=None,
        scorecard=None,
        approver: Optional[Approver] = None,
        max_retries: int = 2,
        alternates: Optional[Dict[str, str]] = None,
        memory_context=None,
    ) -> None:
        self.bus = bus
        # INJECT seam: optional callable(about)->dict; pulled BEFORE the plan smart-call.
        # None (default) -> no memory, prompt unchanged (existing tests unaffected).
        self.memory_context = memory_context
        self.gateway = gateway
        self.store = store
        self.glassbox = glassbox
        self.scorecard = scorecard
        self.approver = approver or AutoApprover(True)
        self.max_retries = max_retries
        # reroute map: if an intent's worker keeps failing, try the alternate.
        self.alternates = alternates if alternates is not None else {"create_event": "browse_task"}
        self._cost_start: Dict[str, float] = {}

    # ---- entry points ----
    async def start_goal(self, goal: Goal) -> Goal:
        self._cost_start[goal.id] = self.gateway.total_cost()
        goal.state = GoalState.planning
        self.store.save(goal)
        self._log("goal_planning", {"goal_id": goal.id})

        context = self.memory_context(goal.description or goal.intent) if self.memory_context else {}
        allowed_intents = self._allowed_live_plan_intents()
        plan_raw = await self.gateway.think(self._plan_prompt(goal, context), tier=SMART, caller="plan", json_mode=True)
        goal.steps = self._parse_plan(plan_raw, allowed_intents=allowed_intents)
        if not goal.steps:   # ONE bounded re-ask for clean JSON (real models drift; the stub never needs it)
            strict = (self._plan_prompt(goal, context)
                      + '\n\nYour previous reply could not be parsed. Reply with ONLY valid minified JSON '
                        '{"steps":[{"intent":"...","args":{},"risk":"low"}]} and nothing else.')
            plan_raw = await self.gateway.think(strict, tier=SMART, caller="plan", json_mode=True)
            goal.steps = self._parse_plan(plan_raw, allowed_intents=allowed_intents)
        if not goal.steps:
            goal.state = GoalState.waiting
            self.store.save(goal)
            self._log("goal_waiting", {"goal_id": goal.id, "reason": "no_valid_user_task_plan"})
            return goal
        goal.state = GoalState.running
        self.store.save(goal)
        self._log("goal_planned", {"goal_id": goal.id, "steps": [s.intent for s in goal.steps]})
        return await self._drive(goal)

    async def resume_waiting(self) -> list:
        resumed = []
        for goal in self.store.waiting():
            self._log("goal_resumed", {"goal_id": goal.id})
            resumed.append(await self._drive(goal))
        return resumed

    # ---- core loop ----
    async def _drive(self, goal: Goal) -> Goal:
        goal.state = GoalState.running
        self.store.save(goal)
        for step in goal.steps:
            if step.state == StepState.done:
                continue  # resume-friendly: already-done steps are skipped
            await self._run_step(goal, step)
            self.store.save(goal)  # persist after EVERY step
            if step.state in (StepState.needs_human, StepState.failed):
                goal.state = GoalState.waiting if step.state == StepState.needs_human else GoalState.failed
                self.store.save(goal)
                self._log(f"goal_{goal.state.value}", {"goal_id": goal.id, "stuck_on": step.intent})
                return goal

        # every step verified done -> collect proof, finish
        goal.proof = {f"{i}:{s.intent}": s.result.proof for i, s in enumerate(goal.steps) if s.result}
        goal.state = GoalState.done
        self.store.save(goal)
        self._log("goal_done", {"goal_id": goal.id, "proof": goal.proof})
        if self.scorecard is not None:
            self.scorecard.record_goal(goal.id, "success", self._goal_cost(goal))
        return goal

    async def _run_step(self, goal: Goal, step: Step) -> None:
        # human path: never run an irreversible/external step without approval
        if step.risk in (Risk.needs_confirm, Risk.ask_human):
            approved = await self.approver.approve(goal, step)
            self._log("approval", {"goal_id": goal.id, "intent": step.intent, "approved": approved})
            if not approved:
                step.state = StepState.needs_human
                return

        if await self._dispatch_with_retry(goal, step, step.intent):
            return
        # exhausted retries -> reroute to an alternate worker/intent if one exists
        alt = self.alternates.get(step.intent)
        if alt:
            self._log("reroute", {"goal_id": goal.id, "from": step.intent, "to": alt})
            if await self._dispatch_with_retry(goal, step, alt):
                return
        step.state = StepState.needs_human  # surface; never silently drop

    async def _dispatch_with_retry(self, goal: Goal, step: Step, intent: str) -> bool:
        attempts = 0
        while attempts <= self.max_retries:
            attempts += 1
            step.attempts += 1
            job = Job(intent=intent, args=step.args, risk=step.risk, goal_id=goal.id)
            result = await self.bus.submit_job(job)
            if result.status == JobStatus.success and self._verify(result):
                step.result = result
                step.state = StepState.done
                return True
            if result.status == JobStatus.needs_human:
                step.state = StepState.needs_human
                return True  # resolved (surfaced); rerouting wouldn't help
            # failed OR success-without-proof -> retry
        return False

    @staticmethod
    def _verify(result: Result) -> bool:
        """No proof, not done."""
        return result.proof is not None and bool(result.proof)

    # ---- helpers ----
    def _plan_prompt(self, goal: Goal, context=None) -> str:
        base = ('Plan the goal into ordered steps. Respond with ONLY a JSON object '
                '{"steps":[{"intent":"...","args":{...},"risk":"low|needs_confirm|ask_human"}]} '
                '- no prose, no markdown fences.\nGOAL: ' + (goal.description or goal.intent))
        # Give a REAL model the available tool/intent vocabulary (general, not per-task; the model still
        # chooses). The stub gateway greps the prompt for keywords, so this is gated to a real provider —
        # the deterministic tier's prompt (and plans) stay byte-identical.
        if getattr(self.gateway, "provider", None) == "openrouter":
            base += "\nUse ONLY these user-task intents: " + ", ".join(self._allowed_live_plan_intents()) + "."
            base += ('\nInternal support tools are not completion proof and must not appear in a user-task plan: '
                     'read_context, write_memory, list_open_loops, send_text, call.'
                     '\nArg shapes - browse_task{"task":<plain-English what to do/find on the web>}, '
                     'send_email{"recipient","subject","body"}, '
                     'send_email_draft{"recipient","subject","body"}, '
                     'create_event{"title","when"}, message{"channel","text"}, post_to_x{"text"}. '
                     'Use create_event for reminders, deadlines, calendar holds, scheduling, and blocked time. '
                     'Use an API-backed intent when one fits; use browse_task only when no API-backed intent fits.')
        return base + (f"\nRELEVANT MEMORY: {context}" if context else "")

    def _allowed_live_plan_intents(self) -> Optional[tuple[str, ...]]:
        if getattr(self.gateway, "provider", None) != "openrouter":
            return None
        available = set(self.bus._workers)
        return tuple(intent for intent in USER_TASK_INTENTS if intent in available)

    @staticmethod
    def _parse_plan(raw: str, allowed_intents: Optional[tuple[str, ...]] = None) -> list:
        """Robust: tolerate fenced / prose-wrapped / {steps:[...]} or bare-list output; skip a
        malformed step rather than dropping the whole plan (the Wave-0 PLAN_BAD @ live killer)."""
        data = _robust_json(raw)
        steps_raw = data.get("steps") if isinstance(data, dict) else (data if isinstance(data, list) else None)
        if not isinstance(steps_raw, list):
            return []
        allowed = set(allowed_intents) if allowed_intents is not None else None
        out = []
        for s in steps_raw:
            if not isinstance(s, dict) or not s.get("intent"):
                continue
            if allowed is not None and s["intent"] not in allowed:
                continue
            risk = s.get("risk", "low")
            risk = Risk(risk) if risk in ("low", "needs_confirm", "ask_human") else Risk.low
            args = s.get("args") if isinstance(s.get("args"), dict) else {}
            out.append(Step(intent=str(s["intent"]), args=args, risk=risk))
        return out

    def _goal_cost(self, goal: Goal) -> float:
        start = self._cost_start.get(goal.id, self.gateway.total_cost())
        return round(self.gateway.total_cost() - start, 6)

    def _log(self, kind: str, payload) -> None:
        if self.glassbox is None:
            return
        data = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload
        self.glassbox.log(kind, data)
