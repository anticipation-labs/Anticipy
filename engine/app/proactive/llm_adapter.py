"""Adapter wiring the proactive cascade to the portable platform seam.

P1 of the whole-system build re wires this module, and ONLY this
module, so the preserved cascade runs through
``app.anticipy.platform_adapter.model_call`` instead of the old
multi provider client. The three cascade modules (demand_detection,
hedge_filter, intent_extraction) keep their prompts and stage logic
byte for byte. This is wiring, not cascade logic, so rewriting it is
explicitly allowed and is what makes the cascade portable.

The contract the cascade depends on is unchanged: a callable
``(system_prompt, user_prompt) -> awaitable[str]`` that returns a clean
JSON string, or "" on full failure. On "" every cascade stage falls to
its documented safe default, so a model failure never produces a wrong
ACT.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from app.anticipy import platform_adapter

LlmCall = Callable[[str, str], Awaitable[str]]


def _has_json_object(text: str) -> bool:
    s = text.find("{")
    e = text.rfind("}")
    return s != -1 and e != -1 and e > s


def make_json_llm_call(max_tokens: int = 1024) -> LlmCall:
    """Returns an LlmCall that returns the model content (a JSON object
    the cascade `_parse` functions extract and json.loads), or "" on
    failure so every stage falls to its documented safe default.

    Port note: strict provider `response_format=json_object` on the
    decider model degenerates into multilingual word salad on the
    cascade's long few shot prompts (observed in the P1 run). The
    cascade prompts already mandate strict JSON and the cascade has
    robust object extraction, which is exactly how this logic was
    originally validated. So json_mode is requested via the prompt, not
    the provider flag, and one stricter reparse is attempted before
    giving up. Wiring only, cascade prompts untouched.
    """

    async def call(system: str, user: str) -> str:
        res = await asyncio.to_thread(
            platform_adapter.model_call, system, user, max_tokens, 0.0, False
        )
        if res.ok and _has_json_object(res.content):
            return res.content
        # one stricter reparse attempt (section 8: one stricter reparse,
        # then the caller safe defaults)
        stricter = (
            user
            + "\n\nReturn ONLY the single JSON object. No prose, no "
            "explanation, no code fences. Start your reply with { and "
            "end it with }."
        )
        res2 = await asyncio.to_thread(
            platform_adapter.model_call, system, stricter, max_tokens, 0.0, False
        )
        if res2.ok and _has_json_object(res2.content):
            return res2.content
        return ""

    return call


def make_text_llm_call(max_tokens: int = 512) -> LlmCall:
    """Returns an LlmCall for non JSON outputs (notes compaction)."""

    async def call(system: str, user: str) -> str:
        res = await asyncio.to_thread(
            platform_adapter.model_call, system, user, max_tokens, 0.0, False
        )
        return res.content if res.ok else ""

    return call
