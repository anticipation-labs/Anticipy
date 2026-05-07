"""
Deterministic unit tests for the proactive engine.

The proactive engine is an AI cascade — five LLM calls per actionable chunk.
Most of its behavior is non-deterministic by construction and is tested by
the adversarial eval harness in app/proactive/eval/harness.py with synthetic
scenarios + LLM-as-judge.

This file covers ONLY the deterministic surfaces:

  - decider routing logic — pure function from (rev, conf, urg, donna) → kind
  - urgency-to-channel mapping — property of the channels themselves
  - notifier channel ladder + cap helpers
  - context buffer windowing — time-based sliding window
  - end-to-end engine wiring — with all five LLM layers mocked

Run: cd engine && python test_proactive.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.proactive.context import ContextBuffer
from app.proactive.decider import HIGH_CONFIDENCE, MID_CONFIDENCE, _route
from app.proactive.donna import DonnaVerdict
from app.proactive.engine import ProactiveEngine
from app.proactive.notifier import _cap_channel, _ladder_from
from app.proactive.types import (
    Confidence,
    DecisionKind,
    Intent,
    NotificationChannel,
    Reversibility,
    TranscriptChunk,
    Urgency,
)


def _chunk(text: str, **kw) -> TranscriptChunk:
    return TranscriptChunk(
        chunk_id=kw.get("chunk_id", 0),
        session_id=kw.get("session_id", "t"),
        user_id=kw.get("user_id", "u"),
        text=text,
        start_ts=time.time(),
        end_ts=time.time() + 1.0,
        confidence=kw.get("confidence", 0.9),
        is_self_talk=kw.get("is_self_talk", False),
        is_addressed_to_agent=kw.get("is_addressed_to_agent", False),
    )


def _intent(verb: str = "search", text: str = "do the thing") -> Intent:
    return Intent.new(user_id="u", text=text, action_verb=verb)


def _urgency(level: int = 2) -> Urgency:
    return Urgency(level=level)


# --- decider routing -----------------------------------------------------------


def test_route_reversible_high_confidence_executes():
    r = _route(Reversibility.REVERSIBLE, Confidence(score=0.9), _intent(), _urgency())
    assert r.kind == DecisionKind.EXECUTE
    assert r.completion_message is not None


def test_route_reversible_mid_confidence_asks():
    r = _route(Reversibility.REVERSIBLE, Confidence(score=0.6), _intent(), _urgency())
    assert r.kind == DecisionKind.ASK
    assert r.user_facing_question is not None


def test_route_reversible_low_confidence_logs():
    r = _route(Reversibility.REVERSIBLE, Confidence(score=0.3), _intent(), _urgency())
    assert r.kind == DecisionKind.LOG


def test_route_irreversible_always_asks_regardless_of_confidence():
    for c in (0.99, 0.85, 0.55, 0.10):
        r = _route(Reversibility.IRREVERSIBLE, Confidence(score=c), _intent("send"), _urgency())
        assert r.kind == DecisionKind.ASK, f"failed at confidence={c}"


def test_route_unknown_treated_as_irreversible():
    r = _route(Reversibility.UNKNOWN, Confidence(score=0.99), _intent("teleport"), _urgency())
    assert r.kind == DecisionKind.ASK


def test_route_donna_refusal_overrides_everything():
    """If Donna says refuse, REFUSE wins regardless of reversibility/confidence."""
    donna = DonnaVerdict(should_refuse=True, reason="you'll regret it")
    r = _route(
        Reversibility.REVERSIBLE,
        Confidence(score=0.99),
        _intent(),
        _urgency(),
        donna=donna,
    )
    assert r.kind == DecisionKind.REFUSE
    assert r.refusal_reason and "regret" in r.refusal_reason


def test_route_donna_no_refuse_passes_through():
    donna = DonnaVerdict(should_refuse=False)
    r = _route(
        Reversibility.REVERSIBLE,
        Confidence(score=0.95),
        _intent(),
        _urgency(),
        donna=donna,
    )
    assert r.kind == DecisionKind.EXECUTE


def test_route_donna_rephrase_appended_to_reason():
    donna = DonnaVerdict(
        should_refuse=True,
        reason="you're tired.",
        rephrase="Sleep on it.",
    )
    r = _route(Reversibility.IRREVERSIBLE, Confidence(score=0.9), _intent(), _urgency(), donna=donna)
    assert r.kind == DecisionKind.REFUSE
    assert r.refusal_reason and "Sleep on it" in r.refusal_reason


def test_high_confidence_threshold_value():
    assert HIGH_CONFIDENCE == 0.85


def test_mid_confidence_threshold_value():
    assert MID_CONFIDENCE == 0.45


# --- urgency-to-channel mapping ------------------------------------------------


def test_urgency_to_channel_mapping():
    assert Urgency(level=5).channel == NotificationChannel.VOICE
    assert Urgency(level=4).channel == NotificationChannel.SMS
    assert Urgency(level=3).channel == NotificationChannel.PUSH
    assert Urgency(level=2).channel == NotificationChannel.IN_APP
    assert Urgency(level=1).channel == NotificationChannel.NOTED


# --- notifier ------------------------------------------------------------------


def test_channel_ladder_starts_at_requested_and_descends():
    ladder = _ladder_from(NotificationChannel.SMS)
    assert NotificationChannel.SMS in ladder
    assert NotificationChannel.PUSH in ladder
    assert NotificationChannel.IN_APP in ladder
    assert NotificationChannel.VOICE not in ladder


def test_channel_ladder_voice_descends_through_all():
    ladder = _ladder_from(NotificationChannel.VOICE)
    assert ladder == [
        NotificationChannel.VOICE,
        NotificationChannel.SMS,
        NotificationChannel.PUSH,
        NotificationChannel.IN_APP,
    ]


def test_channel_ladder_noted_is_empty():
    assert _ladder_from(NotificationChannel.NOTED) == []


def test_cap_channel_caps_above_ceiling():
    assert _cap_channel(NotificationChannel.VOICE, NotificationChannel.PUSH) == NotificationChannel.PUSH


def test_cap_channel_passes_through_below_ceiling():
    assert _cap_channel(NotificationChannel.IN_APP, NotificationChannel.PUSH) == NotificationChannel.IN_APP


# --- context buffer ------------------------------------------------------------


def test_context_buffer_appends_and_lists():
    async def go():
        ctx = ContextBuffer(user_id="u", window_seconds=600)
        await ctx.append(_chunk("hello", chunk_id=0))
        await ctx.append(_chunk("there", chunk_id=1))
        recent = await ctx.recent(seconds=600)
        assert len(recent) == 2
        text = await ctx.recent_text(seconds=600)
        assert "hello" in text and "there" in text
    asyncio.run(go())


def test_context_buffer_prunes_old_chunks():
    async def go():
        ctx = ContextBuffer(user_id="u", window_seconds=1)
        c0 = _chunk("old")
        c0.start_ts = time.time() - 10
        c0.end_ts = time.time() - 9
        await ctx.append(c0)
        await ctx.append(_chunk("new"))
        recent = await ctx.recent(seconds=600)
        assert len(recent) == 1
        assert recent[0].text == "new"
    asyncio.run(go())


# --- end-to-end engine wiring with mocked LLMs ---------------------------------
#
# These tests verify the cascade is wired correctly: salience→extract→
# reversibility/urgency/donna→decider→notifier→executor. The LLM is a stub
# whose response depends on which prompt it sees, so the cascade behaves
# deterministically for the duration of the test.


def _make_mock_llm(responses: dict[str, str]):
    """Build an LLM stub that returns canned responses based on a marker
    in the system prompt.

    Each response key is a substring searched for in the SYSTEM prompt.
    First match wins.
    """

    async def llm(sys_prompt: str, _user_prompt: str) -> str:
        for marker, response in responses.items():
            if marker in sys_prompt:
                return response
        return "{}"

    return llm


def test_engine_skips_non_salient_chunks():
    async def go():
        llm = _make_mock_llm({
            "first-pass attention filter": json.dumps({
                "actionable": False,
                "confidence": 0.95,
                "reasoning": "smalltalk",
            }),
        })
        engine = ProactiveEngine(user_id="u", llm_call=llm, settle_chunks=0)
        decisions = await engine.on_transcript_chunk(_chunk("nice weather huh"))
        assert decisions == []
        assert engine.executor_log == []
    asyncio.run(go())


def test_engine_extracts_executes_reversible_high_confidence():
    async def go():
        llm = _make_mock_llm({
            "first-pass attention filter": json.dumps({
                "actionable": True,
                "confidence": 0.9,
                "reasoning": "looks like an info request",
            }),
            "intent-extraction layer": json.dumps({
                "intents": [{
                    "text": "look up the weather in tokyo",
                    "action_verb": "lookup_info",
                    "parameters": {"topic": "weather", "location": "tokyo"},
                    "evidence_chunk_ids": [0],
                    "confidence": 0.95,
                    "confidence_reasoning": "explicit ask",
                }]
            }),
            "deciding whether a single intended user action is reversible": json.dumps({
                "reversibility": "reversible",
                "confidence": 0.95,
                "reasoning": "lookup is read-only",
            }),
            "scoring how urgent": json.dumps({
                "level": 2,
                "reasoning": "no time signal",
            }),
            "Donna": json.dumps({
                "should_refuse": False,
                "reason": "",
                "rephrase": None,
                "confidence": 0.9,
            }),
        })
        engine = ProactiveEngine(user_id="u", llm_call=llm, settle_chunks=0)
        decisions = await engine.on_transcript_chunk(_chunk("look up the weather in tokyo"))
        assert len(decisions) == 1
        assert decisions[0].kind == DecisionKind.EXECUTE
        # Wait briefly for the asyncio.create_task'd handler to land.
        await asyncio.sleep(0.1)
        assert len(engine.executor_log) == 1
    asyncio.run(go())


def test_engine_asks_on_irreversible_action():
    async def go():
        llm = _make_mock_llm({
            "first-pass attention filter": json.dumps({
                "actionable": True, "confidence": 0.9, "reasoning": "explicit",
            }),
            "intent-extraction layer": json.dumps({
                "intents": [{
                    "text": "send sarah a follow-up email",
                    "action_verb": "send_email_followup",
                    "parameters": {"recipient": "sarah"},
                    "evidence_chunk_ids": [0],
                    "confidence": 0.95,
                    "confidence_reasoning": "clear",
                }]
            }),
            "deciding whether a single intended user action is reversible": json.dumps({
                "reversibility": "irreversible",
                "confidence": 0.95,
                "reasoning": "sending email commits user",
            }),
            "scoring how urgent": json.dumps({"level": 3, "reasoning": "soonish"}),
            "Donna": json.dumps({
                "should_refuse": False, "reason": "", "rephrase": None, "confidence": 0.9,
            }),
        })
        engine = ProactiveEngine(user_id="u", llm_call=llm, settle_chunks=0)
        decisions = await engine.on_transcript_chunk(_chunk("send sarah a follow-up email"))
        assert len(decisions) == 1
        assert decisions[0].kind == DecisionKind.ASK
        assert decisions[0].reversibility == Reversibility.IRREVERSIBLE
    asyncio.run(go())


def test_engine_refuses_when_donna_pushes_back():
    async def go():
        llm = _make_mock_llm({
            "first-pass attention filter": json.dumps({
                "actionable": True, "confidence": 0.9, "reasoning": "looks like venting+intent",
            }),
            "intent-extraction layer": json.dumps({
                "intents": [{
                    "text": "fire off an angry email to my coworker",
                    "action_verb": "send_email_angry",
                    "parameters": {"tone": "angry"},
                    "evidence_chunk_ids": [0],
                    "confidence": 0.95,
                    "confidence_reasoning": "explicit",
                }]
            }),
            "deciding whether a single intended user action is reversible": json.dumps({
                "reversibility": "irreversible", "confidence": 0.95, "reasoning": "email",
            }),
            "scoring how urgent": json.dumps({"level": 4, "reasoning": "user is fired up"}),
            "Donna": json.dumps({
                "should_refuse": True,
                "reason": "you're heated. sleep on it.",
                "rephrase": "I'll draft something you can review tomorrow.",
                "confidence": 0.9,
            }),
        })
        engine = ProactiveEngine(user_id="u", llm_call=llm, settle_chunks=0)
        decisions = await engine.on_transcript_chunk(_chunk("ugh, fire off an angry email to my coworker"))
        assert len(decisions) == 1
        assert decisions[0].kind == DecisionKind.REFUSE
        assert decisions[0].refusal_reason and "sleep on it" in decisions[0].refusal_reason.lower()
    asyncio.run(go())


def test_engine_logs_low_confidence_silently():
    async def go():
        llm = _make_mock_llm({
            "first-pass attention filter": json.dumps({
                "actionable": True, "confidence": 0.6, "reasoning": "borderline",
            }),
            "intent-extraction layer": json.dumps({
                "intents": [{
                    "text": "maybe call my mom this week",
                    "action_verb": "call_person",
                    "parameters": {"person": "mom"},
                    "evidence_chunk_ids": [0],
                    "confidence": 0.35,
                    "confidence_reasoning": "very tentative",
                }]
            }),
            "deciding whether a single intended user action is reversible": json.dumps({
                "reversibility": "reversible", "confidence": 0.7, "reasoning": "calling is fine",
            }),
            "scoring how urgent": json.dumps({"level": 1, "reasoning": "vague"}),
            "Donna": json.dumps({
                "should_refuse": False, "reason": "", "rephrase": None, "confidence": 0.9,
            }),
        })
        engine = ProactiveEngine(user_id="u", llm_call=llm, settle_chunks=0)
        decisions = await engine.on_transcript_chunk(_chunk("hmm I should probably call mom this week"))
        assert len(decisions) == 1
        assert decisions[0].kind == DecisionKind.LOG
    asyncio.run(go())


def test_engine_drops_chunk_for_wrong_user():
    async def go():
        llm = _make_mock_llm({})  # never called
        engine = ProactiveEngine(user_id="alice", llm_call=llm, settle_chunks=0)
        chunk = _chunk("anything", user_id="bob")
        decisions = await engine.on_transcript_chunk(chunk)
        assert decisions == []
    asyncio.run(go())


# --- L0 speaker-ID layer -------------------------------------------------------
#
# L0 sits before L1 salience. Its job: drop chunks the model is confident are
# from someone OTHER than the wearer, before they can be misread as wearer
# intent. These tests verify wiring + fail-open behavior. The model decision
# itself is mocked.


def _wearer_yes(confidence: float = 0.95) -> str:
    return json.dumps({
        "is_wearer": True,
        "confidence": confidence,
        "reasoning": "looks like wearer voice",
    })


def _wearer_no(confidence: float = 0.9) -> str:
    return json.dumps({
        "is_wearer": False,
        "confidence": confidence,
        "reasoning": "addressed-to-wearer phrasing; not a self utterance",
    })


def test_speaker_id_wearer_chunk_flows_through_l1_l2():
    """When L0 says is_wearer=True, the chunk reaches L1/L2 and a decision
    appears. This is the common path."""
    async def go():
        llm = _make_mock_llm({
            "speaker-ID layer": _wearer_yes(0.97),
            "first-pass attention filter": json.dumps({
                "actionable": True, "confidence": 0.9, "reasoning": "explicit",
            }),
            "intent-extraction layer": json.dumps({
                "intents": [{
                    "text": "look up the weather in tokyo",
                    "action_verb": "lookup_info",
                    "parameters": {"topic": "weather", "location": "tokyo"},
                    "evidence_chunk_ids": [0],
                    "confidence": 0.95,
                    "confidence_reasoning": "explicit ask",
                }]
            }),
            "deciding whether a single intended user action is reversible": json.dumps({
                "reversibility": "reversible", "confidence": 0.95, "reasoning": "lookup",
            }),
            "scoring how urgent": json.dumps({"level": 2, "reasoning": "no time signal"}),
            "Donna": json.dumps({
                "should_refuse": False, "reason": "", "rephrase": None, "confidence": 0.9,
            }),
        })
        engine = ProactiveEngine(user_id="u", llm_call=llm, settle_chunks=0)
        decisions = await engine.on_transcript_chunk(_chunk("look up the weather in tokyo"))
        assert len(decisions) == 1
        assert decisions[0].kind == DecisionKind.EXECUTE
    asyncio.run(go())


def test_speaker_id_drops_non_wearer_chunk_high_confidence():
    """When L0 says is_wearer=False with confidence >= 0.6, the chunk is
    dropped: no decisions, no L1/L2 calls."""
    async def go():
        # Track which prompts were issued so we can prove L1/L2 never fired.
        prompts_seen: list[str] = []

        async def llm(sys_prompt: str, user_prompt: str) -> str:
            prompts_seen.append(sys_prompt)
            if "speaker-ID layer" in sys_prompt:
                return _wearer_no(confidence=0.9)
            # Anything else would be a wiring bug — but return safe defaults.
            return "{}"

        engine = ProactiveEngine(user_id="u", llm_call=llm, settle_chunks=0)
        decisions = await engine.on_transcript_chunk(_chunk("hey, did you finish the report?"))
        assert decisions == []
        assert engine.executor_log == []
        # L0 ran exactly once. L1 / L2 / L3 / L4 / L5 must NOT have run.
        joined = "\n---\n".join(prompts_seen)
        assert "speaker-ID layer" in joined
        assert "first-pass attention filter" not in joined, "L1 salience must not run after L0 drop"
        assert "intent-extraction layer" not in joined, "L2 extraction must not run after L0 drop"
        assert "deciding whether a single intended user action is reversible" not in joined
        assert "scoring how urgent" not in joined
        assert "Donna" not in joined
    asyncio.run(go())


def test_speaker_id_low_confidence_non_wearer_still_flows_through():
    """When L0 says is_wearer=False but confidence < 0.6, fail open: the
    chunk continues into L1. This protects against silently dropping wearer
    intent on borderline calls."""
    async def go():
        llm = _make_mock_llm({
            "speaker-ID layer": json.dumps({
                "is_wearer": False, "confidence": 0.4, "reasoning": "ambiguous",
            }),
            "first-pass attention filter": json.dumps({
                "actionable": False, "confidence": 0.9, "reasoning": "smalltalk",
            }),
        })
        engine = ProactiveEngine(user_id="u", llm_call=llm, settle_chunks=0)
        # No exception, no crash — and salience runs (we'll see no decisions
        # because salience says non-actionable, but the point is L1 was reached).
        decisions = await engine.on_transcript_chunk(_chunk("nice weather"))
        assert decisions == []
    asyncio.run(go())


def test_speaker_id_timeout_fails_open_to_wearer():
    """L0 LLM timeout → treat as wearer (fail open). Losing wearer intent
    silently is the failure mode we refuse to ship."""
    async def go():
        # Build a custom llm that hangs forever on the speaker-ID call but
        # returns instantly otherwise. We patch the L0 timeout down so the
        # test runs in a reasonable time.
        from app.proactive import speaker_id as _sid

        original_timeout = _sid.SPEAKER_ID_TIMEOUT_SECONDS
        _sid.SPEAKER_ID_TIMEOUT_SECONDS = 0.05
        try:
            async def llm(sys_prompt: str, _user_prompt: str) -> str:
                if "speaker-ID layer" in sys_prompt:
                    await asyncio.sleep(5.0)  # will trip the (patched) timeout
                    return _wearer_yes()
                if "first-pass attention filter" in sys_prompt:
                    return json.dumps({
                        "actionable": False, "confidence": 0.9, "reasoning": "small",
                    })
                return "{}"

            engine = ProactiveEngine(user_id="u", llm_call=llm, settle_chunks=0)
            # Should not raise. Should not drop. Salience then says non-actionable
            # → no decisions, but the chunk made it past L0.
            decisions = await engine.on_transcript_chunk(_chunk("hello"))
            assert decisions == []
        finally:
            _sid.SPEAKER_ID_TIMEOUT_SECONDS = original_timeout
    asyncio.run(go())


def test_speaker_id_diarization_hint_flows_into_prompt():
    """The diarization_hint set on the chunk must reach the L0 LLM as a soft
    prior. We capture the user-prompt and assert the hint string is present."""
    async def go():
        captured_user_prompts: list[str] = []

        async def llm(sys_prompt: str, user_prompt: str) -> str:
            if "speaker-ID layer" in sys_prompt:
                captured_user_prompts.append(user_prompt)
                return _wearer_yes()
            if "first-pass attention filter" in sys_prompt:
                return json.dumps({
                    "actionable": False, "confidence": 0.9, "reasoning": "small",
                })
            return "{}"

        engine = ProactiveEngine(user_id="u", llm_call=llm, settle_chunks=0)
        chunk = _chunk("ok then")
        chunk.diarization_hint = "wearer"
        await engine.on_transcript_chunk(chunk)
        assert len(captured_user_prompts) == 1
        assert "wearer" in captured_user_prompts[0]

        # Now the "other" hint, on a fresh engine.
        captured_user_prompts.clear()
        engine2 = ProactiveEngine(user_id="u", llm_call=llm, settle_chunks=0)
        chunk2 = _chunk("ok then", chunk_id=1)
        chunk2.diarization_hint = "other"
        await engine2.on_transcript_chunk(chunk2)
        assert len(captured_user_prompts) == 1
        assert "other" in captured_user_prompts[0]
    asyncio.run(go())


# --- dispatcher (L6 dedup gate) ------------------------------------------------


def _decision_for(verb: str, text: str, **params):
    """Convenience: build a Decision for dispatcher tests."""
    from app.proactive.types import Decision
    intent = Intent.new(user_id="u", text=text, action_verb=verb, parameters=params)
    return Decision.new(
        intent=intent,
        kind=DecisionKind.EXECUTE,
        confidence=Confidence(score=0.9),
        reversibility=Reversibility.REVERSIBLE,
        urgency=Urgency(level=2),
    )


def test_dispatcher_admits_when_no_recent_history():
    """Empty recent → admit without calling the LLM."""
    from app.proactive.dispatcher import Dispatcher

    async def go():
        called = []

        async def llm(_s: str, _u: str) -> str:
            called.append(1)
            return '{"duplicate_of": null}'

        d = Dispatcher(llm_call=llm)
        v = await d.admit(_decision_for("buy_gift", "buy gift"))
        assert v.admit is True
        assert v.duplicate_of is None
        assert called == []  # no LLM call when recent is empty
    asyncio.run(go())


def test_dispatcher_drops_duplicate_when_llm_says_so():
    """One recent matches → admit=False with duplicate_of populated."""
    from app.proactive.dispatcher import Dispatcher

    async def go():
        async def llm(_s: str, _u: str) -> str:
            return json.dumps({"duplicate_of": 0, "reasoning": "same goal"})

        d = Dispatcher(llm_call=llm)
        prior = _decision_for("book_appointment", "book annual physical")
        d.record(prior)
        v = await d.admit(_decision_for("set_reminder", "schedule physical"))
        assert v.admit is False
        assert v.duplicate_of == prior.decision_id
        assert "same" in v.reasoning.lower()
    asyncio.run(go())


def test_dispatcher_admits_when_llm_says_distinct():
    """LLM returns null → admit normally."""
    from app.proactive.dispatcher import Dispatcher

    async def go():
        async def llm(_s: str, _u: str) -> str:
            return json.dumps({"duplicate_of": None, "reasoning": "different goal"})

        d = Dispatcher(llm_call=llm)
        d.record(_decision_for("buy_gift", "buy gift for niece"))
        v = await d.admit(_decision_for("send_email", "send email about deadline"))
        assert v.admit is True
        assert v.duplicate_of is None
    asyncio.run(go())


def test_dispatcher_window_expiry_drops_old_recent():
    """Past the window, old recent is ignored — admit without LLM call."""
    from app.proactive.dispatcher import Dispatcher

    async def go():
        called = []

        async def llm(_s: str, _u: str) -> str:
            called.append(1)
            return '{"duplicate_of": 0}'

        d = Dispatcher(llm_call=llm, window_seconds=0.05)
        d.record(_decision_for("buy_gift", "buy gift"))
        await asyncio.sleep(0.10)  # past the window
        v = await d.admit(_decision_for("buy_gift", "buy gift"))
        assert v.admit is True
        assert called == []  # window cleared all recent → no LLM call
    asyncio.run(go())


def test_dispatcher_timeout_fails_open():
    """LLM hang → admit (better to occasionally double-fire than silently drop)."""
    from app.proactive.dispatcher import Dispatcher

    async def go():
        async def slow_llm(_s: str, _u: str) -> str:
            await asyncio.sleep(5.0)
            return '{"duplicate_of": 0}'

        d = Dispatcher(llm_call=slow_llm, timeout_seconds=0.05)
        d.record(_decision_for("a", "a"))
        v = await d.admit(_decision_for("b", "b"))
        assert v.admit is True
        assert "timeout" in v.reasoning.lower()
    asyncio.run(go())


def test_dispatcher_bad_json_fails_open():
    """Malformed JSON → admit."""
    from app.proactive.dispatcher import Dispatcher

    async def go():
        async def llm(_s: str, _u: str) -> str:
            return "not json at all {[}"

        d = Dispatcher(llm_call=llm)
        d.record(_decision_for("a", "a"))
        v = await d.admit(_decision_for("b", "b"))
        assert v.admit is True
    asyncio.run(go())


def test_dispatcher_out_of_range_id_fails_open():
    """LLM returns dup index pointing past the recent list → admit."""
    from app.proactive.dispatcher import Dispatcher

    async def go():
        async def llm(_s: str, _u: str) -> str:
            return json.dumps({"duplicate_of": 99})  # nonsense index

        d = Dispatcher(llm_call=llm)
        d.record(_decision_for("a", "a"))
        v = await d.admit(_decision_for("b", "b"))
        assert v.admit is True
    asyncio.run(go())


def test_engine_integration_dispatch_dedup_drops_re_extraction():
    """End-to-end: two chunks each extract similar intents; dispatcher drops
    the second. Cascade is fully mocked; only the dispatcher's LLM is the
    arbiter.
    """
    async def go():
        # First chunk yields verb 'book_appointment'; second yields
        # 'set_reminder' (semantically same — different verb). Without the
        # dispatcher, both would dispatch.
        verbs = iter(["book_appointment", "set_reminder"])

        async def llm(sys_prompt: str, _user_prompt: str) -> str:
            if "speaker-ID layer" in sys_prompt:
                return _wearer_yes()
            if "first-pass attention filter" in sys_prompt:
                return json.dumps({"actionable": True, "confidence": 0.9, "reasoning": "x"})
            if "intent-extraction layer" in sys_prompt:
                v = next(verbs)
                return json.dumps({"intents": [{
                    "text": f"{v} for annual physical",
                    "action_verb": v,
                    "parameters": {"who": "Dr. Chen"},
                    "evidence_chunk_ids": [0],
                    "confidence": 0.95,
                    "confidence_reasoning": "clear",
                }]})
            if "reversibility" in sys_prompt or "deciding whether a single intended" in sys_prompt:
                return json.dumps({
                    "reversibility": "reversible", "confidence": 0.95, "reasoning": "y",
                })
            if "scoring how urgent" in sys_prompt:
                return json.dumps({"level": 2, "reasoning": "z"})
            if "Donna" in sys_prompt:
                return json.dumps({
                    "should_refuse": False, "reason": "", "rephrase": None, "confidence": 0.9,
                })
            if "re-mention or duplicate" in sys_prompt:
                # Dispatcher-side prompt: model says "yes, dup of recent[0]"
                return json.dumps({
                    "duplicate_of": 0, "reasoning": "same goal — Dr. Chen physical",
                })
            return "{}"

        engine = ProactiveEngine(user_id="u", llm_call=llm, settle_chunks=0)
        decisions_1 = await engine.on_transcript_chunk(_chunk("schedule physical with Dr Chen", chunk_id=0))
        decisions_2 = await engine.on_transcript_chunk(_chunk("remember to set up the annual checkup", chunk_id=1))
        assert len(decisions_1) == 1, f"first chunk should dispatch one, got {len(decisions_1)}"
        assert len(decisions_2) == 0, f"second chunk should be deduped, got {len(decisions_2)}"
    asyncio.run(go())


def test_transcript_chunk_diarization_hint_default_none():
    """Backwards compat: chunks created without the new field default to None."""
    chunk = TranscriptChunk(
        chunk_id=0,
        session_id="s",
        user_id="u",
        text="hello",
        start_ts=time.time(),
        end_ts=time.time() + 1.0,
        confidence=0.9,
    )
    assert chunk.diarization_hint is None
    assert chunk.is_wearer is None


# --- runner --------------------------------------------------------------------


if __name__ == "__main__":
    tests = [
        (name, obj) for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    print(f"running {len(tests)} tests...")
    failed: list[tuple[str, str]] = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed.append((name, f"AssertionError: {e}"))
            print(f"  FAIL  {name}")
        except Exception as e:
            failed.append((name, f"{type(e).__name__}: {e}"))
            print(f"  ERR   {name}  ({type(e).__name__}: {e})")

    print()
    print(f"{len(tests) - len(failed)}/{len(tests)} passed")
    if failed:
        for name, err in failed:
            print(f"  {name}: {err}")
        sys.exit(1)
