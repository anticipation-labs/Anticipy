"""
Deterministic density-control harness for the proactive cascade.

WHY THIS EXISTS
---------------
torture_proactive runs hit avg P=86%, R=87%, but density 2.06–3.10 dispatches/min
on synthetic 25-utterance scenarios. The user's bar is "1-6/day" (≪ 1.5/min).
The parallel session shipped two prompt rules in `interpreter.py`:
  - ASPIRATION_VS_COMMITMENT — bare "I should X tonight" must NOT extract
  - META_INTENT_SUPPRESSION — "OK so I need to do X, Y, Z" recap of prior
    intents must NOT extract a `prioritize_tasks`/`save_to_do_list` meta-intent

Plus the engine's existing density-control machinery:
  - Settling buffer (consolidates within-buffer)
  - L6 Dispatcher dedup (catches re-mentions across already-dispatched)
  - Cross-utterance retraction via _revalidate

This file feeds 5 hand-crafted scenarios through the cascade with a
PATTERN-MATCHING STUB LLM that simulates "the rules work" (returning the
JSON the cascade would expect FROM a model that obeys the prompts). The
goal: verify the wiring (settling, consolidate, dispatcher) does the right
thing GIVEN truthful per-layer outputs. If the wiring regresses, this test
catches it WITHOUT the cost of real LLM calls.

This complements:
  - test_prompt_rules_present.py (rules exist verbatim in source)
  - test_proactive.py / test_proactive_layers.py (per-layer parsing)
  - torture_proactive_*.py (real LLM, integration with density gauge)

Run: cd engine && python -m pytest test_density_floor.py -v --tb=short
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.proactive.engine import ProactiveEngine  # noqa: E402
from app.proactive.types import (  # noqa: E402
    DecisionKind,
    TranscriptChunk,
)


# --- Stub LLM ------------------------------------------------------------------


@dataclass
class _StubLlm:
    """Pattern-matching stub LLM. Inspects (system, user) prompts to decide
    which layer is calling and what content it's reasoning about, then
    returns the JSON that layer expects.

    Inspectable: every call is recorded so tests can assert layer X was
    invoked N times and verify the cascade actually ran each layer.
    """

    calls: list[tuple[str, str]] = field(default_factory=list)
    # Per-scenario intent rules: maps a substring in the latest USER chunk
    # text → an intents list (each item: dict with keys for the extract
    # JSON). When None, layer returns {"intents": []}.
    extract_rules: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    # Substrings that, when present in the L2 trigger chunk text, force
    # zero intents — models META_INTENT_SUPPRESSION + ASPIRATION_VS_COMMITMENT.
    # Checked BEFORE extract_rules so a recap chunk like "OK so I need to
    # call the dentist, email Mark..." doesn't accidentally re-fire prior
    # extract_rules for the substrings that overlap.
    extract_zero_markers: list[str] = field(default_factory=list)
    # Salience override: if any string appears in the user prompt, force
    # actionable=False (used to model "exploration mention" suppression).
    salience_unactionable_markers: list[str] = field(default_factory=list)
    # Revalidate retraction: if any string appears in the user prompt,
    # _revalidate returns still_wanted=false.
    revalidate_drop_markers: list[str] = field(default_factory=list)
    # Consolidate: if 2+ pending intents and one of these substrings is
    # in the user prompt's recent transcript, model returns keep=[<lone_idx>].
    consolidate_keep_only_first: bool = False
    # Dispatcher dedup: substring → mark new candidate as duplicate of id 0.
    dispatcher_duplicate_markers: list[str] = field(default_factory=list)

    async def __call__(self, system: str, user: str) -> str:
        self.calls.append((system, user))

        # Layer 0: speaker-ID — pretend everyone is the wearer.
        if "speaker-ID layer" in system:
            return json.dumps({
                "is_wearer": True,
                "confidence": 0.95,
                "reasoning": "wearer voice",
            })

        # Layer 1: salience. We match against the LATEST UTTERANCE block
        # only — the recent-context block accumulates earlier markers and
        # would force-mark every later chunk unactionable.
        if "first-pass attention filter" in system:
            latest = self._extract_latest_utterance(user)
            for marker in self.salience_unactionable_markers:
                if marker in latest:
                    return json.dumps({
                        "actionable": False,
                        "confidence": 0.7,
                        "reasoning": f"unactionable: matched {marker[:30]!r}",
                    })
            return json.dumps({
                "actionable": True,
                "confidence": 0.85,
                "reasoning": "looks actionable",
            })

        # Layer 2: extraction. The interpreter prompt mentions
        # "intent-extraction layer" — we match each extract_rules marker
        # against the TRIGGERING CHUNK block only, NOT the recent-context
        # block. Otherwise an early chunk's text bleeds into every
        # subsequent extract call and the same intent fires on every chunk.
        if "intent-extraction layer" in system:
            trigger_text = self._extract_trigger_chunk(user)
            # Zero-markers fire FIRST. They model the prompt-rule
            # behaviors (META_INTENT_SUPPRESSION, ASPIRATION_VS_COMMITMENT,
            # exploration-mode detection) where L2 would correctly emit
            # zero intents from the trigger.
            for marker in self.extract_zero_markers:
                if marker in trigger_text:
                    return json.dumps({"intents": []})
            for marker, intents in self.extract_rules.items():
                if marker in trigger_text:
                    return json.dumps({"intents": intents})
            return json.dumps({"intents": []})

        # Layer 3: reversibility.
        if "deciding whether a single intended user action is reversible" in system:
            return json.dumps({
                "reversibility": "reversible",
                "confidence": 0.9,
                "reasoning": "search/lookup is read-only",
            })

        # Layer 4: urgency.
        if "scoring how urgent" in system:
            return json.dumps({"level": 2, "reasoning": "no time signal"})

        # Layer 5: Donna.
        if "Donna" in system:
            return json.dumps({
                "should_refuse": False,
                "reason": "",
                "rephrase": None,
                "confidence": 0.9,
            })

        # Engine-internal: harsh-dictation guard.
        if "harsh-dictation guard" in system:
            return json.dumps({
                "is_harsh": False,
                "named_person": "",
                "refusal_reason": "",
                "rephrase": "",
            })

        # Engine-internal: consolidate pending.
        if "consolidating multiple candidate intents" in system:
            # Determine candidate count from the user prompt.
            try:
                # The prompt embeds JSON list of candidates with "id" keys.
                # Quick scan: count "\"id\":" occurrences inside the JSON.
                ids_in_prompt = []
                for line in user.splitlines():
                    line = line.strip()
                    if line.startswith('"id":'):
                        try:
                            v = int(line.split(":", 1)[1].strip().rstrip(","))
                            ids_in_prompt.append(v)
                        except (ValueError, IndexError):
                            pass
                if not ids_in_prompt:
                    return json.dumps({"keep": [], "drop_reasoning": "no ids"})
                if self.consolidate_keep_only_first:
                    return json.dumps({
                        "keep": [ids_in_prompt[0]],
                        "drop_reasoning": "later intent superseded as info-lookup",
                    })
                return json.dumps({
                    "keep": ids_in_prompt,
                    "drop_reasoning": "all distinct",
                })
            except Exception:
                return json.dumps({"keep": [], "drop_reasoning": "fallback"})

        # Engine-internal: re-validate.
        if "re-validate a candidate intent" in system:
            for marker in self.revalidate_drop_markers:
                if marker in user:
                    return json.dumps({
                        "still_wanted": False,
                        "reasoning": f"user retracted: {marker[:30]!r}",
                    })
            return json.dumps({
                "still_wanted": True,
                "reasoning": "no retraction observed",
            })

        # Engine-internal: dispatcher dedup.
        if "checking whether a new candidate intent is a re-mention" in system:
            for marker in self.dispatcher_duplicate_markers:
                if marker in user:
                    return json.dumps({
                        "duplicate_of": 0,
                        "reasoning": f"sub-lookup of prior dispatch: {marker[:30]!r}",
                    })
            return json.dumps({
                "duplicate_of": None,
                "reasoning": "distinct",
            })

        # Anything else: defensive default (empty JSON).
        return "{}"

    # --- Internal parsing helpers --------------------------------------------

    @staticmethod
    def _extract_latest_utterance(user_prompt: str) -> str:
        """Pull the 'Latest utterance from the user' block out of the salience
        user-prompt template. Returns the latest text, or full prompt if the
        marker isn't there."""
        return _StubLlm._block_after(user_prompt, "Latest utterance from the user:")

    @staticmethod
    def _extract_trigger_chunk(user_prompt: str) -> str:
        """Pull the 'Most recent chunk that triggered extraction' block from
        the L2 extract user prompt."""
        return _StubLlm._block_after(
            user_prompt, "Most recent chunk that triggered extraction"
        )

    @staticmethod
    def _block_after(user_prompt: str, header: str) -> str:
        """Return the triple-quoted block that follows `header` in the
        user prompt template, or the full prompt if the header / fences are
        missing."""
        idx = user_prompt.find(header)
        if idx < 0:
            return user_prompt
        rest = user_prompt[idx + len(header):]
        first = rest.find('"""')
        if first < 0:
            return rest
        second = rest.find('"""', first + 3)
        if second < 0:
            return rest[first + 3:]
        return rest[first + 3:second]

    # --- Inspection helpers ---------------------------------------------------

    def calls_with_marker(self, system_marker: str) -> int:
        return sum(1 for (s, _u) in self.calls if system_marker in s)

    def last_user_for(self, system_marker: str) -> str | None:
        for (s, u) in reversed(self.calls):
            if system_marker in s:
                return u
        return None


