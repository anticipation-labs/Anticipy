"""A GOAL ON THE ROW IS A PROMISE THERE IS A CARD BEHIND IT.

The iOS app renders decision="ignore" + a goal as "Looking into it — I'll
text you what I find". The quiet lanes in hear() called _queue_job and then
stamped the goal WITHOUT EVER READING THE ANSWER, and _queue_job has three
answers: a card id, QUEUE_WRITE_FAILED for a POST that never landed, and None
for a deliberate no-op (a retraction it must not turn into work). Both falsy
answers mean no card exists anywhere, and the row said "Looking into it"
regardless.

Measured live over 7,805 decisions in 8 rounds: 242 lines — 5.5% of every
errand-bearing line — formed a goal and queued no job at all. The flagship
example was the product's own:

    "oh no, I completely forgot to sort anything for dinner and the kids
     will be back by six"
        decision = ignore, goal = "Arrange dinner for the kids for 6 PM",
        jobs = 0, said = 0

Silence would have been honest. Four of these in a row is why he concluded
every plan "gets stuck there".

The invariant these tests assert, on the row hear() actually returns:
    goal non-empty  =>  a job exists
and its other half, which must NOT be bought by deleting goals: real quiet
research keeps its goal, because that is the whole personality of the
product.
"""
import json
import types

from brain import anticipy_core as core
from brain.anticipy_core import Anticipy


class ScriptedLLM:
    """Triage answers with the given verdict; every other question ("does
    this end in the world?", the voice) answers harmlessly."""
    live = True

    def __init__(self, triage):
        self.triage = triage

    def chat(self, system, user, **kw):
        if '"decision"' in (system or ""):
            return types.SimpleNamespace(text=json.dumps(self.triage))
        return types.SimpleNamespace(text="okay")


class Posted:
    """A pb.post stand-in. `alive` decides whether the write lands, which is
    the only difference between the honest row and the 242 dishonest ones."""

    def __init__(self, alive=True):
        self.alive = alive
        self.jobs = []

    def __call__(self, url, **kw):
        body = kw.get("json") or {}
        if "/jobs/" in url:
            if not self.alive:
                # What a 409 from workflow_guard.pb.js or a dead rig looks
                # like from in here: raise_for_status() inside _queue_job.
                raise RuntimeError("409 job fields disagree with the workflow")
            self.jobs.append(body)
        return types.SimpleNamespace(
            status_code=200, ok=True, text="{}",
            json=lambda: {"id": f"job{len(self.jobs)}"},
            raise_for_status=lambda: None)


def build(monkeypatch, triage, alive=True):
    """A brain whose ONLY stubs are backend reads — _queue_job itself is the
    real one, because its return value is the thing under test."""
    posted = Posted(alive)
    monkeypatch.setattr(core.pb, "post", posted)
    mem = types.SimpleNamespace(
        ingest=lambda *a, **k: {"commitment_id": None},
        recall=lambda *a, **k: [],
        open_loops=lambda: [],
        close_from_speech=lambda *a, **k: [])
    a = Anticipy(memory=mem, llm=ScriptedLLM(triage), owner_id="own1",
                 backend_url="http://127.0.0.1:1")
    a._pending_jobs = lambda: []
    a._same_pending = lambda goal: None
    a._refines_pending = lambda goal: None
    a.notify_owner = lambda m, channel="sms": True
    return a, posted


def assert_honest(out, posted):
    """The invariant itself, stated once."""
    goal = (out["decision"].goal or "").strip()
    if goal:
        assert posted.jobs, (
            f"the row claims {goal!r} is in hand and no job exists anywhere — "
            "the feed renders that as 'Looking into it'")


# A read-only errand, worded the way the live model worded the ones that
# went missing (proof/ambient/results.jsonl).
LOOKUP = {"decision": "act",
          "goal": "find local boiler servicing and repair options in Vancouver",
          "addressee": "person", "reason": "no firm plan yet"}


def test_a_dead_queue_leaves_no_goal_on_the_quiet_lookup_row(monkeypatch):
    a, posted = build(monkeypatch, {**LOOKUP, "owes": "nobody"}, alive=False)
    out = a.hear("we should get the boiler looked at at some point")
    assert posted.jobs == []
    assert_honest(out, posted)
    assert not (out["decision"].goal or ""), \
        "no card was created, so the feed must not say 'Looking into it'"
    assert out["decision"].decision == "ignore"
    # And no loop pretending to be work in hand: it has no job id, so
    # review_loops can never poll it and status_report would read it out
    # forever as "handling".
    assert [l for l in a.loops if l.status == "handling"] == []


