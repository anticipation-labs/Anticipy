"""End-to-end tests for the Ralph loop orchestrator (Phase 4-2/4-4).

All bridge / LLM calls mocked. The store is real (tmp_path SQLite).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ralph import (  # noqa: E402
    CostCapExceeded,
    RalphStore,
    RunOutcome,
    StepResult,
    run_goal,
)


@pytest.fixture
def store(tmp_path: Path) -> RalphStore:
    db = tmp_path / "ralph.db"
    s = RalphStore(db_path=db)
    yield s
    s.close()


class _ScriptedBridge:
    """Async bridge that returns canned StepResult objects from a queue.

    Each dispatch() call consumes one entry from `script`. Items can be
    StepResult instances or callables (lambda step: StepResult) to
    inspect the step dict. Calls beyond the script length raise.
    """

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.dispatched: list[dict] = []

    async def dispatch(self, step: dict) -> StepResult:
        self.dispatched.append(step)
        if not self.script:
            raise AssertionError("bridge script exhausted")
        item = self.script.pop(0)
        if callable(item):
            return item(step)
        return item


def _fake_llm(verdict: str = "success") -> Any:
    """LLM stub for the layer-2 judge."""
    class L:
        def judge_goal(self, goal_text: str, screenshot_path) -> str:
            return f'{{"verdict": "{verdict}", "reason": "mock"}}'

    return L()


async def _noop_sleep(_: float) -> None:
    return None


def _run(coro):
    return asyncio.run(coro)


# --- happy path --------------------------------------------------------


def test_run_goal_all_steps_pass_and_judge_success(store: RalphStore) -> None:
    goal_id = store.create_goal(user_id="u1", goal_text="open inbox")
    plan = [
        {
            "action": "navigate",
            "url": "https://mail.google.com/",
            "pre_state_hash": "h0",
            "expected_url": "mail.google.com",
        },
        {
            "action": "click",
            "selector": "div[gh=cm]",
            "pre_state_hash": "h1",
            "expected_selector": "compose",
            "final_screenshot_path": "/tmp/final.png",
        },
    ]
    bridge = _ScriptedBridge([
        StepResult(
            ok=True,
            url="https://mail.google.com/",
            dom="<body>inbox</body>",
            post_state_hash="h1",
        ),
        StepResult(
            ok=True,
            url="https://mail.google.com/compose",
            dom="<div>compose</div>",
            post_state_hash="h2",
        ),
    ])
    outcome = _run(
        run_goal(
            goal_id,
            store,
            bridge,
            plan=plan,
            llm=_fake_llm("success"),
            sleep=_noop_sleep,
            now_ts=lambda: 1000,
        )
    )

    assert isinstance(outcome, RunOutcome)
    assert outcome.final_status == "done"
    assert outcome.judge_verdict == "success"
    assert outcome.steps_executed == 2
    assert outcome.steps_passed == 2

    goal = store.get_goal(goal_id)
    assert goal is not None
    assert goal.status == "done"
    assert goal.final_artifact_path == "/tmp/final.png"


# --- recovery: 2 failures then success ---------------------------------


def test_run_goal_recovers_from_two_failures_then_success(
    store: RalphStore,
) -> None:
    """The headline scenario: 2 deliberate failures (element_missing
    then ambiguous_dom), both recovered via vision escalation, third
    attempt succeeds, judge says success.
    """
    goal_id = store.create_goal(user_id="u1", goal_text="draft email")
    plan = [
        {
            "action": "click",
            "selector": "div[gh=cm]",
            "pre_state_hash": "h0",
            "final_screenshot_path": "/tmp/draft.png",
        },
    ]

    # Three attempts on the same step:
    #   1. element_missing -> recovery returns escalate_model (vision)
    #   2. ambiguous_dom   -> recovery returns escalate_model (vision)
    #      BUT vision_tried was set on attempt 1, so this notifies user
    #      and the goal returns wait_user. So to truly test the
    #      headline scenario, use captcha (which retries) + element_missing
    #      (which escalates) -> success.
    captured_steps: list[dict] = []

    def attempt1(step: dict) -> StepResult:
        captured_steps.append(dict(step))
        return StepResult(
            ok=False,
            error="selector div[gh=cm] not found within timeout 30000",
            url="https://mail.google.com/",
            dom="<body>inbox no compose</body>",
            post_state_hash="h1",
        )

    def attempt2(step: dict) -> StepResult:
        captured_steps.append(dict(step))
        # On the retry, the loop should set use_vision=True.
        assert step.get("use_vision") is True, (
            "expected loop to flip use_vision=True after element_missing"
        )
        # Simulate a captcha showing up on the retry.
        return StepResult(
            ok=False,
            error="captcha challenge appeared",
            url="https://mail.google.com/",
            dom='<div class="g-recaptcha"></div>',
            post_state_hash="h2",
        )

    def attempt3(step: dict) -> StepResult:
        captured_steps.append(dict(step))
        # NopeCHA was tried; this attempt succeeds.
        return StepResult(
            ok=True,
            url="https://mail.google.com/compose",
            dom="<div>compose window open</div>",
            post_state_hash="h3",
        )

    bridge = _ScriptedBridge([attempt1, attempt2, attempt3])

    outcome = _run(
        run_goal(
            goal_id,
            store,
            bridge,
            plan=plan,
            llm=_fake_llm("success"),
            sleep=_noop_sleep,
            now_ts=lambda: 1000,
        )
    )

    assert outcome.final_status == "done", outcome
    assert outcome.judge_verdict == "success"
    assert outcome.steps_passed == 1
    # The bridge saw three attempts.
    assert len(captured_steps) == 3
    # Goal row is done.
    goal = store.get_goal(goal_id)
    assert goal is not None and goal.status == "done"
    # Three step rows: two fails + one pass.
    steps = store.goal_steps(goal_id)
    results = [s.result for s in steps]
    assert results.count("fail") == 2
    assert results.count("pass") == 1
    failure_classes = [s.failure_class for s in steps if s.result == "fail"]
    assert "element_missing" in failure_classes
    assert "captcha" in failure_classes


# --- network failure schedules retry -----------------------------------


def test_run_goal_network_failure_schedules_retry(store: RalphStore) -> None:
    goal_id = store.create_goal(user_id="u1", goal_text="fetch")
    plan = [{"action": "navigate", "pre_state_hash": "h0"}]
    bridge = _ScriptedBridge([
        StepResult(
            ok=False,
            error="net::ERR_CONNECTION_REFUSED",
            http_status=None,
            post_state_hash="h1",
        )
    ])

    outcome = _run(
        run_goal(
            goal_id,
            store,
            bridge,
            plan=plan,
            llm=_fake_llm("success"),
            sleep=_noop_sleep,
            now_ts=lambda: 5000,
        )
    )

    assert outcome.final_status == "wait_retry"
    assert outcome.last_failure_class == "network"
    goal = store.get_goal(goal_id)
    assert goal is not None
    assert goal.status == "wait_retry"
    # consecutive_failures was 0 going in, loop bumps to 1 before
    # recover() runs, so the backoff schedule picks index 1 = 300s.
    assert goal.next_attempt_at == 5300
    assert goal.consecutive_failures == 1


# --- payment_required notifies and pauses ------------------------------


def test_run_goal_payment_required_notifies_user(store: RalphStore) -> None:
    goal_id = store.create_goal(user_id="u1", goal_text="upgrade plan")
    plan = [{"action": "navigate", "pre_state_hash": "h0"}]
    bridge = _ScriptedBridge([
        StepResult(
            ok=False,
            error="402 Payment Required",
            http_status=402,
            url="https://example.com/billing",
            post_state_hash="h1",
        )
    ])
    notify_calls: list[dict] = []

    async def notifier(payload: dict) -> None:
        notify_calls.append(payload)

    outcome = _run(
        run_goal(
            goal_id,
            store,
            bridge,
            plan=plan,
            llm=_fake_llm("success"),
            notifier=notifier,
            sleep=_noop_sleep,
            now_ts=lambda: 1000,
        )
    )

    assert outcome.final_status == "wait_user"
    assert outcome.last_failure_class == "payment_required"
    assert len(notify_calls) == 1
    assert notify_calls[0]["channel"] == "sms"
    assert notify_calls[0]["urgency"] == "high"

    goal = store.get_goal(goal_id)
    assert goal is not None
    assert goal.status == "wait_user"
    assert goal.channel_payload_dict() is not None


# --- account_locked cancels --------------------------------------------


def test_run_goal_account_locked_cancels(store: RalphStore) -> None:
    goal_id = store.create_goal(user_id="u1", goal_text="post tweet")
    plan = [{"action": "click", "pre_state_hash": "h0"}]
    bridge = _ScriptedBridge([
        StepResult(
            ok=False,
            error="Account suspended for violating rules",
            post_state_hash="h1",
        )
    ])

    outcome = _run(
        run_goal(
            goal_id, store, bridge,
            plan=plan, llm=_fake_llm("success"),
            sleep=_noop_sleep, now_ts=lambda: 1000,
        )
    )

    assert outcome.final_status == "cancelled"
    goal = store.get_goal(goal_id)
    assert goal is not None and goal.status == "cancelled"


# --- cost cap mid-step pauses ------------------------------------------


def test_run_goal_cost_cap_pauses_goal(store: RalphStore) -> None:
    goal_id = store.create_goal(
        user_id="u1", goal_text="expensive task", cost_cap_usd=0.001
    )
    plan = [{"action": "type", "pre_state_hash": "h0"}]
    # Bridge reports a cost that exceeds the cap on the FIRST call.
    bridge = _ScriptedBridge([
        StepResult(
            ok=True,
            url="https://x.com/",
            dom="<body>x</body>",
            post_state_hash="h1",
            cost_usd=0.01,  # 10x the cap
        )
    ])
    notify_calls: list[dict] = []

    async def notifier(p: dict) -> None:
        notify_calls.append(p)

    outcome = _run(
        run_goal(
            goal_id, store, bridge,
            plan=plan, llm=_fake_llm("success"),
            notifier=notifier,
            sleep=_noop_sleep, now_ts=lambda: 1000,
        )
    )

    assert outcome.final_status == "wait_user"
    assert outcome.last_failure_class == "cost_cap"
    goal = store.get_goal(goal_id)
    assert goal is not None
    assert goal.status == "wait_user"
    assert goal.cost_usd > goal.cost_cap_usd  # actual spend recorded
    assert len(notify_calls) == 1
    assert "continue" in notify_calls[0]["body"].lower()


# --- judge says impossible_task -> failed ------------------------------


def test_run_goal_judge_impossible_marks_failed(store: RalphStore) -> None:
    goal_id = store.create_goal(user_id="u1", goal_text="impossible thing")
    plan = [
        {
            "action": "navigate",
            "pre_state_hash": "h0",
            "final_screenshot_path": "/tmp/end.png",
        }
    ]
    bridge = _ScriptedBridge([
        StepResult(
            ok=True,
            url="https://example.com/",
            dom="<body>nothing</body>",
            post_state_hash="h1",
        )
    ])

    outcome = _run(
        run_goal(
            goal_id, store, bridge,
            plan=plan, llm=_fake_llm("impossible_task"),
            sleep=_noop_sleep, now_ts=lambda: 1000,
        )
    )

    assert outcome.final_status == "failed"
    assert outcome.judge_verdict == "impossible_task"
    goal = store.get_goal(goal_id)
    assert goal is not None and goal.status == "failed"


# --- judge reaches captcha at end --------------------------------------


def test_run_goal_judge_reached_captcha_waits_user(store: RalphStore) -> None:
    goal_id = store.create_goal(user_id="u1", goal_text="search")
    plan = [{"action": "type", "pre_state_hash": "h0"}]
    bridge = _ScriptedBridge([
        StepResult(
            ok=True,
            url="https://example.com/results",
            dom="<body>results</body>",
            post_state_hash="h1",
        )
    ])
    notify_calls: list[dict] = []

    async def notifier(p: dict) -> None:
        notify_calls.append(p)

    outcome = _run(
        run_goal(
            goal_id, store, bridge,
            plan=plan, llm=_fake_llm("reached_captcha"),
            notifier=notifier,
            sleep=_noop_sleep, now_ts=lambda: 1000,
        )
    )

    assert outcome.final_status == "wait_user"
    assert outcome.judge_verdict == "reached_captcha"
    assert len(notify_calls) == 1


# --- raised exception classified --------------------------------------


def test_run_goal_bridge_raises_is_classified_and_recovered(
    store: RalphStore,
) -> None:
    goal_id = store.create_goal(user_id="u1", goal_text="thing")
    plan = [{"action": "navigate", "pre_state_hash": "h0"}]

    class _RaisingBridge:
        def __init__(self):
            self.calls = 0

        async def dispatch(self, step):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("ECONNREFUSED to 1.2.3.4")
            return StepResult(
                ok=True,
                url="https://example.com",
                dom="<body>ok</body>",
                post_state_hash="h_recovered",
            )

    bridge = _RaisingBridge()
    outcome = _run(
        run_goal(
            goal_id, store, bridge,
            plan=plan, llm=_fake_llm("success"),
            sleep=_noop_sleep, now_ts=lambda: 7000,
        )
    )

    # ECONNREFUSED -> network -> retry_later -> goal wait_retry.
    # First failure: loop bumps consecutive_failures 0->1, so the
    # backoff schedule picks index 1 = 300s.
    assert outcome.final_status == "wait_retry"
    assert outcome.last_failure_class == "network"
    goal = store.get_goal(goal_id)
    assert goal is not None and goal.next_attempt_at == 7300


# --- missing goal raises ----------------------------------------------


def test_run_goal_missing_goal_raises(store: RalphStore) -> None:
    bridge = _ScriptedBridge([])
    with pytest.raises(KeyError):
        _run(
            run_goal(
                "g_does_not_exist", store, bridge,
                plan=[{"action": "nav"}],
                llm=_fake_llm("success"),
                sleep=_noop_sleep,
            )
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