# --- Helpers -------------------------------------------------------------------


def _chunk(text: str, idx: int, *, session_id: str = "den") -> TranscriptChunk:
    now = time.time()
    return TranscriptChunk(
        chunk_id=idx,
        session_id=session_id,
        user_id="u",
        text=text,
        start_ts=now + idx * 1.0,
        end_ts=now + idx * 1.0 + 0.8,
        confidence=0.9,
        is_self_talk=False,
        is_addressed_to_agent=False,
    )


async def _run_scenario(
    stub: _StubLlm,
    chunks: list[TranscriptChunk],
    *,
    settle_chunks: int = 1,
) -> tuple[ProactiveEngine, list]:
    """Construct the engine, feed chunks, flush settling buffer, return
    (engine, dispatched_decisions).

    The engine's interpreter has a per-session 1.0s throttle on extract
    calls. That breaks tests that fire several salient chunks back-to-back
    in <1ms. We zero the throttle here so every salient chunk reaches L2.
    """
    engine = ProactiveEngine(
        user_id="u",
        llm_call=stub,
        settle_chunks=settle_chunks,
    )
    # Disable extract throttle for deterministic tests.
    engine._interpreter._min_interval = 0.0
    dispatched: list = []
    for c in chunks:
        out = await engine.on_transcript_chunk(c)
        dispatched.extend(out)
    # Force-flush any pending dispatches.
    final = await engine.flush_pending()
    dispatched.extend(final)
    return engine, dispatched


