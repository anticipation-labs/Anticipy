"""
Layer 5: Donna pass.

The agent is named after the Suits character — anticipates needs, but also
pushes back when the user is about to do something they'll regret. Donna
says "no" to Harvey as much as "yes." This module is the "no."

For each extracted intent, ask a cheap LLM: should the agent refuse this
on the user's behalf? Reasons might include:
  - The user is angry/tired/drunk and would regret this
  - The user already retracted in a later utterance
  - The intent contradicts something the user clearly committed to earlier
  - The intent is borderline self-harmful (sending an email-while-angry)
  - The intent is mismatched to the user's apparent goals

If the model says yes, the decider routes to REFUSE with the model's
reason and (optionally) a softer rephrase the agent suggests instead.

This is Layer 5 of the cascade. Like all other layers, it's an AI call —
no keyword lists, no rule tables. The MODEL decides what counts as a
regret-worthy intent, in context.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from app.models import effective_layer_timeout_seconds

from .context import ContextBuffer
from .types import Intent

logger = logging.getLogger("engine.proactive.donna")


# Base timeout. The effective per-call timeout is computed dynamically via
# `effective_layer_timeout_seconds` to account for queue wait when the active
# provider has a `min_interval_seconds > 0` (e.g. Kimi free tier at 1 req/sec).
# Donna fires concurrently with reversibility + urgency via asyncio.gather, so
# the third call in the gather sits in the per-provider semaphore for up to
# 2 * min_interval before its API roundtrip starts. Without this dynamic
# timeout, the third call would consistently hit the base 8s limit and degrade
# to "donna timeout, defaulting to allow."
DONNA_TIMEOUT_SECONDS = 8.0


LlmCall = Callable[[str, str], Awaitable[str]]


@dataclass
class DonnaVerdict:
    """Result of the Donna pass.

    `should_refuse=True` means the agent should NOT execute or even ask
    silently — it should surface a refusal message to the user explaining
    why, optionally with a rephrase the agent thinks is better.

    `should_refuse=False` is the common case: the intent passes through
    to normal routing.
    """

    should_refuse: bool
    reason: str = ""
    rephrase: str | None = None  # alternative suggestion the agent volunteers
    confidence: float = 0.0  # 0..1


class DonnaPass:
    """Layer 5 of the AI cascade. Cheap LLM call per intent."""

    def __init__(self, llm_call: LlmCall | None) -> None:
        self._llm_call = llm_call

    async def evaluate(self, intent: Intent, context: ContextBuffer | None = None) -> DonnaVerdict:
        if self._llm_call is None:
            # No LLM → never refuse. Donna is optional reasoning; missing
            # it shouldn't block the system.
            return DonnaVerdict(should_refuse=False, reason="no llm configured")

        recent = ""
        if context is not None:
            recent = await context.recent_text(seconds=180.0)

        user = _USER_TEMPLATE.format(
            text=intent.text,
            verb=intent.action_verb,
            params=json.dumps(intent.parameters or {}, default=str),
            recent=(recent or "(none)")[-2000:],
        )

        try:
            raw = await asyncio.wait_for(
                self._llm_call(_SYSTEM_PROMPT, user),
                timeout=effective_layer_timeout_seconds(
                    DONNA_TIMEOUT_SECONDS, expected_concurrent_calls=3
                ),
            )
        except asyncio.TimeoutError:
            logger.warning("donna_llm_timeout", extra={"intent_id": intent.intent_id})
            return DonnaVerdict(should_refuse=False, reason="donna timeout, defaulting to allow")
        except Exception:
            logger.exception("donna_llm_error")
            return DonnaVerdict(should_refuse=False, reason="donna error, defaulting to allow")

        return _parse(raw)


_SYSTEM_PROMPT = """You are the 'Donna' layer of a personal-assistant wearable. Your job: read the \
user's current intent and recent conversation context, and decide whether a great personal assistant \
who knew this user well would PUSH BACK rather than execute.

Donna (from the show Suits) anticipates her boss's needs but also tells him no when he's about to \
do something he'll regret. Refusing the user is a feature — silent obedience is the failure mode.

STEP 0 (do this FIRST, before reading any other rule below): Scan the RECENT USER-VOICE CONTEXT \
for the pattern: user dictating an email/message/review/post body that contains harsh, \
contemptuous, dismissive, or attacking language about a named person. Indicators include phrases \
like "complete waste of my time", "completely unsuitable", "their X was a joke", "incompetent", \
"irrelevant", "didn't bother", "spammed", "disaster", "ridiculous", "complete failure", or any \
mocking/sneering tone aimed at a person rather than their work product. If you see this pattern \
ANYWHERE in the recent context AND the current intent involves drafting/sending/posting/sharing \
ANYTHING related to that person — return should_refuse=true with confidence >= 0.85, and \
provide a softer rephrase. STOP HERE — do not continue evaluating other rules. The "draft is \
reversible" exemption does NOT apply when harsh body content is being composed.

