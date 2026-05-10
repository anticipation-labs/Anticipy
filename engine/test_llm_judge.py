"""Unit tests for app.llm_judge.

The judge replaces the hardcoded failure-phrase list. These tests verify
the judge:
  - fails closed when the LLM cascade is degraded
  - fails closed when no providers are configured
  - passes / fails based on the LLM verdict shape
  - sync wrapper works from a non-async context
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from app import llm_judge
from app.models import DegradedResponse


# ── helpers ────────────────────────────────────────────────────────────


def _patch_chain(present: bool):
    """Return context manager that swaps MODEL_CHAIN to [] or [{...}]."""
    new_chain = (
        [{"name": "gemini", "base_url": "x", "api_key": "x", "model": "x",
          "cost_input": 0.0, "cost_output": 0.0, "min_interval_seconds": 0.0}]
        if present else []
    )
    return patch.object(llm_judge, "MODEL_CHAIN", new_chain)


# ── tests ──────────────────────────────────────────────────────────────


def test_no_providers_fails_closed():
    """Judge must NEVER pass anything when there's no LLM available."""
    with _patch_chain(False):
        verdict = llm_judge.judge_task_response(
            task="What's the capital of France?",
            response="Paris",
        )
    assert verdict["passed"] is False
    reason = verdict["reason"].lower()
    assert "no llm" in reason or "no provider" in reason


def test_degraded_cascade_fails_closed():
    """When every provider returned DegradedResponse, the judge fails."""
    async def fake_llm_call_json(*args, **kwargs):
        return DegradedResponse()

    with _patch_chain(True), \
         patch.object(llm_judge, "llm_call_json", fake_llm_call_json):
        verdict = llm_judge.judge_task_response(
            task="What's the capital of France?",
            response="Paris",
        )
    assert verdict["passed"] is False
    assert "unavailable" in verdict["reason"].lower()


def test_judge_passes_when_llm_returns_passed_true():
    async def fake_llm_call_json(*args, **kwargs):
        return {"passed": True, "reason": "Paris is the correct capital."}

    with _patch_chain(True), \
         patch.object(llm_judge, "llm_call_json", fake_llm_call_json):
        verdict = llm_judge.judge_task_response(
            task="What's the capital of France?",
            response="Paris",
            expected_facts=["Paris"],
        )
    assert verdict["passed"] is True
    assert "paris" in verdict["reason"].lower()


def test_judge_fails_when_llm_returns_passed_false():
    async def fake_llm_call_json(*args, **kwargs):
        return {"passed": False, "reason": "Rate-limit message — not a real answer."}

    with _patch_chain(True), \
         patch.object(llm_judge, "llm_call_json", fake_llm_call_json):
        verdict = llm_judge.judge_task_response(
            task="What's the capital of France?",
            response="Hit my AI rate limit. Give me a minute and try again.",
        )
    assert verdict["passed"] is False
    assert "rate-limit" in verdict["reason"].lower() or "not a real" in verdict["reason"].lower()


def test_judge_handles_non_dict_verdict():
    """If the cascade returns something weird (not a dict, not a DegradedResponse),
    the judge must NOT pass."""
    async def fake_llm_call_json(*args, **kwargs):
        return "the answer is yes"  # garbage

    with _patch_chain(True), \
         patch.object(llm_judge, "llm_call_json", fake_llm_call_json):
        verdict = llm_judge.judge_task_response(
            task="What's the capital of France?",
            response="Paris",
        )
    assert verdict["passed"] is False
    assert "non-dict" in verdict["reason"].lower()


def test_judge_handles_cascade_exception():
    async def fake_llm_call_json(*args, **kwargs):
        raise RuntimeError("simulated transport blow-up")

    with _patch_chain(True), \
         patch.object(llm_judge, "llm_call_json", fake_llm_call_json):
        verdict = llm_judge.judge_task_response(
            task="What's 2+2?",
            response="4",
        )
    assert verdict["passed"] is False
    assert "raised" in verdict["reason"].lower()


def test_async_form_works_under_running_loop():
    """The async form is what production callers should use."""
    async def fake_llm_call_json(*args, **kwargs):
        return {"passed": True, "reason": "ok"}

    async def driver():
        with _patch_chain(True), \
             patch.object(llm_judge, "llm_call_json", fake_llm_call_json):
            return await llm_judge.judge_task_response_async(
                task="t", response="r",
            )

    verdict = asyncio.run(driver())
    assert verdict["passed"] is True


def test_judge_truncates_overlong_response():
    """A 50KB agent response must not blow up the judge prompt — the
    user message is bounded at 4000 chars."""
    captured = {}
    async def fake_llm_call_json(messages, *args, **kwargs):
        captured["user"] = messages[-1]["content"]
        return {"passed": True, "reason": "ok"}

    huge = "x" * 100000
    with _patch_chain(True), \
         patch.object(llm_judge, "llm_call_json", fake_llm_call_json):
        llm_judge.judge_task_response(task="t", response=huge)
    # The bounded slice keeps the prompt manageable.
    assert len(captured["user"]) < 6000


def test_judge_passes_expected_facts_into_prompt():
    captured = {}
    async def fake_llm_call_json(messages, *args, **kwargs):
        captured["user"] = messages[-1]["content"]
        return {"passed": True, "reason": "ok"}

    with _patch_chain(True), \
         patch.object(llm_judge, "llm_call_json", fake_llm_call_json):
        llm_judge.judge_task_response(
            task="When was Python released?",
            response="In 1991.",
            expected_facts=["1991", "1989"],
        )
    assert "1991" in captured["user"]
    assert "1989" in captured["user"]
    # The facts are framed as guidance, not as a string-match rule.
    assert "guidance" in captured["user"].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