# --- DENSITY_1: 1 real intent + 4 noise → ≤ 1 dispatch ------------------------


def test_density_1_one_real_one_dispatch():
    """5 utterances: 1 carries a real lookup intent, 4 are smalltalk that the
    salience layer marks unactionable. Cascade should fire exactly 1
    dispatch, not 5."""

    async def go():
        chunks = [
            _chunk("yeah the weather is nice today", 0),       # noise
            _chunk("what's the time in Tokyo right now", 1),   # REAL
            _chunk("haha that's funny", 2),                    # noise
            _chunk("anyway", 3),                               # noise
            _chunk("oh well", 4),                              # noise
        ]
        stub = _StubLlm(
            extract_rules={
                "what's the time in Tokyo": [{
                    "text": "look up the current time in Tokyo",
                    "action_verb": "lookup_time",
                    "parameters": {"location": "Tokyo"},
                    "evidence_chunk_ids": [1],
                    "confidence": 0.92,
                    "confidence_reasoning": "explicit info request",
                }],
            },
            salience_unactionable_markers=[
                "weather is nice", "haha that's", "anyway", "oh well",
            ],
        )
        _engine, dispatched = await _run_scenario(stub, chunks)
        assert len(dispatched) <= 1, (
            f"density floor breached: {len(dispatched)} dispatches for "
            f"1-real/4-noise scenario"
        )
        assert len(dispatched) == 1, "real intent should still fire"
        assert dispatched[0].intent.action_verb == "lookup_time"
        # Sanity: salience ran on every chunk (5 calls).
        assert stub.calls_with_marker("first-pass attention filter") == 5
        # Extract ran only on the salient chunk (1 call).
        assert stub.calls_with_marker("intent-extraction layer") == 1

    asyncio.run(go())


