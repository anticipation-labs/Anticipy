"""
Tier-1 unit tests for the deterministic helpers inside individual proactive
layer files. The cascade itself (cross-layer routing) is covered by
`test_proactive.py`; this file exercises the parse helpers, threshold math,
dataclass validators, and structural sanitizers that live inside each layer.

All surfaces tested here are pure-functional or stub-LLM — no live LLM calls.

Surfaces under test:
  - app.proactive.interpreter._parse_salience / _parse_extract
  - app.proactive.urgency._parse  (+ Urgency.channel mapping in types)
  - app.proactive.reversibility._parse
  - app.proactive.donna._parse
  - app.proactive.speaker_id._parse
  - app.proactive.dispatcher.Dispatcher.record / admit (window cutoff,
    fail-open paths, duplicate routing)

Run: cd engine && python -m pytest test_proactive_layers.py -v --tb=short
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.proactive.dispatcher import (  # noqa: E402
    AdmitVerdict,
    Dispatcher,
    _RecentDispatch,
)
from app.proactive.donna import DonnaVerdict, _parse as donna_parse  # noqa: E402
from app.proactive.interpreter import (  # noqa: E402
    SalienceVerdict,
    _parse_extract,
    _parse_salience,
)
from app.proactive.reversibility import (  # noqa: E402
    DEFAULT_REVERSIBILITY_ON_FAILURE,
    ReversibilityVerdict,
    _parse as rev_parse,
)
from app.proactive.speaker_id import (  # noqa: E402
    DEFAULT_IS_WEARER_ON_FAILURE,
    SpeakerVerdict,
    _parse as sid_parse,
)
from app.proactive.types import (  # noqa: E402
    Confidence,
    Decision,
    DecisionKind,
    Intent,
    NotificationChannel,
    Reversibility,
    Urgency,
)
from app.proactive.urgency import (  # noqa: E402
    DEFAULT_URGENCY_ON_FAILURE,
    _parse as urg_parse,
)


# --- Helpers -------------------------------------------------------------------


def _intent(verb: str = "search", text: str = "do the thing", **kw) -> Intent:
    return Intent.new(user_id="u", text=text, action_verb=verb, **kw)


def _decision(verb: str = "search", text: str = "do the thing", **kw) -> Decision:
    return Decision.new(
        intent=_intent(verb=verb, text=text, **kw),
        kind=DecisionKind.EXECUTE,
        confidence=Confidence(score=0.9),
        reversibility=Reversibility.REVERSIBLE,
        urgency=Urgency(level=2),
    )


# --- interpreter._parse_salience ----------------------------------------------


def test_parse_salience_empty_returns_unactionable():
    v = _parse_salience("")
    assert isinstance(v, SalienceVerdict)
    assert v.actionable is False
    assert v.confidence == 0.0


def test_parse_salience_invalid_json_returns_unactionable():
    v = _parse_salience("not json at all {{{")
    assert v.actionable is False
    assert v.confidence == 0.0
    assert "unparseable" in v.reasoning


def test_parse_salience_clamps_confidence_above_one():
    raw = json.dumps({"actionable": True, "confidence": 1.5, "reasoning": "x"})
    v = _parse_salience(raw)
    assert v.actionable is True
    assert v.confidence == 1.0


def test_parse_salience_clamps_negative_confidence_to_zero():
    raw = json.dumps({"actionable": True, "confidence": -0.3, "reasoning": "x"})
    v = _parse_salience(raw)
    assert v.confidence == 0.0


def test_parse_salience_non_object_top_level_fails_safe():
    raw = json.dumps([{"actionable": True, "confidence": 0.9}])
    v = _parse_salience(raw)
    assert v.actionable is False


def test_parse_salience_malformed_confidence_type():
    raw = json.dumps({"actionable": True, "confidence": "high"})
    v = _parse_salience(raw)
    assert v.actionable is False
    assert "malformed" in v.reasoning


# --- interpreter._parse_extract ------------------------------------------------


def test_parse_extract_empty_returns_no_intents():
    assert _parse_extract("", user_id="u") == []


def test_parse_extract_skips_intents_with_blank_verb():
    raw = json.dumps({
        "intents": [
            {"text": "go to store", "action_verb": "", "confidence": 0.9},
            {"text": "buy milk", "action_verb": "buy", "confidence": 0.9},
        ]
    })
    out = _parse_extract(raw, user_id="u")
    assert len(out) == 1
    assert out[0].intent.action_verb == "buy"


def test_parse_extract_skips_intents_with_blank_text():
    raw = json.dumps({
        "intents": [
            {"text": "", "action_verb": "buy", "confidence": 0.9},
        ]
    })
    out = _parse_extract(raw, user_id="u")
    assert out == []


def test_parse_extract_normalizes_dashes_and_spaces_in_verb():
    raw = json.dumps({
        "intents": [
            {"text": "send gift", "action_verb": "Send-Birthday Gift  ", "confidence": 0.8},
        ]
    })
    out = _parse_extract(raw, user_id="u")
    assert len(out) == 1
    # whitespace + dashes → single underscores, lowercased
    assert out[0].intent.action_verb == "send_birthday_gift"


def test_parse_extract_clamps_confidence_above_one():
    raw = json.dumps({
        "intents": [
            {"text": "x", "action_verb": "do", "confidence": 5.0},
        ]
    })
    out = _parse_extract(raw, user_id="u")
    assert out[0].confidence.score == 1.0


def test_parse_extract_handles_missing_intents_key():
    """When the LLM returns valid JSON without an `intents` key, return empty."""
    raw = json.dumps({"reasoning": "no actionable content"})
    assert _parse_extract(raw, user_id="u") == []


def test_parse_extract_preserves_evidence_chunk_ids_as_ints():
    raw = json.dumps({
        "intents": [
            {
                "text": "x",
                "action_verb": "do",
                "confidence": 0.7,
                "evidence_chunk_ids": ["3", 5, "7"],
            }
        ]
    })
    out = _parse_extract(raw, user_id="u")
    assert out[0].intent.evidence_chunk_ids == [3, 5, 7]


def test_parse_extract_skips_malformed_item_but_keeps_others():
    raw = json.dumps({
        "intents": [
            {"text": "ok one", "action_verb": "do", "confidence": 0.7},
            {"text": "broken", "action_verb": "fail", "evidence_chunk_ids": "not-a-list"},
            {"text": "ok two", "action_verb": "send", "confidence": 0.6},
        ]
    })
    out = _parse_extract(raw, user_id="u")
    # First and third survive; broken middle item is skipped
    verbs = [e.intent.action_verb for e in out]
    assert "do" in verbs and "send" in verbs


def test_parse_extract_uses_empty_dict_when_parameters_missing():
    raw = json.dumps({
        "intents": [
            {"text": "x", "action_verb": "do", "confidence": 0.5},
        ]
    })
    out = _parse_extract(raw, user_id="u")
    assert out[0].intent.parameters == {}


# --- urgency._parse + Urgency.channel mapping ----------------------------------


def test_urgency_parse_clamps_level_above_five():
    raw = json.dumps({"level": 99, "reasoning": "x"})
    u = urg_parse(raw)
    assert u.level == 5


def test_urgency_parse_clamps_level_below_one():
    raw = json.dumps({"level": -3, "reasoning": "x"})
    u = urg_parse(raw)
    assert u.level == 1


def test_urgency_parse_empty_fails_to_default():
    u = urg_parse("")
    assert u.level == DEFAULT_URGENCY_ON_FAILURE


def test_urgency_parse_unparseable_fails_to_default():
    u = urg_parse("garbage{{")
    assert u.level == DEFAULT_URGENCY_ON_FAILURE
    assert "unparseable" in u.reasoning


def test_urgency_parse_non_object_fails_to_default():
    u = urg_parse(json.dumps([1, 2, 3]))
    assert u.level == DEFAULT_URGENCY_ON_FAILURE


def test_urgency_parse_string_level_falls_back_to_default():
    raw = json.dumps({"level": "high"})
    u = urg_parse(raw)
    assert u.level == DEFAULT_URGENCY_ON_FAILURE


def test_urgency_channel_maps_each_level_distinctly():
    # 5→VOICE, 4→SMS, 3→PUSH, 2→IN_APP, 1→NOTED
    assert Urgency(level=5).channel == NotificationChannel.VOICE
    assert Urgency(level=4).channel == NotificationChannel.SMS
    assert Urgency(level=3).channel == NotificationChannel.PUSH
    assert Urgency(level=2).channel == NotificationChannel.IN_APP
    assert Urgency(level=1).channel == NotificationChannel.NOTED


# --- reversibility._parse ------------------------------------------------------


def test_reversibility_parse_unknown_string_maps_to_unknown_enum():
    raw = json.dumps({"reversibility": "unknown", "confidence": 0.5})
    v = rev_parse(raw)
    assert v.reversibility == Reversibility.UNKNOWN


def test_reversibility_parse_uppercase_string_normalized():
    raw = json.dumps({"reversibility": "REVERSIBLE", "confidence": 0.9})
    v = rev_parse(raw)
    assert v.reversibility == Reversibility.REVERSIBLE


def test_reversibility_parse_unrecognized_value_fails_to_irreversible():
    raw = json.dumps({"reversibility": "definitely_maybe", "confidence": 0.5})
    v = rev_parse(raw)
    assert v.reversibility == DEFAULT_REVERSIBILITY_ON_FAILURE
    assert v.reversibility == Reversibility.IRREVERSIBLE


def test_reversibility_parse_empty_fails_safe():
    v = rev_parse("")
    assert v.reversibility == Reversibility.IRREVERSIBLE
    assert "empty" in v.reasoning


def test_reversibility_parse_clamps_confidence():
    raw = json.dumps({"reversibility": "reversible", "confidence": 2.5})
    v = rev_parse(raw)
    assert v.confidence == 1.0


# --- donna._parse --------------------------------------------------------------


def test_donna_parse_null_string_rephrase_normalizes_to_none():
    raw = json.dumps({"should_refuse": True, "reason": "x", "rephrase": "null"})
    v = donna_parse(raw)
    assert v.should_refuse is True
    assert v.rephrase is None


def test_donna_parse_empty_rephrase_normalizes_to_none():
    raw = json.dumps({"should_refuse": True, "reason": "x", "rephrase": ""})
    v = donna_parse(raw)
    assert v.rephrase is None


def test_donna_parse_real_rephrase_preserved():
    raw = json.dumps({
        "should_refuse": True,
        "reason": "tone is harsh",
        "rephrase": "Try a softer tone.",
    })
    v = donna_parse(raw)
    assert v.rephrase == "Try a softer tone."


def test_donna_parse_empty_response_defaults_to_allow():
    v = donna_parse("")
    assert v.should_refuse is False


def test_donna_parse_unparseable_defaults_to_allow():
    v = donna_parse("not json")
    assert v.should_refuse is False


def test_donna_parse_clamps_negative_confidence():
    raw = json.dumps({"should_refuse": False, "confidence": -1.0})
    v = donna_parse(raw)
    assert v.confidence == 0.0


# --- speaker_id._parse ---------------------------------------------------------


def test_speaker_id_parse_empty_fails_open_to_wearer():
    v = sid_parse("")
    assert v.is_wearer is True
    assert v.is_wearer == DEFAULT_IS_WEARER_ON_FAILURE


def test_speaker_id_parse_unparseable_fails_open_to_wearer():
    v = sid_parse("{{ broken")
    assert v.is_wearer is True


def test_speaker_id_parse_other_with_high_confidence_drops():
    raw = json.dumps({"is_wearer": False, "confidence": 0.9, "reasoning": "x"})
    v = sid_parse(raw)
    assert v.is_wearer is False
    assert v.confidence == 0.9


# --- Dispatcher.record / admit ------------------------------------------------


def _run(coro):
    """Drive a coroutine to completion. Use `asyncio.run` so each call gets
    a fresh event loop — `get_event_loop()` raises after a prior loop has
    been closed by other tests in the same pytest process. Pure-isolation
    of test_proactive_layers passes either way; the issue only surfaces in
    the combined tier-1 run."""
    return asyncio.run(coro)


def test_dispatcher_admit_with_no_recent_history_admits_without_llm():
    """No history, no LLM call needed — admit fast-path."""
    d = Dispatcher(llm_call=None)
    verdict = _run(d.admit(_decision()))
    assert verdict.admit is True
    assert verdict.duplicate_of is None
    assert verdict.reasoning == "no_recent_or_no_llm"


def test_dispatcher_admit_with_recent_but_no_llm_admits():
    """Even with prior dispatch, no LLM means no dedup — fail open."""
    d = Dispatcher(llm_call=None)
    d.record(_decision(verb="search", text="find recipe"))
    verdict = _run(d.admit(_decision(verb="lookup", text="find that recipe")))
    assert verdict.admit is True


def test_dispatcher_window_cutoff_drops_stale_dispatches():
    """A dispatch older than the window must not be presented to the LLM at all."""
    captured = {}

    async def fake_llm(sys_prompt: str, user_prompt: str) -> str:
        captured["user"] = user_prompt
        return json.dumps({"duplicate_of": None, "reasoning": "distinct"})

    d = Dispatcher(llm_call=fake_llm, window_seconds=10.0)
    # Manually back-date a record so it falls outside the window.
    d._recent.append(_RecentDispatch(
        decision_id="old",
        intent_id="i_old",
        verb="ancient",
        text="ancient task",
        parameters={},
        timestamp=time.time() - 999.0,  # well outside the 10s window
    ))
    verdict = _run(d.admit(_decision()))
    # All recent were stale → admit short-circuits without consulting the LLM
    assert verdict.admit is True
    assert verdict.reasoning == "no_recent_or_no_llm"
    assert "user" not in captured


def test_dispatcher_admit_marks_duplicate_when_model_says_so():
    async def fake_llm(_sys: str, _user: str) -> str:
        # 0 references the only recent dispatch.
        return json.dumps({"duplicate_of": 0, "reasoning": "same goal"})

    d = Dispatcher(llm_call=fake_llm)
    prior = _decision(verb="book", text="book physical with Dr Chen")
    d.record(prior)
    verdict = _run(d.admit(_decision(verb="schedule", text="schedule physical Dr Chen")))
    assert verdict.admit is False
    assert verdict.duplicate_of == prior.decision_id
    assert "same" in verdict.reasoning


def test_dispatcher_admit_distinct_when_model_returns_null():
    async def fake_llm(_sys: str, _user: str) -> str:
        return json.dumps({"duplicate_of": None, "reasoning": "distinct"})

    d = Dispatcher(llm_call=fake_llm)
    d.record(_decision(verb="book", text="book Dr Chen"))
    verdict = _run(d.admit(_decision(verb="email", text="email Mark project")))
    assert verdict.admit is True
    assert verdict.duplicate_of is None


def test_dispatcher_admit_bad_json_fails_open():
    async def fake_llm(_sys: str, _user: str) -> str:
        return "this is not json at all"

    d = Dispatcher(llm_call=fake_llm)
    d.record(_decision())
    verdict = _run(d.admit(_decision()))
    assert verdict.admit is True
    assert verdict.reasoning == "bad_json_fail_open"


def test_dispatcher_admit_dup_id_out_of_range_fails_open():
    async def fake_llm(_sys: str, _user: str) -> str:
        # Only 1 recent dispatch (index 0). Index 99 is OOB.
        return json.dumps({"duplicate_of": 99, "reasoning": "x"})

    d = Dispatcher(llm_call=fake_llm)
    d.record(_decision())
    verdict = _run(d.admit(_decision()))
    assert verdict.admit is True
    assert verdict.reasoning == "dup_id_out_of_range"


def test_dispatcher_admit_non_int_dup_id_fails_open():
    async def fake_llm(_sys: str, _user: str) -> str:
        return json.dumps({"duplicate_of": "not-a-number", "reasoning": "x"})

    d = Dispatcher(llm_call=fake_llm)
    d.record(_decision())
    verdict = _run(d.admit(_decision()))
    assert verdict.admit is True
    assert verdict.reasoning == "bad_dup_id_fail_open"


def test_dispatcher_admit_timeout_fails_open():
    async def slow_llm(_sys: str, _user: str) -> str:
        await asyncio.sleep(5.0)
        return "{}"

    d = Dispatcher(llm_call=slow_llm, timeout_seconds=0.05)
    d.record(_decision())
    verdict = _run(d.admit(_decision()))
    assert verdict.admit is True
    assert verdict.reasoning == "timeout_fail_open"


def test_dispatcher_history_size_evicts_oldest():
    """history_size acts as a cap; the deque drops the oldest entry on overflow."""
    d = Dispatcher(llm_call=None, history_size=2)
    d.record(_decision(verb="a", text="task A"))
    d.record(_decision(verb="b", text="task B"))
    d.record(_decision(verb="c", text="task C"))
    # Only the last two should be kept.
    verbs = [r.verb for r in d._recent]
    assert verbs == ["b", "c"]
