"""Rung 0's lane: a calendar write is delivered to the PHONE, not to Chrome.

`research/2026-08-26-hands2-better-answer.md` §4 rung 0. The one thing that
beats both the browser and the API ladder for one verb: the app already holds
full calendar access, already polls the jobs channel every three seconds, and
already writes status back on it.

WHAT THESE TESTS PIN, and it is the whole point of the file:

  * The lane is decided by the plan's OWN DECLARATION — `ActDeclaration`'s
    `executor`, resolved through a closed registry — and by nothing else.
    Not by the goal's wording, not by a date in it, not by the word
    "calendar". A word list here would be the HARNESS-LAWS Law 1 violation
    this repo removed three of yesterday, and `test_the_wording_decides
    _nothing` is the regression guard that fails the day somebody writes one.
  * Delivery is not permission. Being in the lane registry admits nothing to
    Shelf 2 and buys no exemption from the confirmation gate.
  * A device-lane job no phone ever claims is REPORTED, not silently kept.
    The browser lane has `report_stalled_work` for exactly this; a calendar
    write that sits forever because the phone is off is a promise silently
    broken.
"""
import json
import re
import types
from datetime import datetime, timedelta, timezone

import pytest

import brain.anticipy_core as core
import brain.worker as W
from brain.anticipy_core import (DEVICE_CALENDAR_LANE, DEVICE_EXECUTOR_LANES,
                                 PHONE_CALENDAR_EXECUTOR, RESEARCH_LANE,
                                 Anticipy, device_lane, job_lane)
from brain.workflow import (ADMITTED_ACT_TYPES, ActDeclaration, Consequence,
                            Refusal, UndoInput, UndoPlan, admissible, new_plan)


def calendar_act(executor=PHONE_CALENDAR_EXECUTOR):
    """What the model declares when the errand's effect is a calendar write.

    The minted id is the point: `EKEvent.eventIdentifier` is assigned BY
    EVENTKIT ON SAVE, so an undo that looks up "the identifier EventKit gave
    us" is the shape SHELF 2 excludes by name. The target below is minted
    before the act, so the undo resolves from `minted_by_us` alone.
    """
    return ActDeclaration(
        act_type="calendar_event",
        reach="owner_calendar",
        executor=executor,
        target=UndoInput(name="event tag", provenance="minted_by_us",
                         ref="calendar_event_tag"),
    )


# ------------------------------------------------- what decides the routing

def test_the_declared_executor_decides_the_lane():
    assert device_lane(calendar_act()) == DEVICE_CALENDAR_LANE


def test_the_registry_is_a_lookup_and_not_an_identity_function():
    """The executor and the lane are DIFFERENT strings on purpose.

    If they were the same word, `device_lane` returning its own argument
    would pass every test above while being no registry at all.
    """
    assert PHONE_CALENDAR_EXECUTOR != DEVICE_CALENDAR_LANE
    assert DEVICE_EXECUTOR_LANES[PHONE_CALENDAR_EXECUTOR] == DEVICE_CALENDAR_LANE


def test_the_wording_decides_nothing():
    """LAW 1's regression guard, and the reason this file exists.

    Every one of these goals is a calendar write in English. None of them
    carries an act declaration, so none of them may leave the browser lane.
    The day somebody adds `if "calendar" in goal` this test goes red.
    """
    for goal in ("put dinner Thursday 7pm in my calendar",
                 "add the dentist to my calendar for Friday at 3",
                 "schedule the standup for 9am tomorrow",
                 "book Thursday 7pm"):
        assert device_lane(None) == ""
        assert job_lane(goal) == "", goal


def test_a_goal_that_never_says_calendar_still_reaches_the_phone():
    """The other half of the same guard: the declaration is sufficient.

    A word list would have to recognise this goal, and could not.
    """
    assert device_lane(calendar_act()) == DEVICE_CALENDAR_LANE


def test_an_unknown_executor_never_reaches_the_device_lane():
    """FLOOR POLARITY. An unrecognised executor is not a new lane, it is the
    lane everything already goes to."""
    assert device_lane(calendar_act(executor="anticipy_store")) == ""
    assert device_lane(calendar_act(executor="")) == ""
    assert device_lane(calendar_act(executor="phone_eventkit_v2")) == ""
    assert device_lane(None) == ""
    assert device_lane({"executor": PHONE_CALENDAR_EXECUTOR}) == ""