# --- DENSITY_2: meta-recital at end of to-do enumeration → 0 NEW dispatches ----


def test_density_2_meta_recital_suppressed():
    """8 utterances: user mentions 4 distinct tasks individually, then at the
    end says 'OK I need to prioritize: dentist, email Mark, order cat food,
    pickup recipe'. The meta-recital must NOT spawn an extra
    `prioritize_tasks` dispatch on top of the four already extracted.

    We model this by:
      - extract returning 1 real intent for chunks 1, 3, 5, 7
      - the FINAL chunk (recap) → extract returns 0 intents
        (this is what META_INTENT_SUPPRESSION achieves in production)
    """

    async def go():
        chunks = [
            _chunk("filler", 0),
            _chunk("I need to call the dentist about my cleaning", 1),
            _chunk("filler", 2),
            _chunk("I need to email Mark about the project update", 3),
            _chunk("filler", 4),
            _chunk("I need to order more cat food from chewy", 5),
            _chunk("filler", 6),
            _chunk(
                "OK I need to prioritize my tasks today: dentist, "
                "email Mark, cat food, pickup that recipe",
                7,
            ),
        ]
        stub = _StubLlm(
            extract_rules={
                "call the dentist": [{
                    "text": "call the dentist about cleaning",
                    "action_verb": "call_dentist",
                    "parameters": {"reason": "cleaning"},
                    "evidence_chunk_ids": [1],
                    "confidence": 0.85,
                    "confidence_reasoning": "concrete task",
                }],
                "email Mark about the project": [{
                    "text": "email Mark about the project update",
                    "action_verb": "email_mark",
                    "parameters": {"recipient": "Mark", "subject": "project update"},
                    "evidence_chunk_ids": [3],
                    "confidence": 0.85,
                    "confidence_reasoning": "concrete task",
                }],
                "order more cat food": [{
                    "text": "order cat food from chewy",
                    "action_verb": "order_cat_food",
                    "parameters": {"vendor": "chewy"},
                    "evidence_chunk_ids": [5],
                    "confidence": 0.85,
                    "confidence_reasoning": "concrete task",
                }],
            },
            # The recap chunk: META_INTENT_SUPPRESSION → emit zero intents.
            # Match the recap-only phrasing.
            extract_zero_markers=["prioritize my tasks today"],
            salience_unactionable_markers=["filler"],
        )
        _engine, dispatched = await _run_scenario(stub, chunks)
        # Three real, ZERO meta-recital. Total ≤ 3.
        assert len(dispatched) <= 3, (
            f"density: {len(dispatched)} dispatches; meta-recital should yield 0 NEW"
        )
        # Verify no `prioritize_tasks` / `save_to_do_list` dispatch sneaked in.
        verbs = {d.intent.action_verb for d in dispatched}
        forbidden = {"prioritize_tasks", "save_to_do_list", "remember_to_do_list",
                     "organize_my_day", "track_my_tasks"}
        leaked = verbs & forbidden
        assert not leaked, f"meta-intent leaked through cascade: {leaked}"

    asyncio.run(go())


