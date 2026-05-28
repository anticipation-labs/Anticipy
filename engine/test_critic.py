"""Tests for app.critic — per-step verdict on action quality."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app import critic as critic_mod
from app.critic import CriticResult, CriticVerdict, criticize
from app.models import DegradedResponse


def _stub_llm(payload):
    async def _call(*a, **kw):
        if isinstance(payload, type) and issubclass(payload, BaseException):
            raise payload("boom")
        return payload
    return AsyncMock(side_effect=_call)


# ─────────────────────────────────────────────────────────────────────────
# Verdict shape sanity
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_criticize_returns_critic_result():
    payload = {"verdict": "progress", "reason": "URL changed", "confidence": 0.8}
    with patch.object(critic_mod, "llm_call_json", _stub_llm(payload)):
        r = await criticize(
            action_taken={"action": "click", "target": "A"},
            before_state="<page url='/home'/>",
            after_state="<page url='/results'/>",
            plan=None,
            step_idx=1,
        )
    assert isinstance(r, CriticResult)
    assert r.verdict == "progress"
    assert r.reason
    assert r.confidence == 0.8


# ─────────────────────────────────────────────────────────────────────────
# 20 labeled examples — verdict must match the LLM-provided label.
#
# This validates the dispatcher: given a verdict the LLM produced, the
# critic returns CriticResult with that verdict (after synonym coercion).
# ─────────────────────────────────────────────────────────────────────────


_LABELED_EXAMPLES: list[dict] = [
    # 5 progress
    {"label": "progress", "llm_verdict": "progress",
     "before": "url=/home", "after": "url=/results"},
    {"label": "progress", "llm_verdict": "progressed",   # synonym
     "before": "search empty", "after": "results 1-10 visible"},
    {"label": "progress", "llm_verdict": "advanced",     # synonym
     "before": "no email pane", "after": "compose pane open"},
    {"label": "progress", "llm_verdict": "moved",        # synonym
     "before": "blank cart", "after": "1 item in cart"},
    {"label": "progress", "llm_verdict": "PROGRESS",     # case
     "before": "modal closed", "after": "modal open"},

    # 5 no_progress
    {"label": "no_progress", "llm_verdict": "no_progress",
     "before": "results page", "after": "results page (unchanged)"},
    {"label": "no_progress", "llm_verdict": "no-progress",  # hyphen variant
     "before": "page", "after": "page (no change)"},
    {"label": "no_progress", "llm_verdict": "stalled",      # synonym
     "before": "captcha", "after": "captcha still"},
    {"label": "no_progress", "llm_verdict": "stuck",        # synonym
     "before": "popup", "after": "popup still up"},
    {"label": "no_progress", "llm_verdict": "failed",       # synonym
     "before": "loading", "after": "error toast"},

    # 5 unsafe
    {"label": "unsafe", "llm_verdict": "unsafe",
     "before": "checkout/", "after": "/admin/delete-account"},
    {"label": "unsafe", "llm_verdict": "UNSAFE",
     "before": "form blank", "after": "credit card typed in non-checkout"},
    {"label": "unsafe", "llm_verdict": "unsafe_action",  # synonym
     "before": "draft", "after": "sent to wrong recipient"},
    {"label": "unsafe", "llm_verdict": "dangerous",      # synonym
     "before": "cart", "after": "payment without confirm"},
    {"label": "unsafe", "llm_verdict": "Unsafe",
     "before": "settings", "after": "delete account button clicked"},

    # 5 done
    {"label": "done", "llm_verdict": "done",
     "before": "form filled", "after": "Thank you for your order #ABC123"},
    {"label": "done", "llm_verdict": "complete",       # synonym
     "before": "search", "after": "answer rendered"},
    {"label": "done", "llm_verdict": "completed",      # synonym
     "before": "calendar", "after": "event created"},
    {"label": "done", "llm_verdict": "finished",       # synonym
     "before": "compose", "after": "message sent confirmation"},
    {"label": "done", "llm_verdict": "DONE",
     "before": "task list", "after": "all items checked"},
]


@pytest.mark.parametrize("ex", _LABELED_EXAMPLES, ids=lambda x: f"{x['label']}-{x['llm_verdict']}")
@pytest.mark.asyncio
async def test_critic_labeled_examples(ex):
    payload = {
        "verdict": ex["llm_verdict"],
        "reason": "labeled test",
        "confidence": 0.7,
    }
    with patch.object(critic_mod, "llm_call_json", _stub_llm(payload)):
        r = await criticize(
            action_taken={"action": "click"},
            before_state=ex["before"],
            after_state=ex["after"],
            plan=[{"step": 1, "goal": "x", "success_criteria": "y"}],
            step_idx=1,
        )
    assert r.verdict == ex["label"], (
        f"expected {ex['label']} for LLM='{ex['llm_verdict']}', got {r.verdict}"
    )


# ─────────────────────────────────────────────────────────────────────────
# Failure modes — cascade unavailable / raises / non-dict
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_critic_returns_no_progress_on_degraded():
    with patch.object(critic_mod, "llm_call_json", _stub_llm(DegradedResponse())):
        r = await criticize(
            action_taken={}, before_state="", after_state="", plan=None, step_idx=1,
        )
    assert r.verdict == "no_progress"
    assert "unavailable" in r.reason.lower() or "cascade" in r.reason.lower()


@pytest.mark.asyncio
async def test_critic_returns_no_progress_on_raise():
    with patch.object(critic_mod, "llm_call_json", _stub_llm(RuntimeError)):
        r = await criticize(
            action_taken={}, before_state="", after_state="", plan=None, step_idx=1,
        )
    assert r.verdict == "no_progress"


@pytest.mark.asyncio
async def test_critic_returns_no_progress_on_unknown_verdict():
    payload = {"verdict": "purple", "reason": "x", "confidence": 0.5}
    with patch.object(critic_mod, "llm_call_json", _stub_llm(payload)):
        r = await criticize(
            action_taken={}, before_state="", after_state="", plan=None, step_idx=1,
        )
    assert r.verdict == "no_progress"


@pytest.mark.asyncio
async def test_critic_returns_no_progress_on_non_dict():
    payload = "this is a string"
    with patch.object(critic_mod, "llm_call_json", _stub_llm(payload)):
        r = await criticize(
            action_taken={}, before_state="", after_state="", plan=None, step_idx=1,
        )
    assert r.verdict == "no_progress"


# ─────────────────────────────────────────────────────────────────────────
# Confidence clamping
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_critic_clamps_confidence_above_1():
    payload = {"verdict": "progress", "confidence": 5.0, "reason": "x"}
    with patch.object(critic_mod, "llm_call_json", _stub_llm(payload)):
        r = await criticize(action_taken={}, plan=None)
    assert r.confidence == 1.0


@pytest.mark.asyncio
async def test_critic_clamps_confidence_below_0():
    payload = {"verdict": "progress", "confidence": -0.5, "reason": "x"}
    with patch.object(critic_mod, "llm_call_json", _stub_llm(payload)):
        r = await criticize(action_taken={}, plan=None)
    assert r.confidence == 0.0


@pytest.mark.asyncio
async def test_critic_handles_non_numeric_confidence():
    payload = {"verdict": "progress", "confidence": "high", "reason": "x"}
    with patch.object(critic_mod, "llm_call_json", _stub_llm(payload)):
        r = await criticize(action_taken={}, plan=None)
    assert r.confidence == 0.0


# ─────────────────────────────────────────────────────────────────────────
# Plan + action serialization
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_critic_includes_plan_steps_in_prompt():
    """Verify the plan's success_criteria reach the LLM."""
    captured = {}

    async def fake(messages, *args, **kwargs):
        for m in messages:
            if m["role"] == "user":
                captured["user"] = m["content"]
        return {"verdict": "progress", "confidence": 0.5, "reason": "x"}

    with patch.object(critic_mod, "llm_call_json", AsyncMock(side_effect=fake)):
        await criticize(
            action_taken={"action": "click"},
            plan=[
                {"step": 1, "goal": "Open page", "success_criteria": "URL contains target"},
                {"step": 2, "goal": "Click the button", "success_criteria": "Modal opens"},
            ],
            step_idx=2,
        )

    assert "Open page" in captured["user"]
    assert "URL contains target" in captured["user"]
    assert "Click the button" in captured["user"]


