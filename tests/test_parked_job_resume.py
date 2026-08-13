"""A parked browser run must resume from the owner's text.

Live, 2026-08-10: the browser stopped on an Earls booking with "showing
6:30, did you mean noon?". He texted "Noon pls", then "Find noon", then
"K do it" — the texting brain replied warmly every time while the job sat
in needs_user forever. His answer belongs ON the run, and puts it back to
work with the answer where the agent reads its authority.
"""
import json

import pytest

import brain.conversation as convmod
from brain.anticipy_core import Anticipy
from brain.conversation import Conversation
from brain.memory import Memory
from brain.workflow import (Consequence, approve, claim, from_params,
                            needs_user, new_plan, put_in_params)


def _conv():
    a = Anticipy(memory=Memory(":memory:"), llm=None, owner_id="t")
    return Conversation(a, llm=None)


def _scoped_conv():
    a = Anticipy(memory=Memory(":memory:"), llm=None, owner_id="t",
                 owner_ref="owner-a")
    return Conversation(a, llm=None)


def _pb(monkeypatch, job):
    patched = {}

    class R:
        ok = True
        def __init__(self, payload): self._p = payload
        def json(self): return self._p

    def get(url, **kw):
        if url.rstrip("/").endswith(job["id"]):
            return R(job)
        return R({"items": [job]})

    def patch(url, **kw):
        patched.update(kw.get("json") or {})
        return R(job)

    monkeypatch.setattr(convmod, "pb", type("PB", (), {
        "get": staticmethod(get), "patch": staticmethod(patch)}))
    return patched


def test_answer_resumes_a_parked_run(monkeypatch):
    job = {"id": "j1", "goal": "Book lunch at Earls for tomorrow at noon",
           "status": "needs_user",
           "result": "showing 6:30 PM today; task says tomorrow at noon",
           "params": json.dumps({"authorized": True,
                                 "approved_scope": "Task: book lunch."})}
    patched = _pb(monkeypatch, job)
    out = _conv()._amend("j1", {"time": "noon"}, owner_text="Noon pls")
    assert out == "resumed:j1"
    assert patched["status"] == "queued"
    p = json.loads(patched["params"])
    assert p["time"] == "noon"
    assert "Noon pls" in p["approved_scope"]
    assert "showing 6:30" in p["approved_scope"]
    assert p["needed"].startswith("showing 6:30")


def test_go_ahead_resumes_a_parked_run(monkeypatch):
    job = {"id": "j1", "goal": "Book lunch at Earls for tomorrow at noon",
           "status": "needs_user",
           "result": "showing 6:30 PM today; task says tomorrow at noon",
           "params": json.dumps({"authorized": True,
                                 "approved_scope": "Task: book lunch."})}
    patched = _pb(monkeypatch, job)
    out = _conv()._release("j1", None, owner_text="K do it")
    assert out == "released:j1"
    assert patched["status"] == "queued"
    p = json.loads(patched["params"])
    assert "K do it" in p["approved_scope"]


def test_amend_still_never_releases_a_held_job(monkeypatch):
    job = {"id": "j2", "goal": "Book dinner", "status": "awaiting_confirm",
           "params": json.dumps({})}
    patched = _pb(monkeypatch, job)
    out = _conv()._amend("j2", {"time": "7pm"}, owner_text="make it 7")
    assert out == "amended:j2"
    assert "status" not in patched


def test_release_still_refuses_dead_jobs(monkeypatch):
    job = {"id": "j3", "goal": "Book dinner", "status": "cancelled",
           "params": json.dumps({})}
    _pb(monkeypatch, job)
    assert _conv()._release("j3", None, owner_text="do it") is None


def test_learned_answer_resumes_strict_workflow_with_exact_owner_words(monkeypatch):
    plan = new_plan(owner_ref="owner-a", lineage_key="lineage-a",
                    goal="Submit warranty repair request",
                    consequence=Consequence.CONSEQUENTIAL,
                    source_event_id="event-a", required=("email_address",))
    # The original approval had the required value.  The browser then parked
    # on a newly discovered request; model the parked plan without smuggling
    # an answer into it.
    plan = approve(plan, expected_version=plan.version,
                   owner_words="send the warranty request",
                   changes={"email_address": "old@example.test"})
    plan = claim(plan, expected_version=plan.version, actor_id="browser-a",
                 token="lease-a")
    plan = needs_user(plan, lease_token="lease-a",
                      reason="I need your current email address")
    params = put_in_params({"authorized": True,
                            "approved_scope": "Task: submit warranty request."},
                           plan)
    job = {"id": "j4", "goal": plan.goal, "status": "needs_user",
           "owner_ref": "owner-a", "result": plan.reason,
           "params": json.dumps(params)}
    patched = _pb(monkeypatch, job)

    out = _scoped_conv()._resume_stuck(
        {"email_address": "new@example.test"},
        owner_text="Use new@example.test")

    assert out == "resumed:j4"
    stored = json.loads(patched["params"])
    resumed = from_params(stored)
    assert resumed is not None
    assert resumed.state.value == "queued"
    assert resumed.facts["email_address"] == "new@example.test"
    assert resumed.approval.owner_words == "Use new@example.test"
    assert stored["email_address"] == "new@example.test"
    assert "Use new@example.test" in stored["approved_scope"]


def test_strict_workflow_never_resumes_without_owner_words(monkeypatch):
    plan = new_plan(owner_ref="owner-a", lineage_key="lineage-a",
                    goal="Submit repair request",
                    consequence=Consequence.READ_ONLY,
                    source_event_id="event-a")
    plan = claim(plan, expected_version=plan.version, actor_id="browser-a",
                 token="lease-a")
    plan = needs_user(plan, lease_token="lease-a", reason="I need the model")
    job = {"id": "j5", "goal": plan.goal, "status": "needs_user",
           "owner_ref": "owner-a", "result": plan.reason,
           "params": json.dumps(put_in_params({}, plan))}
    patched = _pb(monkeypatch, job)

    assert _scoped_conv()._requeue(job, {"model": "X1"}) is None
    assert patched == {}


def test_paraphrase_that_mangles_facts_is_replaced():
    from brain.worker import carries_facts
    blocker = ("The current reservation is for Mon, Aug 10 at 6:30 PM, but "
               "the task is to book for tomorrow at noon.")
    mangled = "I'm gonna drive at 6:30. I can change it for tomorrow."
    assert not carries_facts(mangled, blocker)
    ok = ("the page came up showing Mon, Aug 10 at 6:30 PM instead of "
          "tomorrow at noon — switching it now.")
    assert carries_facts(ok, blocker)
    invented = ("it's showing 6:30 PM on Aug 10; I'll book 8 PM tomorrow "
                "at noon instead.")
    assert not carries_facts(invented, blocker)