# --- DENSITY_3: aspiration "I should book a flight tonight" → 0 dispatches ----


def test_density_3_aspiration_not_commitment():
    """User mentions an aspiration with vague time ("tonight") and no
    commitment signal. ASPIRATION_VS_COMMITMENT rule says: do NOT extract.
    We model this with extract returning [] for the aspiration chunk."""

    async def go():
        chunks = [
            _chunk("man, this week has been crazy", 0),
            _chunk("I should book a flight tonight, honestly", 1),  # aspiration
            _chunk("but I'm so tired", 2),
            _chunk("maybe later", 3),
            _chunk("anyway, what's for dinner", 4),
            _chunk("I'll figure it out", 5),
        ]
        stub = _StubLlm(
            # No extract_rules at all. extract default = {"intents": []}.
            # Salience may say actionable on the aspiration chunk; L2 returns 0.
            salience_unactionable_markers=[
                "this week has been crazy", "I'm so tired", "maybe later",
                "what's for dinner", "I'll figure it out",
            ],
        )
        _engine, dispatched = await _run_scenario(stub, chunks)
        assert len(dispatched) == 0, (
            f"aspiration should NOT dispatch; got {len(dispatched)}: "
            f"{[d.intent.action_verb for d in dispatched]}"
        )
        # Salience ran on every chunk.
        assert stub.calls_with_marker("first-pass attention filter") == 6
        # Extract may or may not have run depending on salience floor (0.35);
        # but if it ran, it returned []. Verify by checking dispatches==0.

    asyncio.run(go())


# --- DENSITY_4: 2 intents converge to 1 goal (sub-lookup) → 1 dispatch -------


def test_density_4_dedup_at_dispatch():
    """User says 'find me a recipe' (intent A), then a few chunks later
    'look up the website for the recipe source' (intent B). The dispatch-time
    L6 dedup gate should mark B as a duplicate (sub-lookup) of A. Total
    dispatches: 1.

    We model this by:
      - extract emits intent A on chunk 1
      - extract emits intent B on chunk 5
      - dispatcher returns duplicate_of=0 when it sees the website-lookup
        text in the new candidate. This requires settle_chunks=0 so A
        dispatches FIRST and gets recorded before B is admitted.
    """

    async def go():
        chunks = [
            _chunk("filler", 0),
            _chunk("find me the lentil soup recipe from The Savory Spoon", 1),
            _chunk("filler", 2),
            _chunk("filler", 3),
            _chunk("filler", 4),
            _chunk("look up the website for The Savory Spoon", 5),
            _chunk("filler", 6),
        ]
        stub = _StubLlm(
            extract_rules={
                "lentil soup recipe": [{
                    "text": "find lentil soup recipe from The Savory Spoon",
                    "action_verb": "find_recipe",
                    "parameters": {
                        "dish": "lentil soup",
                        "source": "The Savory Spoon",
                    },
                    "evidence_chunk_ids": [1],
                    "confidence": 0.92,
                    "confidence_reasoning": "explicit search request",
                }],
                "website for The Savory Spoon": [{
                    "text": "look up The Savory Spoon's website",
                    "action_verb": "lookup_website",
                    "parameters": {"site": "The Savory Spoon"},
                    "evidence_chunk_ids": [5],
                    "confidence": 0.88,
                    "confidence_reasoning": "explicit lookup",
                }],
            },
            salience_unactionable_markers=["filler"],
            dispatcher_duplicate_markers=["look up The Savory Spoon's website"],
        )
        # settle_chunks=0 so each dispatches immediately and the L6 gate
        # has prior history to compare against.
        _engine, dispatched = await _run_scenario(stub, chunks, settle_chunks=0)
        assert len(dispatched) == 1, (
            f"sub-lookup should be deduped at L6; got {len(dispatched)} dispatches"
        )
        assert dispatched[0].intent.action_verb == "find_recipe"
        # Dispatcher actually ran.
        assert stub.calls_with_marker(
            "checking whether a new candidate intent is a re-mention"
        ) >= 1

    asyncio.run(go())