def test_a_dead_queue_leaves_no_goal_on_the_ambient_research_row(monkeypatch):
    a, posted = build(monkeypatch, {**LOOKUP, "owes": "owner"}, alive=False)
    out = a.hear("someone should look into who services boilers round here")
    assert posted.jobs == []
    assert_honest(out, posted)
    assert not (out["decision"].goal or "")
    assert out["decision"].decision == "ignore"
    assert out["anticipy_says"] is None, "this lane never speaks"


def test_a_deliberate_no_op_leaves_no_goal_on_an_overheard_plan(monkeypatch):
    """_queue_job returns None on purpose for a retraction: the card it
    would name was taken off his desk. `fresh` is false in that world and in
    the merge world alike, and this branch used to tell BOTH of them
    "already on her desk" — of an empty desk."""
    a, posted = build(monkeypatch, {
        "decision": "act", "goal": "cancel the dinner reservation at Earls",
        "addressee": "person", "owes": "owner", "reason": "called it off"})
    a._retract_pending = lambda goal: True      # she was holding it; it is gone
    out = a.hear("actually cancel the dinner at Earls, we're not going")
    assert posted.jobs == []
    assert_honest(out, posted)
    assert not (out["decision"].goal or ""), \
        "nothing is on her desk — the row must not say the plan is waiting"
    assert out["decision"].decision == "ignore"


def test_quiet_research_that_really_started_keeps_its_goal(monkeypatch):
    """THE LEGITIMATE SHAPE, and the product's whole personality: goal AND
    job, verdict still "ignore". Deleting goals to move the metric would
    break exactly this."""
    a, posted = build(monkeypatch, {**LOOKUP, "owes": "nobody"})
    out = a.hear("we should get the boiler looked at at some point")
    assert len(posted.jobs) == 1
    assert posted.jobs[0]["goal"] == LOOKUP["goal"]
    assert out["decision"].decision == "ignore", "quiet work never announces itself"
    assert out["decision"].goal == LOOKUP["goal"], \
        "real quiet work lost its goal — the feed would claim nothing happened"
    assert out["anticipy_says"] is None
    assert_honest(out, posted)


def test_an_overheard_plan_that_merged_still_says_it_is_on_her_desk(monkeypatch):
    """The other half of the over-correction guard: a plan firming up merges
    into the card he is ALREADY waiting on, so `fresh` is false and a card
    genuinely exists. That row must keep its goal."""
    a, posted = build(monkeypatch, {
        "decision": "act", "goal": "book a table at Earls for 7 PM tomorrow",
        "addressee": "person", "owes": "owner", "reason": "plan made aloud"})
    a._pending_jobs = lambda: [{"id": "job-existing"}]
    a._same_pending = lambda goal: "job-existing"
    a._merge_into = lambda *a_, **k: None
    out = a.hear("seven works, let's do Earls tomorrow")
    assert out["decision"].decision == "ignore"
    assert out["decision"].goal, \
        "the card exists on his desk — the row must still say so"
    assert "already on her desk" in (out["decision"].reason or "")


def test_the_clock_stays_quiet_when_its_prepared_work_never_landed(monkeypatch):
    """The clock composes the words and the goal in ONE model reply, and
    worker.py posts them together (decision="clock"). With a dead queue the
    message promises work that exists in no system, so she says nothing and
    nothing is stamped as reached — the next window may try for real."""
    posted = Posted(alive=False)
    monkeypatch.setattr(core.pb, "post", posted)

    class WantsToReachOut:
        live = True

        def chat(self, system, user, **kw):
            return types.SimpleNamespace(text=json.dumps({
                "initiate": True,
                "say": "Want me to sort dinner for the kids?",
                "goal": "Arrange dinner for the kids for 6 PM",
                "loop_ids": [7]}))

    mem = types.SimpleNamespace(
        open_loops=lambda: [{"id": 7, "what": "dinner for the kids",
                             "status": "open", "ts": 0,
                             "source": "I need to sort dinner for the kids"}],
        recall=lambda *a, **k: [], ingest=lambda *a, **k: {})
    a = Anticipy(memory=mem, llm=WantsToReachOut(), owner_id="own1",
                 backend_url="http://127.0.0.1:1")
    sent = []
    a.notify_owner = lambda m, channel="sms": sent.append(m) or True
    a._pending_jobs = lambda: []
    a._same_pending = lambda goal: None
    a._refines_pending = lambda goal: None
    assert a.clock_tick(now=2000) is None, \
        "nothing was queued, so there is nothing true to say"
    assert sent == []
    assert posted.jobs == []
    assert [l for l in a.loops if l.job_id] == []
