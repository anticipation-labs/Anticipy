"""'Actually scratch that' kills her pending work — it does not breed more.

A cancellation of a plan she is still holding (queued or awaiting his yes)
must cancel those jobs, not mint a new 'cancel X' card beside them. A
cancellation of something real in the world matches nothing pending and
flows through as an ordinary goal.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import pb  # noqa: E402
from brain.anticipy_core import Anticipy  # noqa: E402

JOBS = []


class _R:
    def __init__(self, payload, ok=True):
        self._p, self.ok = payload, ok

    def json(self):
        return self._p

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError("http error")


def _get(url, params=None, timeout=None, **kw):
    if "/jobs/" not in url:
        return _R({"items": []})
    return _R({"items": [j for j in JOBS
                         if j["status"] in ("awaiting_confirm", "queued")]})


def _post(url, json=None, timeout=None, **kw):
    rec = dict(json or {})
    rec["id"] = f"job{len(JOBS) + 1}"
    JOBS.append(rec)
    return _R(rec)


def _patch(url, json=None, timeout=None, **kw):
    jid = url.rstrip("/").rsplit("/", 1)[-1]
    for j in JOBS:
        if j["id"] == jid:
            j.update(json or {})
            return _R(j)
    return _R({}, ok=False)


def _rig(monkeypatch):
    JOBS.clear()
    monkeypatch.setattr(pb, "get", _get)
    monkeypatch.setattr(pb, "post", _post)
    monkeypatch.setattr(pb, "patch", _patch)
    return Anticipy(owner_id="t")


def test_scratching_a_held_plan_cancels_it_and_its_research(monkeypatch):
    a = _rig(monkeypatch)
    JOBS.append({"id": "job1", "goal": "Book gym session with Marcus Saturday",
                 "status": "awaiting_confirm"})
    JOBS.append({"id": "job2", "goal": "Find gym options for Saturday with Marcus",
                 "status": "queued"})
    out = a._queue_job("cancel gym with Marcus on Saturday", {})
    assert out is None
    assert all(j["status"] == "cancelled" for j in JOBS), JOBS


def test_cancelling_something_in_the_world_is_a_normal_errand(monkeypatch):
    a = _rig(monkeypatch)
    JOBS.append({"id": "job1", "goal": "Book dinner at Earls tomorrow at 8",
                 "status": "awaiting_confirm"})
    out = a._queue_job("cancel the Comcast internet subscription", {},
                       hold=True, explicit=True)
    assert out is not None
    assert JOBS[0]["status"] == "awaiting_confirm"
    assert any("comcast" in (j.get("goal") or "").lower() for j in JOBS)


def test_an_overheard_cancel_of_mere_talk_stays_inert(monkeypatch):
    a = _rig(monkeypatch)
    monkeypatch.setattr(a, "_retracting_mere_talk", lambda goal: True)
    out = a._queue_job("cancel gym with Marcus Saturday", {}, hold=True)
    assert out is None
    assert JOBS == []


def test_refining_a_real_world_cancellation_does_not_cancel_its_own_card(monkeypatch):
    a = _rig(monkeypatch)
    JOBS.append({"id": "job1",
                 "goal": "Cancel CloudLedger membership MBR-63068 at the end of the current term",
                 "status": "awaiting_confirm"})
    out = a._queue_job(
        "Cancel membership MBR-63068 at CloudLedger at the end of the current billing period and request written confirmation",
        {"source": "yeah, agreed — of the current billing period and request written confirmation"},
        hold=True)
    assert out == "job1"
    assert JOBS[0]["status"] == "awaiting_confirm"
    assert "written confirmation" in JOBS[0]["goal"]


def test_unambiguous_call_off_still_retracts_a_cancellation_task(monkeypatch):
    a = _rig(monkeypatch)
    JOBS.append({"id": "job1", "goal": "Cancel CloudLedger membership MBR-63068",
                 "status": "awaiting_confirm"})
    assert a._queue_job("call off the CloudLedger membership cancellation", {}) is None
    assert JOBS[0]["status"] == "cancelled"


def test_without_a_model_the_cancellation_errand_survives(monkeypatch):
    a = _rig(monkeypatch)
    out = a._queue_job("cancel gym with Marcus Saturday", {}, hold=True)
    assert out is not None
    assert len(JOBS) == 1


def test_a_non_cancellation_goal_is_untouched(monkeypatch):
    a = _rig(monkeypatch)
    out = a._queue_job("Book dinner at Earls tomorrow at 8", {}, hold=True)
    assert out is not None
    assert len(JOBS) == 1


def test_correction_rewrites_the_deduped_card(monkeypatch):
    a = _rig(monkeypatch)
    JOBS.append({"id": "job1",
                 "goal": "Book dinner at Earls for two people tomorrow at 8 PM",
                 "status": "awaiting_confirm"})
    out = a._queue_job(
        "Book dinner at Earls for two people tomorrow at 7 PM", {}, hold=True)
    assert out == "job1"
    assert "7" in JOBS[0]["goal"], JOBS[0]["goal"]
    assert len(JOBS) == 1
