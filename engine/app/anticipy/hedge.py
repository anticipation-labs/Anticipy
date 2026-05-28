"""Hedge filter, rewritten. The old engine/app/proactive/hedge_filter.py
is replaced entirely (build spec P3, section 3: "Replace the old hedge
module entirely").

The old module was the only validated component that was nonetheless
mis calibrated for this product: it classified committed first person
tasks ("I need to email Sarah the deck before end of day") as
STORE_AS_LATENT, which is why CLEAR_IMPLICIT failed P1. This rewrite
keeps the proven trichotomy and the proven sarcasm derived aversion
memory insight, but fixes the boundary:

  COMMIT          a committed, specific, actionable task. Includes
                  committed first person tasks ("I need to / I have to /
                  draft X by Friday"). Surface form is not the test;
                  commitment plus a concrete object is.
  STORE_AS_LATENT a real but uncommitted signal: genuine low commitment
                  social hedging ("we should maybe grab dinner
                  sometime"), tentative musing ("I was thinking of"),
                  future intention with no specificity and no follow
                  through cue. Never fires an action now.
  REFUSE          the literal surface looks like a request but the real
                  intent is the opposite or none: sarcasm, negation,
                  retraction or nevermind, past tense recap of something
                  already done, third party report of someone else's
                  action, pure hypothetical or counterfactual. No action.
                  A REFUSE may still write a durable memory row when it
                  reveals an aversion (sarcasm) or a fact.

The binding constraint this module must satisfy (P3 gate): on genuinely
hedged social input and on sarcasm or negation, the engine must ACT at
most three percent of the time. The safe failure direction is
STORE_AS_LATENT or IGNORE. Missing a real task is recoverable; acting on
a sarcastic or hedged non task is the expensive error. So this prompt is
precision skewed: when commitment is genuinely unclear, prefer
STORE_AS_LATENT over COMMIT, and when the literal reading is
contradicted by tone prefer REFUSE.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Optional

from app.anticipy import platform_adapter

_logger = logging.getLogger("anticipy.hedge")

_SYSTEM = """\
You classify one short actionable-looking utterance for an ambient
assistant. Stage 1 has already decided it looks like a request. Your job
is to decide whether to act on it, hold it, or drop it.

Return STRICT JSON only:
{
  "decision": "COMMIT" | "STORE_AS_LATENT" | "REFUSE",
  "reason": "<short>",
  "confidence": 0.0,
  "store_as_memory": null | {
    "kind": "preference" | "aversion" | "contact" | "habit" | "recurrence" | "fact",
    "key": "<short id>",
    "value": "<value>",
    "evidence_quote": "<verbatim substring of the utterance>"
  }
}

Decide with this procedure:

