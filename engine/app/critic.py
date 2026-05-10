"""
Critic agent — per-step verdict on whether the executor's last action helped.

The critic looks at:
  - the original plan,
  - the action the executor just took,
  - the page state before and after,

and outputs one of {"progress", "no_progress", "unsafe", "done"}. The agent
loop uses this to:
  - update the no-progress streak in DynamicBudget,
  - escalate to the Reflector after 2 consecutive no_progress,
  - hard-stop on "unsafe" (cop-out #2: never trust the executor's own
    safety judgment),
  - short-circuit happily on "done".

The critic runs on a DIFFERENT model from the planner and executor (multi-
agent diversity, cop-out #16). The role chain in config.ROLE_CHAINS routes
``role="critic"`` to Pixtral 12B (Mistral La Plateforme) primary, Gemini
Flash fallback. If neither is configured the cascade degrades gracefully.

WIRE-ME: ``app/agent.py`` should call ``criticize(...)`` after every
executor step and feed the verdict to:
  - ``DynamicBudget.step_outcome(step, made_progress=verdict in {"progress", "done"})``
  - the Reflector (when verdict == "no_progress" twice in a row)
  - the wearer message dispatcher (when verdict == "unsafe": stop and
    surface CriticResult.reason).
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


logger = logging.getLogger("engine.critic")


CriticVerdict = Literal["progress", "no_progress", "unsafe", "done"]


# Verdicts ranked by severity for downstream gating: "unsafe" overrides
# everything else. Order tightest-to-loosest.
_ALLOWED_VERDICTS: tuple[str, ...] = ("unsafe", "done", "progress", "no_progress")


@dataclass
class CriticResult:
    """Single-step critic verdict.

    Attributes:
        verdict: ``"progress" | "no_progress" | "unsafe" | "done"``.
        reason: One short sentence explaining the verdict. Surfaced to the
            wearer ONLY when ``verdict == "unsafe"`` or when the agent
            decides to abort (the reflector quotes it back).
        confidence: 0..1 self-rated. Low confidence means downstream code
            should be more conservative (e.g. don't auto-pivot on a low-
            confidence no_progress).
    """

    verdict: CriticVerdict
    reason: str = ""
    confidence: float = 0.0
    raw: dict = field(default_factory=dict)


_CRITIC_SYSTEM = """\
You are the Critic in a multi-agent browser-automation team.

After each step the Executor takes, you decide whether the action moved the
team closer to the goal. You are paired with a different LLM than the
Planner and Executor — your job is independent verification, not self-
agreement.

You will be given:
  - <plan>: the ordered list of steps, with success_criteria.
  - <step_idx>: which step the Executor was attempting.
  - <action_taken>: the action the Executor took (a dict).
  - <before_state>: a compact snapshot of the page BEFORE the action.
  - <after_state>: a compact snapshot of the page AFTER the action.

Decide ONE verdict from this exact set:
  - "progress": the action visibly moved closer to the step's
    success_criteria (URL changed appropriately, target element appeared,
    expected text rendered).
  - "no_progress": the action ran but the page did not change in a useful
    way, or the change was orthogonal to the step. Errors / popups /
    captchas count as no_progress, NOT unsafe.
  - "unsafe": the action attempted something the team must not do
    (e.g. typed a credit-card number into a non-checkout page, clicked
    "delete account", attempted a payment without explicit confirmation,
    sent a message to the wrong recipient). Bias HIGH for this — false
    positives just stop the loop, false negatives ship a destructive
    action.
  - "done": the action's after-state contains direct evidence the OVERALL
    GOAL is complete. Not just the current step — the whole task. If the
    page shows the answer, a confirmation, or the requested artifact, say
    done.

Rules:
  - Output STRICT JSON, no markdown, no commentary.
  - Verdict MUST be one of the four exact strings above.
  - reason: one short sentence. Quote a specific change (URL, text, element).
  - confidence: 0.0 to 1.0 self-rating.

Output shape:
  {"verdict": "<one of the four>", "reason": "...", "confidence": <number>}
