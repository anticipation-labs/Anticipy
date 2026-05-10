"""Unit tests for app.proactive.donna_voice — narrative re-phrasing."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.proactive.donna_voice import (
    compose_ask_narrative,
    compose_completion_narrative,
    compose_refusal_narrative,
)
from app.proactive.types import (
    Confidence,
    Decision,
    DecisionKind,
    Intent,
    Reversibility,
    Urgency,
)


def _decision(
    *,
    kind: DecisionKind = DecisionKind.ASK,
    user_facing_question: str | None = "Confirm: book the diner Friday 7pm?",
    completion_message: str | None = "Done. Booked.",
    refusal_reason: str | None = "Not doing that.",
    intent_text: str = "Book the diner Friday 7pm",
):
    intent = Intent.new(user_id="u", text=intent_text, action_verb="v")
    return Decision.new(
        intent=intent,
        kind=kind,
        confidence=Confidence(score=0.9),
        reversibility=Reversibility.REVERSIBLE,
        urgency=Urgency(level=2),
        user_facing_question=user_facing_question,
        completion_message=completion_message,
        refusal_reason=refusal_reason,
    )


def _llm(response: Any):
    async def call(s, u):
        if isinstance(response, Exception):
            raise response
        if isinstance(response, dict):
            return json.dumps(response)
        return response
    return call


# ─── ASK ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ask_falls_back_when_no_llm():
    d = _decision(user_facing_question="Book the diner Friday?")
    out = await compose_ask_narrative(d, llm_call=None)
    assert out == "Book the diner Friday?"


@pytest.mark.asyncio
async def test_ask_uses_llm_when_provided():
    d = _decision(user_facing_question="Confirm: book the diner Friday 7pm?")
    llm = _llm({"rephrased": "Hey — diner Friday at 7? I'll grab it if you nod."})
    out = await compose_ask_narrative(d, llm_call=llm)
    assert "diner" in out.lower()
    assert out != "Confirm: book the diner Friday 7pm?"


@pytest.mark.asyncio
async def test_ask_falls_back_on_llm_error():
    d = _decision(user_facing_question="Original question?")
    llm = _llm(RuntimeError("provider down"))
    out = await compose_ask_narrative(d, llm_call=llm)
    assert out == "Original question?"


@pytest.mark.asyncio
async def test_ask_falls_back_on_malformed_json():
    d = _decision(user_facing_question="Original question?")
    llm = _llm("not json {malformed")
    out = await compose_ask_narrative(d, llm_call=llm)
    assert out == "Original question?"


@pytest.mark.asyncio
async def test_ask_falls_back_on_non_dict_json():
    d = _decision(user_facing_question="Original question?")
    llm = _llm("[1, 2, 3]")
    out = await compose_ask_narrative(d, llm_call=llm)
    assert out == "Original question?"


@pytest.mark.asyncio
async def test_ask_falls_back_on_empty_rephrase():
    d = _decision(user_facing_question="Original question?")
    llm = _llm({"rephrased": ""})
    out = await compose_ask_narrative(d, llm_call=llm)
    assert out == "Original question?"


@pytest.mark.asyncio
async def test_ask_synthesizes_from_intent_when_question_missing():
    d = _decision(user_facing_question=None, intent_text="Order paper towels")
    out = await compose_ask_narrative(d, llm_call=None)
    assert "Order paper towels" in out
    assert out.endswith("?")


# ─── COMPLETION ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_completion_combines_decision_and_actual_result():
    d = _decision(completion_message="Done. Booked the reservation.")
    out = await compose_completion_narrative(
        d, actual_result="Confirmation #ABC123", llm_call=None
    )
    assert "Booked the reservation" in out
    assert "ABC123" in out


@pytest.mark.asyncio
async def test_completion_uses_actual_when_decision_empty():
    intent = Intent.new(user_id="u", text="x", action_verb="v")
    d = Decision.new(
        intent=intent,
        kind=DecisionKind.EXECUTE,
        confidence=Confidence(score=0.9),
        reversibility=Reversibility.REVERSIBLE,
        urgency=Urgency(level=2),
        completion_message=None,
    )
    out = await compose_completion_narrative(
        d, actual_result="Booked the diner Friday 7pm", llm_call=None
    )
    assert "Booked the diner Friday 7pm" in out


@pytest.mark.asyncio
async def test_completion_falls_back_to_done():
    d = _decision(completion_message=None)
    out = await compose_completion_narrative(d, actual_result="", llm_call=None)
    assert out == "Done."


@pytest.mark.asyncio
async def test_completion_doesnt_double_when_actual_equals_done():
    d = _decision(completion_message="Done. Booked.")
    out = await compose_completion_narrative(d, actual_result="Done.", llm_call=None)
    assert out == "Done. Booked."


@pytest.mark.asyncio
async def test_completion_uses_llm_rephrase():
    d = _decision(completion_message="Done. Booked the reservation for Friday at 7.")
    llm = _llm({"rephrased": "Booked. Friday 7. Confirmation in your inbox."})
    out = await compose_completion_narrative(d, llm_call=llm)
    assert "Booked" in out


# ─── REFUSAL ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refusal_falls_back_when_no_llm():
    d = _decision(refusal_reason="That message reads as harsher than you probably want.")
    out = await compose_refusal_narrative(d, llm_call=None)
    assert "harsher" in out


@pytest.mark.asyncio
async def test_refusal_uses_default_when_empty():
    d = _decision(refusal_reason="")
    out = await compose_refusal_narrative(d, llm_call=None)
    assert out
    assert "rather not" in out.lower() or "won't" in out.lower() or "wouldn't" in out.lower()


@pytest.mark.asyncio
async def test_refusal_uses_llm_when_provided():
    d = _decision(refusal_reason="That message reads as too harsh — consider rephrasing.")
    llm = _llm({"rephrased": "That one's harsher than you probably mean. Want a softer version?"})
    out = await compose_refusal_narrative(d, llm_call=llm)
    assert out  # non-empty
    assert out != "That message reads as too harsh — consider rephrasing."


@pytest.mark.asyncio
async def test_refusal_falls_back_on_llm_error():
    d = _decision(refusal_reason="Stay no.")
    llm = _llm(RuntimeError("oops"))
    out = await compose_refusal_narrative(d, llm_call=llm)
    assert out == "Stay no."
