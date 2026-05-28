"""Unit tests for app.verifier — end-state verification for browser actions."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.verifier import EndStateVerifier, FinalPageState, Verdict


def _make_llm(response: Any):
    """Returns an LlmCall stub returning a fixed response."""
    async def call(system: str, user: str) -> str:
        if isinstance(response, Exception):
            raise response
        if isinstance(response, dict):
            return json.dumps(response)
        return response
    return call


@pytest.mark.asyncio
async def test_verify_passed_on_clear_evidence():
    llm = _make_llm({
        "passed": True,
        "evidence": "Your reservation is confirmed for 7:00 PM",
        "missing": [],
        "confidence": 0.95,
        "honest_message_for_wearer": "",
        "reasoning": "page text contains explicit confirmation",
    })
    v = EndStateVerifier(llm)
    verdict = await v.verify(
        goal="Book a reservation at 7pm",
        final_state=FinalPageState(
            url="https://example.com/confirm",
            title="Confirmation",
            visible_text="Your reservation is confirmed for 7:00 PM. Confirmation #ABC123.",
            history_summary="navigated to site → filled form → clicked confirm → done",
        ),
    )
    assert verdict.passed
    assert verdict.confidence == 0.95
    assert "confirmed" in verdict.evidence


@pytest.mark.asyncio
async def test_verify_failed_with_honest_message():
    llm = _make_llm({
        "passed": False,
        "evidence": "",
        "missing": ["confirmation number", "reservation details"],
        "confidence": 0.85,
        "honest_message_for_wearer": "I started the booking but couldn't see a confirmation. Want me to retry?",
        "reasoning": "agent returned to search results page",
    })
    v = EndStateVerifier(llm)
    verdict = await v.verify(
        goal="Book a reservation",
        final_state=FinalPageState(url="https://example.com/search", visible_text="search results"),
    )
    assert not verdict.passed
    assert "couldn't see a confirmation" in verdict.honest_message_for_wearer
    assert "confirmation number" in verdict.missing
    assert "reservation details" in verdict.missing


@pytest.mark.asyncio
async def test_verify_failed_when_llm_raises():
    llm = _make_llm(RuntimeError("provider down"))
    v = EndStateVerifier(llm)
    verdict = await v.verify(
        goal="Book something",
        final_state=FinalPageState(url="x", visible_text="y"),
    )
    assert not verdict.passed
    assert verdict.honest_message_for_wearer
    # Honest message should mention retry or confirm
    lower = verdict.honest_message_for_wearer.lower()
    assert "retry" in lower or "confirm" in lower


@pytest.mark.asyncio
async def test_verify_failed_on_empty_response():
    llm = _make_llm("")
    v = EndStateVerifier(llm)
    verdict = await v.verify(
        goal="X",
        final_state=FinalPageState(url="x", visible_text="y"),
    )
    assert not verdict.passed
    assert verdict.honest_message_for_wearer


@pytest.mark.asyncio
async def test_verify_failed_on_malformed_json():
    llm = _make_llm("this is not json {malformed")
    v = EndStateVerifier(llm)
    verdict = await v.verify(
        goal="X",
        final_state=FinalPageState(url="x", visible_text="y"),
    )
    assert not verdict.passed


@pytest.mark.asyncio
async def test_verify_failed_on_non_dict_json():
    llm = _make_llm("[1, 2, 3]")
    v = EndStateVerifier(llm)
    verdict = await v.verify(
        goal="X",
        final_state=FinalPageState(url="x", visible_text="y"),
    )
    assert not verdict.passed


@pytest.mark.asyncio
async def test_verify_no_signal_at_all_returns_fail_closed():
    """Cop-out #6: if we can't see anything, we don't claim success."""
    # Even if the LLM says passed, no signal means we never call it.
    llm = _make_llm({"passed": True, "confidence": 1.0, "evidence": "fake"})
    v = EndStateVerifier(llm)
    verdict = await v.verify(goal="X")  # no final_state, no history_summary
    assert not verdict.passed
    assert "couldn't tell" in verdict.honest_message_for_wearer.lower() or \
        "couldn't" in verdict.honest_message_for_wearer.lower()


