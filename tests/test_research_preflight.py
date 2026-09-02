"""THE HELD HALF OF THE RESEARCH GATE: the pass that lets the row go again.

`Anticipy._queue_job` parks a world-touching errand on `lane="research"` — the
one lane value both enforcement points HANDS 1 §5.5 names already exclude, so
no browser in the wild can claim it. That hold is only legitimate because of
this pass, which reads how the task is done and then hands the row BACK to the
browser lane.

The invariant every test here is really about: **a gate that holds must always
let go.** Researched, unresearched, keyless, model-less, or crashed mid-read —
the row leaves this lane on the pass that saw it. §5.5: "A gate that cannot run
must open, not hold, and say so in the trace." A parked errand is worse than an
unresearched one, and it is worse silently.
"""
import json
import time
import types

import pytest

import brain.research as research
import brain.worker as W
from brain.memory import Memory


class Resp:
    def __init__(self, payload=None, ok=True):
        self.ok = ok
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


class FakeLLM:
    live = True

    def chat(self, *a, **kw):
        return types.SimpleNamespace(text="{}")


def anticipy(memory=None, llm=None):
    return types.SimpleNamespace(
        owner_id="own1", owner_ref="", backend_url="http://pb",
        llm=llm if llm is not None else FakeLLM(),
        memory=memory or Memory(),
        _voice=lambda ctx: None,
        notify_owner=lambda msg, channel="sms": {"ok": 1})


def held_row(goal="dispute the hydro bill", extra_params=None):
    params = {"source": "he said so", "now": "now",
              "_research_gate": {"verdict": research.GATE_RESEARCH,
                                 "why": "touches=world — look it up first",
                                 "handback": True}}
    params.update(extra_params or {})
    return {"id": "j1", "goal": goal, "params": json.dumps(params),
            "status": "queued", "lane": "research", "claimed_by": "",
            "owner": "own1"}


def wire(monkeypatch, row, patches, key="test-key", tavily_key=None):
    if key is None:
        monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    else:
        monkeypatch.setenv("BRAVE_API_KEY", key)
    if tavily_key is None:
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    else:
        monkeypatch.setenv("TAVILY_API_KEY", tavily_key)
    state = dict(row)

    def fake_get(url, **kw):
        if url.endswith("/records"):
            return Resp({"items": [dict(state)]})
        return Resp(dict(state))

    def fake_patch(url, **kw):
        body = kw.get("json") or {}
        patches.append(body)
        state.update(body)
        return Resp()

    monkeypatch.setattr(W.pb, "get", fake_get)
    monkeypatch.setattr(W.pb, "patch", fake_patch)
    monkeypatch.setattr(W.pb, "post", lambda url, **kw: Resp())
    return state


def learned():
    return {"startUrl": "https://bchydro.com/help", "needs": ["an account number"],
            "steps": ["open the portal", "file the form"], "caveats": [],
            "sources": ["https://bchydro.com/help"],
            "learnedAt": int(time.time() * 1000),
            "question": "dispute the hydro bill"}


# ------------------------------------------------- it lets go, researched

def test_a_researched_row_goes_back_to_the_browser_lane_carrying_what_she_read(monkeypatch):
    patches = []
    wire(monkeypatch, held_row(), patches)
    W.run_preflight_research(anticipy(), learner=lambda *a, **k: learned())
    assert len(patches) == 1
    assert patches[0]["lane"] == ""
    params = json.loads(patches[0]["params"])
    assert params["procedure"]["steps"] == ["open the portal", "file the form"]
    assert params["_research_gate"]["researched"] is True
    # The marker is CLEARED, or the next pass researches the same row forever.
    assert "handback" not in params["_research_gate"]


def test_what_she_read_is_remembered_so_the_second_errand_is_free(monkeypatch):
    """The card's moat: paid for once per task SHAPE, not per errand. The
    store is the owner's own SQLite, so the next dispute of the same shape is
    satisfied at the gate with no research pass at all."""
    memory = Memory()
    wire(monkeypatch, held_row(), [])
    W.run_preflight_research(anticipy(memory=memory),
                             learner=lambda *a, **k: learned())
    hit = research.recall_procedure(
        research.task_shape("dispute the hydro bill"), memory.procedures())
    assert hit and hit["steps"] == ["open the portal", "file the form"]


# ----------------------------------------------- it lets go, EVERY OTHER WAY

