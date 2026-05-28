"""Tests for the new multi-agent planner.plan() entry point."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app import planner
from app.models import DegradedResponse
from app.planner import Plan, PlanStep, plan


def _fake_llm_response(payload):
    """Return an AsyncMock whose await returns ``payload`` (or raises if it's
    an exception class)."""
    async def _call(*args, **kwargs):
        if isinstance(payload, type) and issubclass(payload, BaseException):
            raise payload("boom")
        return payload
    return AsyncMock(side_effect=_call)


# ─────────────────────────────────────────────────────────────────────────
# Happy path — well-formed LLM output
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_plan_returns_3_to_7_steps():
    payload = {
        "steps": [
            {"step": 1, "goal": "Open the page", "success_criteria": "URL contains target"},
            {"step": 2, "goal": "Find the price", "success_criteria": "Price element visible"},
            {"step": 3, "goal": "Quote the price", "success_criteria": "Number in result"},
            {"step": 4, "goal": "Confirm answer", "success_criteria": "result.message has price"},
        ],
        "required_facts": ["AMZN price"],
        "unreachable": False,
        "unreachable_reason": "",
        "starting_url": "https://example.com/quote",
        "success": "We have the price in the message",
    }
    with patch.object(planner, "llm_call_json", _fake_llm_response(payload)):
        p = await plan(
            task='What is the AMZN price?',
            initial_axtree_or_dom="<page><url>about:blank</url></page>",
            user_id="user-1",
        )
    assert isinstance(p, Plan)
    assert 3 <= len(p.steps) <= 7
    assert all(isinstance(s, PlanStep) for s in p.steps)
    assert p.required_facts == ["AMZN price"]
    assert p.starting_url == "https://example.com/quote"
    assert p.unreachable is False


@pytest.mark.asyncio
async def test_plan_steps_have_goal_and_success_criteria():
    payload = {
        "steps": [
            {"step": 1, "goal": "Open Gmail", "success_criteria": "Inbox visible"},
            {"step": 2, "goal": "Click Compose", "success_criteria": "Compose pane shown"},
            {"step": 3, "goal": "Send the message", "success_criteria": "Sent toast appears"},
        ],
        "required_facts": [],
        "unreachable": False,
        "starting_url": "https://mail.google.com",
        "success": "Email sent",
    }
    with patch.object(planner, "llm_call_json", _fake_llm_response(payload)):
        p = await plan("send an email", initial_axtree_or_dom="", user_id="")
    for s in p.steps:
        assert s.goal
        assert s.success_criteria
        assert s.step >= 1


@pytest.mark.asyncio
async def test_plan_caps_at_7_steps():
    payload = {
        "steps": [
            {"step": i, "goal": f"step {i}", "success_criteria": f"check {i}"}
            for i in range(1, 15)
        ],
        "required_facts": [],
        "unreachable": False,
        "starting_url": "https://example.com",
    }
    with patch.object(planner, "llm_call_json", _fake_llm_response(payload)):
        p = await plan("do many things", initial_axtree_or_dom="", user_id="")
    assert len(p.steps) <= 7


@pytest.mark.asyncio
async def test_plan_drops_invalid_steps():
    """LLM returns some malformed steps; planner drops them, keeps good ones."""
    payload = {
        "steps": [
            {"step": 1, "goal": "Good step", "success_criteria": "Visible"},
            {"step": 2, "goal": "", "success_criteria": "Visible"},  # bad
            {"step": 3, "goal": "Good step 2", "success_criteria": ""},  # bad
            {"step": 4, "goal": "Good step 3", "success_criteria": "Visible"},
            "not a dict",  # bad
        ],
        "required_facts": [],
        "unreachable": False,
        "starting_url": "https://example.com",
    }
    with patch.object(planner, "llm_call_json", _fake_llm_response(payload)):
        p = await plan("do x", initial_axtree_or_dom="", user_id="")
    assert len(p.steps) == 2
    assert p.steps[0].goal == "Good step"
    assert p.steps[1].goal == "Good step 3"


# ─────────────────────────────────────────────────────────────────────────
# Required facts
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_plan_extracts_required_facts():
    payload = {
        "steps": [
            {"step": 1, "goal": "x", "success_criteria": "y"},
            {"step": 2, "goal": "x", "success_criteria": "y"},
            {"step": 3, "goal": "x", "success_criteria": "y"},
        ],
        "required_facts": ["May 12 at 2pm", "Acme Corp"],
        "unreachable": False,
        "starting_url": "https://example.com",
    }
    with patch.object(planner, "llm_call_json", _fake_llm_response(payload)):
        p = await plan("schedule meeting", initial_axtree_or_dom="", user_id="")
    assert p.required_facts == ["May 12 at 2pm", "Acme Corp"]


@pytest.mark.asyncio
async def test_plan_drops_overlong_facts():
    """A 500-char fact is dropped (> 200 char cap)."""
    payload = {
        "steps": [
            {"step": 1, "goal": "x", "success_criteria": "y"},
            {"step": 2, "goal": "x", "success_criteria": "y"},
            {"step": 3, "goal": "x", "success_criteria": "y"},
        ],
        "required_facts": ["short fact", "x" * 500],
        "unreachable": False,
        "starting_url": "https://example.com",
    }
    with patch.object(planner, "llm_call_json", _fake_llm_response(payload)):
        p = await plan("x", initial_axtree_or_dom="", user_id="")
    assert "short fact" in p.required_facts
    assert "x" * 500 not in p.required_facts


# ─────────────────────────────────────────────────────────────────────────
# Unreachable
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_plan_unreachable_sets_flag_and_reason():
    payload = {
        "steps": [],
        "required_facts": [],
        "unreachable": True,
        "unreachable_reason": "Banking site requires SMS verification.",
        "starting_url": "https://chase.com",
    }
    with patch.object(planner, "llm_call_json", _fake_llm_response(payload)):
        p = await plan("transfer money in chase", initial_axtree_or_dom="", user_id="")
    assert p.unreachable is True
    assert "verification" in p.unreachable_reason.lower()


@pytest.mark.asyncio
async def test_plan_unreachable_supplies_default_reason():
    """When unreachable=True with empty reason, a generic reason is added."""
    payload = {
        "steps": [],
        "required_facts": [],
        "unreachable": True,
        "unreachable_reason": "",
        "starting_url": "https://x.com",
    }
    with patch.object(planner, "llm_call_json", _fake_llm_response(payload)):
        p = await plan("x", initial_axtree_or_dom="", user_id="")
    assert p.unreachable
    assert p.unreachable_reason


# ─────────────────────────────────────────────────────────────────────────
# Starting URL handling
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_plan_normalises_url_without_scheme():
    payload = {
        "steps": [
            {"step": 1, "goal": "x", "success_criteria": "y"},
            {"step": 2, "goal": "x", "success_criteria": "y"},
            {"step": 3, "goal": "x", "success_criteria": "y"},
        ],
        "required_facts": [],
        "unreachable": False,
        "starting_url": "books.toscrape.com",
    }
    with patch.object(planner, "llm_call_json", _fake_llm_response(payload)):
        p = await plan("x", initial_axtree_or_dom="", user_id="")
    assert p.starting_url.startswith("https://")
    assert "books.toscrape.com" in p.starting_url


@pytest.mark.asyncio
async def test_plan_rejects_unsafe_starting_url_with_search_fallback():
    payload = {
        "steps": [
            {"step": 1, "goal": "x", "success_criteria": "y"},
            {"step": 2, "goal": "x", "success_criteria": "y"},
            {"step": 3, "goal": "x", "success_criteria": "y"},
        ],
        "required_facts": [],
        "unreachable": False,
        "starting_url": "javascript:alert(1)",
    }
    with patch.object(planner, "llm_call_json", _fake_llm_response(payload)):
        p = await plan("find latest news", initial_axtree_or_dom="", user_id="")
    # Falls back to a Google search query URL.
    assert p.starting_url.startswith("https://www.google.com/search")


@pytest.mark.asyncio
async def test_plan_prefers_explicit_url_in_task_when_llm_url_unsafe():
    payload = {
        "steps": [
            {"step": 1, "goal": "x", "success_criteria": "y"},
            {"step": 2, "goal": "x", "success_criteria": "y"},
            {"step": 3, "goal": "x", "success_criteria": "y"},
        ],
        "required_facts": [],
        "unreachable": False,
        "starting_url": "javascript:alert(1)",  # unsafe
    }
    with patch.object(planner, "llm_call_json", _fake_llm_response(payload)):
        p = await plan("go to https://example.com/foo", initial_axtree_or_dom="", user_id="")
    assert p.starting_url == "https://example.com/foo"


# ─────────────────────────────────────────────────────────────────────────
# Cascade failure / degraded
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_plan_falls_back_when_cascade_degraded():
    with patch.object(planner, "llm_call_json", _fake_llm_response(DegradedResponse())):
        p = await plan("any task", initial_axtree_or_dom="", user_id="")
    # Heuristic fallback: 3 steps.
    assert len(p.steps) == 3
    assert not p.unreachable


@pytest.mark.asyncio
async def test_plan_falls_back_when_cascade_raises():
    with patch.object(planner, "llm_call_json", _fake_llm_response(RuntimeError)):
        p = await plan("any task", initial_axtree_or_dom="", user_id="")
    assert len(p.steps) >= 3


@pytest.mark.asyncio
async def test_plan_falls_back_on_empty_task():
    p = await plan("", initial_axtree_or_dom="", user_id="")
    assert len(p.steps) == 3  # heuristic fallback
    assert p.starting_url


@pytest.mark.asyncio
async def test_plan_falls_back_on_empty_steps_response():
    """LLM returns valid shape but empty steps and not-unreachable."""
    payload = {
        "steps": [],
        "required_facts": ["price"],
        "unreachable": False,
        "starting_url": "https://example.com",
    }
    with patch.object(planner, "llm_call_json", _fake_llm_response(payload)):
        p = await plan("get price", initial_axtree_or_dom="", user_id="")
    assert len(p.steps) >= 3
    # Required facts and starting_url are preserved through fallback.
    assert "price" in p.required_facts
    assert "example.com" in p.starting_url


# ─────────────────────────────────────────────────────────────────────────
# Role routing — verify the planner asks the cascade for role="planner"
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_plan_calls_cascade_with_planner_role():
    captured = {}

    async def fake(*args, **kwargs):
        captured["role"] = kwargs.get("role")
        captured["user_id"] = kwargs.get("user_id")
        return {
            "steps": [
                {"step": 1, "goal": "x", "success_criteria": "y"},
                {"step": 2, "goal": "x", "success_criteria": "y"},
                {"step": 3, "goal": "x", "success_criteria": "y"},
            ],
            "required_facts": [],
            "unreachable": False,
            "starting_url": "https://example.com",
        }

    with patch.object(planner, "llm_call_json", AsyncMock(side_effect=fake)):
        await plan("x", initial_axtree_or_dom="", user_id="alice")

    assert captured["role"] == "planner"
    assert captured["user_id"] == "alice"


# ─────────────────────────────────────────────────────────────────────────
# Initial state truncation
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_plan_truncates_huge_initial_state():
    """100KB DOM should not be sent verbatim."""
    huge = "<dom>" + ("x" * 100_000) + "</dom>"

    captured_user_msg = {}

    async def fake(messages, *args, **kwargs):
        # Find the user message
        for m in messages:
            if m["role"] == "user":
                captured_user_msg["content"] = m["content"]
        return {
            "steps": [
                {"step": 1, "goal": "x", "success_criteria": "y"},
                {"step": 2, "goal": "x", "success_criteria": "y"},
                {"step": 3, "goal": "x", "success_criteria": "y"},
            ],
            "required_facts": [],
            "unreachable": False,
            "starting_url": "https://x.com",
        }

    with patch.object(planner, "llm_call_json", AsyncMock(side_effect=fake)):
        await plan("x", initial_axtree_or_dom=huge, user_id="")

    assert "snipped" in captured_user_msg["content"]
    assert len(captured_user_msg["content"]) < 20_000


# ─────────────────────────────────────────────────────────────────────────
# Backwards compat — plan_task still works
# ─────────────────────────────────────────────────────────────────────────


def test_plan_task_still_exported():
    """plan_task must remain importable for legacy callers (agent.py)."""
    from app.planner import plan_task  # noqa: F401
