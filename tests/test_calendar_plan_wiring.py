"""The live calendar hand is selected, filled and held end to end.

The original device-lane suite started at `act=calendar_act()`. No production
caller ever supplied that argument, so hundreds of green assertions proved a
lane the real brain could never choose. These tests start with the same heard
words `hear()` gives `_queue_job` and let the dedicated model question produce
the declaration and facts.
"""
import json
import types

import brain.anticipy_core as core
import brain.conversation as conversation_module
from brain.conversation import Conversation
from brain.memory import Memory
from brain.orchestrator import (
    CALENDAR_NO,
    CALENDAR_PLAN_SYSTEM,
    CALENDAR_UNANSWERED,
    CALENDAR_UNASKED,
    CALENDAR_YES,
    calendar_plan_verdict,
)
from brain.workflow import PlanState, from_params, merge as merge_plan


class Model:
    live = True
    model = "calendar-test"

    def __init__(self, reply, raises=None):
        self.reply = reply
        self.raises = raises
        self.calls = []

    def chat(self, system, user, **kwargs):
        self.calls.append((system, user, kwargs))
        if self.raises:
            raise self.raises
        value = self.reply if isinstance(self.reply, str) else json.dumps(self.reply)
        return types.SimpleNamespace(text=value)


COMPLETE = {
    "calendar_write": True,
    "calendar_title": "Team sync",
    "calendar_start": "2026-09-07T10:00:00-07:00",
    "calendar_end": "2026-09-07T10:30:00-07:00",
    "missing": [],
}
INCOMPLETE = {
    "calendar_write": True,
    "calendar_title": "Team sync",
    "calendar_start": None,
    "calendar_end": None,
    "missing": ["calendar_start", "calendar_end"],
}


def test_calendar_question_is_asked_alone_with_all_authority():
    llm = Model(COMPLETE)
    verdict = calendar_plan_verdict(
        llm, "schedule the team sync next Monday", "Schedule the team sync",
        "Monday 2026-08-31 09:00 America/Vancouver")
    assert verdict.state == CALENDAR_YES
    assert len(llm.calls) == 1
    system, user, kwargs = llm.calls[0]
    assert system == CALENDAR_PLAN_SYSTEM
    assert "schedule the team sync next Monday" in user
    assert "Schedule the team sync" in user
    assert "America/Vancouver" in user
    assert kwargs["temperature"] == 0.0


def test_calendar_question_has_four_distinct_states(capsys):
    no = calendar_plan_verdict(Model({
        "calendar_write": False, "calendar_title": None,
        "calendar_start": None, "calendar_end": None, "missing": [],
    }), "send invites", "Schedule with invitees", "now")
    assert no.state == CALENDAR_NO
    assert calendar_plan_verdict(None, "line", "goal", "now").state == CALENDAR_UNASKED
    dead = calendar_plan_verdict(
        Model("not json", raises=TimeoutError("dead")), "line", "goal", "now")
    assert dead.state == CALENDAR_UNANSWERED
    assert "unanswered" in capsys.readouterr().out


def test_invalid_or_contradictory_calendar_artifacts_never_select_the_phone():
    bad = [
        {**COMPLETE, "calendar_start": "next Monday at ten"},
        {**COMPLETE, "calendar_end": "2026-09-07T09:30:00-07:00"},
        {**INCOMPLETE, "missing": []},
        {**COMPLETE, "missing": ["attendees"]},
        {**COMPLETE, "calendar_write": "yes"},
        {**COMPLETE, "calendar_write": 1},
    ]
    for payload in bad:
        assert calendar_plan_verdict(Model(payload), "line", "goal", "now").state \
            == CALENDAR_UNANSWERED, payload


def queued(monkeypatch, payload):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    posted = {}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"id": "job1", "status": posted.get("status")}

    monkeypatch.setattr(core.pb, "post", lambda _url, **kw: (
        posted.update(kw["json"]), Response())[1])
    a = core.Anticipy(memory=Memory(":memory:"), llm=Model(payload), owner_id="own1")
    a._same_pending = lambda *_a, **_k: None
    a._refines_pending = lambda *_a, **_k: None
    result = a._queue_job(
        "Schedule the team sync next Monday",
        {"source": "schedule the team sync next Monday",
         "now": "Monday 2026-08-31 09:00 America/Vancouver"},
        hold=True, explicit=True, touches="world")
    assert result == "job1"
    return posted


