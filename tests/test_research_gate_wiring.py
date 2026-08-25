"""THE RESEARCH GATE, IN THE PRODUCT.

`brain/research.py` was a library nothing imported: 90-odd tests describing how
well a world-touching job would be held, and no world-touching job held
anywhere. This is the other half — the gate asked at the ONE place a job row is
minted (`Anticipy._queue_job`), and the worker pass that lets the held row go
again.

The shape, from HANDS 1 spec §5.4:
  - a live cached procedure       -> free, no research, and it rides to the hands
  - touches read/compute          -> nothing to gate; that IS the research lane
  - touches world, or undeclared  -> the research pass runs BEFORE a browser
                                     may claim the row
  - the gate itself cannot run    -> it OPENS, and says so in the row

And the invariant §5.5 exists for: a gate that holds must always let go. Every
held row is handed back to the browser lane on the next worker pass, researched
or not, because a parked errand is worse than an unresearched one.
"""
import json
import time
import types

import pytest

import brain.anticipy_core as core
import brain.research as research
from brain.anticipy_core import Anticipy
from brain.memory import Memory


class FakeLLM:
    """Live enough for the recall floor to be askable. `applies` is what the
    one question comes back with."""

    def __init__(self, applies=True):
        self.live = True
        self.applies = applies
        self.asked = []

    def chat(self, system, user, **kw):
        self.asked.append((system, user))
        return types.SimpleNamespace(
            text=json.dumps({"applies": self.applies}))


def procedure(learned_at=None):
    return {"startUrl": "https://bchydro.com/help", "needs": ["an account number"],
            "steps": ["open the portal", "file the form"], "caveats": [],
            "sources": ["https://bchydro.com/help"],
            "learnedAt": learned_at if learned_at is not None
            else int(time.time() * 1000),
            "question": "how do you dispute a hydro bill"}


def queue(monkeypatch, goal, touches=None, key="test-key", llm=None,
          memory=None, **kw):
    """Drive _queue_job with pb mocked; hand back the record it would post."""
    if key is None:
        monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    else:
        monkeypatch.setenv("BRAVE_API_KEY", key)
    posted = {}

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"id": "j1"}

    monkeypatch.setattr(core.pb, "post",
                        lambda url, **kw: (posted.update(kw.get("json") or {}), R())[1])
    a = Anticipy(owner_id="own1", llm=llm, memory=memory or Memory())
    monkeypatch.setattr(a, "_same_pending", lambda goal, **_k: None)
    a._queue_job(goal, {"source": "test", "now": "now"}, touches=touches, **kw)
    return posted


def gate_of(posted) -> dict:
    return json.loads(posted["params"])["_research_gate"]


# ---------------------------------------------------------------- the hold

def test_a_world_touching_job_is_held_off_the_browser_until_research_ran(monkeypatch):
    """The card's actual requirement. `lane="research"` is the hold, and it is
    the one lane value BOTH enforcement points §5.5 names already exclude —
    research_lane.pb.js's poll rewrite and every shipped extension's own
    filter — so nothing in the wild can claim this row."""
    posted = queue(monkeypatch, "dispute the hydro bill", touches="world",
                   llm=FakeLLM())
    assert posted["lane"] == "research"
    gate = gate_of(posted)
    assert gate["verdict"] == research.GATE_RESEARCH
    assert gate["handback"] is True


def test_an_undeclared_goal_is_held_too(monkeypatch):
    """§5.4's polarity, and it is the opposite of the hold gate's on purpose:
    the cost of researching unnecessarily is money, and the cost of NOT
    researching is a run that spends eighteen steps on a marketing page and
    parks. So this gate never has to consult _READ_ONLY_RE and never inherits
    its tape."""
    posted = queue(monkeypatch, "dispute the hydro bill", touches=None,
                   llm=FakeLLM())
    assert posted["lane"] == "research"
    assert gate_of(posted)["verdict"] == research.GATE_RESEARCH


def test_a_declared_read_is_not_held(monkeypatch):
    """A read IS the research lane's own job. Routing it there is what
    job_lane already does, and there is nothing to gate in front of it."""
    posted = queue(monkeypatch, "look up the ferry schedule to Nanaimo",
                   touches="read", llm=FakeLLM())
    assert posted["lane"] == "research"
    assert gate_of(posted)["verdict"] == research.GATE_NOT_REQUIRED
    assert "handback" not in gate_of(posted)


def test_an_undeclared_LOOKUP_is_not_marked_as_a_held_browser_errand(monkeypatch):
    """The hold and the research lane share one lane STRING, so the marker is
    the only thing that tells a parked browser errand from a genuine question.
    An undeclared goal `job_lane` already sent to the server's own arm must not
    be marked: marked, the pre-flight would research it, clear it, and hand a
    read-only lookup to his Chrome — which is the 2026-08-02 tab flood, minted
    by the thing that exists to prevent tab floods."""
    posted = queue(monkeypatch, "look up the ferry schedule to Nanaimo",
                   touches=None, llm=FakeLLM())
    assert posted["lane"] == "research"
    assert gate_of(posted)["verdict"] == research.GATE_NOT_REQUIRED
    assert "handback" not in gate_of(posted)


def test_a_browser_errand_the_owner_asked_for_by_name_is_still_held(monkeypatch):
    """`job_lane` sends "open X in my browser" to the browser arm. The gate is
    a second question asked of the SAME row — may a browser claim it yet —
    and a declared world touch outranks the fact that it is browser work."""
    posted = queue(monkeypatch, "open my hydro account in Chrome and pay it",
                   touches="world", llm=FakeLLM())
    assert posted["lane"] == "research"


