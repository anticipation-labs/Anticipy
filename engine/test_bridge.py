"""Unit tests for app.bridge — wires Decision → execute_task."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.bridge import (
    BrowserAgentExecutor,
    compose_goal_from_decision,
    summarize_history,
)
from app.proactive.types import (
    Confidence,
    Decision,
    DecisionKind,
    Intent,
    Reversibility,
    Urgency,
)
from app.verifier import Verdict


# ─── helpers ────────────────────────────────────────────────────────────


def _decision(
    *,
    kind: DecisionKind = DecisionKind.EXECUTE,
    intent_text: str = "Book a reservation at the diner for Friday at 7pm",
    action_verb: str = "book_reservation",
    parameters: dict | None = None,
    confidence_score: float = 0.9,
    reversibility: Reversibility = Reversibility.REVERSIBLE,
    urgency_level: int = 2,
    completion_message: str | None = "Done. Booked.",
    user_facing_question: str | None = None,
    refusal_reason: str | None = None,
) -> Decision:
    intent = Intent.new(
        user_id="u1",
        text=intent_text,
        action_verb=action_verb,
        parameters=parameters or {},
    )
    return Decision.new(
        intent=intent,
        kind=kind,
        confidence=Confidence(score=confidence_score),
        reversibility=reversibility,
        urgency=Urgency(level=urgency_level),
        user_facing_question=user_facing_question,
        completion_message=completion_message,
        refusal_reason=refusal_reason,
    )


# ─── compose_goal_from_decision ─────────────────────────────────────────


def test_compose_goal_uses_intent_text():
    d = _decision(intent_text="Order paper towels")
    assert "Order paper towels" in compose_goal_from_decision(d)


def test_compose_goal_appends_parameters_as_constraints():
    d = _decision(
        intent_text="Order paper towels",
        parameters={"brand": "Bounty", "quantity": 2},
    )
    out = compose_goal_from_decision(d)
    assert "Order paper towels" in out
    assert "brand: Bounty" in out
    assert "quantity: 2" in out
    assert "Constraints:" in out


def test_compose_goal_drops_empty_string_params():
    d = _decision(parameters={"brand": "  ", "ok": "valid"})
    out = compose_goal_from_decision(d)
    assert "ok: valid" in out
    assert "brand:" not in out


def test_compose_goal_drops_none_params():
    d = _decision(parameters={"a": None, "b": "ok"})
    out = compose_goal_from_decision(d)
    assert "b: ok" in out
    # "a: " should not appear (a is None, dropped)
    assert "a: " not in out


def test_compose_goal_no_constraints_section_when_no_params():
    d = _decision(parameters={})
    out = compose_goal_from_decision(d)
    assert "Constraints" not in out


def test_compose_goal_keeps_numeric_zero_values():
    d = _decision(parameters={"count": 0, "price": 0.0})
    out = compose_goal_from_decision(d)
    assert "count: 0" in out
    assert "price: 0" in out


def test_compose_goal_falls_back_to_action_verb_when_text_empty():
    intent = Intent.new(user_id="u", text="", action_verb="search_for_thing")
    d = Decision.new(
        intent=intent,
        kind=DecisionKind.EXECUTE,
        confidence=Confidence(score=0.9),
        reversibility=Reversibility.REVERSIBLE,
        urgency=Urgency(level=2),
    )
    assert compose_goal_from_decision(d) == "search_for_thing"


# ─── summarize_history ──────────────────────────────────────────────────


def test_summarize_history_drops_unknown_types():
    msgs = [
        {"type": "status", "message": "navigating"},
        {"type": "weird", "message": "ignore me"},
        {"type": "complete", "message": "done"},
    ]
    out = summarize_history(msgs)
    assert "navigating" in out
    assert "done" in out
    assert "ignore me" not in out


def test_summarize_history_keeps_last_n():
    msgs = [{"type": "status", "message": f"step {i}"} for i in range(50)]
    out = summarize_history(msgs, max_lines=5)
    lines = out.split("\n")
    assert len(lines) == 5
    assert "step 49" in out
    assert "step 0" not in out


def test_summarize_history_empty_input():
    assert summarize_history([]) == ""


def test_summarize_history_max_lines_zero():
    msgs = [{"type": "status", "message": "x"}]
    assert summarize_history(msgs, max_lines=0) == ""


def test_summarize_history_drops_empty_messages():
    msgs = [
        {"type": "status", "message": ""},
        {"type": "status", "message": "  "},
        {"type": "status", "message": "real"},
    ]
    out = summarize_history(msgs)
    assert out == "[status] real"


# ─── BrowserAgentExecutor — patches execute_task ────────────────────────


@pytest.fixture
def mock_execute_task(monkeypatch):
    """Patch app.bridge.execute_task. Returns the call log + lets test customize behavior."""
    calls: list[dict] = []

    async def stub(goal, send, receive_confirmation, user_id=None):
        calls.append({"goal": goal, "send": send, "rcv": receive_confirmation, "user_id": user_id})
        await send({"type": "status", "message": "Working..."})
        await send({"type": "complete", "message": "Done. Booked."})

    monkeypatch.setattr("app.bridge.execute_task", stub)
    return calls


@pytest.mark.asyncio
async def test_execute_calls_execute_task_with_composed_goal(mock_execute_task):
    d = _decision(intent_text="Order paper towels", parameters={"brand": "Bounty"})
    bx = BrowserAgentExecutor(user_id="u1")
    event = await bx.execute(d)
    assert event.stage == "completed"
    assert len(mock_execute_task) == 1
    call = mock_execute_task[0]
    assert "Order paper towels" in call["goal"]
    assert "Bounty" in call["goal"]
    assert call["user_id"] == "u1"


@pytest.mark.asyncio
async def test_execute_forwards_messages_to_callback(mock_execute_task):
    received: list[dict] = []

    async def cb(m):
        received.append(m)

    bx = BrowserAgentExecutor(user_id="u1", on_wearer_message=cb)
    await bx.execute(_decision())
    types = [m["type"] for m in received]
    assert "status" in types
    assert "complete" in types


@pytest.mark.asyncio
async def test_execute_callback_failure_does_not_abort(monkeypatch):
    async def stub(goal, send, receive_confirmation, user_id=None):
        await send({"type": "status", "message": "x"})
        await send({"type": "complete", "message": "Done."})
    monkeypatch.setattr("app.bridge.execute_task", stub)

    async def angry_cb(m):
        raise RuntimeError("ui crashed")

    bx = BrowserAgentExecutor(user_id="u1", on_wearer_message=angry_cb)
    event = await bx.execute(_decision())
    # The agent still finished cleanly even though callbacks raised
    assert event.stage == "completed"


@pytest.mark.asyncio
async def test_execute_returns_error_event_when_agent_errors(monkeypatch):
    async def stub(goal, send, receive_confirmation, user_id=None):
        await send({"type": "status", "message": "starting..."})
        await send({"type": "error", "message": "I had trouble loading the page."})
    monkeypatch.setattr("app.bridge.execute_task", stub)

    bx = BrowserAgentExecutor(user_id="u1")
    event = await bx.execute(_decision())
    assert event.stage == "error"
    assert "trouble loading" in event.message


@pytest.mark.asyncio
async def test_execute_returns_error_when_execute_task_raises(monkeypatch):
    async def stub(goal, send, receive_confirmation, user_id=None):
        raise RuntimeError("browser exploded")
    monkeypatch.setattr("app.bridge.execute_task", stub)

    bx = BrowserAgentExecutor(user_id="u1")
    event = await bx.execute(_decision())
    assert event.stage == "error"


@pytest.mark.asyncio
async def test_execute_refuses_non_execute_decision(mock_execute_task):
    d = _decision(kind=DecisionKind.LOG)
    bx = BrowserAgentExecutor(user_id="u1")
    event = await bx.execute(d)
    assert event.stage == "error"
    # execute_task should not have been called
    assert mock_execute_task == []


@pytest.mark.asyncio
async def test_execute_refuses_ask_decision(mock_execute_task):
    """ASK decisions should be confirmed upstream and converted to EXECUTE before reaching the bridge."""
    d = _decision(kind=DecisionKind.ASK)
    bx = BrowserAgentExecutor(user_id="u1")
    event = await bx.execute(d)
    assert event.stage == "error"
    assert mock_execute_task == []


@pytest.mark.asyncio
async def test_execute_refuses_empty_goal(monkeypatch):
    """Defensive: a Decision with empty intent.text and no action_verb shouldn't run anything."""
    async def stub(goal, send, receive_confirmation, user_id=None):
        await send({"type": "complete", "message": "Done."})
    monkeypatch.setattr("app.bridge.execute_task", stub)

    intent = Intent.new(user_id="u", text="", action_verb="")
    d = Decision.new(
        intent=intent,
        kind=DecisionKind.EXECUTE,
        confidence=Confidence(score=0.9),
        reversibility=Reversibility.REVERSIBLE,
        urgency=Urgency(level=2),
    )
    bx = BrowserAgentExecutor(user_id="u1")
    event = await bx.execute(d)
    assert event.stage == "error"


