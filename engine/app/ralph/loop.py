"""Ralph loop orchestrator (Phase 4-2 / 4-4 / 4-5 integration).

Stitches the persistence layer (store.py), classifier (classifier.py),
recovery dispatcher (recovery.py), and verifier (verifier.py) into the
top-down loop diagram from RALPH_LOOP.md:

    goal arrives
      -> for each step in goal.plan:
            execute via bridge.dispatch
            verify Layer 1 (deterministic)
            if pass: store.complete_step('pass'), advance
            if fail:
                classify -> recover
                  retry_now        -> redo step, bump retry_count
                  retry_later      -> store.schedule_retry, return
                  notify_user      -> send notify, mark wait_user, return
                  cancel           -> mark cancelled, return
                  escalate_model   -> redo with vision / fallback
                if cost_cap raised: pause goal, notify
      -> end of plan: Layer 2 vision judge
      -> mark done | failed | wait_user based on verdict

The function is async because real bridges + LLMs are async; the
loop awaits them transparently. Tests provide async mock bridge + llm
that satisfy the protocols below.

Protocols (duck-typed, defined here to keep this module dependency-free):

    bridge.dispatch(step_dict) -> StepResult
        StepResult fields: ok: bool, error: str|None, http_status: int|None,
                           url: str|None, dom: str|None,
                           post_state_hash: str|None, screenshot_path: str|None,
                           cost_usd: float (default 0.0).
        On exception, the loop catches and classifies as model_error /
        unknown / etc. depending on the message.

    llm.judge_goal(goal_text, screenshot_path) -> str (JSON verdict)
        Same shape as verifier.judge_goal expects.

    notifier(notify_dict) -> Awaitable[None]
        Optional callable invoked when recovery returns notify_user /
        cancel / cost_cap. If None, loop just records the plan in
        goal.channel_payload and moves on.

The loop never throws on a step failure. CostCapExceeded is the only
exception that escapes (callers may wrap it; we recover internally).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, Protocol

from app.ralph.classifier import classify
from app.ralph.recovery import (
    ACTION_CANCEL,
    ACTION_ESCALATE_MODEL,
    ACTION_NOTIFY_USER,
    ACTION_RETRY_LATER,
    ACTION_RETRY_NOW,
    RecoveryPlan,
    recover,
)
from app.ralph.store import CostCapExceeded, Goal, RalphStore
from app.ralph.verifier import JudgeResult, judge_goal, verify_step

logger = logging.getLogger("app.ralph.loop")


# Cap on retries for the same step before we replan / surface to user.
_MAX_STEP_RETRIES = 3


@dataclass
class StepResult:
    """Return shape from bridge.dispatch.

    Mirrors what a real CDP / extension bridge sends back. The loop
    cares only about a small set of fields; bridges may add more for
    their own telemetry without affecting correctness.
    """

    ok: bool
    error: Optional[str] = None
    http_status: Optional[int] = None
    url: Optional[str] = None
    dom: Optional[str] = None
    post_state_hash: Optional[str] = None
    screenshot_path: Optional[str] = None
    cost_usd: float = 0.0
    extras: dict[str, Any] = field(default_factory=dict)


class _Bridge(Protocol):
    async def dispatch(self, step: dict[str, Any]) -> StepResult: ...


class _LLM(Protocol):
    def judge_goal(self, goal_text: str, screenshot_path: Optional[str]) -> str: ...


@dataclass
class RunOutcome:
    """Top-level result of run_goal()."""

    goal_id: str
    final_status: str  # 'done' | 'failed' | 'wait_user' | 'wait_retry' | 'cancelled'
    judge_verdict: Optional[str] = None
    steps_executed: int = 0
    steps_passed: int = 0
    last_failure_class: Optional[str] = None
    last_recovery_action: Optional[str] = None
    cost_usd: float = 0.0


async def run_goal(
    goal_id: str,
    store: RalphStore,
    bridge: _Bridge,
    *,
    plan: list[dict[str, Any]],
    llm: Optional[Any] = None,
    notifier: Optional[Callable[[dict[str, Any]], Awaitable[None]]] = None,
    sleep: Optional[Callable[[float], Awaitable[None]]] = None,
    now_ts: Optional[Callable[[], int]] = None,
) -> RunOutcome:
    """Run a goal end-to-end against the supplied bridge.

    Args:
        goal_id:  the row in store.goals to resume / start.
        store:    RalphStore for persistence.
        bridge:   protocol with .dispatch(step) -> StepResult.
        plan:     ordered list of step dicts. Each dict is passed
                  verbatim to bridge.dispatch. May include verify
                  hints (expected_url, expected_selector, ...).
        llm:      vision judge LLM for layer-2 verification. May be
                  None; the verifier degrades gracefully.
        notifier: optional async callable invoked with the notify
                  dict from a RecoveryPlan whenever we need to ping
                  the user (notify_user, cost_cap, cancel).
        sleep:    optional async sleep override (defaults to
                  asyncio.sleep). Tests pass an instant no-op.
        now_ts:   optional clock override returning unix seconds.

    Returns a RunOutcome describing the terminal state. Always
    persists the goal status to store before returning.
    """
    sleep = sleep or asyncio.sleep
    now_ts = now_ts or (lambda: int(time.time()))

    goal = store.get_goal(goal_id)
    if goal is None:
        raise KeyError(f"goal {goal_id!r} not found in store")

    # Mark running. Reset consecutive_failures so retries from a
    # previous wake-up don't poison this attempt.
    store.update_goal_status(goal_id, "running", consecutive_failures=0)

    # Per-step extras carry state across retries on THE SAME step
    # (captcha_tried, vision_tried, model_swaps, etc.). The map is
    # keyed by step_index so we can reset between steps.
    step_extras: dict[int, dict[str, Any]] = {}

    steps_passed = 0
    last_failure_class: Optional[str] = None
    last_recovery_action: Optional[str] = None

    for step_index, step in enumerate(plan):
        step_id = store.add_step(
            goal_id,
            action=str(step.get("action", "unknown")),
            action_payload=step,
            pre_state_hash=step.get("pre_state_hash"),
        )
        extras = step_extras.setdefault(step_index, {})

        attempt = 0
        step_done = False
        while attempt <= _MAX_STEP_RETRIES and not step_done:
            attempt += 1
            t0 = now_ts()
            try:
                result = await bridge.dispatch(step)
            except CostCapExceeded as exc:
                # Recover and surface.
                goal = store.get_goal(goal_id) or goal
                plan_recover = recover("cost_cap", goal, now_ts=now_ts(), extras=extras)
                await _apply_plan(
                    plan_recover, goal_id, store, notifier, status="wait_user"
                )
                store.complete_step(
                    step_id,
                    post_state_hash=None,
                    result="fail",
                    failure_class="cost_cap",
                    failure_detail=str(exc),
                    cost_usd=0.0,
                    duration_ms=(now_ts() - t0) * 1000,
                )
                return RunOutcome(
                    goal_id=goal_id,
                    final_status="wait_user",
                    steps_executed=step_index + 1,
                    steps_passed=steps_passed,
                    last_failure_class="cost_cap",
                    last_recovery_action=plan_recover.action,
                    cost_usd=(store.get_goal(goal_id) or goal).cost_usd,
                )
            except Exception as exc:  # noqa: BLE001
                # Synthetic StepResult so the classifier sees something.
                result = StepResult(ok=False, error=f"bridge raised: {exc}")

            # Track cost (may raise CostCapExceeded mid-step).
            if result.cost_usd > 0:
                try:
                    store.bump_cost(goal_id, result.cost_usd)
                except CostCapExceeded as exc:
                    goal = store.get_goal(goal_id) or goal
                    plan_recover = recover(
                        "cost_cap", goal, now_ts=now_ts(), extras=extras
                    )
                    await _apply_plan(
                        plan_recover,
                        goal_id,
                        store,
                        notifier,
                        status="wait_user",
                    )
                    store.complete_step(
                        step_id,
                        post_state_hash=result.post_state_hash,
                        result="fail",
                        failure_class="cost_cap",
                        failure_detail=str(exc),
                        cost_usd=result.cost_usd,
                        duration_ms=(now_ts() - t0) * 1000,
                    )
                    return RunOutcome(
                        goal_id=goal_id,
                        final_status="wait_user",
                        steps_executed=step_index + 1,
                        steps_passed=steps_passed,
                        last_failure_class="cost_cap",
                        last_recovery_action=plan_recover.action,
                        cost_usd=(store.get_goal(goal_id) or goal).cost_usd,
                    )

            # Layer 1 verify.
            layer1_ok = result.ok and verify_step(
                pre_state_hash=step.get("pre_state_hash"),
                post_state_hash=result.post_state_hash,
                expected_url=step.get("expected_url"),
                expected_url_pattern=step.get("expected_url_pattern"),
                expected_selector=step.get("expected_selector"),
                current_url=result.url,
                current_dom=result.dom,
                require_state_change=bool(step.get("require_state_change", True)),
            )

            duration_ms = (now_ts() - t0) * 1000

            if layer1_ok:
                store.complete_step(
                    step_id,
                    post_state_hash=result.post_state_hash,
                    result="pass",
                    failure_class=None,
                    failure_detail=None,
                    cost_usd=result.cost_usd,
                    duration_ms=duration_ms,
                )
                # Reset consecutive_failures on success.
                store.update_goal_status(
                    goal_id, "running", consecutive_failures=0
                )
                step_done = True
                steps_passed += 1
                break

            # Failure path: classify, then recover.
            failure_class = classify(
                error_msg=result.error,
                url=result.url,
                dom_snapshot=result.dom,
                http_status=result.http_status,
            )
            last_failure_class = failure_class

            # Bump consecutive_failures in the goal row so recovery
            # backoff sees the right value.
            goal = store.get_goal(goal_id) or goal
            new_failures = goal.consecutive_failures + 1
            store.update_goal_status(
                goal_id, "running", consecutive_failures=new_failures
            )
            goal = store.get_goal(goal_id) or goal

            recovery_plan = recover(
                failure_class, goal, now_ts=now_ts(), extras=extras
            )
            step_extras[step_index] = recovery_plan.extras
            last_recovery_action = recovery_plan.action

            store.complete_step(
                step_id,
                post_state_hash=result.post_state_hash,
                result="fail",
                failure_class=failure_class,
                failure_detail=(result.error or "")[:240],
                cost_usd=result.cost_usd,
                duration_ms=duration_ms,
            )

            if recovery_plan.action == ACTION_RETRY_NOW:
                # Add a fresh step row for the retry so the audit
                # trail stays clean. The current step_id is already
                # marked fail; create a new one for the next attempt.
                step_id = store.add_step(
                    goal_id,
                    action=str(step.get("action", "unknown")),
                    action_payload=step,
                    pre_state_hash=step.get("pre_state_hash"),
                )
                continue  # while loop, attempt += 1 next iteration

            if recovery_plan.action == ACTION_ESCALATE_MODEL:
                # Same: redo with vision / fallback flag bumped. The
                # bridge inspects step["use_vision"] / step["swap_model"]
                # to switch reasoning model.
                step = dict(step)
                if recovery_plan.use_vision:
                    step["use_vision"] = True
                if recovery_plan.swap_model:
                    step["swap_model"] = True
                step_id = store.add_step(
                    goal_id,
                    action=str(step.get("action", "unknown")),
                    action_payload=step,
                    pre_state_hash=step.get("pre_state_hash"),
                )
                continue

            if recovery_plan.action == ACTION_RETRY_LATER:
                # Schedule and yield. Caller wakes us up later.
                store.schedule_retry(
                    goal_id, int(recovery_plan.next_attempt_at or now_ts())
                )
                if recovery_plan.notify and notifier is not None:
                    await notifier(recovery_plan.notify)
                return RunOutcome(
                    goal_id=goal_id,
                    final_status="wait_retry",
                    steps_executed=step_index + 1,
                    steps_passed=steps_passed,
                    last_failure_class=failure_class,
                    last_recovery_action=recovery_plan.action,
                    cost_usd=goal.cost_usd,
                )

            if recovery_plan.action == ACTION_NOTIFY_USER:
                await _apply_plan(
                    recovery_plan, goal_id, store, notifier, status="wait_user"
                )
                return RunOutcome(
                    goal_id=goal_id,
                    final_status="wait_user",
                    steps_executed=step_index + 1,
                    steps_passed=steps_passed,
                    last_failure_class=failure_class,
                    last_recovery_action=recovery_plan.action,
                    cost_usd=goal.cost_usd,
                )

            if recovery_plan.action == ACTION_CANCEL:
                await _apply_plan(
                    recovery_plan, goal_id, store, notifier, status="cancelled"
                )
                return RunOutcome(
                    goal_id=goal_id,
                    final_status="cancelled",
                    steps_executed=step_index + 1,
                    steps_passed=steps_passed,
                    last_failure_class=failure_class,
                    last_recovery_action=recovery_plan.action,
                    cost_usd=goal.cost_usd,
                )

            # Shouldn't reach here; safety fall-through ends the step.
            break

        if not step_done:
            # Exhausted retries on this step without recovery. Surface to user.
            goal = store.get_goal(goal_id) or goal
            fallthrough_plan = RecoveryPlan(
                action=ACTION_NOTIFY_USER,
                reason=f"step {step_index} exhausted {_MAX_STEP_RETRIES} retries",
                failure_class=last_failure_class or "unknown",
                notify={
                    "channel": "sms",
                    "body": (
                        f"Anticipy gave up on '{goal.goal_text[:100]}' "
                        f"after {_MAX_STEP_RETRIES} retries on step {step_index}."
                    ),
                    "urgency": "medium",
                    "goal_id": goal_id,
                },
            )
            await _apply_plan(
                fallthrough_plan, goal_id, store, notifier, status="wait_user"
            )
            return RunOutcome(
                goal_id=goal_id,
                final_status="wait_user",
                steps_executed=step_index + 1,
                steps_passed=steps_passed,
                last_failure_class=last_failure_class,
                last_recovery_action=ACTION_NOTIFY_USER,
                cost_usd=goal.cost_usd,
            )

    # --- end of plan: Layer 2 vision judge -------------------------
    goal = store.get_goal(goal_id) or goal
    final_screenshot = _last_screenshot_from_plan(plan)
    judge: JudgeResult = judge_goal(
        goal.goal_text, final_screenshot, llm=llm
    )

    if judge.verdict == "success":
        store.update_goal_status(
            goal_id, "done", final_artifact_path=final_screenshot
        )
        final_status = "done"
    elif judge.verdict == "impossible_task":
        store.update_goal_status(goal_id, "failed")
        final_status = "failed"
    elif judge.verdict == "reached_captcha":
        # Treat as wait_user.
        notify = {
            "channel": "sms",
            "body": (
                f"Anticipy reached a captcha at the end of "
                f"'{goal.goal_text[:100]}'. Please solve in the tab."
            ),
            "urgency": "high",
            "goal_id": goal_id,
        }
        if notifier is not None:
            await notifier(notify)
        store.update_goal_status(goal_id, "wait_user")
        final_status = "wait_user"
    else:  # needs_more_steps or anything else
        store.update_goal_status(goal_id, "failed")
        final_status = "failed"

    return RunOutcome(
        goal_id=goal_id,
        final_status=final_status,
        judge_verdict=judge.verdict,
        steps_executed=len(plan),
        steps_passed=steps_passed,
        last_failure_class=last_failure_class,
        last_recovery_action=last_recovery_action,
        cost_usd=(store.get_goal(goal_id) or goal).cost_usd,
    )


async def _apply_plan(
    recovery_plan: RecoveryPlan,
    goal_id: str,
    store: RalphStore,
    notifier: Optional[Callable[[dict[str, Any]], Awaitable[None]]],
    *,
    status: str,
) -> None:
    """Persist the recovery plan: status change + optional notify."""
    if recovery_plan.notify:
        # Stash the notify dict on the goal row so any wake-up logic
        # has the channel context.
        store.update_goal_status(
            goal_id, status, channel_payload=recovery_plan.notify
        )
        if notifier is not None:
            try:
                await notifier(recovery_plan.notify)
            except Exception as exc:  # noqa: BLE001
                logger.warning("notifier raised: %s", exc)
    else:
        store.update_goal_status(goal_id, status)


def _last_screenshot_from_plan(plan: list[dict[str, Any]]) -> Optional[str]:
    """Look for an explicit final screenshot path in the last step.

    Steps may set 'final_screenshot_path' to point at the page snapshot
    the bridge will produce. Otherwise None and judge_goal gets only
    text context.
    """
    if not plan:
        return None
    return plan[-1].get("final_screenshot_path")


__all__ = ["RunOutcome", "StepResult", "run_goal"]
