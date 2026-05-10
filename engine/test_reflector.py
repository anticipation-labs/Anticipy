"""Tests for app.reflector — pivot/abort/continue meta-decision."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app import reflector as reflect_mod
from app.models import DegradedResponse
from app.planner import Plan, PlanStep
from app.reflector import ReflectorResult, reflect


def _stub_llm(payload):
    async def _call(*a, **kw):
        if isinstance(payload, type) and issubclass(payload, BaseException):
            raise payload("boom")
        return payload
    return AsyncMock(side_effect=_call)


def _sample_plan() -> Plan:
    return Plan(
        steps=[
            PlanStep(step=1, goal="Open Gmail", success_criteria="Inbox visible"),
            PlanStep(step=2, goal="Click Compose", success_criteria="Compose pane"),
            PlanStep(step=3, goal="Send email", success_criteria="Sent toast"),
        ],
        required_facts=[],
        unreachable=False,
        starting_url="https://mail.google.com",
        success="Email sent",
    )


# ─────────────────────────────────────────────────────────────────────────
# pivot
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reflect_pivots_with_new_plan():
    """Critic flagged 2 no_progress → reflector decides to pivot to a new
    plan."""
    payload = {
        "decision": "pivot",
        "new_plan": {
            "steps": [
                {"step": 1, "goal": "Open new compose URL directly",
                 "success_criteria": "Compose pane visible"},
                {"step": 2, "goal": "Type the message",
                 "success_criteria": "Body has draft text"},
                {"step": 3, "goal": "Click Send",
                 "success_criteria": "Sent toast appears"},
            ],
            "required_facts": [],
            "unreachable": False,
            "starting_url": "https://mail.google.com/mail/u/0/?compose=new",
            "success": "Email sent",
        },
        "abort_message": "",
        "reasoning": "The existing compose button was hidden; bypass via URL.",
    }

    history = [
        {"action": {"action": "click", "target": "compose"}, "verdict": "no_progress",
         "reason": "no UI change"},
        {"action": {"action": "click", "target": "compose"}, "verdict": "no_progress",
         "reason": "still no UI change"},
    ]

    with patch.object(reflect_mod, "llm_call_json", _stub_llm(payload)):
        r = await reflect(
            task="email Bob",
            current_plan=_sample_plan(),
            history=history,
            current_state="<page>inbox view</page>",
        )

    assert isinstance(r, ReflectorResult)
    assert r.decision == "pivot"
    assert r.new_plan is not None
    assert isinstance(r.new_plan, Plan)
    assert len(r.new_plan.steps) == 3
    assert r.new_plan.steps[0].goal == "Open new compose URL directly"


@pytest.mark.asyncio
async def test_reflect_pivot_without_new_plan_downgrades_to_continue():
    """Pivot decision but missing/empty new_plan ⇒ downgrade to continue
    rather than crash the loop (cop-out #6)."""
    payload = {
        "decision": "pivot",
        "new_plan": None,  # malformed
        "abort_message": "",
        "reasoning": "x",
    }
    with patch.object(reflect_mod, "llm_call_json", _stub_llm(payload)):
        r = await reflect(
            task="x",
            current_plan=_sample_plan(),
            history=[],
            current_state="x",
        )
    assert r.decision == "continue"
    assert r.new_plan is None


@pytest.mark.asyncio
async def test_reflect_pivot_with_empty_steps_downgrades():
    payload = {
        "decision": "pivot",
        "new_plan": {
            "steps": [],
            "required_facts": [],
            "unreachable": False,
            "starting_url": "https://x.com",
        },
        "abort_message": "",
    }
    with patch.object(reflect_mod, "llm_call_json", _stub_llm(payload)):
        r = await reflect(task="x", current_plan=_sample_plan(), history=[], current_state="")
    assert r.decision == "continue"


# ─────────────────────────────────────────────────────────────────────────
# abort
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reflect_aborts_with_message():
    payload = {
        "decision": "abort",
        "new_plan": None,
        "abort_message": (
            "Bank's site is asking for an SMS code I can't receive. "
            "Want me to retry on a different account?"
        ),
        "reasoning": "Hard auth wall",
    }
    with patch.object(reflect_mod, "llm_call_json", _stub_llm(payload)):
        r = await reflect(
            task="transfer money",
            current_plan=_sample_plan(),
            history=[],
            current_state="<page>SMS verification page</page>",
        )
    assert r.decision == "abort"
    assert "SMS code" in r.abort_message


@pytest.mark.asyncio
async def test_reflect_abort_without_message_supplies_default():
    payload = {
        "decision": "abort",
        "new_plan": None,
        "abort_message": "",
        "reasoning": "x",
    }
    with patch.object(reflect_mod, "llm_call_json", _stub_llm(payload)):
        r = await reflect(task="x", current_plan=_sample_plan(), history=[], current_state="")
    assert r.decision == "abort"
    assert r.abort_message  # non-empty fallback


# ─────────────────────────────────────────────────────────────────────────
# continue
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reflect_continues_when_recoverable():
    """Reflector says 'continue' — keep the existing plan, no new_plan."""
    payload = {
        "decision": "continue",
        "new_plan": None,
        "abort_message": "",
        "reasoning": "Page is mid-navigation; one more step should finish it.",
    }
    with patch.object(reflect_mod, "llm_call_json", _stub_llm(payload)):
        r = await reflect(
            task="x",
            current_plan=_sample_plan(),
            history=[
                {"action": {"action": "click"}, "verdict": "no_progress"},
                {"action": {"action": "click"}, "verdict": "no_progress"},
            ],
            current_state="<page>loading</page>",
        )
    assert r.decision == "continue"
    assert r.new_plan is None
    assert r.abort_message == ""
    assert "mid-navigation" in r.reasoning


@pytest.mark.asyncio
async def test_reflect_returns_continue_after_progress_history():
    """Even if asked, reflector returns continue when it sees the history
    actually shows progress signs."""
    payload = {
        "decision": "continue",
        "reasoning": "Progress visible in history",
    }
    with patch.object(reflect_mod, "llm_call_json", _stub_llm(payload)):
        r = await reflect(
            task="x",
            current_plan=_sample_plan(),
            history=[
                {"action": {"action": "click"}, "verdict": "progress"},
                {"action": {"action": "click"}, "verdict": "progress"},
            ],
            current_state="<page>useful change</page>",
        )
    assert r.decision == "continue"


# ─────────────────────────────────────────────────────────────────────────
# Synonym coercion for decision
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("pivot", "pivot"),
        ("PIVOT", "pivot"),
        ("replan", "pivot"),
        ("abort", "abort"),
        ("stop", "abort"),
        ("give_up", "abort"),
        ("continue", "continue"),
        ("retry", "continue"),
        ("keep_going", "continue"),
    ],
)
@pytest.mark.asyncio
async def test_reflect_decision_synonyms(raw, expected):
    payload = {"decision": raw, "abort_message": "x", "new_plan": None}
    if expected == "pivot":
        # provide a valid plan so we don't hit the downgrade path
        payload["new_plan"] = {
            "steps": [
                {"step": 1, "goal": "x", "success_criteria": "y"},
                {"step": 2, "goal": "x", "success_criteria": "y"},
                {"step": 3, "goal": "x", "success_criteria": "y"},
            ],
            "required_facts": [],
            "unreachable": False,
            "starting_url": "https://x.com",
        }
    with patch.object(reflect_mod, "llm_call_json", _stub_llm(payload)):
        r = await reflect(task="x", current_plan=_sample_plan(), history=[], current_state="")
    assert r.decision == expected


