"""The proactive engine: diarized text in, one typed decision out.

This module is built up across phases. P1 wires the preserved cascade
through the portable spine and proves it still performs. P2 adds
addressee and authority resolution and the four way decision policy with
the progressive autonomy threshold. P3 swaps in the rewritten hedge
filter. P4 adds memory and reference resolution. P5 wires the full
decision policy and the false ACT budget.

The cascade prompts and stage logic are preserved unchanged. Only the
wiring (llm_adapter, which now calls platform_adapter) and the decision
layer around the cascade are this build's work.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from app.anticipy import trajectory
from app.anticipy.seams import EngineDecision, UserContext
from app.proactive.demand_detection import DemandDetector
from app.proactive.hedge_filter import HedgeFilter
from app.proactive.intent_extraction import IntentExtractor


def segment_units(transcript: list[dict]) -> list[dict]:
    """Deterministic text segmentation, no model call. Groups a diarized
    transcript into one conversational unit: the WEARER's speech is the
    candidate utterance, every other speaker's speech is prior context.

    P1 and P2 single intent categories are one unit per transcript.
    Multi unit episode splitting (for crosstalk) is layered in P5 without
    changing this signature.
    """
    wearer_lines = [ln["text"] for ln in transcript if ln.get("speaker_id") == "WEARER"]
    other_lines = [
        f"{ln.get('speaker_id', 'S?')}: {ln['text']}"
        for ln in transcript
        if ln.get("speaker_id") != "WEARER"
    ]
    return [
        {
            "wearer_text": " ".join(wearer_lines).strip(),
            "context": "\n".join(other_lines).strip(),
            "full_text": " ".join(ln["text"] for ln in transcript).strip(),
        }
    ]


class ProactiveEngine:
    """Stage 1 demand, Stage 1.5 hedge, Stage 2 intent, then the decision
    policy. P1 maps the cascade to the four way decision minimally
    (ACT / STORE_AS_LATENT / IGNORE); ASK and authority and memory enter
    in later phases.
    """

    def __init__(
        self,
        demand: Optional[DemandDetector] = None,
        hedge: Optional[HedgeFilter] = None,
        intent: Optional[IntentExtractor] = None,
    ) -> None:
        self._demand = demand or DemandDetector()
        self._hedge = hedge or HedgeFilter()
        self._intent = intent or IntentExtractor()

    async def _decide_unit(self, unit: dict, ctx: UserContext) -> EngineDecision:
        wearer_text = unit["wearer_text"]
        context = unit["context"] or None

        demand = await self._demand.classify(wearer_text, context)
        if not demand.actionable:
            return EngineDecision(
                decision="IGNORE",
                confidence=float(demand.confidence),
                evidence=f"stage1 not actionable: {demand.reason}",
                unit_text=wearer_text,
                user_id=ctx.user_id,
            )

        hedge = await self._hedge.classify(wearer_text, context=context)
        if hedge.decision == "REFUSE":
            return EngineDecision(
                decision="IGNORE",
                confidence=float(hedge.confidence),
                evidence=f"stage1.5 refuse: {hedge.reason}",
                unit_text=wearer_text,
                user_id=ctx.user_id,
                memory_op=(
                    {"op": "ADD", "spec": hedge.store_as_memory.to_dict()}
                    if hedge.store_as_memory is not None
                    else None
                ),
            )

        if hedge.decision == "STORE_AS_LATENT":
            return EngineDecision(
                decision="STORE_AS_LATENT",
                confidence=float(hedge.confidence),
                evidence=f"stage1.5 latent: {hedge.reason}",
                unit_text=wearer_text,
                user_id=ctx.user_id,
            )

        # hedge.decision == COMMIT: extract the typed intent and ACT.
        intent = await self._intent.extract(
            utterance=wearer_text,
            user_id=ctx.user_id,
            utterance_window={
                "transcript_segments": [{"speaker": "wearer", "text": wearer_text}],
                "start_ts": "",
                "end_ts": "",
            },
            hedge_result=hedge,
            source="typed",
            detection_confidence=demand.confidence,
        )
        confidence = round(0.5 * float(demand.confidence) + 0.5 * float(hedge.confidence), 4)
        return EngineDecision(
            decision="ACT",
            confidence=confidence,
            evidence=f"stage1.5 commit: {hedge.reason}",
            unit_text=wearer_text,
            user_id=ctx.user_id,
            intent=intent.to_db_row(),
        )

    async def decide(self, transcript: list[dict], ctx: UserContext) -> EngineDecision:
        units = segment_units(transcript)
        # P1: one unit. Later phases pick the salient unit across many.
        result = await self._decide_unit(units[0], ctx)
        trajectory.log_decision(
            user_id=ctx.user_id,
            input_text=units[0]["full_text"],
            source="ambient",
            features={
                "cascade_evidence": result.evidence,
                "has_intent": result.intent is not None,
            },
            decision=result.decision,
            confidence=result.confidence,
            memory_state={},
            profile_state={"populated": ctx.profile.is_populated() if ctx.profile else False},
        )
        return result


def make_decide_fn(ctx_factory):
    """Builds the synchronous decide_fn the harness runs per case. Each
    case is graded by comparing this typed decision to the label the
    taxonomy stamped at generation time.
    """
    engine = ProactiveEngine()

    def decide_fn(case: dict) -> dict:
        ctx = ctx_factory(case)
        result = asyncio.run(engine.decide(case["transcript"], ctx))
        return result.to_dict()

    return decide_fn