# ─── Verifier wiring ─────────────────────────────────────────────────────


class _PassingVerifier:
    """Stub verifier that always says passed."""
    captured_history: str = ""

    async def verify(self, goal, final_state=None, history_summary=""):
        self.captured_history = history_summary
        return Verdict(passed=True, evidence="x", confidence=0.9)


class _FailingVerifier:
    async def verify(self, goal, final_state=None, history_summary=""):
        return Verdict(
            passed=False,
            confidence=0.9,
            honest_message_for_wearer="I couldn't see a confirmation. Want me to retry?",
            missing=["confirmation number"],
        )


class _RaisingVerifier:
    async def verify(self, goal, final_state=None, history_summary=""):
        raise RuntimeError("verifier broken")


@pytest.mark.asyncio
async def test_verifier_pass_returns_completed(mock_execute_task):
    bx = BrowserAgentExecutor(user_id="u1", verifier=_PassingVerifier())
    event = await bx.execute(_decision())
    assert event.stage == "completed"


@pytest.mark.asyncio
async def test_verifier_pass_receives_history_summary(mock_execute_task):
    v = _PassingVerifier()
    bx = BrowserAgentExecutor(user_id="u1", verifier=v)
    await bx.execute(_decision())
    assert "[status]" in v.captured_history
    assert "[complete]" in v.captured_history


