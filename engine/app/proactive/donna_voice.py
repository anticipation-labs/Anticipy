"""
Donna voice: optional LLM re-phrasing of decider's terse strings into
conversational wearer-facing nudges.

The decider produces functional, plain-English copy:

    "Confirm before I do this: book a reservation at the diner Friday at 7pm?"
    "Done. Booked the reservation."

Donna voice rewraps that with persona — concise, dry, slightly impatient,
willing to be informal — so the wearer hears something more like:

    "Hey — Carbone Friday at 7? I'll grab it if you nod."
    "Booked. Carbone Friday 7pm. Confirmation in your email."

When `llm_call` is None, the original Decision strings pass through
unchanged, so the cascade stays deterministic for tests and for the
default code path.

Per cop-out #10, persona prompts describe categories of behavior, never
specific instances. Per cop-out #15, output never contains technical
terms (model names, JSON, IDs).
"""

from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable

from .types import Decision

LlmCall = Callable[[str, str], Awaitable[str]]

logger = logging.getLogger("engine.proactive.donna_voice")


_DONNA_SYSTEM = """\
You rephrase one functional sentence into a conversational, casual one-line
nudge in the voice of a confident, dry, slightly impatient personal
assistant — concise, opinionated, willing to be informal, never syrupy.

Constraints:
  - One sentence. Under 25 words.
  - Plain English. No emoji unless the input had one.
  - Do not invent facts not present in the input.
  - For ASK nudges: end with a clear yes/no shape ("Sound good?", "Want me
    to grab it?", "Worth a try?", "?"). Lead with what you noticed when
    natural.
  - For COMPLETION messages: past tense, factual, with the key concrete
    detail the wearer cares about (number, name, time, where to find it).
  - For REFUSAL: stay confident, give the reason without lecturing, no
    apologies, never say "I'm sorry".
  - Never use technical terms (no model names, JSON, IDs, "DOM", "selector").
  - Never name a specific website unless the input named it.
  - Do not change the underlying meaning.

Output STRICT JSON only:
{ "rephrased": "<the one-line nudge>" }
"""


async def _rephrase(llm_call: LlmCall, kind_label: str, source_text: str) -> str:
    """Run one LLM call to re-phrase. Returns source_text on any failure."""
    if not source_text or not source_text.strip():
        return source_text

    prompt = (
        f"Kind: {kind_label}\n"
        f"Source sentence to rephrase:\n\"\"\"\n{source_text.strip()}\n\"\"\"\n\n"
        "Output the JSON."
    )
    try:
        raw = await llm_call(_DONNA_SYSTEM, prompt)
    except Exception:
        logger.exception("donna_voice rephrase raised")
        return source_text

    if not raw or not raw.strip():
        return source_text

    try:
        data = json.loads(raw.strip())
    except (ValueError, TypeError):
        return source_text

    if not isinstance(data, dict):
        return source_text

    out = str(data.get("rephrased") or "").strip()
    return out or source_text


async def compose_ask_narrative(
    decision: Decision,
    llm_call: LlmCall | None = None,
) -> str:
    """Wearer-facing ASK string. Falls back to decision.user_facing_question."""
    base = (decision.user_facing_question or "").strip()
    if not base:
        # Defensive: an ASK should always have user_facing_question, but
        # synthesize from intent.text if not.
        base = (decision.intent.text or "").rstrip(".") + "?"
    if llm_call is None:
        return base
    return await _rephrase(llm_call, "ASK (need yes/no)", base)


async def compose_completion_narrative(
    decision: Decision,
    actual_result: str = "",
    llm_call: LlmCall | None = None,
) -> str:
    """Wearer-facing completion string.

    Combines the cascade's pre-composed completion_message with whatever
    the agent actually returned, so the wearer sees the concrete detail
    instead of the generic "Done." pattern.
    """
    base = (decision.completion_message or "").strip()
    extra = (actual_result or "").strip()

    if extra and extra not in (base, "Done.", "Done"):
        if base and base not in extra:
            base = f"{base} — {extra}"
        else:
            base = extra
    if not base:
        base = "Done."

    if llm_call is None:
        return base
    return await _rephrase(llm_call, "COMPLETION (past tense, with concrete detail)", base)


async def compose_refusal_narrative(
    decision: Decision,
    llm_call: LlmCall | None = None,
) -> str:
    """Wearer-facing refusal. Falls back to decision.refusal_reason."""
    base = (decision.refusal_reason or "").strip()
    if not base:
        base = "I'd rather not do that one."
    if llm_call is None:
        return base
    return await _rephrase(llm_call, "REFUSE (firm, no apology, no lecture)", base)
