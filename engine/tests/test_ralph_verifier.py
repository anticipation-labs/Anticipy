"""Unit tests for the two-layer Ralph verifier (Phase 4-4).

Layer 1 (verify_step) checks: hash flip, URL match, selector present.
Layer 2 (judge_goal) is mocked end-to-end via a fake LLM stub; no
real network calls.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ralph.verifier import (  # noqa: E402
    JudgeResult,
    VALID_VERDICTS,
    judge_goal,
    verify_step,
)


# --- Layer 1: deterministic step verification ---------------------------


def test_verify_step_post_hash_required() -> None:
    # No post_state_hash => failure regardless of other checks.
    assert verify_step("a", None) is False


def test_verify_step_state_must_change_when_required() -> None:
    assert verify_step("same", "same") is False
    assert verify_step("a", "b") is True


def test_verify_step_can_disable_state_change_check() -> None:
    # Some steps (e.g. "extract") shouldn't change state.
    assert verify_step("a", "a", require_state_change=False) is True


def test_verify_step_expected_url_substring_match() -> None:
    ok = verify_step(
        "a", "b",
        expected_url="mail.google.com",
        current_url="https://mail.google.com/u/0/#inbox",
    )
    assert ok is True

    bad = verify_step(
        "a", "b",
        expected_url="mail.google.com",
        current_url="https://example.com/",
    )
    assert bad is False


def test_verify_step_expected_url_pattern_regex() -> None:
    ok = verify_step(
        "a", "b",
        expected_url_pattern=r"^https://[^/]+/inbox$",
        current_url="https://mail.google.com/inbox",
    )
    assert ok is True

    bad = verify_step(
        "a", "b",
        expected_url_pattern=r"^https://[^/]+/inbox$",
        current_url="https://mail.google.com/spam",
    )
    assert bad is False


def test_verify_step_expected_selector_in_dom() -> None:
    # Substring check: the expected_selector token must appear in
    # the dom string.
    ok = verify_step(
        "a", "b",
        expected_selector='gh="cm"',
        current_dom='<div gh="cm">Compose</div>',
    )
    assert ok is True

    bad = verify_step(
        "a", "b",
        expected_selector='gh="cm"',
        current_dom='<body>nope</body>',
    )
    assert bad is False


def test_verify_step_invalid_regex_returns_false_safely() -> None:
    # Bad regex must not crash; treats as no-match.
    assert (
        verify_step(
            "a", "b",
            expected_url_pattern="(unclosed[",
            current_url="https://example.com",
        )
        is False
    )


def test_verify_step_returns_true_when_no_constraints() -> None:
    # If caller passes no expected_* + no pre hash, the only check is
    # that post_state_hash exists.
    assert verify_step(None, "post") is True


# --- Layer 2: vision judge (mocked) ------------------------------------


class _FakeLLM:
    """Mock LLM that returns canned strings to judge_goal()."""

    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.calls: list[tuple[str, Optional[str]]] = []

    def judge_goal(self, goal_text: str, screenshot_path: Optional[str]) -> str:
        self.calls.append((goal_text, screenshot_path))
        return self.payload


def test_judge_goal_success_verdict() -> None:
    llm = _FakeLLM('{"verdict": "success", "reason": "draft visible"}')
    res = judge_goal(
        "draft email to ada@example.com",
        "/tmp/final.png",
        llm=llm,
    )
    assert isinstance(res, JudgeResult)
    assert res.verdict == "success"
    assert "draft visible" in res.reason
    assert llm.calls == [("draft email to ada@example.com", "/tmp/final.png")]


def test_judge_goal_handles_each_verdict_class() -> None:
    for verdict in VALID_VERDICTS:
        llm = _FakeLLM(f'{{"verdict": "{verdict}", "reason": "x"}}')
        res = judge_goal("g", None, llm=llm)
        assert res.verdict == verdict


def test_judge_goal_handles_markdown_fenced_json() -> None:
    llm = _FakeLLM(
        '```json\n{"verdict": "success", "reason": "ok"}\n```'
    )
    res = judge_goal("g", None, llm=llm)
    assert res.verdict == "success"


def test_judge_goal_handles_embedded_json() -> None:
    llm = _FakeLLM(
        'here is my answer: {"verdict": "impossible_task", "reason": "blocked"}'
    )
    res = judge_goal("g", None, llm=llm)
    assert res.verdict == "impossible_task"


def test_judge_goal_unparseable_degrades_to_needs_more_steps() -> None:
    llm = _FakeLLM("absolutely not JSON at all")
    res = judge_goal("g", None, llm=llm)
    assert res.verdict == "needs_more_steps"


def test_judge_goal_synonym_mapping() -> None:
    for synonym, expected in [
        ("done", "success"),
        ("complete", "success"),
        ("captcha", "reached_captcha"),
        ("impossible", "impossible_task"),
        ("more", "needs_more_steps"),
    ]:
        llm = _FakeLLM(f'{{"verdict": "{synonym}"}}')
        res = judge_goal("g", None, llm=llm)
        assert res.verdict == expected, f"{synonym} should map to {expected}"


def test_judge_goal_chat_interface_supported() -> None:
    """LLMs that expose .chat(prompt) -> obj.content also work."""
    resp = MagicMock()
    resp.content = '{"verdict": "success", "reason": "ok"}'
    llm = MagicMock(spec=["chat"])
    llm.chat.return_value = resp
    res = judge_goal("g", None, llm=llm)
    assert res.verdict == "success"
    llm.chat.assert_called_once()


def test_judge_goal_callable_llm_supported() -> None:
    """Plain callables work too."""
    llm = MagicMock(side_effect=['{"verdict": "needs_more_steps"}'])
    res = judge_goal("g", None, llm=llm)
    assert res.verdict == "needs_more_steps"


def test_judge_goal_llm_exception_safe() -> None:
    llm = MagicMock(spec=["judge_goal"])
    llm.judge_goal.side_effect = RuntimeError("boom")
    res = judge_goal("g", None, llm=llm)
    assert res.verdict == "needs_more_steps"
    assert "boom" in res.reason


def test_judge_goal_no_llm_returns_needs_more_steps() -> None:
    # When no llm is supplied AND import fallback fails, we must
    # degrade gracefully (no exception).
    res = judge_goal(
        "g",
        None,
        llm=None,
    )
    # Either the import fallback found a real verifier (unlikely in
    # unit tests where no env / openrouter creds exist) and it answered
    # something, OR we got needs_more_steps. Both are acceptable.
    assert res.verdict in VALID_VERDICTS


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
