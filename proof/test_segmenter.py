#!/usr/bin/env python3
"""The boundary rules, tested without a database, a network, or a model.

Every case here is one Omar actually described. Run:
  PYTHONPATH=. python3 proof/test_segmenter.py
"""
import sys
from datetime import datetime, timedelta, timezone

from brain.segmenter import (CONTINUE_S, GATE_BAND_S, LINK_MAX_S, MAX_SEGMENT_S,
                             capture_span, decide_link, is_late, parse_ts,
                             proper_nouns, should_close)

PASS, FAIL = [], []


def check(name, cond):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name)


T0 = datetime(2026, 7, 31, 18, 0, 0, tzinfo=timezone.utc)


def seg(summary="", entities='[]', last=T0, started=T0):
    from brain.segmenter import iso
    return {"id": "s1", "summary": summary, "entities": entities,
            "last_speech_at": iso(last), "started_at": iso(started),
            "ended_at": iso(last)}


# ---------------------------------------------------------------- the gaps

def test_short_gap_is_the_same_conversation():
    """Omar's case (a): a 10-40s gap mid-conversation is NOT an ending."""
    for gap in (2, 10, 25, 40, 44):
        d, _ = decide_link(gap, "and the demo day thing", seg())
        check(f"{gap}s gap continues the conversation", d == "append")


def test_bathroom_break_relinks_on_a_shared_name():
    """Omar's case (b): five minutes away, comes back to the same topic."""
    prior = seg(summary="booking dinner at Cactus with Priya", entities='["cactus","priya"]')
    d, why = decide_link(300, "So what time did we say for Cactus", prior)
    check("5-min gap + shared name relinks", d == "link")


def test_bathroom_break_relinks_on_shared_words():
    prior = seg(summary="the invoice for the launch plan", entities='[]')
    d, _ = decide_link(240, "we still need to sort that invoice and the launch numbers", prior)
    check("shared content words relink", d == "link")


def test_unrelated_speech_after_a_long_gap_is_new():
    prior = seg(summary="booking dinner at Cactus", entities='["cactus"]')
    d, _ = decide_link(900, "I need to renew the car insurance before September", prior)
    check("unrelated + long gap starts a new conversation", d == "new")


def test_beyond_twenty_minutes_never_links():
    prior = seg(summary="booking dinner at Cactus", entities='["cactus"]')
    d, _ = decide_link(LINK_MAX_S + 1, "what time is Cactus open", prior)
    check("past 20 minutes it is always a new conversation", d == "new")


def test_anaphoric_resumption_is_a_continuation():
    prior = seg(summary="the demo day schedule", entities='["residencies"]')
    d, _ = decide_link(120, "anyway, where were we", prior)
    check("'anyway, where were we' relinks", d == "link")


def test_ambiguous_cases_escalate_not_guess():
    prior = seg(summary="dinner plans", entities='["cactus"]')
    d, _ = decide_link(120, "I should probably book the flights for that trip soon", prior)
    check("substantive + recent + no overlap escalates", d == "escalate")


# ------------------------------------------------------------ closing rules

def test_conversation_closes_only_on_real_silence():
    live = seg(last=T0)
    closed, _ = should_close(live, T0 + timedelta(seconds=CONTINUE_S - 5))
    check("still open before the silence window", not closed)
    closed, _ = should_close(live, T0 + timedelta(seconds=CONTINUE_S + 1))
    check("closes after real silence", closed)


def test_runaway_conversation_is_force_closed():
    long_one = seg(started=T0, last=T0 + timedelta(seconds=MAX_SEGMENT_S + 10))
    closed, why = should_close(long_one, T0 + timedelta(seconds=MAX_SEGMENT_S + 20))
    check("a 30-minute conversation force-closes", closed and "force" in why)


# ------------------------------------------------- capture time, not arrival

def test_capture_time_beats_arrival_time():
    """THE rule: backlog audio must be placed by when it was SPOKEN. Judging
    by arrival shatters one walk-outside conversation into many."""
    spoken = "2026-07-31T18:00:00.000Z"
    arrived_much_later = "2026-07-31 18:40:00.000Z"
    start, _ = capture_span({"capture_started_at": spoken, "created": arrived_much_later})
    check("capture time wins over arrival time", start == parse_ts(spoken))


def test_falls_back_to_arrival_only_when_capture_is_absent():
    start, _ = capture_span({"created": "2026-07-31 18:00:00.000Z"})
    check("old app builds still place correctly", start is not None)


def test_stale_speech_is_remembered_but_never_acted_on():
    old = {"capture_started_at": "2026-07-31T10:00:00.000Z"}
    check("6h-old speech is marked late", is_late(old, T0 + timedelta(hours=2)))
    fresh = {"capture_started_at": "2026-07-31T17:50:00.000Z"}
    check("recent speech is not late", not is_late(fresh, T0))


def test_names_are_extracted_for_relinking():
    got = proper_nouns("I told Priya we would meet at Cactus Club on Monday")
    check("names picked up for relinking", {"priya", "cactus"} <= got)


for fn in list(globals().values()):
    if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
        fn()

print(f"\nsegmenter: {len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
