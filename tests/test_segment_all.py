"""How many conversations was that?

Until now that question could not be asked. The boundary rules existed, but the
only way to run them was one turn at a time against PocketBase, so "is this one
call or three?" could only be answered by running the whole system and looking
at a screenshot. Omar's screenshot said three. It was one.

`segment_all(turns)` is the pure entry point. These pin the law it exists for:

    THE ANSWER DEPENDS ON WHEN THINGS WERE SPOKEN AND ON NOTHING ELSE.

The pendant is store-and-forward. It buffers and flushes, so arrival order is
not speech order and a backlog can land in one lump minutes after the fact. Any
boundary that reads arrival time shatters one phone call into several — the bug
Omi ships as #6551, and the one in Omar's screenshot.
"""
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.segmenter import (CONTINUE_S, MAX_SEGMENT_S, parse_ts,  # noqa: E402
                             segment_all)

BASE = 1_760_000_000

# Verbatim from the gate: the sales call that came back as three cards.
THE_CALL = [
    ("hey how's it going", 0),
    ("my name is Angie I'm calling from a startup working with trades", 20),
    ("I was wanting to grab a couple minutes of feedback", 45),
    ("not able to speak to Joe Baxter", 70),
    ("I'm pretty good thanks", 95),
    ("thank you so much I appreciate that", 120),
]


def turn(text, offset, arrived=None, ident=None):
    return {"id": ident or f"t{offset}",
            "text": text,
            "capture_started_at": BASE + offset,
            "capture_ended_at": BASE + offset + 4,
            "created": BASE + (offset if arrived is None else arrived)}


def texts(conversations):
    return [[t["text"] for t in c] for c in conversations]


# ------------------------------------------------------------ the screenshot

def test_one_phone_call_is_one_conversation():
    out = segment_all([turn(t, o) for t, o in THE_CALL])
    assert len(out) == 1, texts(out)
    assert len(out[0]) == len(THE_CALL)


def test_the_turns_come_back_in_the_order_they_were_spoken():
    out = segment_all([turn(t, o) for t, o in THE_CALL])
    assert [t["text"] for t in out[0]] == [t for t, _ in THE_CALL]


# --------------------------------------------------------------- THE LAW

def test_every_delivery_order_gives_the_same_answer():
    """The whole law, exhaustively. Six turns, all 720 orderings, each one
    delivered as a late lump so arrival time says something different from
    capture time every single run."""
    expected = texts(segment_all([turn(t, o) for t, o in THE_CALL]))
    for order in itertools.permutations(range(len(THE_CALL))):
        shuffled = []
        for slot, i in enumerate(order):
            text, off = THE_CALL[i]
            shuffled.append(turn(text, off, arrived=900 + slot))
        assert texts(segment_all(shuffled)) == expected, order


def test_a_backlog_landing_in_one_lump_does_not_merge_two_calls():
    """Two real conversations an hour apart, flushed together seconds apart.
    Arrival says one conversation; capture says two, and capture is right."""
    turns = [turn(t, o, arrived=5000 + i) for i, (t, o) in enumerate(THE_CALL)]
    turns += [turn(t, 3600 + o, arrived=5100 + i)
              for i, (t, o) in enumerate([("right where were we on the pricing", 0),
                                          ("yeah send me the deck", 30)])]
    assert len(segment_all(turns)) == 2


def test_arrival_time_alone_never_changes_the_answer():
    spoken = [turn(t, o) for t, o in THE_CALL]
    for arrival in (0, 1, 999, 100_000):
        moved = [dict(t, created=BASE + arrival) for t in spoken]
        assert texts(segment_all(moved)) == texts(segment_all(spoken))


# ------------------------------------------------------- real boundaries

def test_conversations_hours_apart_stay_apart():
    out = segment_all([
        turn("book a table at Cactus for tomorrow night", 0),
        turn("actually make it seven thirty", 20),
        turn("I need to renew the car insurance before it lapses", 20_000),
    ])
    assert len(out) == 2, texts(out)


def test_a_long_call_is_still_one_call():
    """MAX_SEGMENT_S bounds the size of a database row. It does not mean the
    person stopped talking. A forty-minute call is one call."""
    turns = [turn(f"and another thing number {i}", i * 30)
             for i in range(int(MAX_SEGMENT_S / 30) + 20)]
    assert (turns[-1]["capture_started_at"] - turns[0]["capture_started_at"]
            > MAX_SEGMENT_S)
    assert len(segment_all(turns)) == 1


def test_a_silence_longer_than_the_continue_window_can_end_it():
    close = segment_all([turn("the roof needs doing before winter", 0),
                         turn("get three quotes on the roof", CONTINUE_S - 5)])
    assert len(close) == 1
    apart = segment_all([turn("the roof needs doing before winter", 0),
                         turn("remind me to cancel that gym membership", 20_000)])
    assert len(apart) == 2


# --------------------------------------------------------- times of any shape

def test_the_same_moment_written_four_ways_groups_the_same():
    """Epoch seconds, epoch milliseconds, an ISO string and PocketBase's
    space-separated form are all the same instant. An unreadable capture time
    makes a turn unplaceable, and an unplaceable turn is DROPPED — losing what
    somebody said because a number arrived where a string was expected is not a
    failure this is allowed to have."""
    shapes = [
        lambda n: n,
        lambda n: n * 1000,
        lambda n: parse_ts(n).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        lambda n: parse_ts(n).strftime("%Y-%m-%d %H:%M:%S.000Z"),
        lambda n: str(n),
    ]
    answers = []
    for shape in shapes:
        turns = [{"id": f"t{o}", "text": t,
                  "capture_started_at": shape(BASE + o),
                  "capture_ended_at": shape(BASE + o + 4)} for t, o in THE_CALL]
        answers.append(texts(segment_all(turns)))
    assert all(a == answers[0] for a in answers), answers
    assert len(answers[0]) == 1