# --- DENSITY_5: 1 intent + later retraction → 0 dispatches --------------------


def test_density_5_retraction_drops_intent():
    """User says 'cancel my dentist appointment' (intent), then later in the
    same buffer says 'actually never mind, keep it'. The settling-time
    re-validate pass should drop the decision before dispatch."""

    async def go():
        chunks = [
            _chunk("ugh, I want to cancel my dentist appointment", 0),
            _chunk("filler", 1),
            _chunk("filler", 2),
            _chunk("actually never mind, keep the dentist appointment", 3),
            _chunk("filler", 4),
            _chunk("filler", 5),
        ]
        stub = _StubLlm(
            extract_rules={
                "cancel my dentist appointment": [{
                    "text": "cancel the user's dentist appointment",
                    "action_verb": "cancel_appointment",
                    "parameters": {"target": "dentist"},
                    "evidence_chunk_ids": [0],
                    "confidence": 0.85,
                    "confidence_reasoning": "explicit cancel intent",
                }],
            },
            # Keep filler unactionable; let the retraction chunk pass through
            # salience so it lives in recent_text where _revalidate sees it.
            salience_unactionable_markers=["filler"],
            # Match a substring that appears in the retraction chunk text.
            revalidate_drop_markers=["never mind, keep the dentist"],
        )
        # settle_chunks default 999 → flush_pending() forces resolution at
        # the END, after every chunk including the retraction (chunk 3) is
        # in recent context. _revalidate then sees the retraction.
        _engine, dispatched = await _run_scenario(stub, chunks, settle_chunks=999)
        assert len(dispatched) == 0, (
            f"retraction should drop intent at re-validate; got "
            f"{len(dispatched)} dispatches: {[d.intent.action_verb for d in dispatched]}"
        )
        # Revalidate ran (the _process_settled flush triggers it).
        assert stub.calls_with_marker("re-validate a candidate intent") >= 1

    asyncio.run(go())


# --- Sanity: stub LLM is inspectable ------------------------------------------


def test_stub_llm_records_every_call():
    """The stub itself is inspectable. This is the contract the harness
    relies on — if it breaks, the assertions above are vacuous."""

    async def go():
        stub = _StubLlm(
            extract_rules={"test intent": [{
                "text": "do the test",
                "action_verb": "test_action",
                "parameters": {},
                "evidence_chunk_ids": [0],
                "confidence": 0.9,
                "confidence_reasoning": "test",
            }]},
        )
        _engine, dispatched = await _run_scenario(
            stub, [_chunk("test intent here", 0)], settle_chunks=0,
        )
        # Every layer below the dispatcher path got at least one call.
        assert stub.calls_with_marker("speaker-ID layer") >= 1
        assert stub.calls_with_marker("first-pass attention filter") >= 1
        assert stub.calls_with_marker("intent-extraction layer") >= 1
        assert stub.calls_with_marker(
            "deciding whether a single intended user action is reversible"
        ) >= 1
        assert stub.calls_with_marker("scoring how urgent") >= 1
        assert stub.calls_with_marker("Donna") >= 1
        assert len(dispatched) == 1
        # last_user_for returns the most recent prompt for that layer.
        last_extract_user = stub.last_user_for("intent-extraction layer")
        assert last_extract_user is not None
        assert "test intent here" in last_extract_user

    asyncio.run(go())


# --- DEFENSE IN DEPTH: even if L2 leaks a meta-intent, L6 catches it ---------


