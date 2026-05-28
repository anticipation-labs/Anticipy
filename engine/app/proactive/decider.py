"""
Decider: combines AI-derived (confidence, reversibility, urgency, donna) → Decision.

Inputs are all AI outputs. Outputs are a discrete DecisionKind. The combining
function is deterministic — it doesn't detect intent (the prior layers did
that), it routes the AI's judgments into one of four actions.

Routing rules:

  Donna refuses?    → REFUSE (with donna's reason + optional rephrase)
  Reversibility != REVERSIBLE  → ASK (channel by urgency)
  Confidence >= HIGH (0.85)    → EXECUTE (channel by urgency, fyi-only)
  Confidence >= MID  (0.50)    → ASK    (channel by urgency)
  Otherwise                    → LOG    (silent in 'things I noticed')

The thresholds (HIGH_CONFIDENCE, MID_CONFIDENCE) are tunable hyperparameters
calibrated by the eval harness. Not hardcoded intent detection — calibration
of AI signal output into action space.

The decider runs the three classifiers (reversibility, urgency, donna) in
parallel via asyncio.gather to minimize latency.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from .context import ContextBuffer
from .donna import DonnaPass, DonnaVerdict
from .interpreter import ExtractedIntent
from .reversibility import ReversibilityClassifier
from .types import (
    Confidence,
    Decision,
    DecisionKind,
    Reversibility,
    Urgency,
)
from .urgency import UrgencyScorer

logger = logging.getLogger("engine.proactive.decider")


HIGH_CONFIDENCE = 0.85
MID_CONFIDENCE = 0.45  # tuned 2026-05-01 against the eval harness — under 0.50 catches more
# implicit-but-committal language while keeping false-positive rate bounded by Donna + safety.


@dataclass
class _RouteResult:
    kind: DecisionKind
    user_facing_question: str | None = None
    completion_message: str | None = None
    refusal_reason: str | None = None


class Decider:
    """Combines L3+L4+L5 AI calls into a Decision."""

    def __init__(
        self,
        reversibility_classifier: ReversibilityClassifier,
        urgency_scorer: UrgencyScorer,
        donna_pass: DonnaPass,
    ) -> None:
        self._rev = reversibility_classifier
        self._urg = urgency_scorer
        self._donna = donna_pass

    async def decide(
        self,
        extracted: ExtractedIntent,
        context: ContextBuffer,
    ) -> Decision:
        intent = extracted.intent
        confidence = extracted.confidence

        rev_verdict, urgency, donna_verdict = await asyncio.gather(
            self._rev.classify(intent, context),
            self._urg.score(intent, context),
            self._donna.evaluate(intent, context),
        )

        routed = _route(
            reversibility=rev_verdict.reversibility,
            confidence=confidence,
            intent=intent,
            urgency=urgency,
            donna=donna_verdict,
        )

        decision = Decision.new(
            intent=intent,
            kind=routed.kind,
            confidence=confidence,
            reversibility=rev_verdict.reversibility,
            urgency=urgency,
            user_facing_question=routed.user_facing_question,
            completion_message=routed.completion_message,
            refusal_reason=routed.refusal_reason,
        )

        logger.info(
            "decider_decision",
            extra={
                "user_id": intent.user_id,
                "intent_id": intent.intent_id,
                "verb": intent.action_verb,
                "kind": decision.kind.value,
                "confidence": confidence.score,
                "reversibility": rev_verdict.reversibility.value,
                "rev_confidence": rev_verdict.confidence,
                "urgency": urgency.level,
                "donna_refused": donna_verdict.should_refuse,
            },
        )

        return decision


def _route(
    reversibility: Reversibility,
    confidence: Confidence,
    intent,
    urgency: Urgency,
    donna: DonnaVerdict | None = None,
) -> _RouteResult:
    """Pure routing function. AI signals in, DecisionKind out."""

    if donna is not None and donna.should_refuse:
        reason = donna.reason or "I'd rather not do this one."
        if donna.rephrase:
            reason = f"{reason} {donna.rephrase}".strip()
        return _RouteResult(
            kind=DecisionKind.REFUSE,
            refusal_reason=reason,
        )

    if reversibility != Reversibility.REVERSIBLE:
        return _RouteResult(
            kind=DecisionKind.ASK,
            user_facing_question=_compose_ask(intent, reversibility),
        )

    if confidence.score >= HIGH_CONFIDENCE:
        return _RouteResult(
            kind=DecisionKind.EXECUTE,
            completion_message=_compose_completion(intent),
        )
    if confidence.score >= MID_CONFIDENCE:
        return _RouteResult(
            kind=DecisionKind.ASK,
            user_facing_question=_compose_ask(intent, reversibility),
        )
    return _RouteResult(kind=DecisionKind.LOG)


def _compose_ask(intent, reversibility: Reversibility) -> str:
    if reversibility != Reversibility.REVERSIBLE:
        prefix = "Confirm before I do this: "
    else:
        prefix = ""
    return f"{prefix}{intent.text}".rstrip(".") + "?"


def _compose_completion(intent) -> str:
    return f"Done. {intent.text}"