def test_a_time_that_is_not_a_time_is_refused_not_guessed_at():
    for junk in (None, "", 0, -1, True, False, 20_260_806, "tomorrow",
                 "not a date", 12.5, [], {}):
        assert parse_ts(junk) is None, junk


def test_real_times_survive_in_every_shape():
    iso = parse_ts("2026-08-06T19:09:00Z")
    assert iso is not None and iso.tzinfo is not None
    assert parse_ts("2026-08-06 19:09:00Z") == iso
    assert parse_ts(iso.timestamp()) == iso
    assert parse_ts(int(iso.timestamp() * 1000)) == iso
    assert parse_ts(str(int(iso.timestamp()))) == iso


def test_capture_time_beats_arrival_time_when_both_are_present():
    """The fallback to `created` exists only for old app builds that posted no
    capture time. Where a capture time exists it must WIN — otherwise the
    fallback quietly becomes the rule."""
    out = segment_all([
        turn("first thing he said", 0, arrived=9_000),
        turn("second thing he said", 20, arrived=0),
    ])
    assert [t["text"] for t in out[0]] == ["first thing he said",
                                           "second thing he said"]


def test_an_old_build_with_only_an_arrival_time_still_works():
    turns = [{"id": f"t{o}", "text": t, "created": BASE + o} for t, o in THE_CALL]
    assert len(segment_all(turns)) == 1


# ---------------------------------------------------------------- the wall

def test_a_turn_with_no_usable_time_is_left_out_not_placed_at_random():
    out = segment_all([turn("real speech", 0),
                       {"id": "x", "text": "no time at all"},
                       turn("more real speech", 20)])
    assert len(out) == 1
    assert [t["text"] for t in out[0]] == ["real speech", "more real speech"]


def test_junk_never_raises_and_never_invents():
    assert segment_all([]) == []
    assert segment_all(None) == []
    assert segment_all([None, "a string", 7, []]) == []
    assert segment_all([{"id": "x"}]) == []
    assert segment_all([{"capture_started_at": "nonsense"}]) == []


def test_nothing_is_lost_and_nothing_is_duplicated():
    turns = [turn(t, o) for t, o in THE_CALL]
    turns += [turn("unrelated much later", 40_000)]
    out = segment_all(turns)
    seen = [t["id"] for c in out for t in c]
    assert sorted(seen) == sorted(t["id"] for t in turns)
    assert len(seen) == len(set(seen))


def test_the_input_list_is_not_modified():
    turns = [turn(t, o) for t, o in THE_CALL]
    before = [dict(t) for t in turns]
    segment_all(turns)
    assert turns == before


def test_turns_spoken_in_the_same_second_are_ordered_by_content_not_arrival():
    """A tie broken by `created` would put arrival time back in through the
    side door — deterministic, repeatable, and still wrong.

    Written because a mutation that did exactly that survived: comparing two
    INPUT orders cannot catch it, since sorting by arrival is stable whichever
    order the list came in. The two arrival times have to be swapped instead.
    """
    def pair(a_arrived, b_arrived):
        return [{"id": "aaa", "text": "alpha", "capture_started_at": BASE,
                 "capture_ended_at": BASE, "created": BASE + a_arrived},
                {"id": "bbb", "text": "bravo", "capture_started_at": BASE,
                 "capture_ended_at": BASE, "created": BASE + b_arrived}]
    assert texts(segment_all(pair(500, 0))) == texts(segment_all(pair(0, 500)))
    assert texts(segment_all(pair(500, 0))) == texts(segment_all(pair(0, 500)[::-1]))


# ------------------------------------------------------- a resumed subject

def test_picking_a_subject_back_up_is_the_same_conversation():
    """Past the 45-second window the rules look at what was SAID. A shared name
    is the strongest free signal that a subject resumed, and a resumed subject
    is the same conversation to anyone reading the feed — that is the whole
    point of threading it.

    Written because a mutation that dropped `link` and kept only `append`
    survived every other check: the branch was never exercised at all.
    """
    out = segment_all([
        turn("we should get dinner at Cactus Club this week", 0),
        turn("Cactus Club on Thursday then", 90),
    ])
    assert len(out) == 1, texts(out)


def test_a_shared_topic_is_the_same_conversation_even_without_a_name():
    out = segment_all([
        turn("the roof quotes came back higher than the insurance covers", 0),
        turn("chase the roof quotes and the insurance again", 120),
    ])
    assert len(out) == 1, texts(out)


def test_a_different_subject_after_the_window_is_a_different_conversation():
    """The other side of the same branch. If everything linked, there would
    only ever be one conversation and the grouping would mean nothing."""
    out = segment_all([
        turn("the roof quotes came back higher than the insurance covers", 0),
        turn("Priya needs the quarterly numbers before Friday's board meeting", 700),
    ])
    assert len(out) == 2, texts(out)


# ------------------------------------------------------------- the wiring

def test_the_gate_can_actually_call_it():
    """A leg that cannot be tested does not pass. This is the shape the
    scoreboard depends on."""
    from brain import segmenter
    fn = getattr(segmenter, "segment_all", None)
    assert callable(fn)
    out = fn([turn(t, o) for t, o in THE_CALL])
    assert isinstance(out, list) and out and isinstance(out[0], list)
    assert isinstance(out[0][0], dict)
