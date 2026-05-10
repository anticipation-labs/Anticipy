"""
Reflector agent — meta-decision after consecutive no-progress.

The Reflector is gated: it only fires after 2 consecutive ``no_progress``
verdicts from the Critic. When it fires, it sees the plan, the recent
history, and the latest after-state, and returns one of:

  - ``pivot``: the original plan is wrong/blocked; here is a new plan.
  - ``abort``: the task can't complete from here. Here is the wearer-
    friendly abort message.
  - ``continue``: the no-progress streak is recoverable; keep going with
    the same plan.

The Reflector runs on a THIRD model — different from Planner and Critic.
By default that's Gemini Flash (Critic was Pixtral; Planner was Gemini, so
this is the same model as Planner — but the inputs are different and the
prompt is different, which is what role diversity research actually
requires for breaking rationalization). When the project later wires in
Cerebras for the Executor, the Reflector remains on Gemini for stability.

WIRE-ME: ``app/agent.py`` should call ``reflect(...)`` after the SECOND
consecutive ``no_progress`` from the Critic (track the streak in the loop).
The returned ``ReflectorResult.decision`` drives the loop:

  - ``pivot``: replace ``current_plan`` with ``ReflectorResult.new_plan``,
    optionally call ``DynamicBudget.reset_soft_cap(...)`` to give the new
    plan a fresh budget, reset the no-progress streak, continue.
  - ``abort``: stop the loop, surface ``ReflectorResult.abort_message`` to
    the wearer.
  - ``continue``: keep going with the existing plan; reset the no-progress
    streak so the agent has another window before the next reflection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

from app.models import (
    CostTracker,
    DegradedResponse,
    llm_call_json,
)
from app.planner import Plan, PlanStep, _coerce_required_facts, _coerce_steps


logger = logging.getLogger("engine.reflector")


ReflectorDecision = Literal["pivot", "abort", "continue"]


_ALLOWED_DECISIONS: tuple[str, ...] = ("pivot", "abort", "continue")


@dataclass
class ReflectorResult:
    """Outcome of one reflection.

    Attributes:
        decision: one of ``pivot | abort | continue``.
        new_plan: only populated when ``decision == "pivot"``. None otherwise.
        abort_message: wearer-friendly explanation when ``decision == "abort"``.
            Empty for other decisions.
        reasoning: one short sentence; logged for telemetry.
    """

    decision: ReflectorDecision
    new_plan: Plan | None = None
    abort_message: str = ""
    reasoning: str = ""
    raw: dict = field(default_factory=dict)


_REFLECTOR_SYSTEM = """\
You are the Reflector in a multi-agent browser-automation team.

The Critic has flagged TWO consecutive no-progress steps. Your job is the
meta-decision: should we PIVOT to a new plan, ABORT cleanly, or CONTINUE
with the current plan?

You will receive:
  - <task>: the wearer's original goal.
  - <current_plan>: the steps we've been following.
  - <history>: a compact log of the last few actions and their critic
    verdicts.
  - <current_state>: the page snapshot RIGHT NOW.

Decide ONE of:
  - "pivot": the current plan is genuinely blocked (the site moved its UI,
    a captcha intervened, the planned URL doesn't exist, the planned
    element is gated by login). Output a NEW plan (same shape as the
    Planner's: 3-7 steps with success_criteria, plus required_facts and
    unreachable flag). The new plan must START from the CURRENT state, not
    re-do steps the Executor already completed.
  - "abort": the task is genuinely unreachable from here (login required,
    payment required, captcha that can't be solved, site asking for
    real-human verification). Output a one-sentence abort_message that
    tells the wearer what didn't work and (if useful) suggests a manual
    next step.
  - "continue": the no-progress streak is recoverable — the page is mid-
    transition, the executor just needs another step, the timing was
    unlucky. Bias for "continue" only when you can specifically explain
    why the next step will work.

Rules:
  - STRICT JSON, no markdown.
  - When decision="pivot", new_plan is REQUIRED.
  - When decision="abort", abort_message is REQUIRED and must be plain
    English (no JSON, no model names, no IDs).
  - When decision="continue", new_plan and abort_message are empty/null.

Output shape:
  {
    "decision": "pivot|abort|continue",
    "new_plan": {
      "steps": [{"step": 1, "goal": "...", "success_criteria": "..."}, ...],
      "required_facts": ["..."],
      "unreachable": false,
      "unreachable_reason": "",
      "starting_url": "https://...",
      "success": "..."
    },
    "abort_message": "...",
    "reasoning": "..."
  }

