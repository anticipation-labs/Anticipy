"""Calling something off that was never on is not an errand.

Live, 2026-08-22, same session as the 18-hour merge. Two consecutive lines:

    "I really should get the car booked in for its service before the end of
     the month"
        -> MISSED. decision ignore, no goal, no job. Nothing was arranged,
           nothing was queued, nothing was held.

    "actually you know what, forget the car, my brother said he would take it
     in for me"
        -> decision act, goal "cancel car service booking", a CONSEQUENTIAL
           card, and a text to the owner asking "Which one do you mean?"
           about a booking that had never existed.

_retracting_mere_talk was asked and answered "world", which is defensible on
the words alone — a car service IS the kind of thing one books — and useless,
because the model cannot see that nobody ever booked it. The spoken line can:
"forget the car" withdraws an idea and "my brother said he would take it in"
hands it to someone else. Neither commissions work.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import pb  # noqa: E402
from brain.anticipy_core import Anticipy, is_consequential  # noqa: E402
from brain.memory import Memory  # noqa: E402
from brain.orchestrator import Decision  # noqa: E402

LINE = ("actually you know what, forget the car, my brother said he would "
        "take it in for me")
GOAL = "cancel car service booking"


class _R:
    def __init__(self, payload, ok=True):
        self._p, self.ok = payload, ok

    def json(self):
        return self._p

    def raise_for_status(self):
        return None


class Rig:
    """An in-memory jobs table. Starts EMPTY, which is the whole point: there
    is nothing pending for this call-off to be aimed at."""

    def __init__(self):
        self.jobs = []

    def get(self, url, params=None, timeout=None, **kw):
        want = [s for s in ("awaiting_confirm", "queued")
                if s in (params or {}).get("filter", "")]
        return _R({"items": [j for j in self.jobs if j.get("status") in want]})

    def post(self, url, json=None, timeout=None, **kw):
        rec = dict(json or {})
        rec["id"] = f"j{len(self.jobs) + 1}"
        rec.setdefault("status", "awaiting_confirm")
        self.jobs.append(rec)
        return _R(rec)

    def patch(self, url, json=None, timeout=None, **kw):
        jid = url.rstrip("/").rsplit("/", 1)[-1]
        for j in self.jobs:
            if j.get("id") == jid:
                j.update(json or {})
        return _R({})


class DeadMemory(Memory):
    def __init__(self):
        pass

    def ingest(self, *a, **k):
        return {}

    def recall(self, *a, **k):
        return []


class WorldSayingLLM:
    """The model as it actually answered live: this cancellation is aimed at
    something standing in the world. True about car services in general, and
    the wrong answer about a car service nobody ever booked.

    **kw, not a pinned signature — brain.llm.LLM.chat grew an `aux` flag and a
    double that refuses unknown keywords turns that into a swallowed
    TypeError.
    """

    live = True

    class _Reply:
        def __init__(self, text):
            self.text = text

    def chat(self, system, user, temperature=0.1, **kw):
        return self._Reply('{"aimed_at": "world"}')


def _anticipy(monkeypatch, decision=None, llm=None):
    rig = Rig()
    monkeypatch.setattr(pb, "get", rig.get)
    monkeypatch.setattr(pb, "post", rig.post)
    monkeypatch.setattr(pb, "patch", rig.patch)
    a = Anticipy(memory=DeadMemory(), llm=llm, owner_id="calloff")
    if decision is not None:
        monkeypatch.setattr(a, "_decide", lambda *args, **kw: decision)
    monkeypatch.setattr(a, "_voice", lambda *a_, **k_: "on it")
    sent = []
    a.notify_owner = lambda m, channel="sms": (sent.append(m), True)[1]
    return a, rig, sent


# --------------------------------------------------------------- the failure

def test_a_call_off_with_nothing_pending_makes_no_card_and_no_text(monkeypatch):
    """THE CAR SERVICE. Nothing was ever booked, so there is nothing to
    cancel and nothing to ask him about."""
    assert is_consequential(GOAL), \
        "this test is meaningless if that goal was never going to be a card"
    decision = Decision(decision="act", goal=GOAL,
                        reason="he called the car service off",
                        addressee="self")
    a, rig, sent = _anticipy(monkeypatch, decision, llm=WorldSayingLLM())

    a.hear(LINE, may_say=lambda *a_, **k_: True)

    assert rig.jobs == [], \
        f"invented a cancellation errand out of a call-off: {rig.jobs}"
    assert sent == [], \
        f"texted him about a booking that never existed: {sent}"


def test_someone_else_taking_it_on_is_not_the_owners_errand(monkeypatch):
    """The handoff half of the same line, on its own."""
    a, rig, _ = _anticipy(monkeypatch, llm=WorldSayingLLM())
    out = a._queue_job(GOAL,
                       {"source": "my brother said he would take it in for me"},
                       hold=True)
    assert out is None, out
    assert rig.jobs == []


def test_a_bare_withdrawal_with_nothing_pending_is_inert(monkeypatch):
    """And the withdrawal half."""
    a, rig, _ = _anticipy(monkeypatch, llm=WorldSayingLLM())
    out = a._queue_job("cancel the gym session",
                       {"source": "never mind the gym, I'm not going"},
                       hold=True)
    assert out is None, out
    assert rig.jobs == []


# --------------------------------------------------- what must NOT change

def test_a_real_world_cancellation_he_asked_for_still_becomes_an_errand(
        monkeypatch):
    """No withdrawal, no handoff — he is commissioning work, and swallowing a
    real cancellation is a loss where a useless card is only an annoyance."""
    a, rig, _ = _anticipy(monkeypatch, llm=WorldSayingLLM())
    out = a._queue_job("cancel the Comcast internet subscription",
                       {"source": "can you cancel my Comcast internet "
                                  "subscription this week"},
                       hold=True, explicit=True)
    assert out, "a direct cancellation request was swallowed"
    assert any("comcast" in (j.get("goal") or "").lower() for j in rig.jobs)


def test_the_owner_doing_it_himself_is_not_a_handoff():
    """'I'll take it in myself' is first person and must never read as
    somebody else having it."""
    assert not Anticipy._withdrawn_in_conversation(
        "I'll take the car in myself on Friday")
    assert not Anticipy._withdrawn_in_conversation(
        "book the car in for its service before the end of the month")


def test_a_withdrawal_cannot_kill_a_card_that_does_exist(monkeypatch):
    """When something IS pending, the call-off still retracts it — going
    quiet must not mean going inert."""
    a, rig, _ = _anticipy(monkeypatch, llm=WorldSayingLLM())
    rig.jobs.append({"id": "job1", "goal": "Book the car in for its service",
                     "status": "awaiting_confirm"})
    out = a._queue_job("cancel the car service booking",
                       {"source": "actually forget the car, my brother said "
                                  "he would take it in"}, hold=True)
    assert out is None
    assert rig.jobs[0]["status"] == "cancelled", rig.jobs
