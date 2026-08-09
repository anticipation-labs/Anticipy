"""Day zero: onboarding answers become profile knowledge, exactly once.

He types his name and email into the app; the worker's profile poll must
seed them into memory as high-importance interview facts — and a poll that
runs every minute must not rewrite them forever.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import pb  # noqa: E402
from brain.memory import Memory  # noqa: E402
from brain.worker import seed_profile_identity  # noqa: E402


class _Reply:
    def __init__(self, payload, ok=True):
        self._p, self.ok = payload, ok

    def json(self):
        return self._p


def _poll(monkeypatch, items):
    monkeypatch.setattr(pb, "get", lambda url, params=None, timeout=None, **k:
                        _Reply({"items": items}))


def test_onboarding_name_and_email_become_profile_facts(monkeypatch):
    m = Memory()
    _poll(monkeypatch, [{"first_name": "Omar", "last_name": "Ebrahim",
                         "email": "omar@x.com"}])
    seed_profile_identity(m, _seen={})
    facts = [f["fact"] for f in m.profile_facts()]
    assert any("Omar Ebrahim" in f for f in facts), facts
    assert any("omar@x.com" in f for f in facts), facts
    assert all(f["importance"] == 5 for f in m.profile_facts())


def test_the_minute_poll_does_not_rewrite_unchanged_identity(monkeypatch):
    m = Memory()
    seen = {}
    _poll(monkeypatch, [{"first_name": "Omar", "last_name": "", "email": ""}])
    for _ in range(5):
        seed_profile_identity(m, _seen=seen)
    named = [f for f in m.profile_facts() if "Omar" in f["fact"]]
    assert len(named) == 1, [f["fact"] for f in m.profile_facts()]


def test_a_changed_name_updates_the_profile(monkeypatch):
    m = Memory()
    seen = {}
    _poll(monkeypatch, [{"first_name": "Omar", "last_name": "", "email": ""}])
    seed_profile_identity(m, _seen=seen)
    _poll(monkeypatch, [{"first_name": "Omar", "last_name": "Ebrahim",
                         "email": ""}])
    seed_profile_identity(m, _seen=seen)
    facts = [f["fact"] for f in m.profile_facts()]
    assert any("Omar Ebrahim" in f for f in facts), facts


def test_an_empty_or_failing_profile_never_crashes(monkeypatch):
    m = Memory()
    _poll(monkeypatch, [])
    seed_profile_identity(m, _seen={})
    monkeypatch.setattr(pb, "get", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("backend down")))
    seed_profile_identity(m, _seen={})
    assert m.profile_facts() == []
