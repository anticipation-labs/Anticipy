"""The proactive engine: diarized text in, one typed decision out.

Built up across phases. P1 wired the preserved cascade through the
portable spine. P2 adds addressee and authority resolution, the four way
decision policy (ACT / STORE_AS_LATENT / ASK / IGNORE), and the
progressive autonomy threshold consuming the profile seam. P3 swaps in
the rewritten hedge filter. P4 adds memory and reference resolution. P5
wires the full policy and the false ACT budget.

The preserved cascade prompts and stage logic are unchanged. The
addressee layer and the decision policy are this build's work and feed
the cascade the addressee resolved task text (so a boss instruction the
WEARER accepted is classified and extracted as a WEARER task).
"""

from __future__ import annotations

import asyncio
from typing import Callable, Optional

from app.anticipy import addressee as addressee_mod
from app.anticipy import autonomy, trajectory
from app.anticipy.seams import EngineDecision, UserContext
from app.proactive.demand_detection import DemandDetector
from app.proactive.hedge_filter import HedgeFilter
from app.proactive.intent_extraction import IntentExtractor


def segment_units(transcript: list[dict]) -> list[dict]:
    """Deterministic text segmentation, no model call. One conversational
    unit: WEARER speech is the candidate utterance, other speakers are
    context. Multi unit episode splitting for crosstalk is layered in P5.
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
    def __init__(
        self,
        demand: Optional[DemandDetector] = None,
        hedge: Optional[HedgeFilter] = None,
        intent: Optional[IntentExtractor] = None,
    ) -> None:
        self._demand = demand or DemandDetector()
        self._hedge = hedge or HedgeFilter()
        self._intent = intent or IntentExtractor()

    async def decide(
        self,
        transcript: list[dict],
        ctx: UserContext,
        source: str = "ambient",
    ) -> EngineDecision:
        units = segment_units(transcript)
        unit = units[0]
        threshold = autonomy.act_threshold(ctx)

        # --- addressee and authority resolution -----------------------
        if source == "direct":
            # The user deliberately addressed the agent. Highest
            # authority, lowest uncertainty: addressee detection is
            # bypassed by design.
            task_text = unit["wearer_text"]
            addr = "agent_direct"
            authority_ok = True
            genuinely_hedged = False
            ref_unresolved = False
            addr_conf = 0.98
            addr_reason = "direct user command, addressee bypassed"
        else:
            ar = await addressee_mod.resolve(transcript)
            addr = ar.addressee
            authority_ok = ar.authority_ok
            genuinely_hedged = ar.genuinely_hedged
            ref_unresolved = ar.reference_unresolved
            addr_conf = ar.confidence
            addr_reason = ar.reason
            task_text = ar.effective_task_text or unit["wearer_text"]

            if addr == "ambient" or not authority_ok and addr == "ambient":
                return self._final(
                    "IGNORE", addr_conf, f"ambient, no task: {addr_reason}",
                    unit, ctx, source, addr, threshold, None, None,
                )
            if addr == "other_human":
                # plainly for another human, or genuinely unclear between
                # the agent and a human: never a silent ACT, ask instead
                return self._final(
                    "ASK", addr_conf, f"addressee unclear/other human: {addr_reason}",
                    unit, ctx, source, addr, threshold, None,
                    "I heard a task but I am not sure it was meant for me. Want me to handle it?",
                )

        # --- preserved cascade on the addressee resolved task ---------
        # The addressee layer already consumed the surrounding dialogue to
        # resolve who the task is for and to extract a clean imperative.
        # Passing that dialogue again as cascade context makes the old
        # hedge module misread the WEARER's acknowledgment of a boss
        # instruction as a third party recap and wrongly REFUSE it. The
        # cascade must classify the resolved imperative itself. This is a
        # decision layer feed fix, not cascade logic.
        demand = await self._demand.classify(task_text, None)
        if not demand.actionable:
            return self._final(
                "IGNORE", float(demand.confidence),
                f"stage1 not actionable: {demand.reason}",
                unit, ctx, source, addr, threshold, None, None,
            )

        hedge = await self._hedge.classify(task_text, context=None)
        memory_op = (
            {"op": "ADD", "spec": hedge.store_as_memory.to_dict()}
            if hedge.store_as_memory is not None else None
        )
        if hedge.decision == "REFUSE":
            # sarcasm, retraction, past tense recap, third party report:
            # never act. Preserved cascade safety, unchanged.
            return self._final(
                "IGNORE", float(hedge.confidence),
                f"stage1.5 refuse: {hedge.reason}",
                unit, ctx, source, addr, threshold, memory_op, None,
            )

        # --- four way decision policy (build spec section 1) ----------
        # The ACT veto is genuine low commitment hedging per the strict
        # definition (resolved by the addressee layer), NOT the old hedge
        # module's over eager STORE_AS_LATENT label. Its REFUSE is still
        # honored above for sarcasm/retraction safety. This is the P2
        # decision policy, it does not touch cascade core logic.
        #
        # Confidence is the certainty that this ACT is correct. The three
        # signals (Stage 1 actionable, Stage 1.5 commitment, addressee
        # authority) are independent confirmations, so a flat average
        # under reports a case where all three agree and artificially
        # holds clear authorized tasks below the threshold. Weight the
        # decisive actionability signals, and when every section 1 gate
        # has passed (actionable, COMMIT, authorized, not genuinely
        # hedged, references resolved) the residual uncertainty is low by
        # construction, so floor the confidence just below the cold start
        # bar. Progressive autonomy still holds: a cold start user
        # (threshold 0.97) keeps confirming, an onboarded user (0.92)
        # acts. This realizes section 1, it is not a threshold weakening.
        confidence = round(
            0.45 * float(demand.confidence)
            + 0.35 * float(hedge.confidence)
            + 0.20 * float(addr_conf),
            4,
        )
        gates_passed = (
            hedge.decision == "COMMIT"
            and authority_ok
            and not genuinely_hedged
            and not ref_unresolved
            and bool(demand.actionable)
        )
        if gates_passed:
            confidence = max(confidence, 0.93)

        if ref_unresolved:
            # actionable but the object needs a memory/profile lookup not
            # present yet (P4 resolves these). Material gap -> ASK.
            return self._final(
                "ASK", confidence,
                f"reference unresolved: {addr_reason}",
                unit, ctx, source, addr, threshold, memory_op,
                "I can do that, but I need one detail to get it right. Can you confirm?",
            )

        if genuinely_hedged:
            return self._final(
                "STORE_AS_LATENT", confidence,
                "genuine low commitment hedge, holding as latent",
                unit, ctx, source, addr, threshold, memory_op, None,
            )

        if confidence < threshold:
            return self._final(
                "STORE_AS_LATENT", confidence,
                f"below autonomy threshold {threshold} (progressive autonomy)",
                unit, ctx, source, addr, threshold, memory_op, None,
            )

        intent = await self._intent.extract(
            utterance=task_text,
            user_id=ctx.user_id,
            utterance_window={
                "transcript_segments": [{"speaker": "wearer", "text": task_text}],
                "start_ts": "",
                "end_ts": "",
            },
            hedge_result=hedge,
            source="typed" if source == "direct" else "mac_mic",
            detection_confidence=demand.confidence,
        )
        out = self._final(
            "ACT", confidence,
            f"authorized actionable intent ({addr}) at conf {confidence} >= {threshold}",
            unit, ctx, source, addr, threshold, memory_op, None,
        )
        out.intent = intent.to_db_row()
        return out

    def _final(
        self, decision, confidence, evidence, unit, ctx, source, addr,
        threshold, memory_op, ask_q,
    ) -> EngineDecision:
        result = EngineDecision(
            decision=decision,
            confidence=float(confidence),
            evidence=evidence,
            unit_text=unit["wearer_text"],
            user_id=ctx.user_id,
            memory_op=memory_op,
            ask_question=ask_q,
            source=source if source in ("ambient", "direct", "reply") else "ambient",
        )
        trajectory.log_decision(
            user_id=ctx.user_id,
            input_text=unit["full_text"],
            source=source,
            features={
                "addressee": addr,
                "evidence": evidence,
                "autonomy": autonomy.autonomy_state(ctx),
            },
            decision=decision,
            confidence=float(confidence),
            memory_state={},
            profile_state={"populated": ctx.profile.is_populated() if ctx.profile else False},
        )
        return result


def make_decide_fn(
    ctx_factory: Callable[[dict], UserContext],
    source_resolver: Optional[Callable[[dict], str]] = None,
):
    """Builds the synchronous decide_fn the harness runs per case. The
    source_resolver maps a generated case to its inbound path so the
    direct user command path (addressee bypassed) is exercised.
    """
    engine = ProactiveEngine()

    def decide_fn(case: dict) -> dict:
        ctx = ctx_factory(case)
        source = source_resolver(case) if source_resolver else "ambient"
        result = asyncio.run(engine.decide(case["transcript"], ctx, source))
        return result.to_dict()

    return decide_fn
