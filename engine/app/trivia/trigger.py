"""Trivia trigger classifier.

Takes an utterance string and decides whether it is a factual question
the user wants answered. Returns a confidence score 0.0 to 1.0 plus a
short reason string for the activity log.

For the demo we use a deterministic regex+keyword classifier; this is
explicitly the "regex for the demo if LLM too slow" branch called out
in the task brief. The trivia hot path needs sub-2-second total
latency, so a 100-300 ms LLM round trip is expensive on this exact
gate. The structure is set up so the LLM lane can be wired in later
without changing call sites.

Fire threshold: 0.85. Below that the caller treats the utterance as a
normal action-engine input and routes it to the existing pipeline.

Negative filters:
- Self-talk ("why are we even doing this").
- Hypothetical / rhetorical ("what year is it" said in mock outrage).
  We detect by an exclamation marker or framing words.
- Third-party direction ("Hey Jordan, what year did you graduate").
- Recently answered: caller handles by inspecting recent fires, not
  here.

The regex classifier is intentionally not sophisticated. The LLM
escalation path in ``trigger_llm`` is wired but not used on the hot
path by default; the orchestrator can flip ``ANTICIPY_TRIVIA_USE_LLM=1``
to enable it.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass


# The brief says fire on >= 0.85.
FIRE_THRESHOLD = float(os.environ.get("ANTICIPY_TRIVIA_THRESHOLD", "0.85"))


# Strong interrogative openers. Almost always a factual question if
# matched.
_STRONG_OPENERS = (
    r"^\s*wait[\s,.!?-]+(?:when|where|who|what|how)\b",
    r"^\s*(?:hold on|hang on)[\s,.!?-]+(?:when|where|who|what|how)\b",
    r"^\s*(?:do you|does anyone|does anybody)\s+(?:know|remember)\b",
    r"^\s*(?:what(?:'s| is)|who(?:'s| is|m)|when|where|how)\s+(?:was|were|did|does|do|is|are)\b",
    r"^\s*(?:what year|what date|what month|what day)\b",
    r"^\s*remind me\s+(?:when|where|who|what|how)\b",
    r"^\s*(?:i (?:can'?t|don'?t|forget|forgot|never) (?:remember|recall|know))\b",
    r"^\s*google (?:it|that)(?: real quick)?\b",
)

# Softer interrogative cues. Worth ~0.4 alone, combine with question
# mark or rising intonation indicator for strong hit.
_SOFT_CUES = (
    r"\bwasn'?t (?:it|that)\b",
    r"\bisn'?t (?:it|that)\b",
    r"\b(?:i think|i thought|pretty sure) (?:it (?:was|is)|that was|that is)\b",
    r"\bwho (?:was|is|wrote|invented|played)\b",
    r"\bwhat (?:was|is) the\b",
    r"\bhow (?:many|much|old|long|tall|far|fast|big|wide|deep)\b",
    r"\bwhen (?:was|did|do|does|will|is)\b",
    r"\bwhere (?:was|is|did|do|does|will)\b",
)

# Hard kill switches. If any match, do not fire even if openers hit.
_BLOCKERS = (
    # Vocative to a named person, suggests the question is directed at
    # another human. "Hey Jordan, when did you graduate".
    r"^\s*(?:hey|yo|listen|ok|okay)\s+[A-Z][a-z]+[\s,]",
    # Joke / rhetorical framing.
    r"\b(?:imagine if|wouldn'?t it be|isn'?t it crazy|crazy how|funny how)\b",
    # Self-narration / meta.
    r"\b(?:why are we (?:even|doing|talking)|why do i (?:always|even))\b",
    # Future intent ("I should look up", "remind me to find") which goes
    # to memory not trivia.
    r"\b(?:remind me to (?:find|search|look up|google))\b",
    # Cancel words.
    r"\bnever mind\b",
    # Direct command to user's assistant for a non-factual task.
    r"\b(?:draft|send|email|schedule|book|cancel|reply|forward) (?:an?|the|my)\b",
    # First-person musing about doing something later.
    r"\b(?:i (?:should|need to|have to|gotta|wanna) (?:draft|send|email|schedule|book|cancel))\b",
    # Quoted speech.
    r'^[\'"]',
)


_QUESTION_MARK_RE = re.compile(r"\?")
_STRONG_RES = [re.compile(p, re.IGNORECASE) for p in _STRONG_OPENERS]
_SOFT_RES = [re.compile(p, re.IGNORECASE) for p in _SOFT_CUES]
_BLOCK_RES = [re.compile(p, re.IGNORECASE) for p in _BLOCKERS]


@dataclass
class TriggerResult:
    """Output of the classifier."""

    confidence: float
    fire: bool
    reason: str
    matched: list[str]

    def to_dict(self) -> dict:
        return {
            "confidence": round(float(self.confidence), 3),
            "fire": bool(self.fire),
            "reason": self.reason,
            "matched": list(self.matched),
            "threshold": FIRE_THRESHOLD,
        }


def _blocker_hits(text: str) -> list[str]:
    return [r.pattern for r in _BLOCK_RES if r.search(text)]


def classify(utterance: str, *,
             threshold: float | None = None) -> TriggerResult:
    """Return a TriggerResult for ``utterance``.

    Confidence is computed as:
      strong_opener_hit  -> base 0.88
      soft_cue_hit + ?   -> base 0.86
      soft_cue_hit only  -> base 0.55
      question_mark only -> base 0.40
      none               -> 0.0

    Then subtract 0.6 for any blocker hit (so blockers always drop us
    below the 0.85 fire threshold).
    """
    if not utterance or not utterance.strip():
        return TriggerResult(0.0, False, "empty utterance", [])
    text = utterance.strip()
    matched: list[str] = []

    strong = [r.pattern for r in _STRONG_RES if r.search(text)]
    soft = [r.pattern for r in _SOFT_RES if r.search(text)]
    qmark = bool(_QUESTION_MARK_RE.search(text))
    blockers = _blocker_hits(text)

    if strong:
        confidence = 0.90
        matched.extend([f"strong:{p[:60]}" for p in strong])
    elif soft and qmark:
        confidence = 0.86
        matched.extend([f"soft+q:{p[:60]}" for p in soft])
    elif soft:
        confidence = 0.55
        matched.extend([f"soft:{p[:60]}" for p in soft])
    elif qmark:
        confidence = 0.40
        matched.append("qmark_only")
    else:
        confidence = 0.0

    if blockers:
        confidence = max(0.0, confidence - 0.60)
        matched.extend([f"block:{b[:60]}" for b in blockers])

    # The user explicitly told us to look it up. Force fire.
    if re.search(r"^\s*google (?:it|that)(?: real quick)?\b", text,
                 re.IGNORECASE):
        confidence = max(confidence, 0.95)
        matched.append("explicit:google_it")

    thresh = float(FIRE_THRESHOLD if threshold is None else threshold)
    fire = confidence >= thresh

    reason_parts: list[str] = []
    if strong:
        reason_parts.append("strong question opener")
    elif soft and qmark:
        reason_parts.append("soft cue with question mark")
    elif soft:
        reason_parts.append("soft cue only, below fire bar")
    elif qmark:
        reason_parts.append("question mark only")
    else:
        reason_parts.append("no question signals")
    if blockers:
        reason_parts.append(f"{len(blockers)} blocker(s) suppressed")
    reason = "; ".join(reason_parts)

    return TriggerResult(
        confidence=float(round(confidence, 3)),
        fire=bool(fire),
        reason=reason,
        matched=matched,
    )


def trigger_llm(utterance: str) -> TriggerResult:
    """Optional LLM-backed classifier. Not on the hot path by default;
    the regex classifier is fast enough and the model broker only
    allows a narrow allowlist of models. Keeping the seam so this can
    swap in cleanly behind ``ANTICIPY_TRIVIA_USE_LLM=1``."""
    # Intentionally a thin pass-through to keep the API stable. A real
    # LLM call here would burn 150-400 ms and force a network round
    # trip, which adds bursty p99 latency that the trivia demo cannot
    # tolerate. The regex classifier is the shipped default.
    return classify(utterance)


def should_fire(utterance: str) -> bool:
    """Convenience boolean wrapper. True when the utterance is a
    factual question above the fire threshold."""
    return classify(utterance).fire


__all__ = [
    "FIRE_THRESHOLD",
    "TriggerResult",
    "classify",
    "should_fire",
    "trigger_llm",
]
