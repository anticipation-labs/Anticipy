"""
Layer 3: Reversibility classifier — AI call.

Per Omar's directive 2026-05-01: NO keyword tables, NO verb lookups. The
reversibility judgment for a given intent is an AI call that reads the
intent text, action verb, parameters, and recent context, and returns
reversible / irreversible / unknown with reasoning.

Bias: the model is told to lean IRREVERSIBLE when uncertain. This is the
only baked-in bias — and it's not "intent detection," it's a *failure
mode preference*. False positives (treating reversible as irreversible)
cost a confirmation tap. False negatives (treating irreversible as
reversible) cost a sent email or a charged credit card. The asymmetry is
the whole reason this layer exists.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from app.models import effective_layer_timeout_seconds

from .context import ContextBuffer
from .types import Intent, Reversibility

logger = logging.getLogger("engine.proactive.reversibility")


# Base timeout. Effective timeout is computed dynamically — see donna.py for
# the rationale. Reversibility runs in the L3+L4+L5 gather, concurrent_calls=3.
REVERSIBILITY_TIMEOUT_SECONDS = 8.0
DEFAULT_REVERSIBILITY_ON_FAILURE = Reversibility.IRREVERSIBLE  # fail safe

LlmCall = Callable[[str, str], Awaitable[str]]


@dataclass
class ReversibilityVerdict:
    reversibility: Reversibility
    confidence: float = 0.0  # 0..1, model's own certainty
    reasoning: str = ""


class ReversibilityClassifier:
    """Layer 3 of the AI cascade. One LLM call per intent."""

    def __init__(self, llm_call: LlmCall | None) -> None:
        self._llm_call = llm_call

    async def classify(self, intent: Intent, context: ContextBuffer | None = None) -> ReversibilityVerdict:
        if self._llm_call is None:
            return ReversibilityVerdict(
                reversibility=DEFAULT_REVERSIBILITY_ON_FAILURE,
                confidence=0.0,
                reasoning="no LLM configured; failed safe to irreversible",
            )

        recent = ""
        if context is not None:
            recent = await context.recent_text(seconds=120.0)

        user = _USER_TEMPLATE.format(
            text=intent.text,
            verb=intent.action_verb,
            params=json.dumps(intent.parameters or {}, default=str),
            recent=(recent or "(none)")[-1500:],
        )

        try:
            raw = await asyncio.wait_for(
                self._llm_call(_SYSTEM_PROMPT, user),
                timeout=effective_layer_timeout_seconds(
                    REVERSIBILITY_TIMEOUT_SECONDS, expected_concurrent_calls=3
                ),
            )
        except asyncio.TimeoutError:
            logger.warning("reversibility_llm_timeout", extra={"intent_id": intent.intent_id})
            return ReversibilityVerdict(
                reversibility=DEFAULT_REVERSIBILITY_ON_FAILURE,
                confidence=0.0,
                reasoning="llm timeout; failed safe to irreversible",
            )
        except Exception:
            logger.exception("reversibility_llm_error")
            return ReversibilityVerdict(
                reversibility=DEFAULT_REVERSIBILITY_ON_FAILURE,
                confidence=0.0,
                reasoning="llm error; failed safe to irreversible",
            )

        return _parse(raw)


_SYSTEM_PROMPT = """You are deciding whether a single intended user action is reversible. The user \
wears a personal-assistant wearable that may execute the action on their behalf. Your output \
determines whether the assistant proceeds silently (reversible + confident) or asks the user to \
confirm first (irreversible).

You return STRICT JSON only:
{
  "reversibility": "reversible" | "irreversible" | "unknown",
  "confidence": <float 0..1>,
  "reasoning": "<one sentence>"
}

Frame the question as: what will the AGENT actually DO on the user's behalf — not what the \
user themselves will do later. The agent's action is the unit of reversibility, not the user's \
eventual real-world action.

REVERSIBLE means: if the assistant does this and the user later disagrees, undoing it is trivial — \
no one was contacted, no money moved, no commitment made on the user's behalf. Examples include:
  - searching, reading, navigating to a URL, drafting (without sending), checking availability
  - adding to the user's personal list/note/reminder/shopping list
  - setting a reminder, alarm, or calendar entry on the user's OWN device/calendar
  - extracting a fact, computing something, looking up a price/weather/route
  - even when the USER plans to later make an irreversible action (e.g., user says "I'll buy \
the groceries on my way home"), the agent's helpful contribution here is REVERSIBLE — it is \
adding the items to a shopping list, setting a reminder, or showing the user the store hours. \
None of those agent actions commit anything on the user's behalf. Classify as REVERSIBLE.

IRREVERSIBLE means: doing this changes state outside the user's private device in a way they cannot \
fully undo with one tap. The agent must be the actor for it to count. Examples: sending any \
message (email/SMS/DM) on the user's behalf, making a purchase or payment via the agent, \
booking/reserving with a third party (commits user's name and time), submitting a form or \
application, cancelling a subscription or booking, deleting/removing/unsubscribing/unfollowing, \
posting publicly, voting, donating, accepting/declining invitations, RSVPs, ratings/reviews. If \
the agent is going to TRANSMIT something with the user's identity attached, it is IRREVERSIBLE.

UNKNOWN: when you genuinely cannot tell, return unknown. The downstream system treats unknown as \
irreversible for safety.

Bias: if you're uncertain, lean IRREVERSIBLE. False positives cost a tap; false negatives can cost \
a sent email, a charged card, or a booked reservation the user didn't want.

Rules:
1. STRICT JSON only.
2. Use the recent context to disambiguate (e.g., "send it" — send what?).
3. If parameters mention "draft" or "save as draft" or similar, the action is reversible.
4. If parameters mention "book", "purchase", "send", "pay", they're irreversible regardless of verb.
"""


_USER_TEMPLATE = """Intent under consideration:
  text: {text}
  action_verb: {verb}
  parameters: {params}

Recent user-voice context (last 120s, may be empty):
\"\"\"
{recent}
\"\"\"

Return the reversibility JSON."""


def _parse(raw: str) -> ReversibilityVerdict:
    """Strict JSON parser. The provider is invoked with native JSON mode, so
    `raw` is either a clean JSON object or empty (full-cascade failure). No
    regex, no fence stripping — if it doesn't parse, fail safe."""
    raw = (raw or "").strip()
    if not raw:
        return ReversibilityVerdict(
            reversibility=DEFAULT_REVERSIBILITY_ON_FAILURE,
            confidence=0.0,
            reasoning="empty response; failed safe",
        )
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return ReversibilityVerdict(
            reversibility=DEFAULT_REVERSIBILITY_ON_FAILURE,
            confidence=0.0,
            reasoning="unparseable response; failed safe",
        )
    if not isinstance(data, dict):
        return ReversibilityVerdict(
            reversibility=DEFAULT_REVERSIBILITY_ON_FAILURE,
            confidence=0.0,
            reasoning="non-object response; failed safe",
        )

    rev_str = str(data.get("reversibility") or "").strip().lower()
    rev = {
        "reversible": Reversibility.REVERSIBLE,
        "irreversible": Reversibility.IRREVERSIBLE,
        "unknown": Reversibility.UNKNOWN,
    }.get(rev_str, DEFAULT_REVERSIBILITY_ON_FAILURE)

    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    reasoning = str(data.get("reasoning") or "").strip()
    return ReversibilityVerdict(reversibility=rev, confidence=confidence, reasoning=reasoning)