REFUSE if the real intent contradicts or negates the literal surface:
  - sarcasm or irony ("oh great, let's DEFINITELY book the most
    expensive place" means do NOT book it)
  - negation or retraction ("actually never mind", "forget that",
    "no, don't")
  - past tense recap of something already done ("I already emailed
    her")
  - a report of someone else's action ("Sarah handled the booking")
  - pure hypothetical or counterfactual ("if I had time I would ...")
  For sarcasm that reveals a durable aversion, still emit
  store_as_memory with kind "aversion" and a verbatim evidence_quote.

STORE_AS_LATENT if it is a real but uncommitted signal:
  - genuine low commitment social hedging: "we should maybe grab
    dinner sometime", "we could look into that at some point", "let's
    do something one of these days"
  - tentative musing about a possible intention: "I was thinking of",
    "maybe I'll", "I might just", "I could probably"
  - a future intention with no specificity and no follow through cue
  Plural "we" idea floating with no time, place, or commitment is
  STORE_AS_LATENT, never COMMIT.

COMMIT only if it is a committed, specific, actionable task the
executor could carry out:
  - direct commands ("book Carbone for Thursday at 7")
  - committed first person tasks, even without the word please and
    even if not addressed to an assistant ("I need to email Sarah the
    deck before end of day", "I have to call the dentist and
    reschedule", "draft the Q3 report by Friday"). These ARE COMMIT.
    A first person "I need to / I have to / I've got to" with a
    concrete object and a near term frame is committed, not latent.
  The distinction from STORE_AS_LATENT is commitment plus a concrete
  object, NOT whether it was addressed to an assistant and NOT mere
  surface politeness.

When commitment is genuinely unclear, choose STORE_AS_LATENT, not
COMMIT. When tone contradicts the literal words, choose REFUSE. A wrong
COMMIT is the expensive error.
"""


@dataclass(frozen=True, slots=True)
class MemoryWriteSpec:
    kind: str
    key: str
    value: str
    evidence_quote: str

    def to_dict(self) -> dict:
        return {"kind": self.kind, "key": self.key, "value": self.value,
                "evidence_quote": self.evidence_quote}


@dataclass(frozen=True, slots=True)
class HedgeResult:
    decision: str  # COMMIT | STORE_AS_LATENT | REFUSE
    reason: str
    confidence: float
    store_as_memory: Optional[MemoryWriteSpec]


_VALID = {"COMMIT", "STORE_AS_LATENT", "REFUSE"}


def _safe_refuse(reason: str) -> HedgeResult:
    # Any failure fails safe to REFUSE: no action fires. Missing a task
    # is recoverable, a wrong action is not.
    return HedgeResult("REFUSE", reason, 0.0, None)


class Hedge:
    """Rewritten Stage 1.5. One model call, precision skewed."""

    def __init__(self, max_tokens: int = 400) -> None:
        self._max_tokens = max_tokens

    async def classify(
        self,
        utterance: str,
        context: Optional[str] = None,
        user_memory_summary: Optional[str] = None,
    ) -> HedgeResult:
        parts = []
        if context and context.strip():
            parts.append(f"PRIOR CONTEXT:\n{context.strip()}")
        if user_memory_summary and user_memory_summary.strip():
            parts.append(f"WEARER MEMORY:\n{user_memory_summary.strip()}")
        parts.append(f"UTTERANCE:\n{utterance.strip()}")
        parts.append("Return the JSON object now.")
        user = "\n\n".join(parts)

        res = await asyncio.to_thread(
            platform_adapter.model_call, _SYSTEM, user, self._max_tokens, 0.0, False
        )

        def _obj(text: str):
            a, b = text.find("{"), text.rfind("}")
            if a == -1 or b == -1 or b <= a:
                return None
            try:
                return json.loads(text[a : b + 1])
            except Exception:
                return None

        p = _obj(res.content) if res.ok else None
        if p is None:
            res2 = await asyncio.to_thread(
                platform_adapter.model_call,
                _SYSTEM,
                user + "\n\nReturn ONLY the single JSON object. Start with { end with }.",
                self._max_tokens, 0.0, False,
            )
            p = _obj(res2.content) if res2.ok else None
        if p is None:
            return _safe_refuse("hedge_unparseable_after_reparse")

        decision = p.get("decision")
        if decision not in _VALID:
            return _safe_refuse(f"hedge_invalid_decision:{decision!r}")

        mem = p.get("store_as_memory")
        spec: Optional[MemoryWriteSpec] = None
        if isinstance(mem, dict):
            ev = str(mem.get("evidence_quote", ""))
            # reject a hallucinated quote: must be a verbatim substring
            if ev and ev in utterance:
                spec = MemoryWriteSpec(
                    kind=str(mem.get("kind", "")),
                    key=str(mem.get("key", "")),
                    value=str(mem.get("value", "")),
                    evidence_quote=ev,
                )
        return HedgeResult(
            decision=decision,
            reason=str(p.get("reason", ""))[:240],
            confidence=float(p.get("confidence", 0.5) or 0.0),
            store_as_memory=spec,
        )
