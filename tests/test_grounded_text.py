"""A number she never heard is an invention, whatever the prompt says.

Live, 2026-08-09: "we really gotta go for dinner... I don't know when though...
let's grab dinner at the Earls West Van" produced the text "Got a reservation
at Earls West Van for tomorrow, Monday at 7 p.m." — a time he explicitly did
not know, filled in from habit, presented as a done deal.

Three walls, each tested here or nearby:
  1. The ambient lane now runs the sufficiency check, so "no time" becomes a
     question instead of a guess (the direct lane already had this).
  2. Any digit in her held-plan text must appear in what was heard, the goal,
     the assumption, or the missing list — otherwise the plain fallback
     speaks instead. Deterministic; no model gets a vote.
  3. VOICE_SYSTEM forbids claiming a result while holding for approval —
     model-side, so it is backed by the deterministic walls above.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import pb  # noqa: E402
import brain.anticipy_core as core  # noqa: E402
from brain.anticipy_core import Anticipy  # noqa: E402
from brain.memory import Memory  # noqa: E402
from brain.orchestrator import Decision  # noqa: E402

LINE = ("we really gotta go for dinner I don't know when though my schedule "
        "looks free tomorrow evening let's grab dinner at the Earls West Van")
GOAL = "Book dinner at Earls West Van for tomorrow evening"


class _Reply:
    def __init__(self, payload):
        self._p, self.ok = payload, True

    def json(self):
        return self._p

    def raise_for_status(self):
        return None


class Fake:
    def __init__(self):
        self.jobs = []

    def get(self, url, params=None, timeout=None, **k):
        want = [s for s in ("awaiting_confirm", "queued")
                if s in (params or {}).get("filter", "")]
        return _Reply({"items": [j for j in self.jobs if j.get("status") in want]})

    def post(self, url, json=None, timeout=None, **k):
        rec = dict(json or {})
        rec["id"] = f"j{len(self.jobs) + 1}"
        self.jobs.append(rec)
        return _Reply(rec)

    def patch(self, url, json=None, timeout=None, **k):
        jid = url.rstrip("/").rsplit("/", 1)[-1]
        for j in self.jobs:
            if j.get("id") == jid:
                j.update(json or {})
        return _Reply({})


class DeadMemory(Memory):
    def __init__(self):
        pass

    def ingest(self, *a, **k):
        return {}

    def recall(self, *a, **k):
        return []


def _anticipy(monkeypatch, voice):
    fake = Fake()
    monkeypatch.setattr(pb, "get", fake.get)
    monkeypatch.setattr(pb, "post", fake.post)
    monkeypatch.setattr(pb, "patch", fake.patch)
    a = Anticipy(memory=DeadMemory(), owner_id="grounded")
    # owes="owner" stated since 2026-09-05 (Omi port 10a): the ambient
    # held-card path these legs pin is the path of a plan that is HIS.
    monkeypatch.setattr(a, "_decide", lambda *args, **kw: Decision(
        decision="act", goal=GOAL, reason="a real plan",
        addressee="person", owes="owner", needs_confirmation=True))
    monkeypatch.setattr(a, "_voice", lambda *a_, **k_: voice)
    sent = []
    a.notify_owner = lambda m, channel="sms": (sent.append(m), True)[1]
    return a, fake, sent


def test_an_invented_time_never_reaches_his_phone(monkeypatch):
    """The live failure, verbatim shape: he never said 7, she must not."""
    a, fake, sent = _anticipy(
        monkeypatch, "Got a reservation at Earls West Van for tomorrow at 7 PM")
    a.hear(LINE, may_say=lambda *a_, **k_: True)
    assert len(sent) == 1
    assert "7" not in sent[0], f"an invented time went out: {sent[0]!r}"


def test_a_number_he_actually_said_is_allowed(monkeypatch):
    a, fake, sent = _anticipy(
        monkeypatch, "caught the dinner plan — Earls West Van tomorrow evening, "
                     "want me to find a table?")
    a.hear(LINE, may_say=lambda *a_, **k_: True)
    assert len(sent) == 1
    assert "Earls" in sent[0]


def test_a_number_from_the_goal_is_allowed(monkeypatch):
    a, fake, sent = _anticipy(
        monkeypatch, "holding dinner for 4 at Earls at 7 — say go")
    monkeypatch.setattr(a, "_decide", lambda *args, **kw: Decision(
        decision="act", goal="Book dinner at Earls for 4 people at 7 PM",
        reason="a real plan", addressee="person", owes="owner",
        needs_confirmation=True))
    a.hear("dinner at Earls, seven works, all four of us",
           may_say=lambda *a_, **k_: True)
    assert len(sent) == 1
    assert "7" in sent[0] and "4" in sent[0]


def test_the_ambient_lane_asks_about_what_only_he_can_decide(monkeypatch):
    """The sufficiency check now runs for overheard plans too: 'tomorrow
    evening' with no time becomes a question, never a habit-guess."""
    a, fake, sent = _anticipy(monkeypatch, None)   # fallback voice
    monkeypatch.setattr(core, "check_sufficiency",
                        lambda llm, goal: ["what time they want"])
    a.hear(LINE, may_say=lambda *a_, **k_: True)
    assert len(sent) == 1
    assert "what time they want" in sent[0], sent[0]
