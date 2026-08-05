"""The brain must read his day in the order he SAID it, not the order the
network delivered it.

This is Omi #6551 in our shape. Their chunks raced each other into the
database in parallel; ours arrive one at a time, in a strict single-threaded
loop, but sorted by PocketBase's `created` — the moment the row landed. A
phone that buffers (offline, backgrounded, no signal, a call holding the mic)
then hands the brain a flushed lump in delivery order, and a plan
reconstructed from shuffled turns is a different plan.

Both halves of the degrade matter as much as the fix and are tested here: no
stamp must behave exactly as today, and an implausible stamp must be refused
rather than obeyed. The second is not hypothetical — verification on a sister
branch found that trusting a phone-supplied stamp with no plausibility check
would let one naive-local-time build silence her permanently.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import brain.worker as W  # noqa: E402


def iso(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + "Z"


NOW = datetime(2026, 8, 5, 12, 0, 0, tzinfo=timezone.utc)


def ev(i, created, spoken=None):
    row = {"id": i, "text": i, "created": iso(created)}
    if spoken is not None:
        row["spoken_at"] = iso(spoken)
    return row


def order(rows):
    return [r["id"] for r in sorted(rows, key=W.capture_key)]


# ------------------------------------------------------------ the fix

def test_a_flushed_backlog_is_read_in_speech_order():
    """Three lines spoken 20s apart, all delivered in one lump 40 minutes
    later, and delivered in the WRONG order. This is the Angie call."""
    flush = NOW + timedelta(minutes=40)
    rows = [
        ev("third",  flush,                       NOW + timedelta(seconds=40)),
        ev("first",  flush + timedelta(seconds=1), NOW),
        ev("second", flush + timedelta(seconds=2), NOW + timedelta(seconds=20)),
    ]
    assert order(rows) == ["first", "second", "third"]


def test_live_lines_are_unaffected():
    rows = [ev("b", NOW + timedelta(seconds=5), NOW + timedelta(seconds=5)),
            ev("a", NOW, NOW)]
    assert order(rows) == ["a", "b"]


def test_buffered_lines_sort_before_live_ones_spoken_later():
    """A line spoken at 09:00 and flushed at 12:00 must still be read before
    one spoken at 11:00 — otherwise his morning arrives after his lunch."""
    rows = [
        ev("said_at_11", NOW - timedelta(hours=1), NOW - timedelta(hours=1)),
        ev("said_at_09", NOW, NOW - timedelta(hours=3)),
    ]
    assert order(rows) == ["said_at_09", "said_at_11"]


# ---------------------------------------------------- the honesty wall

def test_no_stamp_at_all_is_exactly_todays_behaviour():
    """Every build before this one sends no spoken_at. Those rows must order
    by arrival, identically to the code this replaces."""
    rows = [ev("c", NOW + timedelta(seconds=2)),
            ev("a", NOW),
            ev("b", NOW + timedelta(seconds=1))]
    assert order(rows) == ["a", "b", "c"]


def test_a_mixed_fleet_does_not_scramble():
    """The state a rollout actually passes through: one device updated, one
    not. Neither may be reordered relative to its own arrival."""
    rows = [ev("old2", NOW + timedelta(seconds=30)),
            ev("new1", NOW + timedelta(seconds=20), NOW + timedelta(seconds=10)),
            ev("old1", NOW + timedelta(seconds=5))]
    assert order(rows) == ["old1", "new1", "old2"]


def test_an_implausible_stamp_is_refused_not_obeyed():
    """A device stamping naive local time from the wrong side of the world.
    We must fall back to arrival, not act on a timestamp hours out."""
    rows = [ev("sane", NOW, NOW),
            ev("wrong_clock", NOW + timedelta(seconds=1),
               NOW - timedelta(hours=11))]
    assert order(rows) == ["sane", "wrong_clock"]
    assert W.capture_key(rows[1]) == W.capture_key(
        {"created": rows[1]["created"]}), "must fall all the way back to arrival"


def test_a_stamp_from_the_future_is_refused():
    rows = [ev("now", NOW, NOW),
            ev("future", NOW + timedelta(seconds=1), NOW + timedelta(days=2))]
    assert order(rows) == ["now", "future"]


def test_garbage_stamps_never_raise():
    for junk in ("", "   ", "not-a-date", "2026-13-45T99:99:99Z", None, 5, [], {}):
        row = {"id": "x", "created": iso(NOW), "spoken_at": junk}
        assert W.capture_key(row) == W.capture_key({"created": iso(NOW)})


def test_a_row_with_no_timestamps_at_all_does_not_raise():
    assert W.capture_key({"id": "x"}) == 0.0


def test_both_offset_forms_parse_to_the_same_instant():
    a = {"created": "2026-08-05 12:00:00.000Z"}
    b = {"created": "2026-08-05T12:00:00.000+00:00"}
    assert W.capture_key(a) == W.capture_key(b)


def test_the_skew_window_is_generous_enough_for_a_real_backlog():
    """A genuinely long offline stretch must NOT be mistaken for a broken
    clock. Four hours buffered is a flight, not a bug."""
    row = ev("long_flight", NOW, NOW - timedelta(hours=4))
    assert W.capture_key(row) == W._ts(row["spoken_at"]), \
        "a 4h backlog was thrown away as if the clock were broken"


# ------------------------------------------------------------ paging

def test_the_page_is_wider_than_the_slice():
    """A re-sort can only reorder rows it can see. If the page equals the
    batch, the earliest-spoken line can sit on page two and be read late
    anyway — the fix would silently do nothing."""
    assert W.PAGE > W.BATCH


def test_the_widening_is_additive_not_multiplicative():
    """A sister branch shipped `limit * 8` for this and turned a 7-line read
    into 56 rows on a call made twice."""
    assert W.PAGE - W.BATCH <= 32
    assert W.PAGE < W.BATCH * 2


def test_fetch_unprocessed_sorts_and_slices(monkeypatch):
    flush = NOW + timedelta(minutes=40)
    rows = [ev(f"n{i}", flush + timedelta(seconds=i),
               NOW + timedelta(seconds=(W.PAGE - i)))
            for i in range(W.PAGE)]

    class R:
        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"items": list(rows)}

    seen = {}

    def fake_get(url, params=None, timeout=None):
        seen.update(params or {})
        return R()

    monkeypatch.setattr(W.pb, "get", fake_get)
    out = W.fetch_unprocessed()

    assert seen["perPage"] == W.PAGE, "must read wider than it returns"
    assert len(out) == W.BATCH, "must hand the loop one batch"
    keys = [W.capture_key(r) for r in out]
    assert keys == sorted(keys), "returned out of speech order"
    # The earliest-SPOKEN line was delivered LAST; it must still come first.
    assert out[0]["id"] == f"n{W.PAGE - 1}"
