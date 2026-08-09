"""Day zero's first proactive touch: a brand-new owner gets ONE hello.

The rules live outside any model: only a freshly created profile earns a
welcome, one durable stamp per number stops repeats forever, and an old
profile discovered without a stamp is stamped silently — never texted.
"""
import os
import sys
import time

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
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S.000Z")


def _rig(monkeypatch, created_ts):
    monkeypatch.setattr(pb, "get", lambda url, params=None, timeout=None, **k:
                        _Reply({"items": [{"created": _iso(created_ts),
                                           "first_name": "Omar"}]}))
    monkeypatch.setattr(worker, "_save_clock_state", lambda s: None)
    monkeypatch.setattr(worker, "post_event", lambda *a, **k: None)


def test_a_fresh_onboarding_gets_exactly_one_welcome(monkeypatch):
    now = time.time()
    _rig(monkeypatch, now - 60)
    a, state = _Anticipy(), {}
    assert maybe_welcome_new_owner(a, state, now=now) is True
    assert len(a.sent) == 1
    # The stamp holds: a second poll says nothing.
    assert maybe_welcome_new_owner(a, state, now=now) is False
    assert len(a.sent) == 1


def test_an_old_profile_is_stamped_silently_never_texted(monkeypatch):
    now = time.time()
    _rig(monkeypatch, now - 7 * 24 * 3600)
    a, state = _Anticipy(), {}
    assert maybe_welcome_new_owner(a, state, now=now) is False
    assert a.sent == []
    # And it is stamped, so the fresh-profile branch can never fire later.
    digits = "6045550123"
    assert digits in state.get("welcomed_phones", [])


def test_no_phone_means_no_welcome(monkeypatch):
    now = time.time()
    _rig(monkeypatch, now - 60)
    a = _Anticipy(phone="")
    assert maybe_welcome_new_owner(a, {}, now=now) is False
    assert a.sent == []


def test_a_failed_send_leaves_no_stamp_so_it_retries(monkeypatch):
    now = time.time()
    _rig(monkeypatch, now - 60)
    a, state = _Anticipy(), {}
    a.notify_owner = lambda msg, channel="sms": None
    assert maybe_welcome_new_owner(a, state, now=now) is False
    assert "6045550123" not in state.get("welcomed_phones", [])


def test_backend_failure_never_crashes_or_texts(monkeypatch):
    monkeypatch.setattr(pb, "get", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("down")))
    a = _Anticipy()
    assert maybe_welcome_new_owner(a, {}) is False
    assert a.sent == []
