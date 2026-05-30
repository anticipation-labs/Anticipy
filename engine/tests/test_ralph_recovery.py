"""Unit tests for the Ralph recovery dispatcher (Phase 4-2).

Covers every failure class mapping, the captcha / vision retry-then-
notify transitions, exponential backoff, and Retry-After honoring.
All mocked, no network.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ralph.recovery import (  # noqa: E402
    ACTION_CANCEL,
    ACTION_ESCALATE_MODEL,
    ACTION_NOTIFY_USER,
    ACTION_RETRY_LATER,
    ACTION_RETRY_NOW,
    VALID_ACTIONS,
    recover,
)
from app.ralph.store import Goal  # noqa: E402


def _goal(
    *,
    goal_id: str = "g_abc",
    user_id: str = "u1",
    goal_text: str = "draft email to ada@example.com",
    cost_usd: float = 0.0,
    cost_cap_usd: float = 0.05,
    consecutive_failures: int = 0,
) -> Goal:
    now = int(time.time())
    return Goal(
        goal_id=goal_id,
        user_id=user_id,
        goal_text=goal_text,
        origin="inject",
        status="running",
        cost_usd=cost_usd,
        cost_cap_usd=cost_cap_usd,
        consecutive_failures=consecutive_failures,
        next_attempt_at=None,
        created_at=now,
        updated_at=now,
        surface="web",
        channel_payload=None,
        final_artifact_path=None,
    )


def test_login_wall_notifies_user_with_tab_url() -> None:
    plan = recover(
        "login_wall",
        _goal(),
        now_ts=1000,
        extras={"tab_url": "https://mail.google.com/"},
    )
    assert plan.action == ACTION_NOTIFY_USER
    assert plan.failure_class == "login_wall"
    assert plan.notify is not None
    assert plan.notify["channel"] == "sms"
    assert plan.notify["urgency"] == "high"
    assert "mail.google.com" in plan.notify["body"]
    assert plan.notify["goal_id"] == "g_abc"
    assert plan.notify["deep_link"] == "anticipy://goal/g_abc/continue"


def test_captcha_first_attempt_tries_solver() -> None:
    plan = recover("captcha", _goal(), now_ts=1000)
    assert plan.action == ACTION_RETRY_NOW
    assert plan.extras.get("captcha_tried") is True
    assert plan.notify is None  # solver runs silently first


def test_captcha_after_solver_failed_notifies_user() -> None:
    plan = recover(
        "captcha",
        _goal(),
        now_ts=1000,
        extras={"captcha_tried": True},
    )
    assert plan.action == ACTION_NOTIFY_USER
    assert plan.notify is not None
    assert "solver failed" in plan.notify["body"].lower()


def test_network_first_failure_backs_off_60s() -> None:
    plan = recover("network", _goal(consecutive_failures=0), now_ts=1000)
    assert plan.action == ACTION_RETRY_LATER
    assert plan.next_attempt_at == 1000 + 60


def test_network_exponential_backoff_progression() -> None:
    schedule = [(0, 60), (1, 300), (2, 1800), (3, 10800), (4, 86400)]
    for consec, expected_wait in schedule:
        plan = recover(
            "network", _goal(consecutive_failures=consec), now_ts=2000
        )
        assert plan.action == ACTION_RETRY_LATER
        assert plan.next_attempt_at == 2000 + expected_wait, (
            f"consec={consec} expected {expected_wait}s, "
            f"got {plan.next_attempt_at - 2000}s"
        )


def test_network_after_backoff_exhausted_notifies_user() -> None:
    plan = recover("network", _goal(consecutive_failures=5), now_ts=1000)
    assert plan.action == ACTION_NOTIFY_USER
    assert plan.notify is not None
    assert "network" in plan.reason.lower()


def test_rate_limit_honors_retry_after() -> None:
    plan = recover(
        "rate_limit",
        _goal(),
        now_ts=1000,
        extras={"retry_after_s": 42},
    )
    assert plan.action == ACTION_RETRY_LATER
    assert plan.next_attempt_at == 1000 + 42


def test_rate_limit_fallback_backoff_when_no_header() -> None:
    plan0 = recover("rate_limit", _goal(consecutive_failures=0), now_ts=1000)
    plan1 = recover("rate_limit", _goal(consecutive_failures=1), now_ts=1000)
    plan2 = recover("rate_limit", _goal(consecutive_failures=2), now_ts=1000)
    plan3 = recover("rate_limit", _goal(consecutive_failures=99), now_ts=1000)
    assert plan0.next_attempt_at == 1000 + 300
    assert plan1.next_attempt_at == 1000 + 1800
    assert plan2.next_attempt_at == 1000 + 21600
    # Clamped at the last slot for large counters.
    assert plan3.next_attempt_at == 1000 + 21600


def test_element_missing_first_escalates_to_vision() -> None:
    plan = recover("element_missing", _goal(), now_ts=1000)
    assert plan.action == ACTION_ESCALATE_MODEL
    assert plan.use_vision is True
    assert plan.extras.get("vision_tried") is True


def test_element_missing_after_vision_notifies_user() -> None:
    plan = recover(
        "element_missing",
        _goal(),
        now_ts=1000,
        extras={"vision_tried": True},
    )
    assert plan.action == ACTION_NOTIFY_USER
    assert plan.notify is not None


def test_payment_required_always_notifies_never_autopays() -> None:
    plan = recover("payment_required", _goal(), now_ts=1000)
    assert plan.action == ACTION_NOTIFY_USER
    assert plan.notify is not None
    # CONFIRM language signals "we will not pay without your reply".
    assert "confirm" in plan.notify["body"].lower()
    assert plan.notify["urgency"] == "high"


def test_account_locked_cancels_goal() -> None:
    plan = recover("account_locked", _goal(), now_ts=1000)
    assert plan.action == ACTION_CANCEL
    assert plan.notify is not None
    assert "locked" in plan.notify["body"].lower() or "suspend" in plan.notify["body"].lower()


def test_ambiguous_dom_first_escalates_to_vision() -> None:
    plan = recover("ambiguous_dom", _goal(), now_ts=1000)
    assert plan.action == ACTION_ESCALATE_MODEL
    assert plan.use_vision is True


def test_ambiguous_dom_after_vision_notifies() -> None:
    plan = recover(
        "ambiguous_dom",
        _goal(),
        now_ts=1000,
        extras={"vision_tried": True},
    )
    assert plan.action == ACTION_NOTIFY_USER


def test_cost_cap_notifies_with_spend_total() -> None:
    plan = recover("cost_cap", _goal(cost_usd=0.07), now_ts=1000)
    assert plan.action == ACTION_NOTIFY_USER
    assert plan.notify is not None
    assert "$0.0700" in plan.notify["body"] or "0.07" in plan.notify["body"]
    assert "continue" in plan.notify["body"].lower()


def test_model_error_swaps_then_notifies() -> None:
    p1 = recover("model_error", _goal(), now_ts=1000)
    assert p1.action == ACTION_ESCALATE_MODEL
    assert p1.swap_model is True
    assert p1.extras["model_swaps"] == 1

    p2 = recover("model_error", _goal(), now_ts=1000, extras=p1.extras)
    assert p2.action == ACTION_ESCALATE_MODEL
    assert p2.extras["model_swaps"] == 2

    # Third call after 2 swaps -> notify user.
    p3 = recover("model_error", _goal(), now_ts=1000, extras=p2.extras)
    assert p3.action == ACTION_NOTIFY_USER


def test_unknown_notifies_user_with_trace() -> None:
    plan = recover(
        "unknown",
        _goal(),
        now_ts=1000,
        extras={"trace": "SomeError at line 42 in foo()"},
    )
    assert plan.action == ACTION_NOTIFY_USER
    assert plan.notify is not None
    assert "SomeError" in plan.notify["body"]


def test_invalid_class_raises() -> None:
    with pytest.raises(ValueError):
        recover("totally_made_up_class", _goal())


def test_recovery_plan_to_dict_is_json_safe() -> None:
    import json

    plan = recover("network", _goal(), now_ts=1000)
    blob = json.dumps(plan.to_dict())
    assert "retry_later" in blob


def test_all_returned_actions_are_valid() -> None:
    """Smoke: every class returns an action in VALID_ACTIONS."""
    classes_and_extras: list[tuple[str, dict]] = [
        ("login_wall", {}),
        ("captcha", {}),
        ("captcha", {"captcha_tried": True}),
        ("network", {}),
        ("rate_limit", {}),
        ("element_missing", {}),
        ("element_missing", {"vision_tried": True}),
        ("payment_required", {}),
        ("account_locked", {}),
        ("ambiguous_dom", {}),
        ("cost_cap", {}),
        ("model_error", {}),
        ("model_error", {"model_swaps": 2}),
        ("unknown", {}),
    ]
    for cls, extras in classes_and_extras:
        plan = recover(cls, _goal(), now_ts=1000, extras=extras)
        assert plan.action in VALID_ACTIONS, f"{cls} -> {plan.action!r}"
        assert plan.failure_class == cls


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