def test_the_device_lane_is_its_own_string():
    assert DEVICE_CALENDAR_LANE not in ("", RESEARCH_LANE, "supervised_read")


# -------------------------------------------------- delivery is not permission

def test_routing_admits_nothing_to_shelf_two():
    """Being in the lane registry is a DELIVERY fact, never an admission.

    §10.3: the admitted set can only ever refuse. A calendar write is held
    for approval by `is_consequential` (touches == "world" sits above the
    explicit escape), and the lane is chosen after the gate has already
    decided. If this ever goes green the wrong way, a device lane has become
    a hole in the gate — the exact failure the research named.
    """
    assert "calendar_event" not in ADMITTED_ACT_TYPES
    assert PHONE_CALENDAR_EXECUTOR not in {
        a.executor for a in ADMITTED_ACT_TYPES.values()}


def test_the_gate_still_holds_a_calendar_write():
    assert core.is_consequential("put dinner Thursday 7pm in my calendar",
                                 explicit=True, touches="world") is True


def test_a_calendar_write_is_refused_act_and_tell_even_with_a_perfect_undo():
    """The outcome the brief asked to be STATED rather than bent around.

    This plan's undo is impeccable by §5.2: one input, `minted_by_us`, whose
    value is held before the act, addressing the same reference the act
    declares as its target. Nothing in it needs anything EventKit returned —
    `EKEvent.eventIdentifier` never appears. It is still refused, at the
    first branch, because `calendar_event` is not in the admitted set and
    §10.3 says that set can only ever refuse.

    So rung 0 ships HELD. The minted id is worth building for moment 11's
    "(undo)" — but it buys the owner a one-tap reversal, not an exemption
    from the tap that starts it. A minted id built as a PERMISSION is one
    refactor away from somebody deciding the approval is redundant.
    """
    tag = UndoInput(name="event tag", provenance="minted_by_us",
                    ref="calendar_event_tag")
    plan = new_plan(
        owner_ref="own1", lineage_key="lin1", goal="dinner Thursday 7pm",
        consequence=Consequence.CONSEQUENTIAL, source_event_id="e1",
        act=calendar_act(),
        undo=UndoPlan(
            act_type="calendar_event",
            steps=("find the event carrying our tag and remove it",),
            inputs=(tag,),
            held={"minted_by_us": {"calendar_event_tag": "a3f1-…"}}),
        lineage_seq=1,
    )
    assert admissible(plan) == Refusal.ACT_TYPE_NOT_ADMITTED.value


# ------------------------------------------------------ through _queue_job

def _queue(monkeypatch, goal, act=None, key="test-key", **kw):
    if key is None:
        monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    else:
        monkeypatch.setenv("BRAVE_API_KEY", key)
    posted = {}

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"id": "j1", "status": "awaiting_confirm"}

    monkeypatch.setattr(core.pb, "post",
                        lambda url, **k: (posted.update(k.get("json") or {}),
                                          R())[1])
    a = Anticipy(owner_id="own1")
    monkeypatch.setattr(a, "_same_pending", lambda goal, **_k: None)
    a._queue_job(goal, {"source": "test", "now": "now"}, act=act, **kw)
    return posted


def test_queue_stamps_the_device_lane(monkeypatch):
    posted = _queue(monkeypatch, "dinner Thursday 7pm", act=calendar_act(),
                    touches="world")
    assert posted["lane"] == DEVICE_CALENDAR_LANE
    assert posted["status"] == "awaiting_confirm"   # the gate still holds it


def test_the_device_lane_does_not_need_a_brave_key(monkeypatch):
    """The research arm needs Brave. The phone does not.

    `_queue_job` reads the lane through `if os.environ.get("BRAVE_API_KEY")`.
    A calendar hand that silently reverts to Chrome because a SEARCH key is
    unset would be a hand that works in staging and not in production.
    """
    posted = _queue(monkeypatch, "dinner Thursday 7pm", act=calendar_act(),
                    key=None, touches="world")
    assert posted["lane"] == DEVICE_CALENDAR_LANE


