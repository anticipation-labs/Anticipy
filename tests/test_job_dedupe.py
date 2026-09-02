"""Dedupe must collapse repeats without ever eating a different job.

The 2026-08-04 dinner failure lived here. Anticipy researched Cactus Club,
Omar then said "book it", and `_queue_job` handed back the RESEARCH job's id
and created nothing — the two goals share almost every word, so the word
overlap rule called them the same work. He saw a lookup and no booking, and
nothing in the logs said a booking had been dropped.

Two rules, tested here:
  1. Looking a thing up is never the same job as doing it.
  2. A plan filled in over several turns is ONE card that improves, not one
     card per turn.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import pb  # noqa: E402
from brain.anticipy_core import Anticipy  # noqa: E402


class FakePB:
    """In-memory jobs table, so the real _queue_job/_same_pending run."""

    def __init__(self):
        self.jobs = []

    class _R:
        def __init__(self, payload, ok=True):
            self._p, self.ok = payload, ok

        def json(self):
            return self._p

        def raise_for_status(self):
            if not self.ok:
                raise RuntimeError("http error")

    def get(self, url, params=None, timeout=None, **kw):
        filt = (params or {}).get("filter", "")
        want = [s for s in ("awaiting_confirm", "queued", "running")
                if f'"{s}"' in filt]
        return self._R({"items": list(reversed(
            [j for j in self.jobs if j["status"] in want]))})

    def post(self, url, json=None, timeout=None, **kw):
        rec = dict(json or {})
        rec["id"] = f"job{len(self.jobs) + 1}"
        self.jobs.append(rec)
        return self._R(rec)

    def patch(self, url, json=None, timeout=None, **kw):
        jid = url.rstrip("/").rsplit("/", 1)[-1]
        for j in self.jobs:
            if j["id"] == jid:
                j.update(json or {})
                return self._R(j)
        return self._R({}, ok=False)


def _anticipy(monkeypatch):
    fake = FakePB()
    monkeypatch.setattr(pb, "get", fake.get)
    monkeypatch.setattr(pb, "post", fake.post)
    monkeypatch.setattr(pb, "patch", fake.patch)
    return Anticipy(owner_id="t"), fake


def test_a_booking_is_never_deduped_into_a_lookup(monkeypatch):
    a, fake = _anticipy(monkeypatch)
    research = "research Cactus Club park location availability for 2 at 7 PM tomorrow"
    booking = "book Cactus Club park location for 2 at 7 PM tomorrow"

    a._queue_job(research, {"source": "x"})
    a._queue_job(booking, {"source": "y"}, hold=True)

    goals = [j["goal"] for j in fake.jobs]
    assert booking in goals, f"the booking was swallowed by the lookup: {goals}"
    assert len(fake.jobs) == 2, goals
    held = [j for j in fake.jobs if j["status"] == "awaiting_confirm"]
    assert len(held) == 1 and held[0]["goal"] == booking


def test_the_same_thing_said_twice_is_still_one_job(monkeypatch):
    a, fake = _anticipy(monkeypatch)
    a._queue_job("book dinner for 2 at Cactus Club tomorrow at 7 PM", {}, hold=True)
    a._queue_job("book dinner at Cactus Club for 2 tomorrow 7 PM", {}, hold=True)
    assert len(fake.jobs) == 1, [j["goal"] for j in fake.jobs]


def test_one_commitment_cannot_spawn_differently_worded_live_jobs(monkeypatch):
    """The production reservation incident: a clock paraphrase is not a new
    workflow merely because it shares almost no words with its earlier one."""
    a, fake = _anticipy(monkeypatch)
    promise = 90
    first = a._queue_job(
        "book dinner at The Keg tomorrow at 7 PM",
        {"source": "clock initiative", "commitment_id": promise}, hold=True)
    second = a._queue_job(
        "confirm the team's arrangements",
        {"source": "clock initiative", "commitment_id": promise}, hold=True)

    assert first == second
    assert len(fake.jobs) == 1, [j["goal"] for j in fake.jobs]
    assert fake.jobs[0]["goal"] == "book dinner at The Keg tomorrow at 7 PM", \
        "a model's later clock paraphrase must not bleach the real workflow"


def test_a_plan_filled_in_over_several_turns_is_one_card(monkeypatch):
    a, fake = _anticipy(monkeypatch)
    vague = "book dinner reservation tomorrow"
    full = ("book dinner reservation for 2 at Cactus Club park location "
            "tomorrow at 7 PM")

    first = a._queue_job(vague, {"source": "early"}, hold=True)
    second = a._queue_job(full, {"source": "later"}, hold=True)

    assert first == second, "the refined plan opened a second card"
    assert len(fake.jobs) == 1, [j["goal"] for j in fake.jobs]
    assert fake.jobs[0]["goal"] == full, "the card kept the vaguer wording"
    # The merge keeps the whole conversation: the original line survives and
    # the refining line is appended, so the agent sees everything he said.
    src = json.loads(fake.jobs[0]["params"])["source"]
    assert "early" in src and "later" in src


def test_a_vaguer_line_arriving_late_never_drags_a_good_card_backwards(monkeypatch):
    a, fake = _anticipy(monkeypatch)
    full = ("book dinner reservation for 2 at Cactus Club park location "
            "tomorrow at 7 PM")
    a._queue_job(full, {}, hold=True)
    a._queue_job("book dinner reservation tomorrow", {}, hold=True)
    assert fake.jobs[0]["goal"] == full, "a later vague line overwrote the details"


def test_a_plan_already_running_never_forks_a_second_card(monkeypatch):
    """Live 2026-08-12: 'Sounds good' after her own 'got it, booking it'
    went back through triage while the booking job was RUNNING. The dedupe
    only saw pending jobs, so a duplicate held card appeared whose text
    contradicted the work in motion."""
    a, fake = _anticipy(monkeypatch)
    a._queue_job("book dinner for two at Earls West Vancouver tomorrow at "
                 "4 PM", {}, hold=True)
    fake.jobs[0]["status"] = "running"
    again = a._queue_job("Book dinner for two at Earls West Vancouver "
                         "tomorrow, Thursday, August 13, at 4 PM", {},
                         hold=True)
    assert again == fake.jobs[0]["id"], "the running plan was not recognised"
    assert len(fake.jobs) == 1, [j["goal"] for j in fake.jobs]
    assert a._running_dup == fake.jobs[0]["id"]


def test_a_running_plan_does_not_swallow_a_different_errand(monkeypatch):
    a, fake = _anticipy(monkeypatch)
    a._queue_job("book dinner at Cactus Club tomorrow at 7 PM", {}, hold=True)
    fake.jobs[0]["status"] = "running"
    a._queue_job("cancel the gym membership this week", {}, hold=True)
    assert len(fake.jobs) == 2, [j["goal"] for j in fake.jobs]
    assert a._running_dup is None


def test_two_genuinely_different_errands_both_survive(monkeypatch):
    """Even inside one conversation window. He can agree a dinner and
    remember the gym in the same breath; folding the second into the first
    silently loses an errand — worse than any duplicate."""
    a, fake = _anticipy(monkeypatch)
    a._queue_job("book dinner at Cactus Club tomorrow at 7 PM", {}, hold=True)
    a._queue_job("cancel the gym membership this week", {}, hold=True)
    assert len(fake.jobs) == 2, [j["goal"] for j in fake.jobs]
    goals = [j["goal"] for j in fake.jobs]
    assert "cancel the gym membership this week" in goals, goals
