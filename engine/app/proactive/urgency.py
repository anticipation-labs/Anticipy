"""
Urgency scorer: 1 (no rush) → 5 (right now).

LLM-driven, not hand-tuned. Hand-tuning would mean hardcoding "if 'today'
appears, score 3" which collapses on real conversations. The LLM reads
context and the intent and returns a score with a one-sentence reasoning.

The score maps to a notification channel via Urgency.channel (in types.py):

    1 → NOTED        (silent; "things I noticed" feed)
    2 → IN_APP       (in-app badge)
    3 → PUSH         (push notification)
    4 → SMS          (text message)
    5 → VOICE        (voice call)

This is the ONLY hardcoded part: the score-to-channel mapping is a property
of the channels' intrusiveness, not a behavior rule. The score itself is
LLM-driven.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Awaitable, Callable

from app.models import effective_layer_timeout_seconds

from .context import ContextBuffer
from .types import Intent, Urgency

logger = logging.getLogger("engine.proactive.urgency")


# Base timeout. Effective timeout is computed dynamically — see donna.py for
# the rationale. Urgency runs in the L3+L4+L5 gather, hence concurrent_calls=3.
LLM_TIMEOUT_SECONDS = 8.0
DEFAULT_URGENCY_ON_FAILURE = 2  # be polite by default — don't blast a push if we can't tell


LlmCall = Callable[[str, str], Awaitable[str]]


_SYSTEM_PROMPT = """You are scoring how urgent a single user intent is on a 1-5 scale, given their \
recent conversation context. Return STRICT JSON only.

Scale:
  1 = no time pressure AND passive note-to-self (something the user wants remembered, not \
actioned). E.g. "I should think about what I want for my birthday someday."
  2 = default for actionable intents without explicit time pressure. Lookups, searches, \
reminders for distant events (next week, this month), errands the user mentioned without a \
deadline. ALSO: routine reminders for a specific time today that is more than a few hours away.
  3 = the user mentioned a specific near-future window (this evening, this afternoon, before \
bed, after work, by tonight) or a soft deadline. ALSO: setting a reminder for an event later \
today (more than ~1 hour away).
  4 = within the hour. The event/deadline is genuinely <60 minutes away, or an immediate \
practical need (the user is about to do something where they need this info now).
  5 = right now. The user said "right now", "immediately", "ASAP", "I'm late", or there's a \
clearly imminent deadline (a meeting starting now, a flight boarding, a person waiting).

Output schema:
{
  "level": <int 1..5>,
  "reasoning": "<one sentence>"
}

Rules:
1. STRICT JSON only.
2. Default to 2 for any actionable intent without time markers. Use 1 only for passive \
remembrances/notes-to-self.
3. Phrases like "today" alone are not 4 or 5; "today" with a specific time more than ~1 hour \
away is 3, exactly within the hour is 4. Only words like "right now", "immediately", "ASAP", \
"I'm late", "leaving now" warrant 5.
4. Setting a reminder for "3 PM today" when it is currently morning/early afternoon is 2-3, \
NOT 4 — the reminder itself isn't urgent, it's prep for a future event.
5. The intent.parameters may include "urgency_signal" set by the extractor — honor it.
6. Past-tense ("I should have called") is usually 2.
"""


_USER_PROMPT_TEMPLATE = """Recent transcript context (oldest first):
\"\"\"
{recent}
\"\"\"

Intent we're scoring:
  text: {intent_text}
  action_verb: {verb}
  parameters: {params}

Return the urgency JSON."""


class UrgencyScorer:
    """LLM-backed urgency scorer with a deterministic fallback for offline tests."""

    def __init__(self, llm_call: LlmCall | None) -> None:
        self._llm_call = llm_call

    async def score(self, intent: Intent, context: ContextBuffer) -> Urgency:
        if self._llm_call is None:
            return Urgency(level=DEFAULT_URGENCY_ON_FAILURE, reasoning="no LLM configured")

        recent = await context.recent_text(seconds=120.0)
        user = _USER_PROMPT_TEMPLATE.format(
            recent=recent or "(no recent context)",
            intent_text=intent.text,
            verb=intent.action_verb,
            params=json.dumps(intent.parameters or {}),
        )
        try:
            raw = await asyncio.wait_for(
                self._llm_call(_SYSTEM_PROMPT, user),
                timeout=effective_layer_timeout_seconds(
                    LLM_TIMEOUT_SECONDS, expected_concurrent_calls=3
                ),
            )
        except asyncio.TimeoutError:
            logger.warning("urgency_llm_timeout", extra={"intent_id": intent.intent_id})
            return Urgency(level=DEFAULT_URGENCY_ON_FAILURE, reasoning="llm timeout")
        except Exception:
            logger.exception("urgency_llm_error")
            return Urgency(level=DEFAULT_URGENCY_ON_FAILURE, reasoning="llm error")

        return _parse(raw)


def _parse(raw: str) -> Urgency:
    """Strict JSON only. JSON mode is forced upstream; fall back safely on failure."""
    raw = (raw or "").strip()
    if not raw:
        return Urgency(level=DEFAULT_URGENCY_ON_FAILURE, reasoning="empty response")
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return Urgency(level=DEFAULT_URGENCY_ON_FAILURE, reasoning="unparseable response")
    if not isinstance(data, dict):
        return Urgency(level=DEFAULT_URGENCY_ON_FAILURE, reasoning="non-object response")

    try:
        level = int(data.get("level", DEFAULT_URGENCY_ON_FAILURE))
    except (TypeError, ValueError):
        level = DEFAULT_URGENCY_ON_FAILURE
    level = max(1, min(5, level))
    reasoning = str(data.get("reasoning") or "").strip()
    return Urgency(level=level, reasoning=reasoning)