def test_the_research_gate_never_parks_a_device_job(monkeypatch):
    """A parked row carries `_research_gate.handback`, and
    `worker.run_preflight_research` hands every one of those back with
    `{"lane": ""}` — hardcoded. A device job that ever got that marker would
    be moved into his Chrome by a pass that has no idea the phone exists.

    The gate is FORCED to hold here. Left to itself it opens in this harness
    (`gate_can_run` needs a live model, and there is none), which would make
    this test green whatever the ordering in `_queue_job` is — the exact
    shape of a test that cannot fail.
    """
    holds = core.research.GateVerdict(core.research.GATE_RESEARCH,
                                      "forced: touches=world")
    monkeypatch.setattr(core.research, "research_gate",
                        lambda *a, **k: holds)
    # The control: with no declaration this same forced gate DOES park it.
    parked = _queue(monkeypatch, "dinner Thursday 7pm", touches="world")
    assert parked["lane"] == RESEARCH_LANE
    assert json.loads(parked["params"])["_research_gate"]["handback"] is True

    posted = _queue(monkeypatch, "dinner Thursday 7pm", act=calendar_act(),
                    touches="world")
    gate = json.loads(posted["params"])["_research_gate"]
    assert "handback" not in gate
    assert posted["lane"] == DEVICE_CALENDAR_LANE


def test_the_same_goal_without_a_declaration_stays_in_the_browser(monkeypatch):
    posted = _queue(monkeypatch, "dinner Thursday 7pm", touches="world")
    assert posted["lane"] == ""


# --------------------------------------------- nobody claimed it, so say so

def test_the_worker_and_the_brain_spell_the_lane_once():
    assert W.DEVICE_CALENDAR_LANE is DEVICE_CALENDAR_LANE


def test_the_brain_and_the_backend_hook_spell_the_lane_the_same():
    """The drift this repo has already had once: `background.js:60-73` kept
    two copies of one lane clause and they diverged. The brain queues the row
    and `backend/pb_hooks/research_lane.pb.js` is what keeps a browser off
    it — a typo in either is a lane nobody enforces, which is worse than no
    lane at all."""
    from pathlib import Path
    import re
    src = (Path(__file__).resolve().parent.parent / "backend" / "pb_hooks"
           / "research_lane.pb.js").read_text()
    m = re.search(r'const DEVICE_LANE = "([^"]+)"', src)
    assert m, "research_lane.pb.js must name the device lane exactly once"
    assert m.group(1) == DEVICE_CALENDAR_LANE


def test_the_worker_loop_actually_calls_it():
    """A pass nothing calls is a comment.

    Deleting the one line from `main()` broke no test in the first draft of
    this file, which is the same failure as the pass not existing: the row
    still waits forever and he is still not told. `report_stalled_work` is
    the control — both hands are announced from the same loop or neither is.
    """
    import inspect
    body = inspect.getsource(W.main)
    assert "report_stalled_work(anticipy)" in body
    assert "report_unclaimed_device_work(anticipy)" in body


def test_a_device_job_is_not_reported_as_a_missing_browser(monkeypatch):
    """The false sentence. `report_stalled_work` says "I just need your Chrome
    open" about every stalled row that is not research and not ambient — and
    a calendar write does not need his Chrome at all. Telling him to open a
    browser that would not help is the same class of lie as promising to
    solve a CAPTCHA."""
    said = []
    _stall_backend(monkeypatch, [_device_row()])
    monkeypatch.setattr(W, "browser_reachable", lambda *a, **k: False)
    W.report_stalled_work(_anticipy(said))
    assert said == [], said


def test_a_device_job_nobody_claimed_is_still_reported(monkeypatch):
    """The silence. With Chrome up, `report_stalled_work` returns at the first
    line and the row is never looked at — so a calendar write whose phone is
    off waits forever with no word to him."""
    said = []
    _stall_backend(monkeypatch, [_device_row()])
    monkeypatch.setattr(W, "browser_reachable", lambda *a, **k: True)
    W.report_unclaimed_device_work(_anticipy(said))
    assert len(said) == 1, said


def test_a_fresh_device_job_is_not_reported(monkeypatch):
    """Three-second poll or not, a row minted seconds ago is not stalled."""
    said = []
    _stall_backend(monkeypatch, [_device_row(minutes_old=0)])
    W.report_unclaimed_device_work(_anticipy(said))
    assert said == []


