"""Stage 1 — demand detection.

Cheap binary gate. Asks the cheapest free-tier provider: "Did the wearer
just *request* something they want done?" Returns ACTIONABLE / NOT_ACTIONABLE.

This is intentionally a low-bar filter — its job is to drop the obvious
non-asks (small talk, observations, narration) before the more expensive
Stage 1.5 hedge filter runs. Stage 1.5 does the nuance (sarcasm, hedging,
retraction, third-party reporting).

Provider: routed through `engine/app/proactive/llm_adapter.make_json_llm_call`
which falls through the MODEL_CHAIN (Gemini → Groq → Mistral → DeepSeek).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional

from app.proactive.llm_adapter import make_json_llm_call

_logger = logging.getLogger("anticipy.proactive.demand_detection")

_SYSTEM_PROMPT = """\
You are Stage 1 of an ambient AI wearable's intent cascade. Your only job
is to decide whether the wearer's most recent utterance is a REQUEST FOR
ACTION (something they want done in the world) versus everything else
(small talk, observation, narration, hypothetical, joke, statement of
fact, complaint, third-party report).

REQUEST FOR ACTION includes ALL of these surface forms:
- direct commands ("book Carbone for Thursday")
- hedged commands ("I should probably text Sarah")
- abandoned commands ("Email her about... no, never mind")
- sarcastic commands (intent is the opposite of literal — "Oh great,
  another team offsite I get to plan" still surfaces a request-shaped
  utterance)
- past-tense reports of an action ("I already replied to John") — these
  LOOK like requests so they DO pass Stage 1, then Stage 1.5 catches them

DO NOT pass through:
- pure observation ("the weather is nice")
- pleasantries ("good morning")
- speech describing third-party state with no action-on-wearer ("Sarah
  liked the photo")
- emoji / non-linguistic content

Output STRICT JSON only:

  {"actionable": true | false, "confidence": 0.0..1.0, "reason": "<one short clause>"}

When in doubt, prefer actionable=true. Stage 1.5 catches the false
positives — it's costlier on false negatives.
"""


@dataclass(frozen=True, slots=True)
class DemandDecision:
    actionable: bool
    confidence: float
    reason: str


class DemandDetector:
    """Stage 1 classifier. One LLM call per utterance."""

    def __init__(self, max_tokens: int = 80) -> None:
        self._llm = make_json_llm_call(max_tokens=max_tokens)

    async def classify(self, utterance: str, context: Optional[str] = None) -> DemandDecision:
        """Classify a single utterance. `context` is the prior conversation
        window joined as a single string ("Wearer: ...\\nOther: ..."), used
        to disambiguate borderline utterances.
        """
        user_msg = (
            f"PRIOR CONVERSATION:\n{context.strip()}\n\n"
            if context and context.strip()
            else ""
        ) + f"WEARER'S MOST RECENT UTTERANCE:\n{utterance.strip()}"

        raw = await self._llm(_SYSTEM_PROMPT, user_msg)
        if not raw:
            # Full cascade failure → default to actionable to avoid
            # missing legitimate requests. Stage 1.5 will catch the
            # false positive if it was one.
            return DemandDecision(actionable=True, confidence=0.0, reason="cascade_failed_open")

        try:
            parsed = json.loads(raw)
            return DemandDecision(
                actionable=bool(parsed.get("actionable")),
                confidence=float(parsed.get("confidence", 0.5)),
                reason=str(parsed.get("reason", ""))[:200],
            )
        except (ValueError, TypeError) as e:
            _logger.warning("demand_detection JSON parse failed: %s; raw=%s", e, raw[:200])
            return DemandDecision(actionable=True, confidence=0.0, reason="json_parse_failed_open")
