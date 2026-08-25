"""Day zero's first proactive touch: a brand-new owner gets ONE hello.

The rules live outside any model: only a freshly created profile earns a
welcome, one durable stamp per number stops repeats forever, an old
profile discovered without a stamp is stamped silently — never texted —
and the hello never arrives in the middle of the night.

THE CLOCK IN THESE TESTS IS PINNED ON PURPOSE. Every `now` here is built
by `_at()` at a named hour in the worker's own zone. Reading `time.time()`
instead would make the whole file pass or fail depending on what time the
suite happened to run — and this suite runs overnight.
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import pb  # noqa: E402
from brain import worker  # noqa: E402
from brain.worker import maybe_welcome_new_owner  # noqa: E402


class _Reply:
    def __init__(self, payload, ok=True):
        self._p, self.ok = payload, ok

    def json(self):
        return self._p


class _Anticipy:
    def __init__(self, phone="+16045550123"):
        self.owner_phone = phone
        self.sent = []

    def _voice(self, ctx):
        return "Hey — I'm here."

    def notify_owner(self, msg, channel="sms"):
        self.sent.append(msg)
        return {"ok": True}


def _iso(ts):
    from datetime import timezone
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S.000Z")


def _at(hour, day=25, minute=0):
    """A timestamp at a named hour in the worker's own clock zone."""
    return datetime(2026, 8, day, hour, minute,
                    tzinfo=worker.CLOCK_TZ).timestamp()


# Named so the intent survives a change to CLOCK_QUIET_START/END: whatever
# the constants say, these two are the middle of the night and mid-morning.
DEEP_NIGHT = _at(1)
MID_MORNING = _at(10)


def _rig(monkeypatch, created_ts, saved=None):
    """Wire the profile lookup, and capture every durable save as the JSON
    the clock-state file would actually hold — so a state that cannot be
    written to disk fails here rather than in production."""
    monkeypatch.setattr(pb, "get", lambda url, params=None, timeout=None, **k:
                        _Reply({"items": [{"created": _iso(created_ts),
                                           "first_name": "Omar"}]}))

    def _save(s):
        if saved is not None:
            saved.append(json.loads(json.dumps(s)))

    monkeypatch.setattr(worker, "_save_clock_state", _save)
    monkeypatch.setattr(worker, "post_event", lambda *a, **k: None)


def test_a_fresh_onboarding_gets_exactly_one_welcome(monkeypatch):
    now = MID_MORNING
    _rig(monkeypatch, now - 60)
    a, state = _Anticipy(), {}
    assert maybe_welcome_new_owner(a, state, now=now) is True
    assert len(a.sent) == 1
    # The stamp holds: a second poll says nothing.
    assert maybe_welcome_new_owner(a, state, now=now) is False
    assert len(a.sent) == 1


def test_an_old_profile_is_stamped_silently_never_texted(monkeypatch):
    now = MID_MORNING
    _rig(monkeypatch, now - 7 * 24 * 3600)
    a, state = _Anticipy(), {}
    assert maybe_welcome_new_owner(a, state, now=now) is False
    assert a.sent == []
    # And it is stamped, so the fresh-profile branch can never fire later.
    digits = "6045550123"
    assert digits in state.get("welcomed_phones", [])


def test_no_phone_means_no_welcome(monkeypatch):
    now = MID_MORNING
    _rig(monkeypatch, now - 60)
    a = _Anticipy(phone="")
    assert maybe_welcome_new_owner(a, {}, now=now) is False
    assert a.sent == []


def test_a_failed_send_leaves_no_stamp_so_it_retries(monkeypatch):
    now = MID_MORNING
    _rig(monkeypatch, now - 60)
    a, state = _Anticipy(), {}
    a.notify_owner = lambda msg, channel="sms": None
    assert maybe_welcome_new_owner(a, state, now=now) is False
    assert "6045550123" not in state.get("welcomed_phones", [])


def test_backend_failure_never_crashes_or_texts(monkeypatch):
    monkeypatch.setattr(pb, "get", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("down")))
    a = _Anticipy()
    assert maybe_welcome_new_owner(a, {}, now=MID_MORNING) is False
    assert a.sent == []


# --------------------------------------------------------------------------
# THE FIRST WORDS RESPECT THE NIGHT — stranger_gate.py leg 6.
#
# The gate proves the clock CAN stop this send. It cannot prove which side
# of the clock speaks: a guard written backwards, texting ONLY at 3am, has
# the same syntax tree. These tests pin the direction, and they pin the
# half the gate says nothing about at all — that a held hello is DELIVERED
# later rather than dropped.
# --------------------------------------------------------------------------
def test_the_first_words_are_held_at_1am(monkeypatch):
    saved = []
    _rig(monkeypatch, DEEP_NIGHT - 60, saved)
    a, state = _Anticipy(), {}
    assert maybe_welcome_new_owner(a, state, now=DEEP_NIGHT) is False
    assert a.sent == []
    # Held, not dropped: the hold is written to the clock-state file, and
    # the number is NOT stamped as welcomed — a stamp here would be the
    # silent drop this leg exists to forbid.
    assert "6045550123" in state.get("welcome_held", {})
    assert "6045550123" not in state.get("welcomed_phones", [])
    assert saved and "6045550123" in saved[-1].get("welcome_held", {})


