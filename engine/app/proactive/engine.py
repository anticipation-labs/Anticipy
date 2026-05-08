"""
Top-level facade for the proactive engine.

Wires the five-layer AI cascade:

  L1 SalienceClassifier  — every chunk
  L2 Interpreter         — extract on salient chunks
  L3 ReversibilityClassifier — per intent
  L4 UrgencyScorer       — per intent
  L5 DonnaPass           — per intent
  → Decider _route()     — deterministic combiner over AI outputs

Three public entry points:

  await engine.on_transcript_chunk(chunk)
  await engine.on_confirmation(decision_id, "yes" | "no")
  engine.set_notes_mode(enabled=True)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol

from .context import ContextBuffer, EmbedFn
from .decider import Decider
from .dispatcher import Dispatcher
from .donna import DonnaPass
from .interpreter import Interpreter, SalienceClassifier
from .notifier import ContactBook, DeliveryRoutes, NoticedFeed, Notifier
from .notes import NotesRecorder, NotesStore
from .reversibility import ReversibilityClassifier
from .speaker_id import SpeakerIDClassifier
from .types import (
    Decision,
    DecisionKind,
    EngineStatusEvent,
    TranscriptChunk,
)
from .urgency import UrgencyScorer

logger = logging.getLogger("engine.proactive.engine")


# Confidence floor for L0 speaker-ID drops. Below this, the engine keeps
# the chunk (fail-open). At/above this, an is_wearer=False verdict drops
# the chunk before L1. 0.6 is the spec-mandated threshold.
SPEAKER_ID_DROP_CONFIDENCE = 0.6


LlmCall = Callable[[str, str], Awaitable[str]]


class Executor(Protocol):
    async def execute(self, decision: Decision) -> EngineStatusEvent: ...


@dataclass
class _HarshGuardVerdict:
    """Result from the dedicated harsh-dictation guard."""
    is_harsh: bool
    named_person: str = ""
    refusal_reason: str = ""


@dataclass
class _LoggingExecutor:
    log: list[Decision]

    async def execute(self, decision: Decision) -> EngineStatusEvent:
        self.log.append(decision)
        return EngineStatusEvent(
            decision_id=decision.decision_id,
            stage="completed",
            message=decision.completion_message or "Done.",
        )


class StatusSink(Protocol):
    async def emit(self, event: EngineStatusEvent) -> None: ...


@dataclass
class _MemoryStatusSink:
    events: list[EngineStatusEvent]

    async def emit(self, event: EngineStatusEvent) -> None:
        self.events.append(event)


class ProactiveEngine:
    """The single object the rest of the codebase talks to.

    `llm_call` is the cheap-model call used by all five layers in the
    reference implementation. In production you'll inject a different
    callable per layer (Layer 1 should be the *cheapest* — Groq Scout or
    on-device 1-3B; Layers 2-5 can be slightly bigger like Haiku 4.5).
    """

    def __init__(
        self,
        user_id: str,
        llm_call: LlmCall,
        *,
        salience_llm_call: LlmCall | None = None,
        executor: Executor | None = None,
        status_sink: StatusSink | None = None,
        contacts: ContactBook | None = None,
        delivery_routes: DeliveryRoutes | None = None,
        noticed_feed: NoticedFeed | None = None,
        notes_store: NotesStore | None = None,
        embed_fn: EmbedFn | None = None,
        settle_chunks: int = 999,  # effectively wait-for-flush; phone calls flush_pending on silence
    ) -> None:
        self.user_id = user_id
        self._executor = executor or _LoggingExecutor(log=[])
        self._status = status_sink or _MemoryStatusSink(events=[])

        self._context = ContextBuffer(user_id=user_id, embed_fn=embed_fn)

        # Layer 1 (salience) can be wired to an even cheaper / on-device
        # model than the rest of the cascade. Defaults to the same llm_call.
        l1_call = salience_llm_call or llm_call
        self._salience = SalienceClassifier(llm_call=l1_call)

        # Layer 0 (speaker-ID): runs before L1. Drops chunks that are
        # confidently NOT from the wearer. Uses the same cheap-model call
        # as L1 — both are per-chunk hot-path filters.
        self._speaker_id = SpeakerIDClassifier(llm_call=l1_call)

        # Layer 2 wraps Layer 1 + does the extraction call.
        self._interpreter = Interpreter(
            llm_call=llm_call,
            salience_classifier=self._salience,
        )

        # Layers 3, 4, 5: separate AI calls, run in parallel inside Decider.
        self._reversibility = ReversibilityClassifier(llm_call=llm_call)
        self._urgency = UrgencyScorer(llm_call=llm_call)
        self._donna = DonnaPass(llm_call=llm_call)

        self._decider = Decider(
            reversibility_classifier=self._reversibility,
            urgency_scorer=self._urgency,
            donna_pass=self._donna,
        )

        self._notifier = Notifier(
            routes=delivery_routes,
            contacts=contacts,
            feed=noticed_feed,
        )
        self._notes = NotesRecorder(llm_call=llm_call, store=notes_store)

        # Dispatch-time AI dedup gate. Uses the cheap-model channel since this
        # is a per-dispatch comparison, not a per-chunk hot path. Fail-open on
        # error / timeout — better to occasionally double-fire than silently
        # drop a real new intent.
        self._dispatcher = Dispatcher(llm_call=l1_call)

        self._pending_confirmations: dict[str, asyncio.Future[bool]] = {}

        # Settling buffer: extracted intents wait `settle_chunks` more chunks
        # before dispatch, then get a model-driven re-validation pass against the
        # latest full context. If the user retracted/contradicted, the decision
        # is dropped instead of executed. This is the architectural fix for
        # cross-utterance retraction — no rules, no keyword matching, just a
        # second AI pass that sees the future the first pass couldn't.
        self._settle_chunks = max(0, int(settle_chunks))
        self._pending_dispatches: list[dict] = []  # {decision, settle_after_chunk_idx}
        self._chunks_seen = 0
        self._llm_call = llm_call  # used by the re-validator

    # --- Public entry points ---------------------------------------------------

    async def on_transcript_chunk(self, chunk: TranscriptChunk) -> list[Decision]:
        """Phone calls this for every diarized user-voice chunk.

        Returns the list of decisions DISPATCHED on this chunk — i.e., decisions
        that have settled and been re-validated against the latest context.
        Decisions extracted on this chunk that are still in the settling
        buffer are not returned until they settle. Mostly used by tests / the
        eval harness.
        """
        if chunk.user_id != self.user_id:
            return []

        self._chunks_seen += 1

        # Always update buffer + notes (cheap, always-on).
        await self._context.append(chunk)
        await self._notes.record(chunk)

        # Layer 0: speaker-ID (AI). Decides whether this chunk is from the
        # WEARER or someone else in the room. If the model is confident the
        # speaker is not the wearer, drop the chunk before L1 sees it. The
        # chunk stays in the context buffer (so wearer responses-to-others
        # remain grounded) but is flagged so downstream layers don't re-read
        # its text as wearer intent.
        speaker = await self._speaker_id.classify(chunk, self._context)
        chunk.is_wearer = speaker.is_wearer
        if not speaker.is_wearer and speaker.confidence >= SPEAKER_ID_DROP_CONFIDENCE:
            logger.info("speaker_id_dropped", extra={
                "chunk_id": chunk.chunk_id,
                "confidence": speaker.confidence,
                "reasoning": speaker.reasoning,
                "diarization_hint": chunk.diarization_hint,
            })
            return []

        # Layer 1: salience (AI). Returns a verdict; should_wake bundles it
        # with the per-session throttle.
        recent_for_salience = await self._context.recent_text(seconds=120.0)
        wake, salience = await self._interpreter.should_wake(chunk, recent_for_salience)
        if wake:
            # Pull related memory before extraction.
            memories = await self._context.retrieve(chunk.text, k=3)

            # Layer 2: extraction (AI). Returns 0..N intents, free-form verbs.
            extracted = await self._interpreter.extract(
                triggering_chunk=chunk,
                context=self._context,
                related_memories=memories,
            )

            for ex in extracted:
                # Layers 3+4+5 (reversibility / urgency / donna) run inside the
                # Decider, in parallel via asyncio.gather.
                decision = await self._decider.decide(ex, self._context)
                # Supersede pending intents that the new one absorbs. Two
                # rules, both designed for natural detail-accumulation across
                # chunks — neither is keyword-based:
                #   1) Same action_verb → new wins (handles "buy_concert_tickets"
                #      restated with more slot fills).
                #   2) Same primary subject parameter (recipient / person /
                #      target / item) → new wins (handles re-extracting Sarah's
                #      birthday gift with a slightly different verb the model
                #      invented the second time).
                def _primary_subject(decision_) -> str | None:
                    p = decision_.intent.parameters or {}
                    for key in ("recipient", "person", "target", "contact",
                                "subject_person", "for", "to"):
                        v = p.get(key)
                        if isinstance(v, str) and v.strip():
                            return v.strip().lower()
                    return None
                new_subject = _primary_subject(decision)
                superseded_idxs = []
                for i, p in enumerate(self._pending_dispatches):
                    pending_dec = p["decision"]
                    if pending_dec.intent.action_verb == decision.intent.action_verb:
                        superseded_idxs.append(i)
                        continue
                    if new_subject is not None:
                        old_subject = _primary_subject(pending_dec)
                        if old_subject == new_subject:
                            superseded_idxs.append(i)
                for idx in reversed(superseded_idxs):
                    self._pending_dispatches.pop(idx)
                self._pending_dispatches.append({
                    "decision": decision,
                    "settle_after_chunk_idx": self._chunks_seen + self._settle_chunks,
                })
        else:
            logger.debug("salience_skip", extra={
                "chunk_id": chunk.chunk_id,
                "actionable": salience.actionable,
                "salience_confidence": salience.confidence,
            })

        # Process any pending dispatches that have settled long enough.
        return await self._process_settled(force=False)

    async def _process_settled(self, force: bool = False) -> list[Decision]:
        """Move settled (or all, if forced) decisions through revalidation,
        then dispatch the survivors. Returns the dispatched list.

        Three checks at settling time, all AI calls (no rules):
          0) "Consolidate" — collapse related pending intents into the
             user's actual current intent (e.g. draft_email + body-dictation
             intents that the interpreter split apart get merged so Donna
             evaluates the WHOLE composition, not the benign half)
          1) "Still wanted?" — did the user retract or supersede in later chunks
          2) "Donna re-check" — does the harsh-content / regret signal that may
             have arrived AFTER extraction now warrant refusal?
        Either of (1) or (2) returning false drops the decision before dispatch.
        """
        # When 2+ intents are pending and at least one is settling, run a
        # consolidation pass first. The LLM merges or drops superseded
        # candidates so we don't dispatch an early-extracted half-intent
        # whose later chunks supplied the rest.
        if len(self._pending_dispatches) >= 2:
            any_settled = force or any(
                self._chunks_seen >= p["settle_after_chunk_idx"]
                for p in self._pending_dispatches
            )
            if any_settled:
                await self._consolidate_pending()

        out: list[Decision] = []
        still_pending: list[dict] = []
        for p in self._pending_dispatches:
            if force or self._chunks_seen >= p["settle_after_chunk_idx"]:
                decision: Decision = p["decision"]
                still_wanted = await self._revalidate(decision)
                if not still_wanted:
                    logger.info("decision_revalidate_dropped", extra={
                        "decision_id": decision.decision_id,
                        "verb": decision.intent.action_verb,
                        "reason": "still_wanted=false",
                    })
                    continue

                # Dedicated harsh-content guard. A single-purpose AI call
                # asking ONLY: "is the user dictating harsh content about a
                # named person right now?" If yes, force a refusal. This
                # exists because Gemini sometimes ignores the harsh-content
                # rule in the multi-purpose Donna prompt — a dedicated
                # focused prompt is more reliable.
                harsh = await self._harsh_dictation_guard(decision)
                if harsh.is_harsh:
                    refused = Decision.new(
                        intent=decision.intent,
                        kind=DecisionKind.REFUSE,
                        confidence=decision.confidence,
                        reversibility=decision.reversibility,
                        urgency=decision.urgency,
                        refusal_reason=harsh.refusal_reason,
                    )
                    out.append(refused)
                    asyncio.create_task(self._handle_decision(refused))
                    logger.info("decision_harsh_dictation_refused", extra={
                        "decision_id": decision.decision_id,
                        "named_person": harsh.named_person,
                    })
                    continue

                # Re-run Donna with the now-larger context. Captures cases
                # where the body of a message being drafted only became harsh
                # in later chunks (post-initial extraction).
                donna_now = await self._donna.evaluate(decision.intent, self._context)
                if donna_now.should_refuse:
                    # Replace with a refusal decision in-place. Keep the same
                    # decision_id so any pending downstream state stays coherent.
                    refused = Decision.new(
                        intent=decision.intent,
                        kind=DecisionKind.REFUSE,
                        confidence=decision.confidence,
                        reversibility=decision.reversibility,
                        urgency=decision.urgency,
                        refusal_reason=(donna_now.reason or decision.refusal_reason
                                        or "I'd rather not do this one.")
                                       + ((" " + donna_now.rephrase) if donna_now.rephrase else ""),
                    )
                    out.append(refused)
                    asyncio.create_task(self._handle_decision(refused))
                    logger.info("decision_donna_recheck_refused", extra={
                        "decision_id": decision.decision_id,
                        "reason": donna_now.reason,
                    })
                    continue

                # Dispatch-time AI dedup gate. The cascade extracted this as
                # a fresh intent, but the user may have already heard about
                # the same goal earlier in the conversation. Skip silently if
                # the model recognizes a prior dispatch that subsumes this one.
                # REFUSE decisions bypass — refusals are safety, not noise.
                admit_verdict = await self._dispatcher.admit(decision)
                if not admit_verdict.admit:
                    logger.info("decision_dispatch_dedup_dropped", extra={
                        "decision_id": decision.decision_id,
                        "verb": decision.intent.action_verb,
                        "duplicate_of": admit_verdict.duplicate_of,
                        "reason": admit_verdict.reasoning,
                    })
                    continue

                self._dispatcher.record(decision)
                out.append(decision)
                asyncio.create_task(self._handle_decision(decision))
            else:
                still_pending.append(p)
        self._pending_dispatches = still_pending
        return out

    async def flush_pending(self) -> list[Decision]:
        """Force-settle and dispatch all remaining buffered decisions.
        Used at end-of-session by the WebSocket handler and the eval harness.
        Runs a consolidation pass first so multi-turn buildups collapse to
        their final resolved action only."""
        await self._consolidate_pending()
        return await self._process_settled(force=True)

    async def _harsh_dictation_guard(self, decision: Decision) -> "_HarshGuardVerdict":
        """Single-purpose AI call: is the user dictating harsh content about a
        named person right now? Returns is_harsh=True if so. We use this as a
        dedicated check because the multi-purpose Donna prompt sometimes lets
        harsh-email drafts through. A focused prompt is more reliable than a
        sub-rule of a larger one.

        NOT a keyword scanner — the LLM reads the recent transcript and the
        intent and decides. No keyword tables.
        """
        if self._llm_call is None:
            return _HarshGuardVerdict(is_harsh=False)
        try:
            recent = await self._context.recent_text(seconds=300.0)
        except Exception:
            recent = ""

        sys = (
            "You are the harsh-dictation guard. ONE question: is the user "
            "currently dictating an email/message/review/post/document body "
            "that contains contemptuous, hostile, dismissive, demeaning, "
            "mocking, or attacking language directed at a NAMED PERSON?\n\n"
            "Output STRICT JSON only:\n"
            '{ "is_harsh": <true|false>, "named_person": "<name or empty>", '
            '"refusal_reason": "<one sentence in the agent\'s voice>", '
            '"rephrase": "<professional alternative or empty>" }\n\n'
            "Return is_harsh=TRUE when ANY of these are present in the "
            "recent transcript:\n"
            "  - Insults or mocking adjectives aimed at a person: 'incompetent', "
            "'a joke', 'completely unsuitable', 'irrelevant', 'a waste of time', "
            "'disaster', 'spammed', 'ridiculous', 'wow [sarcastic]', 'idiot', "
            "'useless'.\n"
            "  - Contemptuous tone: 'don't even get me started', 'didn't even "
            "bother', 'past the initial screening', 'looking for actual talent', "
            "any sneering or dismissive framing.\n"
            "  - Direct attacks on the person rather than critique of work: "
            "'their cover letter was a joke' (attack), vs 'the cover letter "
            "doesn't address the role' (critique). Attacks trigger refuse.\n"
            "  - Note: 'completely unsuitable' / 'irrelevant' targeting a "
            "PERSON is an attack. Same words targeting a PROCESS or DOCUMENT "
            "may not be.\n\n"
            "Return is_harsh=FALSE when:\n"
            "  - The user is calmly drafting professional but firm content "
            "(e.g. 'we have decided to move forward with other candidates') "
            "without attacks.\n"
            "  - The user is drafting praise, approval, neutral notification.\n"
            "  - There is no draft / message / post / review composition in "
            "the recent transcript at all.\n\n"
            "When in doubt, return is_harsh=true. False positives let the "
            "user refine the message; false negatives ship a regret."
        )
        user_prompt = (
            f"Recent transcript (oldest first):\n\"\"\"\n{recent or '(empty)'}\n\"\"\"\n\n"
            f"Current intent the engine is about to dispatch:\n"
            f"  text: {decision.intent.text}\n"
            f"  action_verb: {decision.intent.action_verb}\n"
            f"  parameters: {decision.intent.parameters}\n\n"
            f"Output the JSON."
        )
        try:
            raw = await asyncio.wait_for(self._llm_call(sys, user_prompt), timeout=10.0)
        except (asyncio.TimeoutError, Exception):
            return _HarshGuardVerdict(is_harsh=False)
        try:
            import json as _json
            data = _json.loads((raw or "").strip() or "{}")
        except (ValueError, TypeError):
            return _HarshGuardVerdict(is_harsh=False)
        if not isinstance(data, dict):
            return _HarshGuardVerdict(is_harsh=False)
        is_harsh = bool(data.get("is_harsh", False))
        if not is_harsh:
            return _HarshGuardVerdict(is_harsh=False)
        named = str(data.get("named_person") or "").strip()
        reason = str(data.get("refusal_reason") or "").strip() or "That message reads as harsher than you probably want."
        rephrase = str(data.get("rephrase") or "").strip()
        if rephrase:
            reason = reason + " " + rephrase
        return _HarshGuardVerdict(
            is_harsh=True,
            named_person=named,
            refusal_reason=reason,
        )

    async def _consolidate_pending(self) -> None:
        """When multiple pending intents exist for the same session, ask the
        model which represent the user's CURRENT actual intent and which
        were superseded by later, more specific actions. Drops the superseded
        ones from the pending buffer.

        This is the AI-driven answer to multi-turn buildup: the user states
        a goal ("send a package today"), then explores ("post office? FedEx?"),
        then resolves ("nearest FedEx drop-off"). Only the resolved action
        should fire — the earlier vaguer goal was a step toward it, not its
        own separate intent.
        """
        if len(self._pending_dispatches) < 2:
            return
        if self._llm_call is None:
            return
        try:
            recent = await self._context.recent_text(seconds=600.0)
        except Exception:
            recent = ""
        intents_payload = []
        for i, p in enumerate(self._pending_dispatches):
            d = p["decision"]
            intents_payload.append({
                "id": i,
                "verb": d.intent.action_verb,
                "text": d.intent.text,
                "parameters": d.intent.parameters,
            })
        sys = (
            "You are consolidating multiple candidate intents that were "
            "extracted from a single user's recent conversation, deciding "
            "which represent the user's CURRENT actual intent at the end of "
            "the conversation, and which were superseded by later, more "
            "specific actions OR are redundant meta-recitals of sibling intents.\n\n"
            "Output STRICT JSON only:\n"
            '{ "keep": [<id int>, ...], "drop_reasoning": "<one sentence>" }\n\n'
            "Drop intents whose goal was superseded by a more specific "
            "intent that resolves the same goal (e.g., \"send a package\" "
            "is superseded by \"find nearest FedEx drop-off\" because the "
            "second IS the user's chosen way to do the first). Drop intents "
            "the user retracted or contradicted later. Keep intents that "
            "stand on their own — distinct goals the user resolved.\n"
            "Drop META-RECITALS: a candidate intent like "
            "\"remember to do these things: dentist, email Mark, order cat food\" "
            "or \"prioritize my tasks\" or \"organize my day\" — if its content "
            "ENUMERATES sibling intents already in the candidate list (or already "
            "dispatched). These are the user reciting their to-do list aloud, not "
            "asking for a separate to-do-list notification. Drop the meta-recital, "
            "keep the individual intents.\n"
            "Drop SAME-GOAL information sub-lookups: if one candidate is "
            "\"find recipe for soup from The Savory Spoon\" and another is "
            "\"look up The Savory Spoon website\" — the second is HOW the user "
            "would do the first. Drop the sub-lookup, keep the original goal.\n"
            "Bias: when in doubt about whether a vaguer goal was superseded "
            "by a specific resolution, drop the vaguer one. Specific wins."
        )
        import json as _json
        user_prompt = (
            f"Recent transcript (oldest first):\n\"\"\"\n{recent or '(empty)'}\n\"\"\"\n\n"
            f"Candidate intents:\n{_json.dumps(intents_payload, indent=2)}\n\n"
            f"Output the JSON deciding which ids to keep."
        )
        try:
            raw = await asyncio.wait_for(self._llm_call(sys, user_prompt), timeout=12.0)
        except (asyncio.TimeoutError, Exception):
            logger.warning("consolidate_failed", extra={"n_pending": len(self._pending_dispatches)})
            return  # fail-open: keep all pending
        try:
            data = _json.loads((raw or "").strip() or "{}")
        except (ValueError, TypeError):
            return
        if not isinstance(data, dict):
            return
        keep_ids = data.get("keep")
        if not isinstance(keep_ids, list):
            return
        keep_set = {int(i) for i in keep_ids if isinstance(i, (int, float, str)) and str(i).isdigit()}
        if not keep_set:
            # Defensive: if model returned empty keep, do nothing — don't drop everything.
            return
        new_pending = [p for i, p in enumerate(self._pending_dispatches) if i in keep_set]
        if len(new_pending) < len(self._pending_dispatches):
            logger.info("consolidate_dropped", extra={
                "before": len(self._pending_dispatches),
                "after": len(new_pending),
                "reason": data.get("drop_reasoning", ""),
            })
        self._pending_dispatches = new_pending

    async def _revalidate(self, decision: Decision) -> bool:
        """Ask the model whether this decision is still wanted given the LATEST
        context (which now includes whatever came after the chunk that produced
        this decision). Returns True if still wanted, False if retracted /
        contradicted / superseded.

        This is the architectural answer to multi-utterance retractions: no
        keyword list, no rule engine — just a second AI pass with the benefit
        of hindsight that the first pass didn't have.
        """
        if self._llm_call is None:
            return True
        try:
            recent = await self._context.recent_text(seconds=300.0)
        except Exception:
            recent = ""
        sys = (
            "You re-validate a candidate intent that was extracted earlier in a "
            "conversation. The user has spoken more since then. Decide whether the "
            "user STILL wants this action, given their LATEST POSITION in the "
            "conversation. Output STRICT JSON only:\n"
            '{ "still_wanted": <true|false>, "reasoning": "<one sentence>" }\n\n'
            "Mark still_wanted=FALSE in any of these cases:\n"
            "  - The user said 'never mind', 'actually no', 'forget it', "
            "    'scratch that', 'on second thought no', 'I changed my mind'.\n"
            "  - The user said something like 'no point', 'not even sure I'm going', "
            "    'maybe later', 'I'll think about it', 'I'm not ready' — this is a "
            "    soft retraction; honor it.\n"
            "  - The user later contradicted the intent (e.g. originally 'cancel my "
            "    dentist' then 'actually keep the appointment').\n"
            "  - A more specific intent supersedes this one (e.g. 'send a package' "
            "    superseded by 'go to the FedEx on 5th street').\n"
            "Mark still_wanted=TRUE only if the user maintains, repeats, or "
            "reinforces this intent in the latest position, OR if they have not "
            "spoken about it at all since extraction. Silence is consent.\n"
            "When in doubt, lean FALSE. A false negative is silent and recoverable. "
            "A false positive is a visible action the user didn't want."
        )
        user_prompt = (
            f"Recent transcript (oldest first, all utterances from this user):\n"
            f"\"\"\"\n{recent or '(empty)'}\n\"\"\"\n\n"
            f"Candidate intent extracted earlier:\n"
            f"  text: {decision.intent.text}\n"
            f"  action_verb: {decision.intent.action_verb}\n"
            f"  parameters: {decision.intent.parameters}\n\n"
            f"Is this still wanted? Output the JSON."
        )
        try:
            raw = await asyncio.wait_for(self._llm_call(sys, user_prompt), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("revalidate_timeout", extra={"decision_id": decision.decision_id})
            # On timeout, retry once before falling back. False negatives here
            # cost a real action the user retracted — worth the extra latency.
            try:
                raw = await asyncio.wait_for(self._llm_call(sys, user_prompt), timeout=10.0)
            except (asyncio.TimeoutError, Exception):
                return True  # fail-open after retry too
        except Exception:
            logger.exception("revalidate_error")
            return True
        try:
            import json as _json
            data = _json.loads((raw or "").strip() or "{}")
            if not isinstance(data, dict):
                return True
            return bool(data.get("still_wanted", True))
        except (ValueError, TypeError):
            return True

    async def on_confirmation(self, decision_id: str, response: str) -> None:
        """The user replied yes/no to an ASK."""
        fut = self._pending_confirmations.pop(decision_id, None)
        if fut is None or fut.done():
            logger.warning("confirmation_for_unknown_decision", extra={
                "decision_id": decision_id,
            })
            return
        fut.set_result(response.strip().lower() == "yes")

    def set_notes_mode(self, enabled: bool) -> None:
        self._notes.set_enabled(enabled)

    async def flush_notes(self, session_id: str) -> None:
        await self._notes.flush(session_id)

    # --- Decision handling -----------------------------------------------------

    async def _handle_decision(self, decision: Decision) -> None:
        try:
            await self._notifier.announce(decision)

            if decision.kind == DecisionKind.LOG:
                return
            if decision.kind == DecisionKind.REFUSE:
                return  # the announce() carried the refusal copy

            if decision.kind == DecisionKind.EXECUTE:
                await self._execute(decision)
                return

            if decision.kind == DecisionKind.ASK:
                confirmed = await self._await_confirmation(decision)
                if confirmed:
                    await self._execute(decision)
                else:
                    await self._status.emit(EngineStatusEvent(
                        decision_id=decision.decision_id,
                        stage="completed",
                        message="OK, leaving it.",
                    ))
                return
        except Exception:
            logger.exception("handle_decision_error", extra={
                "decision_id": decision.decision_id,
            })
            await self._status.emit(EngineStatusEvent(
                decision_id=decision.decision_id,
                stage="error",
                message="Something went wrong on my end. I'll try this again later.",
            ))

    async def _execute(self, decision: Decision) -> None:
        await self._status.emit(EngineStatusEvent(
            decision_id=decision.decision_id,
            stage="executing",
            message=decision.completion_message or "Working on it...",
        ))
        result = await self._executor.execute(decision)
        await self._status.emit(result)

    async def _await_confirmation(self, decision: Decision, timeout_s: float = 600.0) -> bool:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[bool] = loop.create_future()
        self._pending_confirmations[decision.decision_id] = fut
        try:
            return await asyncio.wait_for(fut, timeout=timeout_s)
        except asyncio.TimeoutError:
            logger.info("confirmation_timeout", extra={
                "decision_id": decision.decision_id,
            })
            return False
        finally:
            self._pending_confirmations.pop(decision.decision_id, None)

    # --- Introspection (used by tests and the eval harness) -------------------

    @property
    def executor_log(self) -> list[Decision]:
        if isinstance(self._executor, _LoggingExecutor):
            return list(self._executor.log)
        return []

    @property
    def status_events(self) -> list[EngineStatusEvent]:
        if isinstance(self._status, _MemoryStatusSink):
            return list(self._status.events)
        return []