def test_real_mint_path_selects_phone_and_carries_executable_artifacts(monkeypatch):
    posted = queued(monkeypatch, COMPLETE)
    assert posted["lane"] == core.DEVICE_CALENDAR_LANE
    assert posted["status"] == "awaiting_confirm"
    params = json.loads(posted["params"])
    plan = params["_workflow"]
    assert plan["state"] == "awaiting_approval"
    assert plan["act"] == {
        "act_type": core.PHONE_CALENDAR_ACT_TYPE,
        "reach": core.PHONE_CALENDAR_REACH,
        "executor": core.PHONE_CALENDAR_EXECUTOR,
        "target": {"name": "event tag", "provenance": "minted_by_us",
                   "ref": core.PHONE_CALENDAR_TAG_REF},
    }
    assert plan["facts"] == {
        "calendar_title": "Team sync",
        "calendar_start": "2026-09-07T10:00:00-07:00",
        "calendar_end": "2026-09-07T10:30:00-07:00",
    }
    undo = plan["undo"]
    assert undo["act_type"] == core.PHONE_CALENDAR_ACT_TYPE
    assert undo["held"]["minted_by_us"][core.PHONE_CALENDAR_TAG_REF]
    assert undo["held"]["owner_supplied"]["calendar_start"] == plan["facts"]["calendar_start"]
    assert undo["held"]["owner_supplied"]["calendar_end"] == plan["facts"]["calendar_end"]


def test_under_specified_calendar_plan_asks_before_it_can_be_approved(monkeypatch):
    posted = queued(monkeypatch, INCOMPLETE)
    plan = from_params(json.loads(posted["params"]))
    assert plan.state == PlanState.DRAFT
    assert plan.missing == ("calendar_start", "calendar_end")
    assert posted["status"] == "awaiting_confirm"
    assert posted["result"] == "I still need when it starts and when it ends."
    assert not plan.approval

    amended = merge_plan(
        plan, expected_version=plan.version,
        facts={"calendar_start": "2026-09-07T10:00:00-07:00",
               "calendar_end": "2026-09-07T10:30:00-07:00"},
        authority_text="schedule it at ten for thirty minutes")
    assert amended.state == PlanState.AWAITING_APPROVAL
    assert amended.missing == ()
    held = amended.undo.held["owner_supplied"]
    assert held["calendar_start"] == amended.facts["calendar_start"]
    assert held["calendar_end"] == amended.facts["calendar_end"]


def test_owner_answer_moves_the_real_draft_to_approval(monkeypatch):
    posted = queued(monkeypatch, INCOMPLETE)
    job = {"id": "job1", **posted}

    class Response:
        ok = True

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    def get(url, **kwargs):
        if url.rstrip("/").endswith("/job1"):
            return Response(dict(job))
        query = (kwargs.get("params") or {}).get("filter", "")
        if 'status="awaiting_confirm"' in query or 'workflow_state="draft"' in query:
            return Response({"items": [dict(job)]})
        return Response({"items": []})

    def patch(_url, **kwargs):
        job.update(kwargs.get("json") or {})
        return Response(dict(job))

    monkeypatch.setattr(conversation_module, "pb", types.SimpleNamespace(
        get=get, patch=patch))
    anticipy = core.Anticipy(
        memory=Memory(":memory:"), llm=Model(COMPLETE), owner_id="own1")
    out = Conversation(anticipy)._amend(
        "job1", {"owner_answer": "Monday at ten for thirty minutes"},
        owner_text="Monday at ten for thirty minutes")

    assert out == "amended:job1"
    plan = from_params(json.loads(job["params"]))
    assert plan.state == PlanState.AWAITING_APPROVAL
    assert plan.missing == ()
    assert plan.facts == {
        "calendar_title": "Team sync",
        "calendar_start": "2026-09-07T10:00:00-07:00",
        "calendar_end": "2026-09-07T10:30:00-07:00",
    }
    assert "owner_answer" not in plan.facts
    assert job["status"] == "awaiting_confirm"
    assert job["workflow_state"] == "awaiting_approval"
    assert job["result"] == ""


def test_false_or_unanswered_hand_selection_stays_on_existing_browser_lane(monkeypatch):
    false = {
        "calendar_write": False, "calendar_title": None,
        "calendar_start": None, "calendar_end": None, "missing": [],
    }
    assert queued(monkeypatch, false)["lane"] == ""
    assert queued(monkeypatch, "not json")["lane"] == ""