@pytest.mark.asyncio
async def test_verify_history_only_is_a_signal():
    """If we have history_summary even without final_state, we still ask the verifier."""
    llm = _make_llm({"passed": True, "confidence": 0.6, "evidence": "saw confirmation in history"})
    v = EndStateVerifier(llm)
    verdict = await v.verify(
        goal="X",
        history_summary="navigated → done with confirmation #123",
    )
    assert verdict.passed


@pytest.mark.asyncio
async def test_verify_clamps_confidence_above_one():
    llm = _make_llm({"passed": True, "confidence": 5.0, "evidence": "ok"})
    v = EndStateVerifier(llm)
    verdict = await v.verify(
        goal="X",
        final_state=FinalPageState(url="x", visible_text="ok"),
    )
    assert verdict.confidence == 1.0


@pytest.mark.asyncio
async def test_verify_clamps_confidence_below_zero():
    llm = _make_llm({"passed": True, "confidence": -0.5, "evidence": "ok"})
    v = EndStateVerifier(llm)
    verdict = await v.verify(
        goal="X",
        final_state=FinalPageState(url="x", visible_text="ok"),
    )
    assert verdict.confidence == 0.0


@pytest.mark.asyncio
async def test_verify_handles_non_numeric_confidence():
    llm = _make_llm({"passed": True, "confidence": "not a number", "evidence": "ok"})
    v = EndStateVerifier(llm)
    verdict = await v.verify(
        goal="X",
        final_state=FinalPageState(url="x", visible_text="ok"),
    )
    assert verdict.confidence == 0.0


@pytest.mark.asyncio
async def test_verify_handles_missing_array_gracefully():
    llm = _make_llm({"passed": False, "missing": "not a list", "honest_message_for_wearer": "x"})
    v = EndStateVerifier(llm)
    verdict = await v.verify(goal="X", final_state=FinalPageState(url="x", visible_text="y"))
    assert verdict.missing == []  # fallback to empty list when malformed


@pytest.mark.asyncio
async def test_verify_falls_back_to_default_message_when_honest_empty_on_fail():
    """If the verifier said failed but didn't supply an honest message, we add one."""
    llm = _make_llm({"passed": False, "honest_message_for_wearer": ""})
    v = EndStateVerifier(llm)
    verdict = await v.verify(goal="X", final_state=FinalPageState(url="x", visible_text="y"))
    assert not verdict.passed
    assert verdict.honest_message_for_wearer  # non-empty fallback


@pytest.mark.asyncio
async def test_verify_truncates_long_visible_text():
    """Sanity: 100KB of page text doesn't blow the prompt up unbounded."""
    captured = {}
    async def call(system, user):
        captured["user_len"] = len(user)
        return json.dumps({"passed": True, "confidence": 0.9, "evidence": "ok"})

    v = EndStateVerifier(call)
    huge_text = "x" * 100_000
    await v.verify(
        goal="X",
        final_state=FinalPageState(url="x", visible_text=huge_text),
    )
    # Visible text is capped at 4000 chars in the prompt
    assert captured["user_len"] < 10_000


@pytest.mark.asyncio
async def test_verify_uses_history_summary_from_final_state_first():
    """When both are provided, FinalPageState.history_summary wins."""
    captured = {}
    async def call(system, user):
        captured["user"] = user
        return json.dumps({"passed": True, "confidence": 0.9, "evidence": "ok"})

    v = EndStateVerifier(call)
    await v.verify(
        goal="X",
        final_state=FinalPageState(
            url="x", visible_text="y",
            history_summary="from-final-state",
        ),
        history_summary="from-arg",
    )
    assert "from-final-state" in captured["user"]
    assert "from-arg" not in captured["user"]
