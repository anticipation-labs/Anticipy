"""
Dynamic step budget for the browser agent.

Replaces the old ``MAX_STEPS=60`` hard cap. Past failure mode: the agent was
on step 58 of a 7-step task because no early-exit logic existed; budget was
spent on wandering. New model:

    - soft_cap (default 30): below this, default to continue.
    - hard_cap (default 200): absolute ceiling, recoverable by caller.
    - no-progress trigger: 5 consecutive ``made_progress=False`` calls
      stop the loop with reason="No progress in last 5 steps".
    - between soft_cap and hard_cap: keep going, but inject a self-eval
      nudge once: "If you're more than 2 steps from done, abort cleanly."

Decisions are pure data — the caller is the one that calls
``DynamicBudget.step_outcome(...)`` after each step and acts on
``ContinueDecision.should_continue``.

WIRE-ME: ``engine/app/agent.py`` main loop should:
    1. instantiate ``DynamicBudget(soft_cap=30, hard_cap=200)`` once per task,
    2. after each browser-use step, compute ``made_progress`` (e.g. URL
       changed, DOM tree size delta, action verdict from critic),
    3. call ``budget.step_outcome(step_idx, made_progress)`` and break
       the loop if ``decision.should_continue is False``,
    4. if ``decision.nudge`` is non-None, append it to the next LLM
       call's system message.

Cop-out #4: hard caps survive, but only as a recoverable backstop, not a
load-bearing termination signal.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("engine.dynamic_budget")


_NO_PROGRESS_LIMIT = 5
"""Stop after this many consecutive no-progress steps."""

_SOFT_CAP_NUDGE = (
    "You have used most of your default step budget. If you are more than "
    "2 steps from being done, abort cleanly with the answer or partial result "
    "you have so far. Do not start a new sub-goal."
)


@dataclass
class ContinueDecision:
    """Outcome of a single ``step_outcome`` call.

    Attributes:
        should_continue: True ⇒ run another step; False ⇒ stop the loop.
        reason: Human-readable explanation of the decision. Always set.
        nudge: Optional message the caller should inject into the next LLM
            call's system prompt. Used at the soft-cap boundary to encourage
            graceful self-termination. ``None`` when no nudge is needed.
    """

    should_continue: bool
    reason: str
    nudge: str | None = None


class DynamicBudget:
    """Per-task dynamic step budget.

    Not thread-safe — one instance per task. The browser agent runs serially
    within a task so this is fine.
    """

    def __init__(self, soft_cap: int = 30, hard_cap: int = 200) -> None:
        if soft_cap <= 0:
            raise ValueError(f"soft_cap must be > 0, got {soft_cap}")
        if hard_cap < soft_cap:
            raise ValueError(
                f"hard_cap ({hard_cap}) must be >= soft_cap ({soft_cap})"
            )

        self._soft_cap = soft_cap
        self._hard_cap = hard_cap
        self._consecutive_no_progress = 0
        self._soft_cap_nudge_fired = False
        self._last_reason = ""

    # ── Public knobs (caller can adjust mid-task) ──────────────────────

    @property
    def soft_cap(self) -> int:
        return self._soft_cap

    @property
    def hard_cap(self) -> int:
        return self._hard_cap

    def extend_hard_cap(self, new_hard_cap: int) -> None:
        """Recoverable extension of the absolute ceiling.

        After a hard-cap hit, the caller can decide to push it out (e.g. user
        confirmed they want to keep going, or the task type expects long
        loops). New value must be > current hard_cap.
        """
        if new_hard_cap <= self._hard_cap:
            raise ValueError(
                f"new_hard_cap ({new_hard_cap}) must be > current "
                f"hard_cap ({self._hard_cap})"
            )
        logger.info(
            "DynamicBudget hard_cap extended %d → %d", self._hard_cap, new_hard_cap,
        )
        self._hard_cap = new_hard_cap

    def reset_soft_cap(self, new_soft_cap: int) -> None:
        """Recoverable reset of the soft cap.

        Re-enables the nudge — useful when the caller decided "actually, let's
        keep going" after a soft-cap nudge fired. New value > current step.
        """
        if new_soft_cap <= 0:
            raise ValueError(f"new_soft_cap must be > 0, got {new_soft_cap}")
        self._soft_cap = new_soft_cap
        self._soft_cap_nudge_fired = False
        logger.info("DynamicBudget soft_cap reset → %d", new_soft_cap)

    def reason(self) -> str:
        """Return the most recent decision's explanation."""
        return self._last_reason

    # ── Core decision ──────────────────────────────────────────────────

    def step_outcome(self, step_idx: int, made_progress: bool) -> ContinueDecision:
        """Decide whether the agent should keep going after step ``step_idx``.

        Args:
            step_idx: 1-based step number that just completed. The next
                step (if continuing) would be ``step_idx + 1``.
            made_progress: Did the agent visibly advance toward the goal in
                the step that just finished? Caller is responsible for
                deciding what counts as progress (URL change, content
                appeared, critic verdict ∈ {progress, done}, etc.).

        Returns:
            ContinueDecision dataclass. ``should_continue=False`` means the
            caller MUST stop the loop, even if the budget says room remains.

        Behavior:
            1. If ``step_idx >= hard_cap``: stop, reason="Hard ceiling …".
            2. Update consecutive-no-progress counter.
            3. If 5 consecutive no-progress steps: stop, reason="No progress …".
            4. If ``step_idx >= soft_cap`` and nudge not yet fired: continue
               but emit the nudge once. Future steps still continue.
            5. Otherwise: continue, no nudge.
        """
        if step_idx <= 0:
            raise ValueError(f"step_idx must be >= 1, got {step_idx}")

        # Track consecutive-no-progress *first* — every call updates state
        # regardless of which gate fires.
        if made_progress:
            self._consecutive_no_progress = 0
        else:
            self._consecutive_no_progress += 1

        # 1. Hard ceiling — recoverable but caller must explicitly extend.
        if step_idx >= self._hard_cap:
            self._last_reason = (
                f"Hard ceiling reached without conclusion "
                f"(step {step_idx} >= hard_cap {self._hard_cap})"
            )
            logger.warning("DynamicBudget hard cap: %s", self._last_reason)
            return ContinueDecision(
                should_continue=False,
                reason=self._last_reason,
                nudge=None,
            )

        # 2. No-progress trigger — cheaper to bail than to keep paying for
        # spinning.
        if self._consecutive_no_progress >= _NO_PROGRESS_LIMIT:
            self._last_reason = (
                f"No progress in last {_NO_PROGRESS_LIMIT} steps "
                f"(step {step_idx})"
            )
            logger.info("DynamicBudget no-progress: %s", self._last_reason)
            return ContinueDecision(
                should_continue=False,
                reason=self._last_reason,
                nudge=None,
            )

        # 3. Soft-cap nudge — fires once. After it fires we keep going
        # (until hard_cap or no_progress_limit), but the LLM gets a clear
        # message that the budget is tight.
        if step_idx >= self._soft_cap and not self._soft_cap_nudge_fired:
            self._soft_cap_nudge_fired = True
            self._last_reason = (
                f"Soft cap reached (step {step_idx} >= soft_cap "
                f"{self._soft_cap}); injecting self-eval nudge"
            )
            logger.info("DynamicBudget soft-cap nudge: %s", self._last_reason)
            return ContinueDecision(
                should_continue=True,
                reason=self._last_reason,
                nudge=_SOFT_CAP_NUDGE,
            )

        # 4. Default — continue, no nudge.
        self._last_reason = (
            f"Continue (step {step_idx}, "
            f"no_progress_streak={self._consecutive_no_progress})"
        )
        return ContinueDecision(
            should_continue=True,
            reason=self._last_reason,
            nudge=None,
        )


__all__ = ["DynamicBudget", "ContinueDecision"]