def test_the_first_words_go_out_at_10am(monkeypatch):
    """The direction pin. Same rig, same profile age, waking hour: sends."""
    _rig(monkeypatch, MID_MORNING - 60)
    a, state = _Anticipy(), {}
    assert maybe_welcome_new_owner(a, state, now=MID_MORNING) is True
    assert len(a.sent) == 1


def test_a_held_welcome_is_delivered_in_the_morning(monkeypatch):
    """01:00 holds; 10:00 sends it — even though the profile is now hours
    old and would fail the young-profile guardrail on its own."""
    created = DEEP_NIGHT - 60
    _rig(monkeypatch, created)
    a, state = _Anticipy(), {}
    assert maybe_welcome_new_owner(a, state, now=DEEP_NIGHT) is False
    assert a.sent == []
    # Nine hours later the profile is far past the one-hour young window.
    assert MID_MORNING - created > 3600
    assert maybe_welcome_new_owner(a, state, now=MID_MORNING) is True
    assert len(a.sent) == 1
    # Exactly once, and the hold is cleared behind it.
    assert maybe_welcome_new_owner(a, state, now=MID_MORNING) is False
    assert len(a.sent) == 1
    assert "6045550123" not in state.get("welcome_held", {})


def test_a_held_welcome_survives_a_restart_and_still_sends_once(monkeypatch):
    """The worker dies at 2am and comes back at 10. The hold lives in the
    clock-state file, so the morning still happens — and happens once."""
    saved = []
    _rig(monkeypatch, DEEP_NIGHT - 60, saved)
    a = _Anticipy()
    assert maybe_welcome_new_owner(a, {}, now=DEEP_NIGHT) is False

    # Restart: the process keeps nothing, `_clock_state()` re-reads the file.
    reloaded = saved[-1]
    b = _Anticipy()
    assert maybe_welcome_new_owner(b, reloaded, now=MID_MORNING) is True
    assert len(b.sent) == 1

    # Restart again after the send. The welcomed stamp is on disk now.
    again = saved[-1]
    c = _Anticipy()
    assert maybe_welcome_new_owner(c, again, now=MID_MORNING) is False
    assert c.sent == []


def test_a_hold_that_outlived_its_morning_is_not_sent_days_late(monkeypatch):
    """Quiet hours are ten hours long, so a hold is a night — not a week.
    A worker that was down for days must not open with "your very first
    minutes with me" to somebody who onboarded on Tuesday. It is stamped
    and logged rather than sent."""
    created = DEEP_NIGHT - 60
    _rig(monkeypatch, created)
    a, state = _Anticipy(), {}
    assert maybe_welcome_new_owner(a, state, now=DEEP_NIGHT) is False
    much_later = _at(10, day=29)          # four days on
    assert maybe_welcome_new_owner(a, state, now=much_later) is False
    assert a.sent == []
    assert "6045550123" in state.get("welcomed_phones", [])


def test_quiet_hours_helper_says_night_at_1am_and_day_at_10am():
    """The helper the guard reads, on its own, in the worker's own zone."""
    assert worker._in_quiet_hours(DEEP_NIGHT) is True
    assert worker._in_quiet_hours(MID_MORNING) is False
    # And it is the SAME night the rest of the worker keeps, not a second
    # parallel notion of one.
    assert worker._in_quiet_hours(_at(worker.CLOCK_QUIET_START)) is True
    assert worker._in_quiet_hours(_at(worker.CLOCK_QUIET_END)) is False


def test_a_malformed_clock_state_never_crashes_the_profile_beat(monkeypatch):
    """A kill mid-write left a half-written clock_state.json once already
    (brain/supervisor.py:45). This beat also refreshes the phone, the zone
    and the name, so a bad key here must cost one hello at most."""
    _rig(monkeypatch, DEEP_NIGHT - 60)
    a = _Anticipy()
    for junk in ([], "welcome_held", {"6045550123": None},
                 {"6045550123": "last tuesday"}):
        assert maybe_welcome_new_owner(
            a, {"welcome_held": junk}, now=DEEP_NIGHT) is False
    assert a.sent == []
    # And the junk does not swallow a welcome that is due: same malformed
    # key, a fresh profile, mid-morning — it goes out.
    _rig(monkeypatch, MID_MORNING - 60)
    b = _Anticipy()
    assert maybe_welcome_new_owner(
        b, {"welcome_held": []}, now=MID_MORNING) is True
    assert len(b.sent) == 1