@pytest.mark.asyncio
async def test_verifier_fail_overrides_agent_self_report(mock_execute_task):
    """Cop-out #8: agent's `done` doesn't count if verifier disagrees."""
    bx = BrowserAgentExecutor(user_id="u1", verifier=_FailingVerifier())
    event = await bx.execute(_decision())
    assert event.stage == "error"
    assert "couldn't see a confirmation" in event.message


@pytest.mark.asyncio
async def test_verifier_raise_fails_closed(mock_execute_task):
    """Cop-out #6: if we can't verify, we don't claim success."""
    bx = BrowserAgentExecutor(user_id="u1", verifier=_RaisingVerifier())
    event = await bx.execute(_decision())
    assert event.stage == "error"
    assert "couldn't confirm" in event.message.lower() or "retry" in event.message.lower()


# ─── No verifier (back-compat / testing path) ───────────────────────────


@pytest.mark.asyncio
async def test_no_verifier_uses_agent_self_report(mock_execute_task):
    bx = BrowserAgentExecutor(user_id="u1", verifier=None)
    event = await bx.execute(_decision())
    assert event.stage == "completed"
    assert event.message == "Done. Booked."


@pytest.mark.asyncio
async def test_no_verifier_falls_back_to_decision_completion_when_agent_silent(monkeypatch):
    """If agent never sent a complete/error, use the cascade's pre-composed completion."""
    async def silent_stub(goal, send, receive_confirmation, user_id=None):
        await send({"type": "status", "message": "x"})
        # No complete or error
    monkeypatch.setattr("app.bridge.execute_task", silent_stub)

    bx = BrowserAgentExecutor(user_id="u1", verifier=None)
    d = _decision(completion_message="Done. Booked Friday at 7.")
    event = await bx.execute(d)
    assert event.stage == "completed"
    assert "Friday" in event.message


# ─── receive_confirmation passthrough ────────────────────────────────────


@pytest.mark.asyncio
async def test_receive_confirmation_default_is_confirmed(monkeypatch):
    captured: list[str] = []

    async def stub(goal, send, receive_confirmation, user_id=None):
        captured.append(await receive_confirmation())
        await send({"type": "complete", "message": "ok"})

    monkeypatch.setattr("app.bridge.execute_task", stub)
    bx = BrowserAgentExecutor(user_id="u1")
    await bx.execute(_decision())
    assert captured == ["confirmed"]


@pytest.mark.asyncio
async def test_receive_confirmation_custom_callback(monkeypatch):
    captured: list[str] = []

    async def stub(goal, send, receive_confirmation, user_id=None):
        captured.append(await receive_confirmation())
        await send({"type": "complete", "message": "ok"})

    monkeypatch.setattr("app.bridge.execute_task", stub)

    async def my_recv():
        return "yes please"

    bx = BrowserAgentExecutor(user_id="u1", receive_confirmation=my_recv)
    await bx.execute(_decision())
    assert captured == ["yes please"]


@pytest.mark.asyncio
async def test_receive_confirmation_fallback_when_callback_raises(monkeypatch):
    captured: list[str] = []

    async def stub(goal, send, receive_confirmation, user_id=None):
        captured.append(await receive_confirmation())
        await send({"type": "complete", "message": "ok"})

    monkeypatch.setattr("app.bridge.execute_task", stub)

    async def my_recv():
        raise RuntimeError("oops")

    bx = BrowserAgentExecutor(user_id="u1", receive_confirmation=my_recv)
    await bx.execute(_decision())
    assert captured == ["confirmed"]


# ─── Cancellation propagates ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancellation_propagates(monkeypatch):
    """Cancellation of the bridge should propagate through execute_task."""
    cancelled = []

    async def slow_stub(goal, send, receive_confirmation, user_id=None):
        try:
            await asyncio.sleep(10.0)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    monkeypatch.setattr("app.bridge.execute_task", slow_stub)
    bx = BrowserAgentExecutor(user_id="u1")
    task = asyncio.create_task(bx.execute(_decision()))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled == [True]
