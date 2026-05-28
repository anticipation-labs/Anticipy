"""
Unit tests for app.router — AI-only classification.

After the keyword/regex pre-classifier was removed, all routing decisions
are LLM calls. These tests verify the deterministic surfaces:

  - empty/whitespace input → ambiguous, no LLM call
  - parsed valid response → propagates the category
  - unknown category in response → ambiguous (defensive)
  - DegradedResponse → ambiguous + degraded=True
  - non-dict response → ambiguous

The live AI behavior is covered by the integration tests / browser eval.
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.models import CostTracker, DegradedResponse  # noqa: E402
from app.router import classify  # noqa: E402


def _patch_llm(response):
    import app.router as r
    orig = r.llm_call_json

    async def stub(*_a, **_kw):
        return response

    r.llm_call_json = stub  # type: ignore[assignment]
    return orig


def _restore_llm(orig):
    import app.router as r
    r.llm_call_json = orig


def test_classify_empty_short_circuits_to_ambiguous():
    state = {"called": False}
    import app.router as r
    orig = r.llm_call_json

    async def stub(*_a, **_kw):
        state["called"] = True
        return {"category": "action"}

    r.llm_call_json = stub  # type: ignore[assignment]
    try:
        async def go():
            c = await classify("", CostTracker())
            assert c.category == "ambiguous"
            assert c.degraded is False
            assert state["called"] is False
            c2 = await classify("    ", CostTracker())
            assert c2.category == "ambiguous"
            assert state["called"] is False
        asyncio.run(go())
    finally:
        r.llm_call_json = orig


def test_classify_returns_chat():
    orig = _patch_llm({"category": "chat"})
    try:
        async def go():
            c = await classify("hey there", CostTracker())
            assert c.category == "chat"
            assert c.degraded is False
        asyncio.run(go())
    finally:
        _restore_llm(orig)


def test_classify_returns_action():
    orig = _patch_llm({"category": "action"})
    try:
        async def go():
            c = await classify("book me a flight", CostTracker())
            assert c.category == "action"
        asyncio.run(go())
    finally:
        _restore_llm(orig)


def test_classify_returns_question():
    orig = _patch_llm({"category": "question"})
    try:
        async def go():
            c = await classify("what is the speed of light", CostTracker())
            assert c.category == "question"
        asyncio.run(go())
    finally:
        _restore_llm(orig)


def test_classify_returns_ambiguous_on_unknown_category():
    """Defensive: if the model invents a category, fall back to ambiguous."""
    orig = _patch_llm({"category": "totally_made_up"})
    try:
        async def go():
            c = await classify("???", CostTracker())
            assert c.category == "ambiguous"
        asyncio.run(go())
    finally:
        _restore_llm(orig)


def test_classify_returns_ambiguous_on_degraded():
    orig = _patch_llm(DegradedResponse())
    try:
        async def go():
            c = await classify("hi", CostTracker())
            assert c.category == "ambiguous"
            assert c.degraded is True
        asyncio.run(go())
    finally:
        _restore_llm(orig)


def test_classify_returns_ambiguous_on_non_dict():
    orig = _patch_llm("not a dict")  # type: ignore[arg-type]
    try:
        async def go():
            c = await classify("hi", CostTracker())
            assert c.category == "ambiguous"
        asyncio.run(go())
    finally:
        _restore_llm(orig)


def test_classify_returns_ambiguous_on_missing_category_field():
    orig = _patch_llm({"reasoning": "no category key"})
    try:
        async def go():
            c = await classify("???", CostTracker())
            assert c.category == "ambiguous"
        asyncio.run(go())
    finally:
        _restore_llm(orig)


def test_no_keyword_or_regex_used():
    """Guard the no-hardcoding rule: router.py should not import re or define
    pattern lists. If someone re-adds a keyword pre-classifier this test fires."""
    src = open(os.path.join(os.path.dirname(__file__), "app/router.py")).read()
    assert "import re" not in src, "router.py must not use regex for intent classification"
    assert "CHAT_PATTERNS" not in src
    assert "ACTION_KEYWORDS" not in src
    assert "QUESTION_PATTERNS" not in src


# --- runner --------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        (name, obj) for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    print(f"running {len(tests)} tests...")
    failed: list[tuple[str, str]] = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed.append((name, f"AssertionError: {e}"))
            print(f"  FAIL  {name}")
        except Exception as e:
            failed.append((name, f"{type(e).__name__}: {e}"))
            print(f"  ERR   {name}  ({type(e).__name__}: {e})")

    print()
    print(f"{len(tests) - len(failed)}/{len(tests)} passed")
    if failed:
        for name, err in failed:
            print(f"  {name}: {err}")
        sys.exit(1)
