"""The second key: whose job did these words create?

Triage saying "act" is one key. This is the other, and both must turn
before anything consequential happens. On 2026-08-04 one dictation Omar
gave his LAPTOP ("kill 491, kill 492, kill 493 of your list") became three
real jobs, because the only question being asked was "does this look
actionable" — and it did.

These tests use a scripted model, so they pin the POLICY, not the model's
judgement. The judgement is measured separately against Omar's real logged
day in overnight/evaluate.py.
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
        self.prompts: list[str] = []

    def chat(self, system, user, **kw):
        if '"decision"' in (system or ""):
            self.prompts.append(user)
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
    a.queued, a.texts = [], []
    a._queue_job = lambda goal, params, hold=False, explicit=False: (
        a.queued.append({"goal": goal, "hold": hold, "params": params})
        or f"job{len(a.queued)}")
    a._pending_jobs = lambda: []
    a._same_pending = lambda goal: None
    a._refines_pending = lambda goal: None
    a.notify_owner = lambda m, channel="sms": (a.texts.append(m), {"ok": 1})[1]
    return a


BOOK = {"decision": "act", "goal": "book a table for two at 7pm",
        "addressee": "person", "reason": "plan agreed"}


def test_a_machine_errand_does_nothing_at_all():
    """He is voice-typing; the app in front of him is already doing it."""
    a = build({**BOOK, "goal": "remove items 491, 492, 493 from the list",
               "owes": "machine"})
    out = a.hear("Pill 491 kill 492 kill 493 of your list")
    assert a.queued == [], a.queued
    assert a.texts == []
    assert out["decision"].decision == "ignore"
    assert out["decision"].owes == "machine"


def test_someone_elses_promise_is_never_his_errand():
    a = build({**BOOK, "goal": "book the Vienna flights", "owes": "other"})
    out = a.hear("leave the flights with me, I'll sort them")
    assert a.queued == [] and a.texts == []
    assert "someone else" in out["decision"].reason


def test_his_own_plan_still_gets_prepared():
    """The failure we are NOT repeating: going quiet on his real plan."""
    a = build({**BOOK, "owes": "owner"})
    a.hear("seven at Cactus tomorrow, just the two of us")
    assert len(a.queued) == 1, a.queued
    assert a.queued[0]["hold"] is True


def test_no_obligation_may_still_look_something_up_quietly():
    """Looking is free, silent and reversible — be generous there."""
    a = build({"decision": "act", "goal": "research dinner spots in Vancouver",
               "addressee": "person", "owes": "nobody", "reason": "soft plan"})
    a.hear("we should eat somewhere good tomorrow")
    assert len(a.queued) == 1
    assert a.queued[0]["hold"] is False
    assert a.queued[0]["params"].get("lane") == "ambient"
    assert a.texts == []


def test_no_obligation_never_buys_books_or_interrupts():
    a = build({"decision": "act", "goal": "book a table somewhere nice",
               "addressee": "person", "owes": "nobody", "reason": "vague"})
    a.hear("we should eat somewhere good sometime")
    assert a.queued == [] and a.texts == []


class SettledLLM(ScriptedLLM):
    """Scripted model that also answers the settled-plan tiebreaker."""

    def __init__(self, triage, settled):
        super().__init__(triage)
        self.settled = settled

    def chat(self, system, user, **kw):
        if '"settled"' in (system or ""):
            return types.SimpleNamespace(
                text=json.dumps({"settled": self.settled}))
        if '"ends_in_the_world"' in (system or ""):
            return types.SimpleNamespace(
                text=json.dumps({"ends_in_the_world": True}))
        return super().chat(system, user, **kw)


def test_a_settled_plan_survives_a_nobody_verdict():
    """"We should… Earl's tomorrow at 2:30… I'd be down" is a settled plan,
    not musing — a "nobody owes it" verdict must not drop it silently."""
    a = build({"decision": "act",
               "goal": "book dinner at Earl's in West Van tomorrow at 2:30",
               "addressee": "person", "owes": "nobody",
               "reason": "mutual plan"})
    a.llm = SettledLLM(a.llm.triage, settled=True)
    out = a.hear("Yeah I know we should really go out for dinner yeah we "
                 "totally should tomorrow at Earl's at 2:30 in West Van "
                 "yeah for sure I'd be down for that")
    assert len(a.queued) == 1, "settled plan must reach the held-card lane"
    assert a.queued[0]["hold"] is True
    assert out["decision"].decision == "act"


def test_unsettled_musing_stays_quiet_whatever_it_names():
    a = build({"decision": "act",
               "goal": "book dinner at Earl's in West Van",
               "addressee": "person", "owes": "nobody", "reason": "musing"})
    a.llm = SettledLLM(a.llm.triage, settled=False)
    a.hear("we should totally do Earl's again at some point")
    assert a.queued == [] and a.texts == []


def test_when_he_asks_her_directly_nothing_overrides_him():
    """An explicit line is his own instruction; no second opinion applies."""
    a = build({**BOOK, "owes": "machine"})   # even a wrong verdict
    a.hear("book the table for 7", explicit=True)
    assert len(a.queued) == 1, a.queued


def test_a_missing_verdict_changes_nothing():
    """Old model, unparseable reply: behave exactly as before the field."""
    a = build({k: v for k, v in BOOK.items()})       # no "owes" at all
    a.hear("seven at Cactus tomorrow, just the two of us")
    assert len(a.queued) == 1, "no verdict must not silence her"


def test_a_garbage_verdict_changes_nothing():
    a = build({**BOOK, "owes": "banana"})
    a.hear("seven at Cactus tomorrow, just the two of us")
    assert len(a.queued) == 1


def test_the_model_is_actually_asked_the_question():
    a = build({**BOOK, "owes": "owner"})
    a.hear("seven at Cactus tomorrow")
    from brain.orchestrator import TRIAGE_SYSTEM
    assert '"owes"' in TRIAGE_SYSTEM
    assert "WHOSE JOB" in TRIAGE_SYSTEM