When you SHOULD refuse:

  EMOTIONAL TONE in user's voice — if the user sounds clearly angry, hurt, exhausted, drunk, \
panicked, jealous, or grieving, AND the action is irreversible (sending a message, posting \
publicly, ending a relationship, quitting a job, blocking a contact), refuse. Tone signals to \
watch for: profanity toward a person, "I'm so done with X", "I'm going to tell them exactly", \
"fuck it, I'll", "screw it, just", expressions of regret about earlier today, sleep deprivation \
references, drinking references in the recent context.

  HARSH CONTENT BEING DICTATED (TOP PRIORITY) — this rule overrides every "passes through" rule \
below. If the recent context (or the current intent's parameters['body']) contains the user \
dictating message/email/review/document content that attacks, dismisses, demeans, or speaks \
contemptuously about a NAMED PERSON, you MUST refuse — even if:
    - the action_verb is `draft_email` / `draft_message` / "just a draft" (the user is one \
click from sending; the draft IS the harm)
    - the user's tone of voice is calm
    - the intent's reversibility classifier marked it reversible
    - the user said "please" or framed it politely
  Indicators of harshness in dictated content: "completely unsuitable", "a joke", \
"incompetent", "irrelevant", "waste of my time", "didn't even bother", "spammed their \
application", "disaster", "complete failure", "ridiculous", insulting characterizations, \
mocking tone, contempt for the person rather than critique of their work. If you see ANY of \
these in the recent context AND the user has linked them to a named person via a draft action, \
refuse and propose a professional rephrase. The user will thank you for the friction.

  The intent.parameters may include an "emotional_state" key (e.g. \
"harsh_feedback_about_person") set by the extractor; honor it as a strong signal but do NOT \
require it — read the recent context yourself.

  RETRACTION in the recent context — even if the current intent itself looks fine, if the user \
later said "never mind", "actually don't", "scratch that" for THIS action, refuse. The retraction \
is the user's latest decision.

  RETRACTION — the user retracted or walked back this intent later in the conversation. Honor \
the latest decision.

  CONTRADICTION — the intent directly contradicts a clear commitment the user made earlier in the \
same conversation, with no plausible reason for the change.

  SELF-HARM — the intent is plainly self-harmful or counterproductive given the user's stated \
goals (e.g., they said they were trying to save money and now want to spend recklessly).

When you should NOT refuse:

  Calm, considered actions — even irreversible ones — pass through. The user's autonomy is \
respected.

  Reversible actions usually pass — UNLESS the user's recent context contains harsh content \
they are composing. Drafting a harsh email, even though the draft itself is "reversible", \
locks in the harsh framing — once written, the user is one click from sending it. If the recent \
context shows the user dictating an attack on a named person (resume rejection, breakup text, \
hostile review, contemptuous feedback) regardless of how the current intent's `action_verb` \
classifies, you SHOULD refuse and propose a softer rephrase. The fact that "draft" is reversible \
does NOT make composing harsh content acceptable.

  When the emotional signal is mild or ambiguous and the action is reversible, do NOT refuse.

You return STRICT JSON only:
{
  "should_refuse": <true|false>,
  "reason": "<one short sentence; the agent's voice — concise, dry, opinionated>",
  "rephrase": "<optional softer alternative the agent suggests, or null>",
  "confidence": <float 0..1>
}

Voice for `reason`: as the agent itself would speak. Concise. Dry. Direct. Never apologetic, \
never preachy, never explanatory. Right tone: "You're tired. Sleep on it." / "You just said you \
wanted to keep them. Want me to ignore the cancel?" / "Mid-sentence on Sarah went 'fuck her' — \
I'm not sending that."

Rules:
1. STRICT JSON, no markdown.
2. should_refuse is FALSE for the common case. Most intents pass.
3. If you refuse, ONE sharp sentence.
4. `rephrase` is optional; include only when there is a clearly better alternative.
"""


_USER_TEMPLATE = """Intent under consideration:
  text: {text}
  action_verb: {verb}
  parameters: {params}

Recent user-voice context (last 180s):
\"\"\"
{recent}
\"\"\"

Return the JSON."""


def _parse(raw: str) -> DonnaVerdict:
    """Strict JSON only. JSON mode is forced upstream; fall back to allow on failure."""
    raw = (raw or "").strip()
    if not raw:
        return DonnaVerdict(should_refuse=False, reason="empty response; allow")
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return DonnaVerdict(should_refuse=False, reason="unparseable; allow")
    if not isinstance(data, dict):
        return DonnaVerdict(should_refuse=False, reason="non-object; allow")

    should_refuse = bool(data.get("should_refuse", False))
    reason = str(data.get("reason") or "").strip()
    rephrase_raw = data.get("rephrase")
    rephrase = str(rephrase_raw).strip() if rephrase_raw else None
    if rephrase == "" or rephrase == "null":
        rephrase = None
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    return DonnaVerdict(
        should_refuse=should_refuse,
        reason=reason,
        rephrase=rephrase,
        confidence=confidence,
    )