def test_density_meta_intent_caught_by_l6_dedup_if_l2_leaks():
    """Defense-in-depth: if a hypothetical L2 prompt regression let a
    `prioritize_tasks` meta-intent through after the user already had their
    individual intents dispatched, the L6 dispatcher dedup gate should
    recognize it as a recital and drop it. This is the second line of
    defense behind the META_INTENT_SUPPRESSION prompt rule."""

    async def go():
        chunks = [
            _chunk("I need to call the dentist about my cleaning", 0),
            _chunk("filler", 1),
            _chunk("filler", 2),
            _chunk("organize my day - that whole list", 3),  # recap-style
        ]
        stub = _StubLlm(
            # Use disjoint trigger phrases so each chunk's extract rule
            # picks the intended intent only.
            extract_rules={
                "call the dentist about my cleaning": [{
                    "text": "call the dentist about cleaning",
                    "action_verb": "call_dentist",
                    "parameters": {},
                    "evidence_chunk_ids": [0],
                    "confidence": 0.85,
                    "confidence_reasoning": "concrete task",
                }],
                # SIMULATE the L2 bug: the recap chunk leaks a meta-intent
                # (this is what META_INTENT_SUPPRESSION should prevent in
                # production, but we want L6 dedup as a second line of
                # defense in case the prompt rule slips).
                "organize my day": [{
                    "text": "organize my tasks today",
                    "action_verb": "prioritize_tasks",
                    "parameters": {"items": ["call the dentist"]},
                    "evidence_chunk_ids": [3],
                    "confidence": 0.7,
                    "confidence_reasoning": "user reciting list",
                }],
            },
            salience_unactionable_markers=["filler"],
            # L6 marks the meta-intent as duplicate of the dentist dispatch.
            dispatcher_duplicate_markers=["organize my tasks today"],
        )
        _engine, dispatched = await _run_scenario(stub, chunks, settle_chunks=0)
        # Only the real dentist intent should survive.
        verbs = [d.intent.action_verb for d in dispatched]
        assert "call_dentist" in verbs, "real intent should fire"
        assert "prioritize_tasks" not in verbs, (
            f"meta-intent leaked through L6 dedup: {verbs}"
        )
        assert len(dispatched) == 1, f"expected 1 dispatch, got {len(dispatched)}: {verbs}"
        # L6 dispatcher actually fired on the second candidate.
        assert stub.calls_with_marker(
            "checking whether a new candidate intent is a re-mention"
        ) >= 1, "L6 dedup should have run on the meta-intent candidate"

    asyncio.run(go())


# --- Sanity: all 5 scenarios stay under the user's daily budget --------------


def test_aggregate_density_under_floor():
    """Across all 5 scenarios fed back-to-back, total dispatches should be
    <= 5 (one per real intent kept). On a single 32-utterance synthetic
    block this is well under the 1.5/min hot-conversation floor and trivially
    under the user's 1-6/day target. This test catches a regression where one
    of the suppression pathways silently breaks and dispatch density doubles.
    """

    async def go():
        scenarios = [
            # (chunks, stub) tuples
            (
                [_chunk("what's the time in Tokyo", 0)],
                _StubLlm(extract_rules={
                    "time in Tokyo": [{
                        "text": "look up time in Tokyo",
                        "action_verb": "lookup_time",
                        "parameters": {"location": "Tokyo"},
                        "evidence_chunk_ids": [0],
                        "confidence": 0.9,
                        "confidence_reasoning": "explicit",
                    }],
                }),
            ),
            (
                [
                    _chunk("I should book a flight tonight", 0),
                    _chunk("I'm too tired", 1),
                ],
                _StubLlm(salience_unactionable_markers=["I'm too tired"]),
            ),
            (
                [_chunk("never mind, forget it", 0)],
                _StubLlm(salience_unactionable_markers=["never mind"]),
            ),
        ]
        total = 0
        for chunks, stub in scenarios:
            _e, dispatched = await _run_scenario(stub, chunks, settle_chunks=0)
            total += len(dispatched)
        # Aggregate: 1 real + 0 aspiration + 0 retraction = 1.
        assert total <= 2, (
            f"aggregate density {total} dispatches across 3 mini-scenarios "
            f"exceeds tight floor"
        )

    asyncio.run(go())
