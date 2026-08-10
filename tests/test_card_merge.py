"""A re-mention may ADD to a card; it must never bleach one out.

Live, 2026-08-09: "Book a table for 2 at Earls in West Vancouver for tomorrow
evening" was held; "I'll get that booked now" arrived as "Confirm Earls West
Van tomorrow at 7 PM" — same plan, and the merge REPLACED the goal with that
meta-wording. The booking verb, party size and venue details vanished, and
the browser agent read "Confirm …" as "send a confirmation" and opened Gmail.
"""

import json

from brain.anticipy_core import Anticipy
from brain.memory import Memory


class _Job:
    def __init__(self, goal, params=None):
        self.rec = {"id": "job1", "goal": goal, "status": "awaiting_confirm",
                    "params": json.dumps(params or {})}


def _core(monkeypatch, job, patches):
    a = Anticipy(memory=Memory(":memory:"), llm=None, owner_id="t")
    monkeypatch.setattr(a, "_pending_jobs", lambda: [job.rec])
    import brain.anticipy_core as C

    class FakePB:
        @staticmethod
        def patch(url, json=None, timeout=10):
            patches.append(json)
    monkeypatch.setattr(C, "pb", FakePB)
    return a


def test_a_meta_wording_never_overwrites_the_real_goal(monkeypatch):
    patches = []
    job = _Job("Book a table for 2 at Earls in West Vancouver for tomorrow "
               "evening, August 10th", {"source": "let's do drinks at Earls"})
    a = _core(monkeypatch, job, patches)
    a._merge_into("job1", job.rec, "Confirm Earls West Van tomorrow at 7 PM",
                  {"source": "booked now"})
    assert patches, "the new detail (7 PM) must be written somewhere"
    fields = patches[-1]
    assert "goal" not in fields, "the booking goal must survive untouched"
    params = json.loads(fields["params"])
    assert "7 PM" in params["update"]
    assert "let's do drinks at Earls" in params["source"], \
        "the original conversation must not be replaced by a fragment"
    assert "booked now" in params["source"]


def test_a_genuinely_richer_wording_does_replace(monkeypatch):
    patches = []
    job = _Job("Book dinner at Earls tomorrow", {"source": "dinner at Earls"})
    a = _core(monkeypatch, job, patches)
    richer = "Book dinner at Earls tomorrow at 7 PM for 4 people"
    a._merge_into("job1", job.rec, richer, {"source": "make it 7 for four"})
    fields = patches[-1]
    assert fields.get("goal") == richer
    params = json.loads(fields["params"])
    assert "dinner at Earls" in params["source"]