def test_the_device_stall_notice_is_not_repeated(monkeypatch):
    """Same durable-record discipline every other send in this file carries:
    a write outage turned one notification into one text every two seconds."""
    said = []
    _stall_backend(monkeypatch, [_device_row()], writes_fail=True)
    for _ in range(8):
        W.report_unclaimed_device_work(_anticipy(said))
    assert len(said) == 1, said


def test_the_device_stall_notice_respects_quiet_hours(monkeypatch):
    said = []
    _stall_backend(monkeypatch, [_device_row()])
    monkeypatch.setattr(W, "CLOCK_QUIET_START", 0)
    monkeypatch.setattr(W, "CLOCK_QUIET_END", 25)
    W.report_unclaimed_device_work(_anticipy(said))
    assert said == []


def test_an_undelivered_device_notice_is_not_recorded_as_sent(monkeypatch):
    """`notify_owner` returning falsy means it did not go. Recording it
    anyway is how she stamped his questions delivered and sent nothing for
    ten hours."""
    said = []
    _stall_backend(monkeypatch, [_device_row()])
    a = _anticipy(said)
    a.notify_owner = lambda msg, channel="sms": (said.append(msg), False)[1]
    W.report_unclaimed_device_work(a)
    assert len(said) == 1
    a.notify_owner = lambda msg, channel="sms": (said.append(msg), {"ok": 1})[1]
    W.report_unclaimed_device_work(a)
    assert len(said) == 2, "a failed send must be retried, not swallowed"


# ------------------------------------------------------------------ harness


@pytest.fixture(autouse=True)
def clean_process_state():
    W.REPORTED.clear()
    W._SENT_RECENTLY.clear()
    yield
    W.REPORTED.clear()
    W._SENT_RECENTLY.clear()


class _Resp:
    def __init__(self, payload=None, ok=True):
        self.ok = ok
        self.status_code = 200 if ok else 500
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError("write refused")


def _anticipy(said):
    return types.SimpleNamespace(
        owner_id="own1", owner_ref="", backend_url="http://pb", llm=None,
        _voice=lambda ctx: None,
        notify_owner=lambda msg, channel="sms": (said.append(msg), {"ok": 1})[1])


def _device_row(minutes_old=30):
    stamp = (datetime.now(timezone.utc) - timedelta(minutes=minutes_old)
             ).strftime("%Y-%m-%d %H:%M:%S")
    return {"id": "d1", "goal": "dinner Thursday 7pm",
            "status": "queued", "lane": DEVICE_CALENDAR_LANE,
            "params": "{}", "owner": "own1", "updated": stamp,
            "created": stamp}


def _stall_backend(monkeypatch, jobs, writes_fail=False):
    monkeypatch.setattr(W, "CLOCK_QUIET_START", 25)
    monkeypatch.setattr(W, "CLOCK_QUIET_END", 0)

    def _get(url, **kw):
        """A jobs collection that actually APPLIES the two clauses on test.

        It has to. A double that hands every row back regardless of the query
        makes `test_a_fresh_device_job_is_not_reported` green whether or not
        the cutoff was ever put in the filter — six can't-fail tests were
        found in this repo yesterday and this is the shape of all of them.
        """
        if "/collections/events/" in url:
            return _Resp({"items": []})
        want = (kw.get("params") or {}).get("filter") or ""
        cutoff = re.search(r'updated<="([^"]+)"', want)
        # BOTH POLARITIES, and the negative one is the load-bearing half.
        # An earlier version of this double only honoured `lane="X"`, so a
        # row whose lane the filter EXCLUDED was dropped for the wrong
        # reason — and deleting `lane!="device_calendar"` from
        # `report_stalled_work` stayed green. The mutation that survives is
        # the one the double is hiding.
        only = {m.group(1) for m in re.finditer(r'(?<!!)lane="([^"]*)"', want)}
        never = {m.group(1) for m in re.finditer(r'lane!="([^"]*)"', want)}
        rows = []
        for j in jobs:
            lane = j["lane"]
            if only and lane not in only:
                continue
            if lane in never:
                continue
            if cutoff and j["updated"] > cutoff.group(1):
                continue          # too fresh — the server would not return it
            rows.append(j)
        return _Resp({"items": rows})

    monkeypatch.setattr(W.pb, "get", _get)
    monkeypatch.setattr(W.pb, "post", lambda *a, **k: _Resp(ok=not writes_fail))
    monkeypatch.setattr(W.pb, "patch", lambda *a, **k: _Resp())
