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
import json
from typing import Awaitable, Callable, Optional

from app.anticipy import platform_adapter

LlmCall = Callable[[str, str], Awaitable[str]]


def _clean_json(text: str) -> Optional[str]:
    """Return a string the cascade `_parse` functions WILL json.loads,
    or None if the content is genuinely not a JSON object.

    The strictest cascade callers (demand_detection, intent_extraction)
    do ``json.loads(raw)`` on the WHOLE string, so brace presence is not
    enough: multilingual token salad like ``{ "alles חיים ..."`` has
    braces but is not valid JSON, and returning it makes the caller's
    real parse fail and the stage fall to a wrong safe default. So we
    parse here, exactly as the caller will. If the whole string is not
    pure JSON we try the first ``{`` .. last ``}`` slice (matching the
    slice callers) and, if THAT parses, return the cleaned slice so the
    whole string callers also succeed. Pure robustness: clean JSON in,
    same clean JSON out; trailing prose or corruption is repaired or
    rejected, never silently passed through.
    """
    if not text:
        return None
    t = text.strip()
    try:
        obj = json.loads(t)
        return t if isinstance(obj, dict) else None
    except (ValueError, TypeError):
        pass
    s = t.find("{")
    e = t.rfind("}")
    if s == -1 or e == -1 or e <= s:
        return None
    sliced = t[s : e + 1]
    try:
        obj = json.loads(sliced)
    except (ValueError, TypeError):
        return None
    return sliced if isinstance(obj, dict) else None


def make_json_llm_call(max_tokens: int = 1024) -> LlmCall:
    """Returns an LlmCall that returns a JSON object string the cascade
    `_parse` functions WILL json.loads, or "" on full failure so every
    stage falls to its documented safe default (no wrong ACT).

    Port note: strict provider `response_format=json_object` on the
    decider model degenerates into multilingual word salad on the
    cascade's long few shot prompts (observed in the P1 run), and a bad
    OpenRouter provider occasionally returns corrupted token salad or a
    body truncated at max_tokens (observed in the P9 run: 4 corrupt
    responses in 590 cases, each silently degrading a CLEAR_IMPLICIT
    case to under action). An unparseable response to a strict JSON
    prompt carries zero signal; it is a transient provider/budget
    failure, the SAME class the frozen action engine and
    platform_adapter already recover from for empty content with a
    doubled token retry. So this JSON aware wrapper retries with the
    proven mechanism: a stricter prompt (and OpenRouter rotating the
    provider between calls is precisely what escapes a single bad
    provider) and an escalating token budget (covers truncation),
    bounded, returning "" only if every attempt is still uncleanable.
    Wiring only: cascade prompts and stage logic are byte untouched, no
    test or threshold is weakened, and clean JSON is unchanged in/out.
    """

    stricter_suffix = (
        "\n\nReturn ONLY the single JSON object. No prose, no "
        "explanation, no code fences. Start your reply with { and "
        "end it with }."
    )

    async def call(system: str, user: str) -> str:
        # attempt budget escalates: 1x (as-is), 2x (stricter), 3x
        # (stricter). Bounded at 3 — no infinite retry.
        attempts = (
            (user, max_tokens),
            (user + stricter_suffix, max_tokens * 2),
            (user + stricter_suffix, max_tokens * 3),
        )
        for prompt, budget in attempts:
            res = await asyncio.to_thread(
                platform_adapter.model_call, system, prompt, budget, 0.0, False
            )
            if res.ok:
                cleaned = _clean_json(res.content)
                if cleaned is not None:
                    return cleaned
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
