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
from brain.anticipy_core import (DEVICE_ACT_LANES, DEVICE_CALENDAR_LANE,
                                 PHONE_CALENDAR_ACT_TYPE,
                                 PHONE_CALENDAR_EXECUTOR,
                                 PHONE_CALENDAR_REACH, RESEARCH_LANE,
                                 Anticipy, device_lane, job_lane)
from brain.workflow import (ADMITTED_ACT_TYPES, ActDeclaration, Consequence,
                            Refusal, UndoInput, UndoPlan, admissible,
                            merge as merge_plan, new_plan)


def calendar_act(executor=PHONE_CALENDAR_EXECUTOR,
                 act_type=PHONE_CALENDAR_ACT_TYPE,
                 reach=PHONE_CALENDAR_REACH):
    """What the model declares when the errand's effect is a calendar write.

    Spelled from the module's constants and never from literals, so this
    helper cannot be quietly "fixed" into agreeing with a brain that has
    drifted away from the phone. The strings themselves are pinned against
    `CalendarHandPolicy.swift` by
    `test_the_brain_and_the_phone_spell_the_act_the_same`.

    The minted id is the point: `EKEvent.eventIdentifier` is assigned BY
    EVENTKIT ON SAVE, so an undo that looks up "the identifier EventKit gave
    us" is the shape SHELF 2 excludes by name. The target below is minted
    before the act, so the undo resolves from `minted_by_us` alone.
    """
    return ActDeclaration(
        act_type=act_type,
        reach=reach,
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
    assert DEVICE_ACT_LANES[
        (PHONE_CALENDAR_ACT_TYPE, PHONE_CALENDAR_REACH,
         PHONE_CALENDAR_EXECUTOR)
    ] == DEVICE_CALENDAR_LANE


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
    assert device_lane(
        calendar_act(executor=PHONE_CALENDAR_EXECUTOR + "_v2")) == ""
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
    assert PHONE_CALENDAR_ACT_TYPE not in ADMITTED_ACT_TYPES
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
    first branch, because `calendar_write` is not in the admitted set and
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
            act_type=PHONE_CALENDAR_ACT_TYPE,
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


def test_refining_a_card_cannot_move_it_to_another_hand():
    """The row's `lane` column is written ONCE, at mint.

    `Anticipy._merge_into` — the path a plan assembled over several turns
    takes, "book dinner tomorrow" becoming "book dinner for 2 at Cactus Club
    at 7 PM" — returns before the lane is ever computed and its PATCH does
    not carry a `lane` field. That is only safe while the ACT is stable
    across a merge, because the lane was derived from the act: if an
    amendment could replace the act, the row would keep a lane its own
    embedded plan no longer agrees with, and a calendar errand would be
    delivered to Chrome (or a restaurant booking to a phone that cannot
    make one) with nothing anywhere disagreeing.

    `merge()` preserves it today only because `replace()` does not name it.
    That is an accident of one line, so it is pinned here rather than
    trusted.
    """
    plan = new_plan(
        owner_ref="own1", lineage_key="lin1", goal="dinner Thursday",
        consequence=Consequence.CONSEQUENTIAL, source_event_id="e1",
        act=calendar_act(),
    )
    amended = merge_plan(plan, expected_version=plan.version,
                         goal="dinner Thursday 7pm for two",
                         authority_text="make it 7, for two")
    assert amended.goal != plan.goal          # the amendment really landed
    assert device_lane(amended.act) == device_lane(plan.act)
    assert device_lane(amended.act) == DEVICE_CALENDAR_LANE


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


def _calls(fn, name):
    """Does `fn`'s body contain a CALL to `name` — not a mention of it.

    `"name(" in inspect.getsource(fn)` was the first draft, and a
    commented-out line contains that substring. Mutation, in `worker.main`:
    `report_unclaimed_device_work(anticipy)` -> `pass  #
    report_unclaimed_device_work(anticipy)`. 23 passed, 2251 passed, exit 0.
    A comment parses to nothing at all, so the AST cannot be fooled the same
    way — and neither can a docstring, a log line naming the function, or a
    string in a list of names somebody meant to call later.
    """
    import ast
    import inspect
    import textwrap
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    return any(isinstance(node, ast.Call)
               and getattr(node.func, "id", None) == name
               for node in ast.walk(tree))


def test_the_worker_loop_actually_calls_it():
    """A pass nothing calls is a comment.

    Deleting the one line from `main()` broke no test in the first draft of
    this file, which is the same failure as the pass not existing: the row
    still waits forever and he is still not told. `report_stalled_work` is
    the control — both hands are announced from the same loop or neither is.
    """
    assert _calls(W.main, "report_stalled_work")
    assert _calls(W.main, "report_unclaimed_device_work")


# The two shapes `_calls` has to tell apart, written as REAL functions in a
# REAL file — which is the whole difficulty. The first draft of the control
# below built them with `exec` of a string, and `exec`ed code has
# `co_filename == "<string>"` with nothing behind it, so `inspect.getsource`
# raised `OSError: could not get source code` and the control could not run at
# all. A source-inspecting check has to be tested against a subject that HAS
# source, on the same code path `W.main` takes.
#
# `_wiring_sample_commented_out` is the exact mutation that beat the
# substring check: `report_unclaimed_device_work(anticipy)` demoted to a
# trailing comment. Neither sample is ever called; the name inside the second
# is deliberately unbound, and binding it would be the mistake — `_calls`
# reads source, and a helper that also had to RUN would pin nothing about
# `W.main`.


def _wiring_sample_commented_out():
    pass  # report_unclaimed_device_work(anticipy)


def _wiring_sample_really_calls():
    report_unclaimed_device_work(anticipy)  # noqa: F821  # never executed


def test_the_wiring_check_can_tell_a_call_from_a_comment():
    """The control for the control.

    `_calls` is the only thing standing between "the worker announces
    unclaimed device work" and a green suite that proves nothing, so it is
    tested against the exact mutation that beat its predecessor rather than
    trusted because it says `ast`.

    Both directions, always. Only the negative half would stay green for
    `_calls = lambda *a: False`, which would take `test_the_worker_loop
    _actually_calls_it` down with it — but silently, as a helper nobody
    doubted.
    """
    assert not _calls(_wiring_sample_commented_out,
                      "report_unclaimed_device_work")
    assert _calls(_wiring_sample_really_calls,
                  "report_unclaimed_device_work")


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


def _device_row(minutes_old=30, lane=DEVICE_CALENDAR_LANE, status="queued"):
    """One row on the device lane.

    `lane` is a parameter because the STORED string is the thing under test
    below: the hook accepts a rewrite to "Device_Calendar" as no change at
    all, and PocketBase keeps what it was given.
    """
    stamp = (datetime.now(timezone.utc) - timedelta(minutes=minutes_old)
             ).strftime("%Y-%m-%d %H:%M:%S")
    return {"id": "d1", "goal": "dinner Thursday 7pm",
            "status": status, "lane": lane,
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


# ==================================================================== REPAIR
# Everything below was added because the first draft of this file left four
# doors open. Each block names the door and the mutation that walked through
# it while the whole suite stayed green.


# --------------------------------------------------------------------------
# LAW 1, AT THE MINT POINT — not at `device_lane`.
#
# `test_the_wording_decides_nothing` above cannot see this. It asserts
# `device_lane(None) == ""` inside a loop over goals, which is loop-invariant,
# and `job_lane(goal) == ""`, which is about the RESEARCH lane. `device_lane`
# takes an `ActDeclaration`, so no word list can ever be written INTO it — a
# word list has to go where the GOAL is, and that is `_queue_job`. This is the
# mutation that survived the first draft, at anticipy_core.py's lane line:
#
#   lane = device_lane(act) or (DEVICE_CALENDAR_LANE
#                               if "calendar" in (goal or "").lower() else lane)
#
# 23 passed, 2251 passed, exit 0.
#
# So the property is not "no word list is in `device_lane`". It is: THE DEVICE
# LANE DOES NOT VARY WITH THE GOAL. Hold the declaration fixed, vary the words
# over every shape a word list would reach for, and the answer must not move.
# That kills a predicate on any vocabulary, in any language, including one
# nobody thought to put in a corpus.

CALENDAR_IN_PLAIN_ENGLISH = (
    "put dinner with Sara Thursday 7pm on my calendar",
    "add the dentist to my calendar for Friday at 3",
    "schedule the standup for 9am tomorrow",
    "block out Thursday evening",
    "create a calendar event for the flight home",
    "book Thursday 7pm",
)

# The same errands with every word a list could key on removed. A word list
# strong enough to pass the block above would have to recognise these too, and
# cannot.
NOTHING_A_WORD_LIST_COULD_SEE = (
    "dinner with Sara",
    "the thing Omar asked about",
    "sara + me, the italian place",
    "tell Marcus I am in",
)

EVERY_GOAL = CALENDAR_IN_PLAIN_ENGLISH + NOTHING_A_WORD_LIST_COULD_SEE


def test_the_mint_point_routes_on_the_declaration_and_never_on_the_goal(
        monkeypatch):
    """The invariance, stated as an invariance.

    With a declaration, every goal lands on the device lane. Without one, no
    goal does. Both halves are needed: the first kills
    `device_lane(act) and <word list>`, the second kills
    `device_lane(act) or <word list>`.
    """
    with_declaration = {
        goal: _queue(monkeypatch, goal, act=calendar_act(),
                     touches="world")["lane"]
        for goal in EVERY_GOAL}
    without_declaration = {
        goal: _queue(monkeypatch, goal, touches="world")["lane"]
        for goal in EVERY_GOAL}

    assert set(with_declaration.values()) == {DEVICE_CALENDAR_LANE}, \
        with_declaration
    assert DEVICE_CALENDAR_LANE not in set(without_declaration.values()), \
        without_declaration


def test_no_wording_mints_a_device_lane_row_on_its_own(monkeypatch):
    """The half that goes red the day somebody adds the demo fallback.

    Named separately from the invariance above so the failure reads as what it
    is rather than as a set comparison.
    """
    for goal in CALENDAR_IN_PLAIN_ENGLISH:
        posted = _queue(monkeypatch, goal, touches="world")
        assert posted["lane"] != DEVICE_CALENDAR_LANE, goal


# --------------------------------------------------------------------------
# THE GATE, WITH EVERY ARGUMENT THE MINT POINT IS HOLDING.
#
# `_queue_job` had `touches` in its hands — it passes it to `_refines_pending`
# and to `_research_gate` — and dropped it on the floor at the consequence
# line. `is_consequential(goal, params, explicit=True)` is False for a
# calendar write; `is_consequential(goal, params, explicit=True,
# touches="world")` is True. Same act, opposite sides of the confirmation
# gate, decided by whether the verb happened to be in a regex.
#
# Reproduced against the tree before the fix: act=<calendar act>,
# explicit=True, touches="world" posted lane='device_calendar',
# status='queued', consequence='read_only', approval=''. Neither server layer
# refuses that row.
#
# The pin below is not "explicit+world is held". It is that THE ROW CARRIES
# THE GATE'S OWN ANSWER, computed from every input the mint point has. Drop
# any argument and a cell of the matrix disagrees.

GATE_INPUTS = [(hold, explicit, touches)
               for hold in (False, True)
               for explicit in (False, True)
               for touches in (None, "world", "read", "compute")]


@pytest.mark.parametrize("hold,explicit,touches", GATE_INPUTS)
def test_the_row_carries_the_gates_own_answer(monkeypatch, hold, explicit,
                                              touches):
    """Asked with NO declaration, which is the only way this can see the bug.

    The first draft asked it with `act=calendar_act()`, and the device floor
    below now holds every one of those cells whatever the gate says — so with
    a declaration on the row this matrix would stay green with `touches`
    dropped again. A plain row is the one that still moves when the argument
    goes missing: `is_consequential(goal, explicit=True)` is False and
    `is_consequential(goal, explicit=True, touches="world")` is True.
    """
    goal = "put dinner with Sara Thursday 7pm on my calendar"
    want = bool(hold or core.is_consequential(
        goal, {"source": "test", "now": "now"},
        explicit=explicit, touches=touches))
    posted = _queue(monkeypatch, goal, hold=hold,
                    explicit=explicit, touches=touches)
    assert (posted["consequence"] == "consequential") is want, posted
    assert (posted["status"] == "awaiting_confirm") is want, posted


# --------------------------------------------------------------------------
# AND THE FLOOR UNDER ALL OF IT: A DEVICE WRITE IS NEVER READ-ONLY.
#
# Passing `touches` closed the cell the reviewer reproduced and left the rest
# of the row open. Read the matrix above against a CALENDAR ACT:
#
#   explicit=True,  touches=None    -> is_consequential False
#   explicit=False, touches="read"  -> is_consequential False
#
# Both mint `lane='device_calendar'`, `consequence='read_only'`,
# `status='queued'`, `approval=''` — an unapproved calendar write standing in
# the phone's queue, and `workflow_guard`'s NO_APPROVAL_NEEDED contains
# `read_only`, so no server layer refuses it. Whether the owner has to tap is
# decided by whether his verb happened to reach a regex and by which effect
# channel triage filled in. That is a device lane that does not route through
# the same gate, which the research names as a hole in the gate and not a
# hand.
#
# The floor does not consult any of that. `device_lane(act)` is non-empty
# only for a declaration whose act type is `calendar_write` and whose reach is
# the owner's calendar store — the model saying, in a typed field, that this
# errand leaves the machine. A row that says so is consequential, and no
# wording, flag or missing argument can lower it.


@pytest.mark.parametrize("hold,explicit,touches", GATE_INPUTS)
def test_a_declared_device_write_is_never_minted_read_only(
        monkeypatch, hold, explicit, touches):
    posted = _queue(monkeypatch,
                    "put dinner with Sara Thursday 7pm on my calendar",
                    act=calendar_act(), hold=hold, explicit=explicit,
                    touches=touches)
    assert posted["lane"] == DEVICE_CALENDAR_LANE, posted
    assert posted["consequence"] == "consequential", posted
    assert posted["status"] == "awaiting_confirm", posted
    assert posted["approval"] == "", posted


def test_the_floor_holds_for_every_wording_a_device_act_can_carry(monkeypatch):
    """The words vary, the declaration does not, the answer does not move.

    Same invariance as the routing one and for the same reason: a floor that
    read the goal would be the Law 1 violation wearing a different hat.
    """
    for goal in EVERY_GOAL:
        posted = _queue(monkeypatch, goal, act=calendar_act(), explicit=True,
                        touches=None)
        assert posted["consequence"] == "consequential", (goal, posted)
        assert posted["status"] == "awaiting_confirm", (goal, posted)


def test_the_floor_is_the_declaration_and_not_the_lane_string(monkeypatch):
    """Polarity: a row with no declaration is NOT floored into a hold.

    `consequential = True` unconditionally would pass every assertion above
    while destroying the read-only path the browser lane runs on.
    """
    posted = _queue(monkeypatch, "what time does the italian place close",
                    touches="read")
    assert posted["consequence"] == "read_only", posted
    assert posted["status"] != "awaiting_confirm", posted


def test_an_asked_for_calendar_write_is_still_held(monkeypatch):
    """The instance, spelled out, because it is the one that ships.

    The owner asking in so many words is authority to START the errand. It is
    not authority to skip the tap on an act that leaves his world — that is
    what `touches == "world"` sitting ABOVE the explicit escape means, and the
    lane's own header claims it as the reason a device lane is not a hole in
    the gate. The claim was true of `is_consequential` and false of the only
    caller that mints a device row.
    """
    posted = _queue(monkeypatch,
                    "put dinner with Sara Thursday 7pm on my calendar",
                    act=calendar_act(), explicit=True, touches="world")
    assert posted["lane"] == DEVICE_CALENDAR_LANE
    assert posted["consequence"] == "consequential"
    assert posted["status"] == "awaiting_confirm"
    assert posted["approval"] == ""


# --------------------------------------------------------------------------
# THE ROW SAYS WHAT IT IS — and the phone is the one that reads it.
#
# `CalendarHandPolicy.decide` reads `params._workflow.act` and refuses on
# `act_type`, `reach` and `executor` before it looks at anything else.
# `_queue_job` used the act to CHOOSE the lane and then never put it on the
# plan: `new_plan(...)` was called without `act=`. So every device row the
# brain minted arrived at the phone with no act at all and was refused
# `.actTypeNotAdmitted("")`, after which `report_unclaimed_device_work` texted
# the owner "it just needs the Anticipy app open" about an app that was open
# and refusing.
#
# This is the wire contract, tested as the wire, not as two constants that
# agree with each other in Python.


def _swift(name):
    """A `static let` out of the phone's policy file."""
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "app" / "ios" / "Anticipy"
           / "Backend" / "CalendarHandPolicy.swift").read_text()
    m = re.search(r'static let %s = "([^"]+)"' % re.escape(name), src)
    assert m, f"CalendarHandPolicy must name {name} exactly once"
    return m.group(1)


def test_a_device_row_carries_the_act_the_phone_will_accept(monkeypatch):
    posted = _queue(monkeypatch, "dinner Thursday 7pm", act=calendar_act(),
                    touches="world")
    assert posted["lane"] == _swift("lane")
    plan = json.loads(posted["params"])["_workflow"]
    act = plan.get("act")
    assert act, "a device-lane row with no act is refused by the phone"
    assert act["act_type"] == _swift("writeActType"), act
    assert act["reach"] == _swift("reach"), act
    assert act["executor"] == _swift("executor"), act


def test_the_brain_and_the_phone_spell_the_act_the_same():
    """The constants, pinned in the direction that matters.

    Each of these strings lived in exactly one file plus its own tests, and a
    grep across the repo found zero overlap: the brain routed `phone_eventkit`
    and the phone refused anything that was not `anticipy_phone`. Nothing was
    red. `test_the_brain_and_the_backend_hook_spell_the_lane_the_same` pins
    the LANE across two files and stops there.

    AND IT PINS THEM IN A DIRECTION, which is the half a bare `==` leaves to
    whoever reads the failure. The brain is canonical: it mints the row and it
    enforces the gate, so `anticipy_core.py` names the contract and
    `CalendarHandPolicy.swift` is the file that moves when these disagree.
    Left symmetric, the cheapest way to green is to edit whichever side is
    already open in the editor — and the side that is usually open is the one
    that cannot be recalled once it is on a phone.
    """
    fix = ("the brain is canonical here: change CalendarHandPolicy.swift to "
           "match brain/anticipy_core.py, never the other way round")
    assert PHONE_CALENDAR_EXECUTOR == _swift("executor"), fix
    assert PHONE_CALENDAR_ACT_TYPE == _swift("writeActType"), fix
    assert PHONE_CALENDAR_REACH == _swift("reach"), fix
    assert DEVICE_CALENDAR_LANE == _swift("lane"), fix


def test_a_goal_with_no_declaration_leaves_no_act_on_the_row(monkeypatch):
    """Floor polarity for the line above: the act is carried, never invented.

    `act=act` must not become `act=act or something_the_goal_implies`.
    """
    for goal in CALENDAR_IN_PLAIN_ENGLISH:
        posted = _queue(monkeypatch, goal, touches="world")
        plan = json.loads(posted["params"])["_workflow"]
        assert plan.get("act") in (None, {}), (goal, plan.get("act"))


# --------------------------------------------------------------------------
# THE SCOPE IS ONE VERB, AND THE BRAIN'S HALF MUST SAY SO.
#
# `DEVICE_EXECUTOR_LANES` was an executor->lane registry, so a second verb was
# one dict line — `'phone_mail': DEVICE_CALENDAR_LANE` — plus a device-side
# handler. No lane rename anybody has to type, no server change, and every
# server refusal still passes: `deviceShapeRefusal` reads `workflow_id` and
# `consequence` and never `act_type`. "The scope is in the lane string" was
# not true of the brain's side of the seam.
#
# The registry is now keyed on the ACT, and it is pinned to exactly one entry,
# so widening it is a diff that goes red and has to be defended.


def test_a_second_verb_cannot_ride_the_calendar_lane():
    mail = ActDeclaration(
        act_type="mail_send", reach=PHONE_CALENDAR_REACH,
        executor=PHONE_CALENDAR_EXECUTOR,
        target=UndoInput(name="draft tag", provenance="minted_by_us",
                         ref="mail_tag"))
    assert device_lane(mail) == ""


def test_the_device_registry_holds_exactly_the_one_calendar_act():
    """A closed table, pinned whole.

    Not `DEVICE_CALENDAR_LANE in .values()` — that stays green while a second
    key sits beside the first. The whole dict, so any added row is red.
    """
    assert dict(DEVICE_ACT_LANES) == {
        (PHONE_CALENDAR_ACT_TYPE, PHONE_CALENDAR_REACH,
         PHONE_CALENDAR_EXECUTOR): DEVICE_CALENDAR_LANE}


def test_the_right_executor_with_the_wrong_act_is_not_a_lane():
    assert device_lane(calendar_act(act_type="calendar_undo")) == ""
    assert device_lane(calendar_act(act_type="")) == ""


# --------------------------------------------------------------------------
# THE BRAIN MUST ROUTE ON EVERY FIELD THE PHONE REFUSES ON.
#
# Found while verifying the contract-strings finding, and not closed by it.
# Count the fields each layer reads off the declaration:
#
#   brain  `device_lane`                     act_type, executor
#   hook   `deviceShapeRefusal`              act_type
#   phone  `CalendarHandPolicy.decide`       act_type, reach, executor
#
# `reach` is read by exactly one of the three, and it is the one that cannot
# be recalled. So a declaration of `calendar_write` / `anticipy_phone` with
# any other reach was routed ONTO the device lane by the brain, passed the
# hook's act-type leg, arrived at the phone, and was refused
# `.reachDisagrees` — after which `report_unclaimed_device_work` texts the
# owner "it goes the moment the app is open" about an app that is open and
# refusing. That is the same untruth the contract-strings finding was about,
# reached through the one field that finding did not name, and no test in
# this file could see it: every helper spelled all three from the constants
# at once, so the three were never varied independently.
#
# The property, stated so it cannot rot: whatever the phone compares, the
# brain compares too. Read straight out of the Swift file rather than from
# this module's constants, because a brain that has drifted would otherwise
# agree with itself.


def test_the_brain_routes_on_every_field_the_phone_refuses_on():
    """Vary one field at a time; each one alone must take the lane away.

    Not `!=` against our own constants — the values come out of
    `CalendarHandPolicy.swift`, so this is the wire contract and not two
    Python names agreeing.
    """
    canonical = {"act_type": _swift("writeActType"),
                 "reach": _swift("reach"),
                 "executor": _swift("executor")}
    assert device_lane(calendar_act(**canonical)) == DEVICE_CALENDAR_LANE, \
        "the canonical triple must still route, or the test proves nothing"
    for field in canonical:
        for wrong in (canonical[field] + "_v2", "", "owner_gmail"):
            act = calendar_act(**dict(canonical, **{field: wrong}))
            assert device_lane(act) == "", (
                f"the phone refuses a declaration whose {field} is {wrong!r}; "
                f"the brain must not deliver one to it")


# =================================================================== REPAIR 2
# The second adversarial pass. Two findings landed on this half of rung 0 and
# they are the same two shapes as the first pass's: a sentence the brain has
# no standing to say, and a lane string the brain read differently from every
# other layer.


# --------------------------------------------------------------------------
# ONE LANE STRING, THREE READERS, TWO OF THEM NORMALISING.
#
# `research_lane.pb.js` normalises with `.trim().toLowerCase()` BEFORE it
# judges anything, so a PATCH rewriting a row's lane to "Device_Calendar" is
# no change at all to its immutability leg and is accepted with a `next()`.
# PocketBase then stores the raw string. `CalendarHandPolicy.normalizedLane`
# normalises too, so the phone still calls that row its own — and says why in
# its own comment: "an orphan is worse than a refusal, because a refusal is
# countable and an orphan is silence."
#
# The brain was the layer that compared raw strings, inside a SQLite filter
# where `=` is case-sensitive. The same row was therefore:
#   (b) NOT excluded by `report_stalled_work`'s `lane!="device_calendar"`, so
#       a calendar errand was announced to him as a stalled BROWSER errand —
#       "I just need your Chrome open" about work Chrome cannot do, which is
#       verbatim the untruth this whole lane was built to end; and
#   (c) NOT matched by `report_unclaimed_device_work`'s `lane="..."`, so the
#       one function that would have told him the truth never saw it either.
#
# Both are closed the same way and in one place: `anticipy_core.
# normalized_lane` is the hook's rule and the phone's rule spelled once, the
# SQL clause is demoted to an optimisation, and the decision is made in
# Python on every row that comes back.


def test_a_case_variant_device_row_is_never_called_a_browser_errand(
        monkeypatch):
    """(b), the untruth — and the one that has to hold even if (c) never did.

    The double applies the filter clauses exactly as the server does, which is
    what makes this test able to fail: "Device_Calendar" is not the string in
    `lane!="device_calendar"`, so the row comes back and reaches the loop.
    """
    said = []
    _stall_backend(monkeypatch, [_device_row(lane="Device_Calendar")])
    monkeypatch.setattr(W, "browser_reachable", lambda *a, **k: False)
    W.report_stalled_work(_anticipy(said))
    assert said == [], said


def test_a_browser_errand_is_still_reported_as_one(monkeypatch):
    """The control. A guard wide enough to silence the browser lane would
    make the test above green while breaking the function it guards."""
    said = []
    _stall_backend(monkeypatch, [_device_row(lane="")])
    monkeypatch.setattr(W, "browser_reachable", lambda *a, **k: False)
    W.report_stalled_work(_anticipy(said))
    assert len(said) == 1, said


def test_every_casing_of_the_device_lane_is_still_reported(monkeypatch):
    """(c), the orphan: a row no hand claims and no notice mentions.

    Stated over casings rather than on one string, because the property is
    not "Device_Calendar works" — it is that the brain reads a stored lane
    the way the two layers that judge it do.
    """
    for lane in ("Device_Calendar", " device_calendar ", "DEVICE_CALENDAR",
                 "device_calendar\n"):
        said = []
        W.REPORTED.clear()
        W._SENT_RECENTLY.clear()
        _stall_backend(monkeypatch, [_device_row(lane=lane)])
        W.report_unclaimed_device_work(_anticipy(said))
        assert len(said) == 1, (lane, said)


def test_the_device_notice_speaks_for_no_other_lane(monkeypatch):
    """The control for the widened query.

    The filter now asks for a superset — everything that is not the browser
    and not research — so the narrowing moved into Python, where a bug is a
    notice claiming a research errand is "waiting on your phone".
    """
    said = []
    _stall_backend(monkeypatch, [_device_row(lane="Research"),
                                 _device_row(lane="supervised_read")])
    W.report_unclaimed_device_work(_anticipy(said))
    assert said == [], said


# --------------------------------------------------------------------------
# WHAT THE BRAIN MAY CLAIM ABOUT A PHONE IT CANNOT SEE.
#
# The first draft told him a queued device errand "goes the moment the app is
# open". That is a statement about the phone's FUTURE BEHAVIOUR, and the
# comment above `report_unclaimed_device_work` spends a paragraph establishing
# that this process cannot see the phone at all: there is no heartbeat row,
# which is exactly why "it is still sitting at queued" is the only observation
# available.
#
# `CalendarHandPolicy.decide` refuses on two dozen enumerated causes
# (CalendarHandPolicy.swift:303-347). The mint point already agrees with the
# phone on the three the routing key can see — act_type, reach, executor — so
# a row that arrives there agrees about the ACT. The rest are invisible from
# here: `.noWritableCalendar`, `.startAlreadyPast`, `.factsIncomplete`,
# `.approvalNotOnTheRow`, `.unresolvedReference`… Every one of them paints the
# same picture: the app is open, it is refusing, and she is texting him that
# it is about to run. The app open and refusing is the ORDINARY case this
# notice exists for, not an edge of it.

# Instances, and named as instances: the wordings the first draft actually
# used, plus the ones a rewrite reaches for first. A phrase list cannot
# enumerate a promise nobody has thought of yet — the exact pin below is what
# covers that half, because any change to these sentences is red and has to be
# argued in a diff rather than merged.
A_PROMISE_THE_BRAIN_CANNOT_KEEP = (
    "the moment the app",
    "just needs",
    "all it needs",
    "as soon as",
    "i'm ready",
    "will go",
    "will run",
    "when the app is open",
    "once the app is open",
)


def _device_notice(monkeypatch, status="queued"):
    """Both halves of what can actually reach him.

    The BRIEF is what steers the sentence he normally gets, and it is the
    only deterministic handle on that sentence — the voice is a model. The
    FALLBACK is what is sent verbatim when the voice is not there.
    """
    said, briefs = [], []
    _stall_backend(monkeypatch, [_device_row(status=status)])
    a = _anticipy(said)
    a._voice = lambda ctx: briefs.append(ctx) or None
    W.report_unclaimed_device_work(a)
    assert len(said) == 1 and len(briefs) == 1, (said, briefs)
    return briefs[0]["situation"], said[0]


@pytest.mark.parametrize("status", ("queued", "running"))
def test_the_device_notice_promises_nothing_about_a_phone_it_cannot_see(
        monkeypatch, status):
    """Neither half may claim the errand is about to run.

    The brief is held to the same list as the sentence, which constrains how
    the prohibition itself may be worded: an instruction that QUOTES the
    promise in order to forbid it is a brief one careless edit away from
    carrying it.
    """
    brief, sentence = _device_notice(monkeypatch, status)
    for phrase in A_PROMISE_THE_BRAIN_CANNOT_KEEP:
        assert phrase not in sentence.lower(), (status, phrase, sentence)
        assert phrase not in brief.lower(), (status, phrase, brief)


@pytest.mark.parametrize("status", ("queued", "running"))
def test_the_device_brief_says_the_phone_cannot_be_seen(monkeypatch, status):
    """The positive half. Absence of a promise is not the same as telling the
    voice it has no standing to make one — and the voice writes the sentence
    that actually goes out."""
    brief, _ = _device_notice(monkeypatch, status)
    low = brief.lower()
    assert "cannot see their phone" in low, brief
    assert "make no promise" in low, brief
    assert "never say it is done" in low, brief


def test_the_queued_brief_names_the_case_that_makes_a_promise_a_lie(
        monkeypatch):
    """A brief that says "do not promise" without saying WHY reads as
    fussiness and gets edited out. The reason is the phone's refusal set."""
    brief, _ = _device_notice(monkeypatch, "queued")
    assert "open and refusing" in brief.lower(), brief


def test_the_device_fallback_sentences_are_pinned(monkeypatch):
    """The half a phrase list cannot cover.

    These two strings are what he receives when the voice is down, and any
    edit to either is red here. That is the point: a promise nobody thought
    to enumerate cannot be re-introduced quietly, only in a diff that also
    edits this test, which is the thing a reviewer reads.
    """
    _, queued = _device_notice(monkeypatch, "queued")
    _, midway = _device_notice(monkeypatch, "running")
    assert queued == (
        "dinner Thursday 7pm — still waiting on your phone. The Anticipy app "
        "hasn't picked it up, and nothing has changed yet."), queued
    assert midway == (
        "dinner Thursday 7pm stopped partway on your phone. It hasn't "
        "finished, and I'm still holding it."), midway
