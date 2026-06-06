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


class Approver:
    async def approve(self, goal: Goal, step: Step) -> bool:  # pragma: no cover - interface
        raise NotImplementedError


class AutoApprover(Approver):
    """Human-path stub: a test can auto-approve or auto-deny."""

    def __init__(self, approve: bool = True) -> None:
        self._approve = approve

    async def approve(self, goal: Goal, step: Step) -> bool:
        return self._approve


SUPPORT_ONLY_INTENTS = {"read_context", "write_memory", "list_open_loops", "read_page"}
EXTERNAL_ACTION_INTENTS = {
    "send_email", "send_email_draft", "send_text", "call", "create_event", "create_doc",
    "update_record", "message", "post_to_x",
}
EXTERNAL_ACTION_RE = re.compile(
    r"\b("
    r"send|email|mail|message|text|call|draft|schedule|book|reschedule|cancel|delete|"
    r"buy|purchase|order|reserve|register|post|tweet|submit|apply|pay|transfer|create|"
    r"invite|share|upload|file|fill|sign"
    r")\b",
    re.I,
)
REMINDER_ONLY_RE = re.compile(r"\b(remind me|remind us|remember to|set (a )?reminder)\b", re.I)
BROWSER_EXTERNAL_PROOF_KEYS = {
    "confirmation_id", "confirmation", "submitted", "submitted_url", "order_id",
    "reservation_id", "booking_id", "cart_id", "transaction_id", "record_id",
}


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
        plan_raw = await self.gateway.think(self._plan_prompt(goal, context), tier=SMART, caller="plan", json_mode=True)
        goal.steps = self._parse_plan(plan_raw)
        if not goal.steps:   # ONE bounded re-ask for clean JSON (real models drift; the stub never needs it)
            strict = (self._plan_prompt(goal, context)
                      + '\n\nYour previous reply could not be parsed. Reply with ONLY valid minified JSON '
                        '{"steps":[{"intent":"...","args":{},"risk":"low"}]} and nothing else.')
            plan_raw = await self.gateway.think(strict, tier=SMART, caller="plan", json_mode=True)
            goal.steps = self._parse_plan(plan_raw)
        if self._needs_external_artifact(goal) and not self._has_external_action_candidate(goal):
            goal.state = GoalState.waiting
            self.store.save(goal)
            self._log("goal_needs_human", {
                "goal_id": goal.id,
                "reason": "planner produced only support/read steps for an external action goal",
                "steps": [s.intent for s in goal.steps],
            })
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
        if self._needs_external_artifact(goal) and not self._has_external_completion_proof(goal):
            goal.state = GoalState.waiting
            self.store.save(goal)
            self._log("goal_needs_human", {
                "goal_id": goal.id,
                "reason": "support or read-only proof is not enough for external action completion",
                "proof": goal.proof,
            })
            return goal
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

    @staticmethod
    def _needs_external_artifact(goal: Goal) -> bool:
        text = f"{goal.intent} {goal.description}".lower()
        if REMINDER_ONLY_RE.search(text):
            return False
        return bool(EXTERNAL_ACTION_RE.search(text))

    @staticmethod
    def _has_external_action_candidate(goal: Goal) -> bool:
        return any(
            step.intent not in SUPPORT_ONLY_INTENTS and step.intent in EXTERNAL_ACTION_INTENTS
            for step in goal.steps
        )

    @staticmethod
    def _result_proof_is_external_action(step: Step) -> bool:
        result = step.result
        if result is None:
            return False
        proof = result.proof or {}
        output = result.output or {}
        if proof.get("tool") or proof.get("record_id") or proof.get("action"):
            return True
        return any(bool(proof.get(k) or output.get(k)) for k in BROWSER_EXTERNAL_PROOF_KEYS)

    @classmethod
    def _has_external_completion_proof(cls, goal: Goal) -> bool:
        for step in goal.steps:
            if step.state != StepState.done or step.result is None or not cls._verify(step.result):
                continue
            if step.intent in EXTERNAL_ACTION_INTENTS and cls._result_proof_is_external_action(step):
                return True
            if step.intent == "browse_task" and cls._result_proof_is_external_action(step):
                return True
        return False

    # ---- helpers ----
    def _plan_prompt(self, goal: Goal, context=None) -> str:
        base = ('Plan the goal into ordered steps. Respond with ONLY a JSON object '
                '{"steps":[{"intent":"...","args":{...},"risk":"low|needs_confirm|ask_human"}]} '
                '- no prose, no markdown fences.\nGOAL: ' + (goal.description or goal.intent))
        # Give a REAL model the available tool/intent vocabulary (general, not per-task; the model still
        # chooses). The stub gateway greps the prompt for keywords, so this is gated to a real provider —
        # the deterministic tier's prompt (and plans) stay byte-identical.
        if getattr(self.gateway, "provider", None) == "openrouter":
            base += "\nUse ONLY these intents (pick the closest fit): " + ", ".join(sorted(self.bus._workers)) + "."
            base += ('\nArg shapes - browse_task{"task":<plain-English what to do/find on the web>}, '
                     'read_page{"task":<what to read>}, send_email{"recipient","subject","body"}, '
                     'send_text{"recipient","body"}, create_event{"title","when"}, create_doc{"title","body"}, '
                     'write_memory{"text"}. For any web search / lookup / shopping / browsing step, use '
                     'browse_task with a "task" string. read_context, write_memory, read_page, and search '
                     'screenshots are support/read proof only. For goals that send, book, schedule, post, '
                     'submit, buy, call, file, create, or otherwise change an outside app, include at least '
                     'one matching action intent. If no action-capable intent exists, use risk "ask_human" '
                     'instead of pretending a search or memory write completed it.')
        return base + (f"\nRELEVANT MEMORY: {context}" if context else "")

    @staticmethod
    def _parse_plan(raw: str) -> list:
        """Robust: tolerate fenced / prose-wrapped / {steps:[...]} or bare-list output; skip a
        malformed step rather than dropping the whole plan (the Wave-0 PLAN_BAD @ live killer)."""
        data = _robust_json(raw)
        steps_raw = data.get("steps") if isinstance(data, dict) else (data if isinstance(data, list) else None)
        if not isinstance(steps_raw, list):
            return []
        out = []
        for s in steps_raw:
            if not isinstance(s, dict) or not s.get("intent"):
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
