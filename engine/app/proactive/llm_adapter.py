"""
Adapter wiring the proactive cascade to engine/app/models.py.

The cascade expects a callable `(system_prompt, user_prompt) -> awaitable[str]`
that returns a CLEAN JSON string. Provider-native JSON mode guarantees the
return value is parseable by `json.loads` with no regex recovery, no fence
stripping, no fallback strategies.

If every provider in MODEL_CHAIN fails, the adapter returns "" — every
cascade layer's `_parse` then yields its safe-default (irreversible /
allow / level-2 / not-actionable / etc.) so the system stays in a
known-good state under model failures.

Two flavors:

  make_json_llm_call() → for L1 salience, L2 extract, L3 reversibility,
  L4 urgency, L5 donna, plus the eval judge and scenario generator. JSON
  mode forced.

  make_text_llm_call() → for the notes-recorder compaction step, where the
  model returns short text rather than JSON.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from app.models import CostTracker, DegradedResponse, llm_call_json_str, llm_call_text


LlmCall = Callable[[str, str], Awaitable[str]]


def make_json_llm_call(max_tokens: int = 1024) -> LlmCall:
    """Returns an LlmCall that forces provider-native JSON mode.

    The returned string is guaranteed to be valid JSON (or empty on full
    cascade failure). Cascade `_parse` functions can call `json.loads`
    without any pre-processing.
    """

    async def call(system: str, user: str) -> str:
        tracker = CostTracker()
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        return await llm_call_json_str(messages, tracker, max_tokens=max_tokens)

    return call


def make_text_llm_call(max_tokens: int = 512) -> LlmCall:
    """Returns an LlmCall for non-JSON outputs (notes compaction)."""

    async def call(system: str, user: str) -> str:
        tracker = CostTracker()
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        result = await llm_call_text(messages, tracker, max_tokens=max_tokens)
        if isinstance(result, DegradedResponse):
            return ""
        return result or ""

    return call
