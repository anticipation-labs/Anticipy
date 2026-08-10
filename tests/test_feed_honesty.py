"""ignore + a goal is a PROMISE: the feed renders it as "Looking into it —
I'll text you what I find". Live, 2026-08-09, four plans in a row wore that
label while she was doing nothing (do-nothing owes verdicts, a cancelled
card, authored dictation) — he reasonably concluded every plan "gets stuck
there". Only actual quiet work may carry a goal on an ignore.
"""
import json
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.anticipy_core import Anticipy  # noqa: E402


class ScriptedLLM:
    live = True

    def __init__(self, triage):
        self.triage = triage

    def chat(self, system, user, **kw):
        if '"decision"' in (system or ""):
            return types.SimpleNamespace(text=json.dumps(self.triage))
        return types.SimpleNamespace(text="okay")


def build(triage):
    mem = types.SimpleNamespace(
        ingest=lambda *a, **k: {"commitment_id": None},
        recall=lambda *a, **k: [],
        open_loops=lambda: [],
        close_from_speech=lambda *a, **k: [])
    a = Anticipy(memory=mem, llm=ScriptedLLM(triage),
                 backend_url="http://127.0.0.1:1")
    a.queued = []
    a._queue_job = lambda goal, params, hold=False, explicit=False: (
        a.queued.append(goal) or f"job{len(a.queued)}")
    a._pending_jobs = lambda: []
    a._same_pending = lambda goal: None
    a._refines_pending = lambda goal: None
    a.notify_owner = lambda m, channel="sms": True
    return a


BOOK = {"decision": "act", "goal": "book the Vienna flights",
        "addressee": "person", "reason": "plan"}


def test_someone_elses_errand_carries_no_goal_to_the_feed():
    a = build({**BOOK, "owes": "other"})
    out = a.hear("leave the flights with me, I'll sort them")
    assert a.queued == []
    assert not out["decision"].goal, \
        "she is doing nothing — the feed must not say 'Looking into it'"


def test_a_machine_errand_carries_no_goal_to_the_feed():
    a = build({**BOOK, "owes": "machine"})
    out = a.hear("book the Vienna flights and confirm the dates")
    assert a.queued == []
    assert not out["decision"].goal


def test_a_vague_consequential_plan_carries_no_goal_to_the_feed():
    a = build({"decision": "act", "goal": "book a table somewhere nice",
               "addressee": "person", "owes": "nobody", "reason": "vague"})
    out = a.hear("we should eat somewhere good sometime")
    assert a.queued == []
    assert not out["decision"].goal


def test_actual_quiet_work_still_says_so():
    """The Paris-flights incident must not come back: work she IS doing
    quietly keeps its goal, so the feed shows 'Looking into it'."""
    a = build({"decision": "act", "goal": "research dinner spots in Vancouver",
               "addressee": "person", "owes": "nobody", "reason": "soft plan"})
    out = a.hear("we should eat somewhere good tomorrow")
    assert len(a.queued) == 1
    assert out["decision"].goal, \
        "real quiet work lost its goal — the feed would claim nothing happened"