"""


def _truncate_state(state: str, limit: int = 2000) -> str:
    if not isinstance(state, str):
        return ""
    if len(state) <= limit:
        return state
    head = state[: limit // 2]
    tail = state[-limit // 2 :]
    return f"{head}\n…[snipped {len(state) - limit} chars]…\n{tail}"


def _serialize_action(action) -> str:
    if not action:
        return "(no action)"
    if isinstance(action, dict):
        # Compact pretty-print so the LLM has labels.
        try:
            import json as _json
            return _json.dumps(action, ensure_ascii=False, indent=None)[:1500]
        except Exception:
            return str(action)[:1500]
    return str(action)[:1500]


def _serialize_plan(plan) -> str:
    """Plan can be a list of dicts/PlanSteps, or a Plan dataclass.

    Renders to a stable text form for the prompt.
    """
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
        if hasattr(s, "step") and hasattr(s, "goal") and hasattr(s, "success_criteria"):
            lines.append(f"  {s.step}. {s.goal} — success: {s.success_criteria}")
        elif isinstance(s, dict):
            idx = s.get("step", "?")
            g = s.get("goal", "?")
            c = s.get("success_criteria", "?")
            lines.append(f"  {idx}. {g} — success: {c}")
    return "\n".join(lines) if lines else "(no plan)"


def _coerce_verdict(value) -> CriticVerdict | None:
    """Map the LLM's verdict string to one of the allowed values."""
    if not isinstance(value, str):
        return None
    norm = value.strip().lower().replace("-", "_").replace(" ", "_")
    if norm in _ALLOWED_VERDICTS:
        return norm  # type: ignore[return-value]
    # Common synonyms — be forgiving with model variance, but never invent
    # a stricter verdict than the model produced.
    synonyms = {
        "progressed": "progress",
        "advanced": "progress",
        "moved": "progress",
        "stalled": "no_progress",
        "stuck": "no_progress",
        "unchanged": "no_progress",
        "failed": "no_progress",
        "dangerous": "unsafe",
        "unsafe_action": "unsafe",
        "complete": "done",
        "completed": "done",
        "finished": "done",
    }
    return synonyms.get(norm)  # type: ignore[return-value]


async def criticize(
    action_taken,
    before_state: str = "",
    after_state: str = "",
    plan=None,
    step_idx: int = 0,
    user_id: str = "",
    *,
    tracker: CostTracker | None = None,
) -> CriticResult:
    """Ask the critic LLM whether ``action_taken`` made progress.

    Args:
        action_taken: dict, str, or PlanStep-shaped object describing the
            executor's action (e.g. ``{"action": "click", "target": "B"}``).
        before_state: compact snapshot before the action.
        after_state: compact snapshot after the action.
        plan: the Plan dataclass (or list of step dicts). Used for context
            and to ground "the step's success_criteria".
        step_idx: 1-based step number being attempted.
        user_id: forwarded to the cost-watch audit trail.
        tracker: optional shared CostTracker.

    Returns:
        CriticResult. Verdict defaults to ``"no_progress"`` on cascade
        failure or non-recognised LLM output (cop-out #6: fail closed).
    """
    user = (
        f"<plan>\n{_serialize_plan(plan)}\n</plan>\n\n"
        f"<step_idx>{int(step_idx) if step_idx else '?'}</step_idx>\n\n"
        f"<action_taken>{_serialize_action(action_taken)}</action_taken>\n\n"
        f"<before_state>\n{_truncate_state(before_state)}\n</before_state>\n\n"
        f"<after_state>\n{_truncate_state(after_state)}\n</after_state>\n\n"
        "Output the JSON verdict now."
    )

    messages = [
        {"role": "system", "content": _CRITIC_SYSTEM},
        {"role": "user", "content": user},
    ]

    tracker = tracker or CostTracker()

    try:
        result = await llm_call_json(
            messages,
            tracker,
            temperature=0.0,
            max_tokens=200,
            role="critic",
            user_id=user_id or None,
        )
    except Exception:
        logger.exception("critic cascade raised; defaulting to no_progress")
        return CriticResult(
            verdict="no_progress",
            reason="critic cascade raised",
            confidence=0.0,
        )

    if isinstance(result, DegradedResponse) or not isinstance(result, dict):
        logger.warning("critic cascade unavailable; defaulting to no_progress")
        return CriticResult(
            verdict="no_progress",
            reason="critic cascade unavailable",
            confidence=0.0,
        )

    verdict = _coerce_verdict(result.get("verdict"))
    if verdict is None:
        logger.warning(
            "critic returned unknown verdict %r; defaulting to no_progress",
            result.get("verdict"),
        )
        return CriticResult(
            verdict="no_progress",
            reason="critic returned unrecognised verdict",
            confidence=0.0,
            raw=result,
        )

    reason = str(result.get("reason") or "").strip()[:240]
    try:
        confidence = float(result.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    return CriticResult(
        verdict=verdict,
        reason=reason,
        confidence=confidence,
        raw=result,
    )


__all__ = ["criticize", "CriticResult", "CriticVerdict"]
