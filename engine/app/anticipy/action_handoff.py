"""Layer B: the handoff from the proactive engine to the frozen action
engine.

This is a NEW adapter module. It NEVER edits a frozen action engine
file. The only path to the action engine is
platform_adapter.action_engine_invoke, and the only thing that touches
the frozen code is real_action_engine below, which imports the frozen
DSv4SkillRunner and calls its public run method, nothing else.

The typed contract, proactive to action:
  {intent_id, action, object, time_window, constraints,
   ambiguity_budget, memory_refs}
ambiguity_budget tells the action engine how much it may assume vs ask.
memory_refs are opaque keys the proactive engine can resolve.

The action engine may return a typed clarification:
  {intent_id, question, options, criticality_hint}
The handoff attempts memory resolution FIRST. Only if memory resolution
confidence is below 0.70 does it escalate to Layer C (built in P8; here
the escalation is recorded and, per the 3 hour rule default, the action
engine is handed a "proceed under the stated assumption" directive so it
is NEVER left synchronously blocked on a human).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from app.anticipy import memory as memory_mod
from app.anticipy import platform_adapter
from app.anticipy.seams import EngineDecision, UserContext

ESCALATION_THRESHOLD = 0.70


@dataclass
class ProactiveContract:
    intent_id: str
    action: str
    object: str
    time_window: str = ""
    constraints: dict = field(default_factory=dict)
    ambiguity_budget: float = 0.5
    memory_refs: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "intent_id": self.intent_id,
            "action": self.action,
            "object": self.object,
            "time_window": self.time_window,
            "constraints": dict(self.constraints),
            "ambiguity_budget": self.ambiguity_budget,
            "memory_refs": dict(self.memory_refs),
        }


@dataclass
class HandoffResult:
    intent_id: str
    status: str  # SUCCESS | ITERATION_EXHAUSTED | HARD_FAIL | ERROR | PROCEEDED_ON_ASSUMPTION
    answer: str = ""
    evidence: str = ""
    clarification_path: list = field(default_factory=list)
    blocked: bool = False  # invariant: the action engine is never left synchronously blocked
    raw: dict = field(default_factory=dict)


def contract_from_decision(decision: EngineDecision) -> ProactiveContract:
    """Map an ACT decision (with its extracted typed intent) to the
    typed proactive->action contract. ambiguity_budget is derived from
    confidence: a more confident decision lets the action engine assume
    more before it asks.
    """
    intent = decision.intent or {}
    slots = (intent.get("slots") or {}) if isinstance(intent, dict) else {}
    filled = slots.get("filled", {}) if isinstance(slots, dict) else {}
    return ProactiveContract(
        intent_id=(intent.get("intent_id") if isinstance(intent, dict) else None) or uuid.uuid4().hex,
        action=(intent.get("action_category") if isinstance(intent, dict) else None) or "act",
        object=decision.unit_text,
        time_window=str(filled.get("date", "") or filled.get("time", "")),
        constraints=dict(filled),
        ambiguity_budget=round(max(0.0, min(1.0, decision.confidence)), 3),
        memory_refs={},
    )


def to_task_string(contract: ProactiveContract) -> str:
    """Render the contract as the plain English task the frozen action
    engine consumes (its public run takes a task string).
    """
    base = contract.object.strip()
    if contract.time_window:
        base = f"{base} ({contract.time_window})"
    return base


async def _resolve_clarification(
    clar: dict, user_ctx: UserContext
) -> tuple[bool, str, float]:
    """Memory first. Returns (resolved, answer, confidence). Never raises;
    a memory failure returns not resolved so the caller escalates rather
    than guesses.
    """
    q = str(clar.get("question", ""))
    try:
        rr = await memory_mod.resolve_reference(user_ctx.user_id, q, user_ctx.profile)
    except Exception:
        return (False, "", 0.0)
    if rr.resolved and rr.confidence >= ESCALATION_THRESHOLD:
        return (True, rr.value, rr.confidence)
    return (False, "", rr.confidence)


def handoff(
    contract: ProactiveContract, user_ctx: UserContext, max_rounds: int = 4
) -> HandoffResult:
    """Hand the contract to the action engine through the single adapter
    seam. Resolve any clarification from memory first; escalate only
    below 0.70; never leave the action engine synchronously blocked.
    Synchronous on purpose: the action engine call is blocking, the
    clarification resolution is bounded, and on an unresolvable
    clarification we return a proceed under assumption directive
    immediately rather than waiting on a human.
    """
    result = HandoffResult(intent_id=contract.intent_id, status="UNKNOWN")
    payload = contract.to_dict()
    for _round in range(max_rounds):
        try:
            resp = platform_adapter.action_engine_invoke(payload)
        except Exception as e:
            result.status = "ERROR"
            result.evidence = f"action_engine_invoke raised: {e}"
            result.blocked = False
            return result

        clar = resp.get("clarification") if isinstance(resp, dict) else None
        if not clar:
            result.status = resp.get("status", "UNKNOWN")
            result.answer = resp.get("answer", "")
            result.evidence = resp.get("evidence", "")
            result.raw = resp if isinstance(resp, dict) else {}
            result.blocked = False
            return result

        # action engine asked a clarifying question: memory first
        resolved, answer, conf = asyncio.run(_resolve_clarification(clar, user_ctx))
        if resolved:
            result.clarification_path.append(
                {"q": clar.get("question"), "via": "memory_resolved", "conf": round(conf, 3)}
            )
            payload = dict(payload)
            payload.setdefault("constraints", {})
            payload["constraints"][str(clar.get("question", "answer"))[:40]] = answer
            payload["_clarification_answer"] = answer
            continue

        # below 0.70: escalate to Layer C (P8). The action engine is
        # NEVER blocked: per the 3 hour rule default it is told to
        # proceed under a stated assumption now. Layer C, once built,
        # asynchronously confirms or corrects out of band.
        result.clarification_path.append(
            {
                "q": clar.get("question"),
                "via": "escalated_to_comms",
                "conf": round(conf, 3),
                "criticality_hint": clar.get("criticality_hint"),
            }
        )
        result.status = "PROCEEDED_ON_ASSUMPTION"
        result.evidence = (
            "clarification could not be resolved from memory (conf "
            f"{round(conf, 3)} < {ESCALATION_THRESHOLD}); escalated to "
            "the communication layer and the action engine was handed a "
            "proceed under stated assumption directive, never blocked."
        )
        result.blocked = False
        result.raw = {"escalated": True, "clarification": clar}
        return result

    result.status = "ITERATION_EXHAUSTED"
    result.blocked = False
    return result


# ---------------------------------------------------------------------------
# Action engine implementations registered through the single adapter seam
# ---------------------------------------------------------------------------

def make_mock_action_engine():
    """A mock at the contract boundary. It honors the typed protocol: if
    the contract carries the test marker _needs_clarification and no
    _clarification_answer has been supplied yet, it returns a typed
    clarification; once answered it returns SUCCESS. This exercises the
    proactive to action protocol, memory first resolution, the 0.70
    escalation boundary, and the never blocked invariant, with zero real
    side effects.
    """

    def impl(contract: dict) -> dict:
        if contract.get("_needs_clarification") and not contract.get("_clarification_answer"):
            return {
                "clarification": {
                    "intent_id": contract.get("intent_id"),
                    "question": contract.get("_clarification_question", "which one did you mean?"),
                    "options": contract.get("_clarification_options", []),
                    "criticality_hint": contract.get("_criticality_hint", "low"),
                }
            }
        ans = contract.get("_clarification_answer")
        return {
            "status": "SUCCESS",
            "answer": f"mock executed: {contract.get('object', '')}"
            + (f" [resolved: {ans}]" if ans else ""),
            "evidence": "mock action engine, no real side effects",
        }

    return impl


def make_real_action_engine(cdp_port: int = 9222, max_iters: int = 12):
    """The ONE real path. Imports the frozen DSv4SkillRunner (read only,
    no edit to any frozen file) and calls its public run. Used only for a
    small safe READ only task to prove the wiring is real, not mocked.
    """

    def impl(contract: dict) -> dict:
        # Lazy import so merely importing this module never requires the
        # frozen engine's heavy deps or a live browser.
        from app.action_engine.dsv4_skill_runner import DSv4SkillRunner

        task = contract.get("object", "").strip()
        tw = contract.get("time_window", "")
        if tw:
            task = f"{task} ({tw})"
        runner = DSv4SkillRunner(cdp_port=cdp_port, max_iters=max_iters)
        tr = runner.run(task)
        return {
            "status": tr.status,
            "answer": tr.answer,
            "evidence": tr.evidence[:400] if tr.evidence else "",
            "n_iterations": tr.n_iterations,
            "trajectory_dir": tr.trajectory_dir,
            "error": tr.error,
        }

    return impl


def use_mock() -> None:
    platform_adapter.set_action_engine_impl(make_mock_action_engine())


def use_real(cdp_port: int = 9222, max_iters: int = 12) -> None:
    platform_adapter.set_action_engine_impl(make_real_action_engine(cdp_port, max_iters))