def test_a_row_is_handed_back_even_when_the_pages_did_not_say_how(monkeypatch):
    """An honest blank is a real answer. §5.5: the browser goes through
    unresearched rather than the errand being parked."""
    patches = []
    wire(monkeypatch, held_row(), patches)
    W.run_preflight_research(anticipy(), learner=lambda *a, **k: None)
    assert patches[0]["lane"] == ""
    gate = json.loads(patches[0]["params"])["_research_gate"]
    assert gate["researched"] is False
    assert "handback" not in gate


def test_a_row_is_handed_back_when_there_is_no_search_provider_key(monkeypatch):
    """The existing keyless fallback is the precedent: a job queued for an
    executor that does not exist would sit forever."""
    patches = []
    wire(monkeypatch, held_row(), patches, key=None)
    W.run_preflight_research(anticipy(),
                             learner=lambda *a, **k: pytest.fail("no key, no read"))
    assert patches[0]["lane"] == ""
    assert json.loads(patches[0]["params"])["_research_gate"]["researched"] is False


def test_tavily_alone_can_supply_preflight_research(monkeypatch):
    patches, calls = [], []
    wire(monkeypatch, held_row(), patches, key=None, tavily_key="tvly-test")

    def fake_learn(*args, **kwargs):
        calls.append((args, kwargs))
        return learned()

    monkeypatch.setattr(W.research, "learn_procedure", fake_learn)
    W.run_preflight_research(anticipy())
    assert calls
    assert calls[0][1]["api_key"] is None
    assert calls[0][1]["tavily_api_key"] == "tvly-test"
    assert json.loads(patches[0]["params"])["_research_gate"]["researched"] is True


def test_a_row_is_handed_back_when_the_read_itself_raises(monkeypatch):
    """A crash inside the read is the case a `try` around the happy path
    would miss, and it is exactly how an errand goes silently missing."""
    patches = []
    wire(monkeypatch, held_row(), patches)

    def boom(*a, **k):
        raise RuntimeError("brave is down")

    W.run_preflight_research(anticipy(), learner=boom)
    assert patches[0]["lane"] == ""
    assert json.loads(patches[0]["params"])["_research_gate"]["researched"] is False


def test_a_row_is_handed_back_when_a_hostile_page_talked_the_model_into_junk(monkeypatch):
    """`learn_procedure` returns a record or None; anything else is not a
    procedure and must not be written onto the row as one."""
    patches = []
    wire(monkeypatch, held_row(), patches)
    W.run_preflight_research(anticipy(),
                             learner=lambda *a, **k: "totally a procedure")
    assert patches[0]["lane"] == ""
    assert "procedure" not in json.loads(patches[0]["params"])


# ------------------------------------------------------- it holds nothing else

def test_a_genuine_research_job_is_left_alone(monkeypatch):
    """A read-only lookup on this lane is the research arm's own work and must
    be ANSWERED, not handed to a browser. The marker is what tells them
    apart, and it is written by the worker at mint, never by a claimant."""
    patches = []
    row = held_row()
    row["params"] = json.dumps({"source": "s", "now": "n"})
    wire(monkeypatch, row, patches)
    W.run_preflight_research(anticipy(),
                             learner=lambda *a, **k: pytest.fail("not its row"))
    assert patches == []


def test_the_research_arm_never_answers_a_held_browser_errand(monkeypatch):
    """The other side of the same coin, and the more expensive one to get
    wrong: `run_research_jobs` marking a booking "done" with a summary of the
    open web is an errand that never happened, reported as finished."""
    patches = []
    wire(monkeypatch, held_row(), patches)
    W.run_research_jobs(anticipy(),
                        runner=lambda *a, **k: pytest.fail("not its row"))
    assert not any(p.get("status") in ("done", "failed") for p in patches)


# ------------------------------------------------------------------- law 1

def test_the_question_that_travels_is_the_goal_and_nothing_else(monkeypatch):
    """`design/LOCAL-FIRST.md` blesses the research arm in the cloud because
    "only the QUESTION travels, phrased as a goal, not his transcript". The
    row carries `source` — the authorizing utterance — and it must not go."""
    seen = {}
    wire(monkeypatch, held_row(), [])

    def spy(question, **kw):
        seen["question"] = question
        return learned()

    W.run_preflight_research(anticipy(), learner=spy)
    assert seen["question"] == "dispute the hydro bill"