@pytest.mark.asyncio
async def test_critic_handles_plan_dataclass():
    """Plan can be the planner.Plan dataclass — critic must serialize it."""
    from app.planner import Plan, PlanStep

    plan = Plan(
        steps=[
            PlanStep(step=1, goal="Search", success_criteria="Results page"),
            PlanStep(step=2, goal="Click first", success_criteria="Detail page"),
        ],
        required_facts=[],
        unreachable=False,
        starting_url="https://x.com",
        success="ok",
    )

    captured = {}
    async def fake(messages, *args, **kwargs):
        for m in messages:
            if m["role"] == "user":
                captured["user"] = m["content"]
        return {"verdict": "progress", "confidence": 0.5, "reason": "x"}

    with patch.object(critic_mod, "llm_call_json", AsyncMock(side_effect=fake)):
        await criticize(action_taken={"action": "click"}, plan=plan, step_idx=1)

    assert "Search" in captured["user"]
    assert "Detail page" in captured["user"]


@pytest.mark.asyncio
async def test_critic_truncates_huge_states():
    big_before = "<page>" + ("x" * 50_000) + "</page>"
    big_after = "<page>" + ("y" * 50_000) + "</page>"

    captured = {}
    async def fake(messages, *args, **kwargs):
        for m in messages:
            if m["role"] == "user":
                captured["user"] = m["content"]
        return {"verdict": "progress", "confidence": 0.5}

    with patch.object(critic_mod, "llm_call_json", AsyncMock(side_effect=fake)):
        await criticize(
            action_taken={"action": "scroll"},
            before_state=big_before,
            after_state=big_after,
            plan=None,
            step_idx=1,
        )

    # Massive states are truncated.
    assert "snipped" in captured["user"]
    # Total prompt stays small.
    assert len(captured["user"]) < 12_000


# ─────────────────────────────────────────────────────────────────────────
# Role routing — critic uses role="critic"
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_critic_uses_critic_role():
    captured = {}

    async def fake(*args, **kwargs):
        captured["role"] = kwargs.get("role")
        captured["user_id"] = kwargs.get("user_id")
        return {"verdict": "progress", "confidence": 0.5}

    with patch.object(critic_mod, "llm_call_json", AsyncMock(side_effect=fake)):
        await criticize(
            action_taken={"action": "click"},
            plan=None,
            step_idx=1,
            user_id="bob",
        )

    assert captured["role"] == "critic"
    assert captured["user_id"] == "bob"


# ─────────────────────────────────────────────────────────────────────────
# Reason field is preserved and trimmed
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_critic_trims_long_reason():
    long_reason = "x" * 1000
    payload = {"verdict": "progress", "reason": long_reason, "confidence": 0.5}
    with patch.object(critic_mod, "llm_call_json", _stub_llm(payload)):
        r = await criticize(action_taken={}, plan=None)
    assert len(r.reason) <= 240
