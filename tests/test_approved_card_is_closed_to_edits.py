"""Once he has said yes, the next thing he says is a NEW errand.

_queue_job's open-plan carry says exactly that in a comment, and the check
under it did not enforce it: liveness was "is this job in _pending_jobs()",
and that pool means awaiting_confirm OR QUEUED. Nothing clears _open_plan when
the SMS or app lane releases a card, so for the whole ten-minute window an
already-approved job still read as his to approve.

He approves "book dinner at Earls tonight" (extension backlogged, so it sits
queued), then two minutes later says "also book dinner at Earls Friday for the
team". Same plan by every word test — so the merge rewrote TONIGHT's approved
booking to say Friday, and the second dinner never existed.

The write behind it was doomed anyway: merge() demotes a consequential plan
back to AWAITING_APPROVAL, and workflow_guard.pb.js:allowed forbids
queued -> awaiting_confirm outright. The 409 landed in a bare `except: pass`,
so the correction disappeared with no log at all.
"""
import json
import time

from brain.anticipy_core import Anticipy
from brain.memory import Memory


class _Job:
    def __init__(self, goal, status="awaiting_confirm", params=None):
        self.rec = {"id": "job1", "goal": goal, "status": status,
                    "params": json.dumps(params or {})}


def _core(monkeypatch, job, patches, patch_response=None):
    a = Anticipy(memory=Memory(":memory:"), llm=None, owner_id="t")
    monkeypatch.setattr(a, "_pending_jobs", lambda: [job.rec])
    monkeypatch.setattr(a, "_open_card_in_lineage", lambda _l: None)
    import brain.anticipy_core as C

    class FakePB:
        @staticmethod
        def patch(url, json=None, timeout=10):
            patches.append(json)
            return patch_response

        @staticmethod
        def post(url, json=None, timeout=10):
            class Response:
                @staticmethod
                def raise_for_status():
                    return None

                @staticmethod
                def json():
                    return {"id": "job2", "status": "awaiting_confirm"}
            return Response()
    monkeypatch.setattr(C, "pb", FakePB)
    return a


TONIGHT = "Book dinner at Earls tonight at 7 PM for 2"
FRIDAY = "Book dinner at Earls Friday for the team"


def test_a_queued_booking_is_not_rewritten_by_the_next_thing_he_says(monkeypatch):
    patches = []
    job = _Job(TONIGHT, status="queued", params={"source": "dinner at Earls"})
    a = _core(monkeypatch, job, patches)
    a._open_plan = ("job1", time.time(), TONIGHT)
    # The word tests all agree these are one plan — that is the trap, not the
    # bug. Approval, not similarity, is what ends the editing window.
    monkeypatch.setattr(a, "_same_plan", lambda *_a: True)
    monkeypatch.setattr(a, "_same_pending", lambda _g: None)
    monkeypatch.setattr(a, "_refines_pending", lambda _g: None)

    assert a._queue_job(FRIDAY, {"source": "also dinner Friday"},
                        hold=True) == "job2", \
        "the Friday dinner must become its own card"
    assert patches == [], "tonight's approved booking must not be touched"
    assert a._open_plan[0] == "job2"


def test_the_same_carry_still_improves_a_card_he_has_not_answered(monkeypatch):
    """The open-plan carry is the whole reason one dinner makes one card.
    Narrowing it to held work must not switch it off."""
    patches = []
    job = _Job("Book dinner at Earls tomorrow",
               params={"source": "dinner at Earls"})
    a = _core(monkeypatch, job, patches)
    a._open_plan = ("job1", time.time(), "Book dinner at Earls tomorrow")
    richer = "Book dinner at Earls tomorrow at 7 PM for 4 people"

    assert a._queue_job(richer, {"source": "make it 7 for four"},
                        hold=True) == "job1"
    assert patches[-1]["goal"] == richer


def test_merging_into_approved_work_is_refused_out_loud(monkeypatch, capsys):
    """The last line of defence: _same_pending and _refines_pending both read
    the same queued-inclusive pool, so the guard belongs at the write too."""
    patches = []
    job = _Job(TONIGHT, status="queued", params={"source": "dinner at Earls"})
    a = _core(monkeypatch, job, patches)
    a._merge_into("job1", job.rec, FRIDAY, {"source": "also dinner Friday"})
    assert patches == []
    assert "already queued" in capsys.readouterr().out


def test_a_rejected_amendment_is_never_silent(monkeypatch, capsys):
    """requests does not raise on 4xx and the except swallowed the rest, so a
    refused correction read exactly like an applied one all the way up."""
    patches = []

    class Refused:
        ok = False
        status_code = 409

    job = _Job("Book dinner at Earls tomorrow",
               params={"source": "dinner at Earls"})
    a = _core(monkeypatch, job, patches, patch_response=Refused())
    a._merge_into("job1", job.rec,
                  "Book dinner at Earls tomorrow at 8 PM for 4 people",
                  {"source": "actually make it 8"})
    assert patches, "the write is still attempted"
    out = capsys.readouterr().out
    assert "amend REFUSED for job1" in out
    assert "409" in out