# ─────────────────────────────────────────────────────────────────────────
# Failure modes
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reflect_continues_on_degraded_cascade():
    """Cop-out #6: don't abort spuriously when the LLM is down."""
    with patch.object(reflect_mod, "llm_call_json", _stub_llm(DegradedResponse())):
        r = await reflect(task="x", current_plan=_sample_plan(), history=[], current_state="")
    assert r.decision == "continue"


@pytest.mark.asyncio
async def test_reflect_continues_on_raise():
    with patch.object(reflect_mod, "llm_call_json", _stub_llm(RuntimeError)):
        r = await reflect(task="x", current_plan=_sample_plan(), history=[], current_state="")
    assert r.decision == "continue"


@pytest.mark.asyncio
async def test_reflect_continues_on_unknown_decision():
    payload = {"decision": "purple", "reasoning": "x"}
    with patch.object(reflect_mod, "llm_call_json", _stub_llm(payload)):
        r = await reflect(task="x", current_plan=_sample_plan(), history=[], current_state="")
    assert r.decision == "continue"


# ─────────────────────────────────────────────────────────────────────────
# Role routing — reflector uses role="reflector"
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reflect_uses_reflector_role():
    captured = {}

    async def fake(*args, **kwargs):
        captured["role"] = kwargs.get("role")
        return {"decision": "continue", "reasoning": "x"}

    with patch.object(reflect_mod, "llm_call_json", AsyncMock(side_effect=fake)):
        await reflect(task="x", current_plan=_sample_plan(), history=[], current_state="", user_id="alice")

    assert captured["role"] == "reflector"


# ─────────────────────────────────────────────────────────────────────────
# History serialization handles common shapes
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reflect_includes_history_in_prompt():
    captured = {}

    async def fake(messages, *args, **kwargs):
        for m in messages:
            if m["role"] == "user":
                captured["user"] = m["content"]
        return {"decision": "continue", "reasoning": "x"}

    history = [
        {"action": {"action": "click", "target": "B"}, "verdict": "no_progress",
         "reason": "no DOM change"},
        {"action": {"action": "scroll", "value": "down"}, "verdict": "no_progress",
         "reason": "still nothing"},
    ]

    with patch.object(reflect_mod, "llm_call_json", AsyncMock(side_effect=fake)):
        await reflect(task="x", current_plan=_sample_plan(), history=history, current_state="")

    assert "no_progress" in captured["user"]
    # Both actions appear in the prompt (action verb visible).
    assert "click" in captured["user"]
    assert "scroll" in captured["user"]


@pytest.mark.asyncio
async def test_reflect_handles_tuple_history():
    """History as list of (action, verdict) tuples."""
    captured = {}
    async def fake(messages, *args, **kwargs):
        for m in messages:
            if m["role"] == "user":
                captured["user"] = m["content"]
        return {"decision": "continue", "reasoning": "x"}

    with patch.object(reflect_mod, "llm_call_json", AsyncMock(side_effect=fake)):
        await reflect(
            task="x",
            current_plan=_sample_plan(),
            history=[("click_compose", "no_progress"), ("click_compose", "no_progress")],
            current_state="",
        )
    assert "click_compose" in captured["user"]
    assert "no_progress" in captured["user"]