# ------------------------------------------------------------- the recall

def test_a_cached_procedure_satisfies_the_gate_and_rides_to_the_hands(monkeypatch):
    """The card's "second time = instant". Free — no research pass, no hold —
    and the procedure travels on the row so the browser does not have to
    re-learn what the server already knows."""
    memory = Memory()
    research.remember_procedure(research.task_shape("dispute the hydro bill"),
                                procedure(), memory.procedures())
    posted = queue(monkeypatch, "dispute the hydro bill", touches="world",
                   llm=FakeLLM(applies=True), memory=memory)
    assert posted["lane"] == ""
    assert gate_of(posted)["verdict"] == research.GATE_SATISFIED
    assert json.loads(posted["params"])["procedure"]["steps"] == [
        "open the portal", "file the form"]


def test_a_cached_procedure_for_a_DIFFERENT_errand_does_not_satisfy(monkeypatch):
    """The shape key is lossy on purpose ("the March bill" and "the April
    bill" are one shape) and the same lossiness collides opposite errands. It
    NOMINATES; a model with both errands in front of it decides. A floor, so
    an unconfirmed candidate researches rather than replaying unread."""
    memory = Memory()
    research.remember_procedure(research.task_shape("dispute the hydro bill"),
                                procedure(), memory.procedures())
    posted = queue(monkeypatch, "dispute the hydro bill", touches="world",
                   llm=FakeLLM(applies=False), memory=memory)
    assert posted["lane"] == "research"
    assert gate_of(posted)["verdict"] == research.GATE_RESEARCH


def test_a_stale_procedure_costs_no_model_call_at_all(monkeypatch):
    """The free sift stays in front of the floor: an expired record is a miss
    at zero cost, so the common case never buys a question."""
    memory = Memory()
    research.remember_procedure(
        research.task_shape("dispute the hydro bill"),
        procedure(learned_at=int(time.time() * 1000) - research.PROCEDURE_TTL_MS - 1),
        memory.procedures())
    llm = FakeLLM()
    queue(monkeypatch, "dispute the hydro bill", touches="world", llm=llm,
          memory=memory)
    assert llm.asked == []


# --------------------------------------------------------- the dead gate

def test_a_gate_that_cannot_run_opens_and_says_so(monkeypatch):
    """§5.5: "A gate that cannot run must open, not hold, and say so in the
    trace." Without a Brave key there is no research pass to wait for, and a
    row held for one that will never come is a parked errand."""
    posted = queue(monkeypatch, "dispute the hydro bill", touches="world",
                   key=None, llm=FakeLLM())
    assert posted["lane"] == ""
    assert gate_of(posted)["verdict"] == research.GATE_OPEN
    assert "handback" not in gate_of(posted)


def test_a_gate_with_no_model_opens_too(monkeypatch):
    """learn_procedure returns None without a live model — no model, no
    procedure, and no web traffic either. Holding a row for a pass that
    cannot produce anything is the same parked errand."""
    posted = queue(monkeypatch, "dispute the hydro bill", touches="world",
                   llm=None)
    assert posted["lane"] == ""
    assert gate_of(posted)["verdict"] == research.GATE_OPEN


def test_opening_is_recorded_differently_from_needing_nothing(monkeypatch):
    """"We had the knowledge" and "we gave up looking for it" must never be
    one outcome in the row, because the second is the one worth counting."""
    broken = queue(monkeypatch, "dispute the hydro bill", touches="world",
                   key=None, llm=FakeLLM())
    fine = queue(monkeypatch, "look up the ferry schedule", touches="read",
                 llm=FakeLLM())
    assert gate_of(broken)["verdict"] != gate_of(fine)["verdict"]


# ------------------------------------------------------------------ law 1

def test_the_gate_is_never_handed_the_goal(monkeypatch):
    """§5.3, and it is the whole reason the gate takes no goal parameter: you
    cannot pattern-match on prose you were never given. What reaches it is an
    effect channel a model declared and the SHAPE of a cache hit."""
    seen = {}
    real = research.research_gate

    def spy(touches, procedure=None, gate_can_run=True):
        seen.update(touches=touches, procedure=procedure,
                    gate_can_run=gate_can_run)
        return real(touches, procedure, gate_can_run)

    monkeypatch.setattr(core.research, "research_gate", spy)
    goal = "dispute the hydro bill for the Kitsilano house"
    queue(monkeypatch, goal, touches="world", llm=FakeLLM())
    assert seen["touches"] == "world"
    assert goal not in json.dumps(seen, default=str)


def test_the_gate_is_not_asked_at_all_on_a_merge(monkeypatch):
    """The dedupe/merge ladder returns before the mint. A card assembled over
    five turns must not buy five gates — and must not have its lane rewritten
    by the last fragment of the conversation."""
    monkeypatch.setenv("BRAVE_API_KEY", "test-key")
    asked = []
    monkeypatch.setattr(core.research, "research_gate",
                        lambda *a, **k: asked.append(a) or research.GateVerdict(
                            research.GATE_OPEN, "spy"))
    a = Anticipy(owner_id="own1", llm=FakeLLM(), memory=Memory())
    monkeypatch.setattr(a, "_same_pending", lambda goal, **_k: "existing")
    monkeypatch.setattr(a, "_pending_jobs", lambda: [])
    assert a._queue_job("dispute the hydro bill", {"source": "s", "now": "n"},
                        touches="world") == "existing"
    assert asked == []