When the field doesn't apply, set new_plan=null and abort_message="".
"""


def _truncate(text: str, limit: int = 2500) -> str:
    if not isinstance(text, str):
        return ""
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-limit // 2 :]
    return f"{head}\n…[snipped {len(text) - limit} chars]…\n{tail}"


def _serialize_history(history) -> str:
    """History can be a list of (action, verdict) pairs or message dicts."""
    if not history:
        return "(no history)"
    if isinstance(history, str):
        return _truncate(history, 2000)
    if not isinstance(history, list):
        return _truncate(str(history), 2000)
    lines: list[str] = []
    for h in history[-12:]:
        if isinstance(h, dict):
            verdict = h.get("verdict", "?")
            action = h.get("action", "?")
            note = h.get("reason", h.get("note", ""))
            lines.append(f"  [{verdict}] {action} — {note}"[:200])
        elif isinstance(h, (tuple, list)) and len(h) >= 2:
            lines.append(f"  [{h[1]}] {h[0]}"[:200])
        else:
            lines.append(f"  {str(h)[:200]}")
    return "\n".join(lines) or "(no history)"


def _serialize_plan(plan) -> str:
    if plan is None:
        return "(no plan)"
    steps = None
    if hasattr(plan, "steps"):
        steps = plan.steps
    elif isinstance(plan, list):
        steps = plan
    if not steps:
        return "(no plan)"
    lines: list[str] = []
    for s in steps:
        if hasattr(s, "step") and hasattr(s, "goal"):
            lines.append(f"  {s.step}. {s.goal} — success: {s.success_criteria}")
        elif isinstance(s, dict):
            lines.append(
                f"  {s.get('step', '?')}. {s.get('goal', '?')} "
                f"— success: {s.get('success_criteria', '?')}"
            )
    return "\n".join(lines) if lines else "(no plan)"


def _coerce_decision(value) -> ReflectorDecision | None:
    if not isinstance(value, str):
        return None
    norm = value.strip().lower().replace("-", "_").replace(" ", "_")
    if norm in _ALLOWED_DECISIONS:
        return norm  # type: ignore[return-value]
    synonyms = {
        "replan": "pivot",
        "retry": "continue",
        "keep_going": "continue",
        "stop": "abort",
        "give_up": "abort",
        "fail": "abort",
    }
    return synonyms.get(norm)  # type: ignore[return-value]


def _coerce_plan_from_dict(d) -> Plan | None:
    """Build a Plan from the raw ``new_plan`` dict the LLM returns. Reuses
    the planner's coercion helpers so behaviour stays consistent."""
    if not isinstance(d, dict):
        return None

    steps = _coerce_steps(d.get("steps"))
    if not steps:
        return None
    required = _coerce_required_facts(d.get("required_facts"))
    unreachable = bool(d.get("unreachable", False))
    unreachable_reason = str(d.get("unreachable_reason") or "").strip()[:200]
    starting_url = str(d.get("starting_url") or "").strip()[:300]
    success = str(d.get("success") or "Task completed").strip()[:200]
    return Plan(
        steps=steps,
        required_facts=required,
        unreachable=unreachable,
        unreachable_reason=unreachable_reason,
        starting_url=starting_url,
        success=success,
    )


async def reflect(
    task: str,
    current_plan,
    history,
    current_state: str = "",
    user_id: str = "",
    *,
    tracker: CostTracker | None = None,
) -> ReflectorResult:
    """Decide pivot / abort / continue after 2 consecutive no_progress.

    Args:
        task: original wearer goal.
        current_plan: existing Plan (or list of step dicts).
        history: recent (action, verdict) tuples or dicts; last ~10 entries
            are sent to the LLM.
        current_state: compact snapshot of the page right now.
        user_id: forwarded to the cost-watch audit trail.
        tracker: optional shared CostTracker.

    Returns:
        ReflectorResult. On cascade failure, defaults to ``decision="continue"``
        (cop-out #6: don't abort spuriously on an LLM outage; the
        DynamicBudget's ceilings will still stop runaway loops).
    """
    user = (
        f"<task>{(task or '').strip()[:600]}</task>\n\n"
        f"<current_plan>\n{_serialize_plan(current_plan)}\n</current_plan>\n\n"
        f"<history>\n{_serialize_history(history)}\n</history>\n\n"
        f"<current_state>\n{_truncate(current_state)}\n</current_state>\n\n"
        "Output the JSON decision now."
    )

    messages = [
        {"role": "system", "content": _REFLECTOR_SYSTEM},
        {"role": "user", "content": user},
    ]

    tracker = tracker or CostTracker()

    try:
        result = await llm_call_json(
            messages,
            tracker,
            temperature=0.1,
            max_tokens=1200,
            role="reflector",
            user_id=user_id or None,
        )
    except Exception:
        logger.exception("reflector cascade raised; defaulting to continue")
        return ReflectorResult(
            decision="continue",
            reasoning="reflector cascade raised; conservative continue",
        )

    if isinstance(result, DegradedResponse) or not isinstance(result, dict):
        logger.warning("reflector cascade unavailable; defaulting to continue")
        return ReflectorResult(
            decision="continue",
            reasoning="reflector cascade unavailable",
        )

    decision = _coerce_decision(result.get("decision"))
    if decision is None:
        logger.warning(
            "reflector returned unknown decision %r; defaulting to continue",
            result.get("decision"),
        )
        return ReflectorResult(
            decision="continue",
            reasoning="reflector returned unrecognised decision",
            raw=result,
        )

    reasoning = str(result.get("reasoning") or "").strip()[:240]

    new_plan: Plan | None = None
    abort_message = ""

    if decision == "pivot":
        new_plan = _coerce_plan_from_dict(result.get("new_plan"))
        if new_plan is None:
            # Pivot without a plan is useless — downgrade to continue rather
            # than blow up the loop.
            logger.warning(
                "reflector chose pivot but new_plan was missing/invalid; "
                "downgrading to continue"
            )
            return ReflectorResult(
                decision="continue",
                reasoning=(
                    "reflector pivot lacked a valid new_plan; "
                    "continuing with existing plan"
                ),
                raw=result,
            )
    elif decision == "abort":
        abort_message = str(result.get("abort_message") or "").strip()[:300]
        if not abort_message:
            abort_message = (
                "I couldn't complete that. Want me to retry, or do you want "
                "to take it from here?"
            )

    return ReflectorResult(
        decision=decision,
        new_plan=new_plan,
        abort_message=abort_message,
        reasoning=reasoning,
        raw=result,
    )


__all__ = ["reflect", "ReflectorResult", "ReflectorDecision"]
