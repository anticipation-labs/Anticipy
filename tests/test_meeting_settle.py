"""The digest may not fire into the middle of the meeting it is digesting.

Locked against the REAL recorded call (research/evals/call-2026-08-23-tejas):
27.4 minutes, with mid-call silences of 67s, 90s and 310s — the longest at
only 35% through. The first settle window (90s fixed) would have ended that
meeting twice while it was still happening. These tests replay the actual
timestamps through the actual detector.
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import worker

EVAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "research", "evals", "call-2026-08-23-tejas",
                    "call_transcripts.json")


def _timestamps():
    rows = json.load(open(EVAL))
    def ts(r):
        raw = (r.get("capture_started_at") or r.get("created") or "").replace(
            "Z", "+00:00").replace(" ", "T")
        return datetime.fromisoformat(raw).timestamp()
    return sorted(ts(r) for r in rows)


def _reset():
    worker.MEETING_ARRIVALS = []
    worker.MEETING_ARMED = False
    worker.MEETING_MAX_GAP = 0.0
    worker.MEETING_LOW_SINCE = 0.0
    worker.MEETING_ARMED_AT = 0.0
    worker.DIGEST_PENDING = None
    worker.LAST_HEARD_AT = 0.0


def test_recorded_call_never_settles_mid_call():
    _reset()
    stamps = _timestamps()
    armed_ever = False
    for prev, cur in zip(stamps, stamps[1:]):
        worker.meeting_heard(now=prev)
        if worker.MEETING_ARMED:
            armed_ever = True
            # The digest check runs continuously DURING the gap; the window
            # in force throughout the gap is the one computed before the
            # next line lands. It must outlast every real mid-call silence.
            assert cur - prev < worker.meeting_settle_s(), (
                f"settle window {worker.meeting_settle_s():.0f}s loses to a "
                f"real mid-call silence of {cur - prev:.0f}s — the digest "
                "would fire into the meeting")
    worker.meeting_heard(now=stamps[-1])
    assert armed_ever, "the detector never armed on a 137-line call"


def test_the_meeting_does_eventually_end():
    _reset()
    stamps = _timestamps()
    for t in stamps:
        worker.meeting_heard(now=t)
    assert worker.MEETING_ARMED
    # Ten minutes of true silence must always be believed, whatever was
    # learned — the ceiling guarantees the digest is never later than that.
    end = stamps[-1] + worker.MEETING_SETTLE_CEIL_S + 1
    assert end - stamps[-1] >= worker.meeting_settle_s(), (
        "the settle window exceeded its own ceiling")


def test_gap_learning_only_counts_armed_gaps():
    _reset()
    # Two lines an hour apart BEFORE arming must not teach a 2-hour window.
    worker.meeting_heard(now=1000.0)
    worker.meeting_heard(now=4600.0)
    for i in range(12):
        worker.meeting_heard(now=5000.0 + i * 10)
    assert worker.meeting_settle_s() <= worker.MEETING_SETTLE_CEIL_S
    assert worker.MEETING_MAX_GAP < 3600.0, (
        "pre-meeting silence was counted as a mid-meeting gap")


class _DeadAnticipy:
    def meeting_digest(self): return None
    def clear_meeting_held(self): pass


def test_a_lived_in_evening_does_not_stay_a_meeting_forever():
    """Finding 5 of the Law-6 review: the armed latch plus a 360-600s settle
    made 'in a meeting' the permanent state of a home — dinner conversation
    arms it, then one stray line every few minutes keeps it armed all
    evening, muting her completely. Sustained sub-density must end it."""
    _reset()
    t = 1000.0
    for i in range(12):                       # dinner talk arms it
        worker.meeting_heard(now=t + i * 10)
    assert worker.MEETING_ARMED
    t += 120
    # An evening of one stray line every 5 minutes: never silent long
    # enough for the settle window, but sparse the whole time.
    disarmed_by = None
    for i in range(12):
        t += 300
        worker.LAST_HEARD_AT = t
        worker.meeting_heard(now=t)
        worker.maybe_meeting_digest(_DeadAnticipy(), now=t + 150)
        if not worker.MEETING_ARMED:
            disarmed_by = t + 150
            break
    assert disarmed_by is not None, (
        "an hour of sparse ambience never ended the meeting — she would "
        "stay mute all evening")
    assert disarmed_by - 1120 <= 3 * worker.MEETING_SETTLE_CEIL_S, (
        "disarm took longer than three ceilings — too slow to matter")


def test_recorded_call_never_ends_via_the_sparse_path_either():
    """The low-density decay must not end the REAL call mid-way: its 310s
    silence is followed by dense talk, so the sparse clock has to reset
    before it ever reaches a full settle window."""
    _reset()
    stamps = _timestamps()
    for prev, cur in zip(stamps, stamps[1:]):
        worker.LAST_HEARD_AT = prev
        worker.meeting_heard(now=prev)
        if worker.MEETING_ARMED and worker.MEETING_LOW_SINCE:
            assert cur - worker.MEETING_LOW_SINCE < worker.meeting_settle_s(), (
                "the sparse clock outran the settle window inside the real "
                "call — the digest would fire mid-meeting")
    worker.meeting_heard(now=stamps[-1])
    assert worker.MEETING_ARMED
