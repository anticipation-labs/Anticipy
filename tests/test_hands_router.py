"""The Overwatch router in production: `job_lane` asks a model which hand takes
a step, and holds the seatbelt AFTER the verdict.

Until 2026-09-06 `job_lane` (brain/anticipy_core.py) decided the hand with
three regexes over the goal's wording. The spec's router
(spike/two-hands/src/router.ts, 102 tests) had zero production importers.
brain/hands.py is the production router: ONE question asked of a model on its
own, a FOUR-STATE verdict (browser / api / research / hold) plus two honest
non-answers, and the caller comparing the verdict — the house shape from
HARNESS-LAWS.md Law 1 and brain/orchestrator.py.

What these legs pin, and the polarity of each:

  * the four states map to lanes, and hold / unasked / unanswered land on the
    research lane — never the browser, never the api hand (a FLOOR);
  * the irreversible-verb deny list is a seatbelt that holds after ANY
    verdict, including a model that said "research";
  * a connected app with writes OFF is never "api" for a write; with writes
    ON the ladder still needs rung 3; the read case IS licensed, so the floor
    can be told from a router that never says api;
  * connections that could not be read are UNKNOWN and license nothing;
  * the facts are read through the brain's own records client and the owner
    is never taken from params;
  * neither brain/hands.py nor job_lane names an app;
  * CONTROLS: "open example.net in my browser" -> browser lane, "what did I
    promise Marcus" -> research — outcomes that must not move;
  * the source scan: job_lane no longer contains the two wording regexes and
    asks the router EXACTLY ONCE (the mutation literal).

The live leg at the bottom drives the real model over goals from
docs/BRIEF.html's fifty moments and runs only with ANTICIPY_HANDS_LIVE=1: it
is the measurement, and a suite must not spend a model call per run to have
it.

THE PLANNER (2026-09-06, "the planner" section below) — WHICH TOOL, the
fourth house-shape question, `hands.choose_tool`, wired into `choose_hand`
after an api verdict has held the floors (job_lane's one call is untouched):

  * THE REPRODUCTION: an api verdict rode on the row with no `tool` and no
    `args`, so the Worker's /hands/api/run refused every api-lane job
    `tool_required` and handed it to the browser — now the note carries
    {tool, args, effect, tool_verdict, tool_asked} and the lane is "api";
  * the four states — tool / none / unclear / no-verdict — and what each
    does to the lane: only a chosen tool keeps the api hand; none, unclear
    and no-verdict go to the browser with the reason; irreversible is a hold;
  * a slug the model typed that is not in the catalog is no verdict, never
    trusted; the CONTROL is the same slug that is; identity is the catalog's
    spelling (case-folded identifier, as api_hand.ts sameSlug);
  * a destructiveHint tool is irreversible whatever the model declared; a
    createHint tool turns a declared read into a write and the floors run
    AGAIN on the tightened effect (writes off / rung 0 -> browser; CONTROL:
    writes on, rung 3 -> api, write); hints never loosen;
  * no catalog (the live shape today: the Worker serves no catalog route) is
    no verdict, and the api lane is NOT taken; an empty catalog is the
    vendor's own "none" and costs no ask;
  * missing required arguments are asked again in different words, then no
    verdict; arguments are never printed;
  * CONTROL: "what's on my calendar tomorrow" against the REAL 49-row
    catalog (tests/fixtures/googlecalendar_tools_2026-09-06.json, captured
    live) -> GOOGLECALENDAR_FIND_EVENT, effect read, lane "api", and every
    one of the 49 slugs reached the model exactly once;
  * the rendering gets leaner under a budget and never drops a row;
  * the catalog is read through the records client at API_HAND_TOOLS_PATH
    and UNKNOWN is never "no tools";
  * choose_hand asks the tool question EXACTLY ONCE (the mutation literal).
"""
from __future__ import annotations

import inspect
import json
import os
import re
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import brain.anticipy_core as core  # noqa: E402
from brain import hands  # noqa: E402
from brain.anticipy_core import Anticipy, job_lane  # noqa: E402
from brain.hands import (HAND_API, HAND_BROWSER, HAND_HOLD, HAND_RESEARCH,  # noqa: E402
                         HAND_UNANSWERED, HAND_UNASKED, ConnectedApp,
                         HandContext, HandVerdict, choose_hand, lane_for)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ------------------------------------------------------------------ doubles
class ScriptedLLM:
    """Live enough to be asked. `replies` are popped one per call: a string is
    the model's text, an Exception is raised as a transport fault. Records
    every ask so a test can read the prompt the model actually saw."""

    def __init__(self, *replies, live=True):
        self.live = live
        self.replies = list(replies)
        self.asked: list[tuple[str, str, float]] = []

    def chat(self, system, user, temperature=0.1, **kw):
        self.asked.append((system, user, temperature))
        if not self.replies:
            raise AssertionError("the model was asked more times than scripted")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return types.SimpleNamespace(text=reply)


def says(hand, app=None, effect="read", reason="scripted"):
    return json.dumps({"hand": hand, "app": app, "effect": effect,
                       "reason": reason})


@pytest.fixture
def offline(monkeypatch):
    """No network, no key, no owner: every fact is UNKNOWN and any attempt to
    read one is a failure of the test, not a timeout."""
    monkeypatch.delenv("ANTICIPY_PB", raising=False)
    monkeypatch.delenv("ANTICIPY_OWNER_REF", raising=False)
    monkeypatch.setenv("BRAVE_API_KEY", "test-key")

    def tripwire(*a, **k):
        raise AssertionError("a fact was read from the network in an offline test")
    monkeypatch.setattr(hands.pb, "get", tripwire)
    monkeypatch.setattr(hands, "_default_llm", lambda: None)


def route(monkeypatch, goal, *replies, params=None, ctx=None):
    """job_lane with the router's model scripted. Returns (lane, params)."""
    llm = ScriptedLLM(*replies)
    monkeypatch.setattr(hands, "_default_llm", lambda: llm)
    if ctx is not None:
        monkeypatch.setattr(hands, "gather_context", lambda *a, **k: ctx)
    params = dict(params or {"source": "test", "now": "now"})
    return job_lane(goal, params), params, llm


# ------------------------------------------------------- the reproduction
def test_job_lane_no_longer_routes_on_wording():
    """RED before the fix: job_lane held the browser-target and read-only
    regexes and never asked a model. Now it asks the router exactly once —
    the literal a mutation test can count."""
    src = inspect.getsource(job_lane)
    assert "_BROWSER_TARGET_RE" not in src
    assert "_READ_ONLY_RE" not in src
    assert src.count("hands.choose_hand(") == 1
    # The seatbelt is still there, once, and it is not the decider.
    assert src.count("_IRREVERSIBLE_RE.search(g)") == 1


# ------------------------------------------------------- the four states
def test_the_four_verdicts_and_their_lanes():
    assert lane_for(HandVerdict(HAND_BROWSER, "")) == ""
    assert lane_for(HandVerdict(HAND_RESEARCH, "")) == "research"
    assert lane_for(HandVerdict(HAND_HOLD, "")) == "research"
    # api -> its own lane, since 2026-09-06: brain/worker.py run_api_jobs
    # claims it and the Worker's /hands/api/run runs it (routes/hands_api.ts).
    # Until then it mapped to "" because no executor existed; that pin and
    # its reason are in git. tests/test_api_lane.py owns the executor side.
    assert lane_for(HandVerdict(HAND_API, "")) == "api"
    assert hands.LANE_API == "api"
    # The non-answers are the floor's own state, not the browser's.
    assert lane_for(HandVerdict(HAND_UNASKED, "")) == "research"
    assert lane_for(HandVerdict(HAND_UNANSWERED, "")) == "research"
    # A state nobody defined is no verdict.
    assert lane_for(HandVerdict("shadow", "")) == "research"
    assert lane_for(None) == "research"


def test_each_verdict_reaches_the_lane_through_job_lane(monkeypatch, offline):
    # HOLD on a consequential goal is a CARD, not research: the app renders
    # only awaiting_confirm/needs_user as cards, and research is neither, so a
    # held "get the car serviced" parked on research would do nothing and tell
    # nobody. The verifier of 2026-09-06 proved the opposite flip unsafe too
    # (a no-verdict READ must never run in the browser), so the rule is: no
    # verdict + consequential -> "", no verdict + read -> research.
    for hand, lane in ((HAND_BROWSER, ""), (HAND_RESEARCH, "research"),
                       (HAND_HOLD, "")):
        got, params, llm = route(monkeypatch, "sort out the thing with the car",
                                 says(hand))
        assert got == lane, hand
        assert params["_hand"]["hand"] == hand
        assert params["_hand"]["lane"] == lane
        assert len(llm.asked) == 1


def test_no_model_is_unasked_and_lands_on_research(offline):
    v = choose_hand("get the car serviced", HandContext(), llm=None)
    assert v.hand == HAND_UNASKED
    assert v.asked == 0
    assert lane_for(v) == "research"
    dead = ScriptedLLM(live=False)
    assert choose_hand("get the car serviced", HandContext(), llm=dead).hand == HAND_UNASKED
    assert dead.asked == []


def test_an_empty_step_is_unasked_without_a_model_call():
    llm = ScriptedLLM(says(HAND_BROWSER))
    assert choose_hand("   ", HandContext(), llm=llm).hand == HAND_UNASKED
    assert llm.asked == []


def test_unreadable_twice_is_unanswered_and_the_second_ask_differs():
    llm = ScriptedLLM("not json at all", '{"hand": "shadow"}')
    v = choose_hand("get the car serviced", HandContext(), llm=llm)
    assert v.hand == HAND_UNANSWERED
    assert v.asked == 2
    assert lane_for(v) == "research"
    first, second = llm.asked
    assert first[2] == 0.0 and second[2] == 0.2
    assert second[1] != first[1] and second[1].startswith(first[1])
    assert first[0] == second[0] == hands.HANDS_SYSTEM


def test_a_transport_fault_is_unanswered_not_a_no():
    llm = ScriptedLLM(RuntimeError("503 from the gateway"))
    v = choose_hand("get the car serviced", HandContext(), llm=llm)
    assert v.hand == HAND_UNANSWERED
    assert "503" in v.reason
    assert lane_for(v) == "research"


def test_a_readable_first_reply_needs_no_second_ask():
    llm = ScriptedLLM("```json\n" + says(HAND_RESEARCH) + "\n```")
    v = choose_hand("find a dentist open Saturdays near work", HandContext(),
                    llm=llm)
    assert v.hand == HAND_RESEARCH
    assert v.asked == 1


def test_no_verdict_through_job_lane_is_research(monkeypatch, offline):
    # "get the car serviced" is consequential (it leaves the owner's world), so
    # two unreadable replies land it on the HELD browser lane as a card -- see
    # test_each_verdict_reaches_the_lane_through_job_lane. The read-only case
    # that stays on research is pinned below.
    got, params, _ = route(monkeypatch, "get the car serviced",
                           "garbage", "more garbage")
    assert got == ""
    assert params["_hand"]["hand"] == HAND_UNANSWERED
    assert params["_hand"]["asked"] == 2
    # THE CONTROL: a read-only goal with no verdict stays on research -- the
    # exact hole the browser-lane flip opened and the verifier closed.
    got, params, _ = route(monkeypatch, "look up the ferry schedule",
                           "not json", "still not json")
    assert got == "research"
    assert params["_hand"]["hand"] == HAND_UNANSWERED


# ------------------------------------------------------------ the seatbelt
@pytest.mark.parametrize("scripted", [
    says(HAND_BROWSER), says(HAND_API), says(HAND_RESEARCH), says(HAND_HOLD),
    "garbage", None])
def test_an_irreversible_verb_is_refused_after_any_verdict(monkeypatch, offline,
                                                            scripted):
    """The deny list is the seatbelt Law 1 permits. It holds AFTER the model
    answered — whatever it answered — and after no answer at all."""
    replies = () if scripted is None else (scripted, "still garbage")
    if scripted is None:
        monkeypatch.setattr(hands, "_default_llm", lambda: None)
        got, params, _ = job_lane("send the pitch deck to Marcus",
                                  {"source": "t"}), None, None
    else:
        got, params, llm = route(monkeypatch, "send the pitch deck to Marcus",
                                 *replies)
        assert len(llm.asked) >= 1          # the model WAS asked...
    assert got == ""                         # ...and the lane is still held.
    for goal in ("find a flight to Montreal and book the cheapest",
                 "research restaurants and reserve one for Friday",
                 "pay the deposit for Santouka"):
        monkeypatch.setattr(hands, "_default_llm",
                            lambda: ScriptedLLM(says(HAND_RESEARCH)))
        assert job_lane(goal, {"source": "t"}) == "", goal


# --------------------------------------------------------- the api floors
def connected(*rows):
    return HandContext(connections=tuple(rows), browser_online=True)


# The planner's fixtures. `mailer` is an INVENTED toolkit and its slugs are
# invented too, so no real app is named anywhere a scan could confuse with
# code; the real catalog (CALENDAR) is fixture data captured live.
FIXTURE = os.path.join(ROOT, "tests", "fixtures",
                       "googlecalendar_tools_2026-09-06.json")


def load_calendar():
    with open(FIXTURE, encoding="utf-8") as f:
        doc = json.load(f)
    rows = tuple(hands.CatalogTool.from_row(r) for r in doc["items"])
    assert len(rows) == 49 and None not in rows
    return rows


CALENDAR = load_calendar()


def tool(slug, *tags, required=(), params=(), deprecated=False,
         toolkit="mailer", desc=""):
    props = {k: {"type": "string", "description": f"the {k}"}
             for k in tuple(required) + tuple(params)}
    schema = ({"type": "object", "properties": props, "required": list(required)}
              if props else None)
    return hands.CatalogTool(slug=slug, name=slug,
                             description=desc or f"{slug.lower()} does one thing",
                             toolkit=toolkit, deprecated=deprecated,
                             tags=tuple(tags), input_parameters=schema)


MAILER = (
    tool("MAILER_SEARCH", "readOnlyHint", "important", params=("query",)),
    tool("MAILER_SEND", "createHint", required=("to", "body")),
    tool("MAILER_TRASH", "destructiveHint", "idempotentHint", required=("id",)),
    tool("MAILER_PLAIN"),                                # no hint tags at all
    tool("MAILER_OLD_SEARCH", "readOnlyHint", "deprecated", deprecated=True),
)


def names(slug, args=None, effect="read", verdict="tool", reason="scripted"):
    """A scripted reply to the tool question."""
    return json.dumps({"verdict": verdict, "tool": slug,
                       "args": {} if args is None else args,
                       "effect": effect, "reason": reason})


def connected_with(catalog, *rows, **kw):
    kw.setdefault("browser_online", True)
    return HandContext(connections=tuple(rows),
                       catalogs={rows[0].toolkit: catalog}, **kw)


def plan(goal, catalog, *replies, effect="read", heard="", toolkit="mailer"):
    """choose_tool with the model scripted. Returns (verdict, llm)."""
    llm = ScriptedLLM(*replies)
    return hands.choose_tool(goal, toolkit, catalog, llm=llm, heard=heard,
                             effect=effect), llm


def test_a_connected_app_with_writes_off_is_never_api_for_a_write():
    ctx = connected(ConnectedApp("mailer", status="connected", writes_enabled=False))
    for effect in ("write", "irreversible", "nonsense", None):
        llm = ScriptedLLM(says(HAND_API, app="mailer", effect=effect))
        v = choose_hand("reply to the landlord about the heater", ctx, llm=llm)
        assert v.hand == HAND_BROWSER, effect
        assert "writes are off" in v.reason
        assert v.app == "mailer"


def test_writes_on_still_needs_the_ladder_rung():
    row = ConnectedApp("mailer", status="connected", writes_enabled=True)
    at_zero = HandContext(connections=(row,), rung=0)
    llm = ScriptedLLM(says(HAND_API, app="mailer", effect="write"))
    v = choose_hand("reply to the landlord", at_zero, llm=llm)
    assert v.hand == HAND_BROWSER
    assert "rung 0" in v.reason
    assert len(llm.asked) == 1              # refused by the floor: no tool question
    # Since 2026-09-06 the api hand is reached only once a tool is named
    # from the app's catalog, so the control for the floor names one.
    at_three = HandContext(connections=(row,), rung=3,
                           catalogs={"mailer": MAILER})
    v = choose_hand("reply to the landlord", at_three,
                    llm=ScriptedLLM(says(HAND_API, app="mailer", effect="write"),
                                    names("MAILER_SEND", {"to": "l@x", "body": "hi"},
                                          effect="write")))
    assert v.hand == HAND_API, "the floor must be a floor, not a wall"
    assert v.tool == "MAILER_SEND" and v.effect == "write"


def test_a_read_on_a_connected_app_is_licensed():
    """Control for the floors: the api hand can be reached, so a test that
    never sees it is testing a floor and not a router that always says no.
    Since 2026-09-06 reaching it also means a tool was named from the app's
    catalog; the planner's own legs are further down."""
    ctx = connected_with(MAILER, ConnectedApp("mailer", status="connected"))
    v = choose_hand("what did Dana send this week", ctx,
                    llm=ScriptedLLM(says(HAND_API, app="Mailer", effect="read"),
                                    names("MAILER_SEARCH", {"query": "Dana"})))
    assert v.hand == HAND_API
    assert v.app == "mailer"                # the row's spelling, not the model's
    assert v.effect == "read"
    assert v.tool == "MAILER_SEARCH" and v.args == {"query": "Dana"}
    assert lane_for(v) == "api"


def test_api_is_not_licensed_for_an_app_that_is_not_connected():
    rows = (ConnectedApp("mailer", status="needs_reconnect"),
            ConnectedApp("notes", status="disconnected"))
    for app in ("mailer", "notes", "calendar-thing", "", None):
        v = choose_hand("what did Dana send", HandContext(connections=rows),
                        llm=ScriptedLLM(says(HAND_API, app=app)))
        assert v.hand == HAND_BROWSER, app
        assert "not a connected app" in v.reason


def test_unknown_connections_license_nothing():
    v = choose_hand("what did Dana send", HandContext(connections=None),
                    llm=ScriptedLLM(says(HAND_API, app="mailer")))
    assert v.hand == HAND_BROWSER
    assert "could not be read" in v.reason
    assert "unknown" in hands.facts_block(HandContext(connections=None))
    assert "none" in hands.facts_block(HandContext(connections=()))


def test_the_prompt_carries_the_facts():
    ctx = HandContext(connections=(ConnectedApp("mailer", alias="work",
                                                writes_enabled=True),
                                   ConnectedApp("notes")),
                      browser_online=False, source="i still owe Dana the form")
    llm = ScriptedLLM(says(HAND_BROWSER))
    choose_hand("email Dana the insurance form", ctx, llm=llm)
    _, user, _ = llm.asked[0]
    assert "STEP: email Dana the insurance form" in user
    assert "HEARD: i still owe Dana the form" in user
    assert "mailer (work) — status connected, writes ON" in user
    assert "notes — status connected, writes OFF" in user
    assert "MAC ONLINE: no" in user
    assert "rung 0" in user
    assert "MAC ONLINE: unknown" in hands.facts_block(HandContext())


# ------------------------------------------------------------ the controls
def test_control_open_in_my_browser_is_browser(monkeypatch, offline):
    got, params, llm = route(monkeypatch, "open example.net in my browser",
                             says(HAND_BROWSER, effect="read"))
    assert got == ""
    assert params["_hand"]["hand"] == HAND_BROWSER
    assert "open example.net in my browser" in llm.asked[0][1]


def test_control_what_did_i_promise_is_research(monkeypatch, offline):
    got, params, _ = route(monkeypatch, "what did I promise Marcus",
                           says(HAND_RESEARCH, effect="read"))
    assert got == "research"
    assert params["_hand"]["hand"] == HAND_RESEARCH


def test_a_computable_goal_needs_no_hand(monkeypatch, offline):
    """Capability, not wording: the calculator can answer it, so it is the
    server's and the model is not spent on it."""
    llm = ScriptedLLM()
    monkeypatch.setattr(hands, "_default_llm", lambda: llm)
    params = {"source": "t"}
    assert job_lane("5 PM CST is what in PST", params) == "research"
    assert params["_hand"]["hand"] == HAND_RESEARCH
    assert params["_hand"]["asked"] == 0
    assert llm.asked == []


# ------------------------------------------------------------- the facts
class _R:
    def __init__(self, ok=True, items=None, status=200):
        self.ok, self._items, self.status_code = ok, items or [], status

    def json(self):
        return {"items": self._items}


def test_connections_are_read_through_the_records_client(monkeypatch):
    seen = {}

    def fake_get(url, params=None, timeout=None, **kw):
        seen["url"], seen["params"], seen["timeout"] = url, params, timeout
        return _R(items=[
            {"toolkit": "mailer", "alias": "work", "status": "connected",
             "writes_enabled": 1},
            {"toolkit": "notes", "alias": "", "status": "needs_reconnect",
             "writes_enabled": 0},
            {"toolkit": "", "status": "connected"},          # unusable row
            "not a row",
        ])
    monkeypatch.setattr(hands.pb, "get", fake_get)
    rows = hands.read_connections('own"1', "https://api.example/")
    assert seen["url"] == "https://api.example/api/collections/connections/records"
    assert seen["params"]["filter"] == 'user_id="own\\"1"'
    assert seen["timeout"] == hands.FACT_TIMEOUT
    assert rows == (ConnectedApp("mailer", "work", "connected", True),
                    ConnectedApp("notes", "", "needs_reconnect", False))


def test_connections_that_cannot_be_read_are_unknown(monkeypatch):
    monkeypatch.setattr(hands.pb, "get", lambda *a, **k: _R(ok=False, status=404))
    assert hands.read_connections("own1", "https://api.example") is None
    monkeypatch.setattr(hands.pb, "get", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("timeout")))
    assert hands.read_connections("own1", "https://api.example") is None
    # An owner with no rows is NOT unknown — it is an owner who connected
    # nothing, and the prompt must say so in different words.
    monkeypatch.setattr(hands.pb, "get", lambda *a, **k: _R(items=[]))
    assert hands.read_connections("own1", "https://api.example") == ()


def test_browser_online_reads_the_agents_heartbeat(monkeypatch):
    from datetime import datetime, timedelta, timezone
    seen = {}
    fresh = (datetime.now(timezone.utc) - timedelta(seconds=10)
             ).strftime("%Y-%m-%d %H:%M:%S.%fZ")
    stale = (datetime.now(timezone.utc) - timedelta(seconds=3600)
             ).strftime("%Y-%m-%d %H:%M:%S.%fZ")

    def fake_get(url, params=None, timeout=None, **kw):
        seen["url"], seen["params"] = url, params
        return _R(items=[{"last_seen": seen.get("seen", fresh)}])
    monkeypatch.setattr(hands.pb, "get", fake_get)
    assert hands.browser_is_online("own1", "https://api.example") is True
    assert seen["url"] == "https://api.example/api/collections/agents/records"
    assert seen["params"]["filter"] == '(paired=true) && owner_ref="own1"'
    seen["seen"] = stale
    assert hands.browser_is_online("own1", "https://api.example") is False
    monkeypatch.setattr(hands.pb, "get", lambda *a, **k: _R(items=[]))
    assert hands.browser_is_online("own1", "https://api.example") is False
    monkeypatch.setattr(hands.pb, "get", lambda *a, **k: _R(ok=False))
    assert hands.browser_is_online("own1", "https://api.example") is None


def test_freshness_matches_the_worker():
    import brain.worker as W
    assert hands.AGENT_FRESH_SECONDS == W.AGENT_FRESH_SECONDS


def test_no_owner_or_no_backend_reads_nothing(monkeypatch):
    def tripwire(*a, **k):
        raise AssertionError("read attempted with no owner or no backend")
    monkeypatch.setattr(hands.pb, "get", tripwire)
    monkeypatch.delenv("ANTICIPY_PB", raising=False)
    monkeypatch.delenv("ANTICIPY_OWNER_REF", raising=False)
    monkeypatch.setattr(hands, "active_owner_ref", lambda owner_ref="": "")
    ctx = hands.gather_context({"source": "s"})
    assert ctx.connections is None and ctx.browser_online is None
    assert ctx.source == "s"
    assert hands.read_connections("", "https://api.example") is None
    assert hands.read_connections("own1", "") is None
    assert hands.browser_is_online("", "https://api.example") is None


def test_the_owner_never_comes_from_params(monkeypatch):
    """The owner is the process' own scope — the caller's, ANTICIPY_OWNER_REF,
    or the worker's resolved ACTIVE_OWNER_REF — never a key on params, which
    is the closest thing the brain has to a body."""
    monkeypatch.delenv("ANTICIPY_OWNER_REF", raising=False)
    fake_worker = types.SimpleNamespace(ACTIVE_OWNER_REF="")
    monkeypatch.setitem(sys.modules, "brain.worker", fake_worker)
    assert hands.active_owner_ref("") == ""
    reads = []
    monkeypatch.setattr(hands.pb, "get", lambda *a, **k: reads.append(a) or _R(items=[]))
    monkeypatch.setenv("ANTICIPY_PB", "https://api.example")
    hands.gather_context({"owner": "own1", "owner_ref": "own1", "user_id": "own1"})
    assert reads == []
    # The three honest sources, in order.
    assert hands.active_owner_ref("given") == "given"
    monkeypatch.setenv("ANTICIPY_OWNER_REF", "fromenv")
    assert hands.active_owner_ref("") == "fromenv"
    monkeypatch.delenv("ANTICIPY_OWNER_REF")
    fake_worker.ACTIVE_OWNER_REF = "resolved"
    assert hands.active_owner_ref("") == "resolved"
    hands.gather_context({})
    assert len(reads) == 2                  # connections and agents, scoped


# ------------------------------------------------------------ no app names
APP_NAMES = [
    "gmail", "googlecalendar", "google", "outlook", "slack", "notion", "github",
    "gitlab", "linear", "asana", "trello", "jira", "confluence", "salesforce",
    "hubspot", "stripe", "shopify", "twilio", "sendgrid", "airtable", "dropbox",
    "box", "zoom", "discord", "figma", "intercom", "zendesk", "quickbooks",
    "xero", "calendly", "docusign", "mailchimp", "clickup", "monday", "chrome",
    "whatsapp", "telegram", "instagram", "facebook", "twitter", "linkedin",
    "amazon", "uber", "doordash", "opentable", "spotify", "apple", "microsoft",
    "composio",
]


def _hits(text):
    low = text.lower()
    return [n for n in APP_NAMES if re.search(rf"\b{n}\b", low)]


def test_the_router_names_no_app():
    with open(os.path.join(ROOT, "brain", "hands.py"), encoding="utf-8") as f:
        assert _hits(f.read()) == []
    assert _hits(inspect.getsource(job_lane)) == []
    # The scan can go red.
    assert _hits('if app == "slack": return 1') == ["slack"]


# ------------------------------------------------------------ the wiring
def test_the_verdict_rides_on_the_row(monkeypatch, offline):
    """The mint point posts params with the router's note, so the audit line
    the spec asks for — hand, reason — is on the row and not only in a log."""
    posted = {}

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"id": "j1"}

    def fake_post(url, **kw):
        posted.update(kw.get("json") or {})
        return R()
    monkeypatch.setattr(core.pb, "post", fake_post)
    monkeypatch.setattr(hands, "_default_llm",
                        lambda: ScriptedLLM(says(HAND_BROWSER, effect="read",
                                                 reason="he asked to see it")))
    a = Anticipy(owner_id="own1")
    monkeypatch.setattr(a, "_same_pending", lambda goal, **_k: None)
    a._queue_job("open example.net in my browser", {"source": "test", "now": "now"})
    assert posted["lane"] == ""
    note = json.loads(posted["params"])["_hand"]
    assert note["hand"] == HAND_BROWSER
    assert note["reason"] == "he asked to see it"
    assert note["lane"] == ""


# ---------------------------------------------------------------- LIVE
# Goals from docs/BRIEF.html's fifty moments, with the verdicts a reader of
# the spec would accept. `ok` is a set: the measurement flags anything outside
# it as LOOKS WRONG and never fails the run for it — except the two controls.
#
# MEASURED 2026-09-06, google/gemini-2.5-flash over OpenRouter, the brain's
# own LLM class, .env.local key, nothing connected unless the row says so.
# Three prompt drafts; this is the third, and the one shipped:
#
#   draft 1  22 verdicts, 2 flagged: m43 "what do I have tomorrow" -> browser
#            (defensible: no calendar connected), and the CONTROL "what did I
#            promise Marcus" -> browser ("no apps connected, defaults to the
#            browser"). An untaught model — Law 5 step 3.
#   draft 2  taught the memory case; the controls held, but m5 and m29 (two
#            open-web lookups) moved to browser ("a web search that doesn't
#            involve any connected apps"). Still untaught.
#   draft 3  the browser-is-for-DOING sentence and seven worked examples
#            (none of them a probe goal): 22 verdicts, 0 flagged.
#
#   m1  email Dana the insurance form ........ browser  write        lane ''
#   m3  work out 18% tip on 84 dollars ....... research read         research
#   m5  find local gutter companies .......... research read         research
#   m8  renew the parking permit, hold at pay  browser  write        lane ''
#   m11 send the revised quote by Thursday ... hold     irreversible CARD  ''*
#   m11 move the call to Monday 3pm .......... browser  write        lane ''
#   m25 book the 7pm table at Santouka ....... browser  write        lane ''
#   m27 email the landlord re the heater ..... browser  write        lane ''
#   m29 find a dentist open Saturdays ........ research read         research
#   m34 what's the wifi at the cabin ......... research read         research
#   m36 wire $2,000 to the account ........... hold     irreversible CARD  ''*
#   m37 book my usual haircut ................ browser  write        lane ''
#   m39 text Laura I'm running late .......... hold     irreversible CARD  ''*
#   m41 cancel that .......................... hold     irreversible CARD  ''*
#   m43 what do I have tomorrow .............. browser  read         lane ''‡
#   m47 check in for the flight .............. browser  write        lane ''
#   C   open example.net in my browser ....... browser  read         lane ''
#   C   what did I promise Marcus ............ research read         research
#   read on a connected mail app ............. api      read         lane 'api'†
#   write on it, writes OFF .................. browser  write
#   write on it, writes ON, rung 0 ........... browser  write   (floor: rung 0)
#   read on a connected calendar, Mac offline  api      read         lane 'api'†
#
#   RE-MEASURED 2026-09-06 (later the same day), same model, same key, the
#   .env.local key loaded through overnight/_env: 22 verdicts, 0 flagged,
#   both controls held. Two rows moved between the two runs and both are
#   inside their accepted sets — m43 (‡) went research -> browser ("needs to
#   read from an app, but no app is connected"), and the writes-ON row came
#   back `browser` from the FLOOR ("rung 0 is below 3") where the morning run
#   had recorded `hold`; the model's own answer was api/write, which is what
#   the floor exists to catch. Everything else is byte-for-byte the morning
#   table.
#
#   * REFRESHED 2026-09-06, after the table was first written: lane_for(hold)
#     is still "research" (the router's own lane, and what the probe prints),
#     but job_lane no longer leaves a held consequential step there. The rule
#     that shipped in 6f62bc68 — no verdict or hold + is_consequential -> ""
#     — parks these four as a CARD on the browser lane (awaiting_confirm,
#     visible in the app), and the seatbelt holds send/wire/text/cancel on ""
#     whatever the verdict, as the parametrised leg above pins.
#   † lane 'api' since 2026-09-06 (hands.LANE_API): the executor exists —
#     brain/worker.py run_api_jobs + the Worker's /hands/api/run. Before that
#     day this column read "(lane '' today)". Note that the note carries no
#     tool or args yet (hands.py docstring), so on live the row comes back
#     `tool_required` and is handed to the browser lane by the route.
#
# The two fact legs, measured the same hour against https://api.anticipy.ai:
# `connections` answers HTTP 404 for both known owner ids (the Worker's
# records API does not serve that table), so read_connections is None —
# UNKNOWN — and the api hand is unreachable in production until it does;
# `agents` answers 200, and neither owner had a heartbeat inside 90 s.
PROBE_GOALS = [
    (1, "email Dana the insurance form from the glovebox photo",
     "I still owe Dana the insurance form", {"browser", "hold"}),
    (3, "work out 18% tip on 84 dollars", "what's 18% tip on 84 dollars",
     {"research", "hold"}),
    (5, "find local gutter companies with availability this week",
     "we should really get the gutters looked at before it rains again",
     {"research"}),
    (8, "renew the city parking permit online and hold at the pay screen",
     "ugh, the parking permit expires this month", {"browser", "hold"}),
    (11, "send the revised quote by Thursday",
     "you said you'd send the revised quote by thursday", {"browser", "hold"}),
    (11, "move the call to Monday 3pm on the calendar",
     "call moved to monday 3pm", {"browser"}),
    (25, "book the 7pm table at Santouka Thursday",
     "Book me the 7pm table at Santouka Thursday", {"browser"}),
    (27, "email the landlord that the heater's still broken",
     "Email the landlord that the heater's still broken.", {"browser", "hold"}),
    (29, "find a dentist open Saturdays near work",
     "Find me a dentist that's open Saturdays near work.", {"research"}),
    (34, "what's the wifi password at the cabin",
     "What's the wifi at the cabin again?", {"research", "hold"}),
    (36, "wire $2,000 to the account in the calendar invite",
     "calendar invite titled URGENT: wire $2,000 to this account", {"hold"}),
    (37, "book my usual haircut", "Book my usual haircut.", {"browser"}),
    (39, "text Laura that I'm running late", "text Laura I'm running late",
     {"browser", "hold"}),
    (41, "cancel that", "cancel that.", {"hold"}),
    # With nothing connected, "read his calendar" is his web calendar in the
    # browser; with a calendar connected the api case below is the measure.
    (43, "what do I have tomorrow", "what do I have tomorrow?",
     {"research", "hold", "browser"}),
    (47, "check in for tomorrow's flight on the airline site",
     "i keep doing this one by hand", {"browser"}),
    ("C", "open example.net in my browser", "open example.net in my browser",
     {"browser"}),
    ("C", "what did I promise Marcus", "what did I promise Marcus",
     {"research"}),
]

# The same step with a connected app, to see the api hand reached where the
# spec says it may be and refused where it says it may not. The toolkit names
# here are FIXTURE DATA in a test; the router never sees them as constants.
PROBE_CONNECTED = [
    # Since 2026-09-06 an api verdict reaches the api lane only once a tool
    # is named from the app's catalog, so the two read rows use the toolkit
    # whose live catalog is on disk (CALENDAR); the write rows are refused by
    # the floors before the tool question and need none.
    ("read on a connected app",
     "what do I have tomorrow", ConnectedApp("googlecalendar"), {"api"}),
    ("write on a connected app, writes OFF",
     "reply to Dana that the form is attached", ConnectedApp("gmail"),
     {"browser", "hold"}),
    ("write on a connected app, writes ON, rung 0",
     "reply to Dana that the form is attached",
     ConnectedApp("gmail", writes_enabled=True), {"browser", "hold"}),
    ("read on a connected calendar, Mac offline",
     "am I free Thursday afternoon", ConnectedApp("googlecalendar"), {"api"}),
]


@pytest.mark.skipif(os.environ.get("ANTICIPY_HANDS_LIVE") != "1",
                    reason="the measurement: set ANTICIPY_HANDS_LIVE=1 with a "
                           "model key to drive the real model")
def test_live_probe_against_the_real_model():
    from brain.llm import LLM
    llm = LLM()
    assert llm.live, "ANTICIPY_HANDS_LIVE=1 but no model key in the environment"
    print(f"\nLIVE PROBE  model={llm.model}")
    wrong = []
    rows = []
    for moment, goal, source, ok in PROBE_GOALS:
        v = choose_hand(goal, HandContext(connections=(), browser_online=True,
                                          source=source), llm=llm)
        lane = lane_for(v)
        flag = "" if v.hand in ok else "  LOOKS WRONG"
        if flag:
            wrong.append((moment, goal, v.hand))
        rows.append(f"  m{moment:<3} {v.hand:<9} {v.effect:<12} lane={lane!r:<11} "
                    f"asked={v.asked} {goal!r}{flag}\n        {v.reason}")
    for label, goal, row, ok in PROBE_CONNECTED:
        offline_mac = "Mac offline" in label
        v = choose_hand(goal, HandContext(connections=(row,),
                                          browser_online=not offline_mac,
                                          source=goal,
                                          catalogs={"googlecalendar": CALENDAR}),
                        llm=llm)
        flag = "" if v.hand in ok else "  LOOKS WRONG"
        if flag:
            wrong.append((label, goal, v.hand))
        rows.append(f"  [{label}] {v.hand:<9} {v.effect:<12} app={v.app!r} "
                    f"tool={v.tool or '-'} asked={v.asked}+{v.tool_asked} "
                    f"{goal!r}{flag}\n        {v.reason}")
    print("\n".join(rows))
    print(f"  {len(rows)} verdicts, {len(wrong)} look wrong: {wrong}")
    control = {g: h for m, g, _s, ok in PROBE_GOALS if m == "C"
               for (_m, _g, h) in wrong if _g == g}
    assert not control, f"a CONTROL moved: {control}"


# ------------------------------------------------------------ the planner
# WHICH TOOL — the fourth house-shape question (2026-09-06). hands.choose_tool
# is handed the app's CATALOG — the vendor's own tool rows, the Worker's
# provider.tools() shape — and asked to name ONE slug from it and its
# arguments. Four states; only "tool" takes the api lane.
def test_an_api_verdict_names_the_tool_on_the_row(monkeypatch, offline):
    """THE REPRODUCTION. RED before the planner: an api verdict rode on the
    row as {hand, reason, app, effect, asked, lane} and nothing else, so the
    Worker's /hands/api/run read `tool: ""` off it and refused every api-lane
    job `tool_required` before any vendor call (hands-api.test.ts:784), then
    handed it to the browser lane — the wire was a pipe to nowhere. Now the
    note carries what stepFromRow reads: app, tool, args, effect."""
    args = {"timeMin": "2026-09-07T00:00:00-07:00",
            "timeMax": "2026-09-07T23:59:59-07:00"}
    ctx = HandContext(connections=(ConnectedApp("googlecalendar"),),
                      browser_online=True, catalogs={"googlecalendar": CALENDAR})
    got, params, llm = route(monkeypatch, "what's on my calendar tomorrow",
                             says(HAND_API, app="googlecalendar", effect="read"),
                             names("GOOGLECALENDAR_FIND_EVENT", args), ctx=ctx)
    assert got == "api"
    note = params["_hand"]
    assert note["hand"] == HAND_API and note["lane"] == "api"
    assert note["app"] == "googlecalendar"
    assert note["tool"] == "GOOGLECALENDAR_FIND_EVENT"
    assert note["args"] == args
    assert note["effect"] == "read"
    assert note["tool_verdict"] == hands.TOOL_CHOSEN
    assert note["asked"] == 1 and note["tool_asked"] == 1
    assert len(llm.asked) == 2              # two questions, each on its own
    assert llm.asked[0][0] == hands.HANDS_SYSTEM
    assert llm.asked[1][0] == hands.TOOLS_SYSTEM
    assert {"app", "tool", "args", "effect"} <= set(note)   # stepFromRow's keys


def test_the_four_tool_states():
    # tool
    v, llm = plan("what did Dana send", MAILER,
                  names("MAILER_SEARCH", {"query": "Dana"}))
    assert v.verdict == hands.TOOL_CHOSEN and v.chosen
    assert v.tool == "MAILER_SEARCH" and v.args == {"query": "Dana"}
    assert v.effect == "read" and v.asked == 1 and llm.asked[0][2] == 0.0
    # none
    v, _ = plan("what did I promise Marcus", MAILER,
                names(None, verdict="none", reason="memory"))
    assert v.verdict == hands.TOOL_NONE and not v.chosen
    assert v.tool == "" and v.args is None and v.reason == "memory"
    # unclear
    v, _ = plan("reply to the landlord", MAILER,
                names(None, verdict="unclear", effect="write"))
    assert v.verdict == hands.TOOL_UNCLEAR and not v.chosen
    assert v.effect == "write"
    # no-verdict, nothing asked: no step, no app, no catalog, no live model
    for goal, toolkit, catalog in (("", "mailer", MAILER), ("x", "", MAILER),
                                   ("x", "mailer", None)):
        llm = ScriptedLLM(names("MAILER_SEARCH"))
        v = hands.choose_tool(goal, toolkit, catalog, llm=llm)
        assert v.verdict == hands.TOOL_NO_VERDICT, (goal, toolkit, catalog)
        assert llm.asked == [] and v.asked == 0
    dead = ScriptedLLM(live=False)
    assert hands.choose_tool("x", "mailer", MAILER, llm=dead).verdict == hands.TOOL_NO_VERDICT
    assert dead.asked == []
    # no-verdict, asked: unreadable twice, and the second ask is a different ask
    v, llm = plan("x", MAILER, "not json at all", '{"verdict": "shadow"}')
    assert v.verdict == hands.TOOL_NO_VERDICT and v.asked == 2
    first, second = llm.asked
    assert first[2] == 0.0 and second[2] == 0.2
    assert second[1] != first[1] and second[1].startswith(first[1])
    assert first[0] == second[0] == hands.TOOLS_SYSTEM
    # no-verdict: a transport fault
    v, _ = plan("x", MAILER, RuntimeError("503 from the gateway"))
    assert v.verdict == hands.TOOL_NO_VERDICT and "503" in v.reason and v.asked == 1
    # a chosen tool with no effect, or arguments that are not an object, is
    # UNREADABLE — silence about the effect licenses nothing — and asked again
    v, llm = plan("x", MAILER,
                  json.dumps({"verdict": "tool", "tool": "MAILER_SEARCH", "args": {}}),
                  json.dumps({"verdict": "tool", "tool": "MAILER_SEARCH",
                              "args": [1], "effect": "read"}))
    assert v.verdict == hands.TOOL_NO_VERDICT and v.asked == 2
    # a reply that named a tool and forgot the word is still a tool; null
    # arguments are an empty object (the Worker refuses a non-object)
    v, _ = plan("x", MAILER, json.dumps({"tool": "MAILER_SEARCH", "args": None,
                                         "effect": "read"}))
    assert v.chosen and v.args == {}
    # a fenced reply is still a reply
    v, _ = plan("x", MAILER, "```json\n" + names("MAILER_SEARCH") + "\n```")
    assert v.chosen and v.asked == 1


def test_a_typed_slug_not_in_the_catalog_is_no_verdict():
    """The slug is compared BY IDENTITY against the catalog rows. A slug the
    model typed that is not in the list is asked again, in words that name
    the miss, and then it is no verdict — never trusted."""
    v, llm = plan("delete everything", MAILER,
                  names("MAILER_DELETE_EVERYTHING", {}),
                  names("MAILER_NUKE_ALL", {}))
    assert v.verdict == hands.TOOL_NO_VERDICT and v.asked == 2
    assert v.tool == "" and v.args is None
    assert "MAILER_DELETE_EVERYTHING" in llm.asked[1][1]
    assert "not a slug in the catalog" in llm.asked[1][1]
    assert "MAILER_NUKE_ALL" in v.reason
    # THE CONTROL: the slug that IS in the catalog, same goal, same catalog
    v, _ = plan("delete everything", MAILER, names("MAILER_TRASH", {"id": "m1"}))
    assert v.chosen and v.tool == "MAILER_TRASH"
    # identity is the catalog's spelling: a case-folded identifier resolves
    # to the row (api_hand.ts sameSlug) and the ROW's spelling goes on the note
    v, _ = plan("x", MAILER, names("mailer_search", {}))
    assert v.chosen and v.tool == "MAILER_SEARCH"
    # whitespace inside is not an identifier
    v, _ = plan("x", MAILER, names("MAILER SEARCH", {}), names("MAILER SEARCH", {}))
    assert v.verdict == hands.TOOL_NO_VERDICT
    # a real slug from ANOTHER catalog is not in this one
    v, _ = plan("x", MAILER, names("GOOGLECALENDAR_FIND_EVENT", {}),
                names("GOOGLECALENDAR_FIND_EVENT", {}))
    assert v.verdict == hands.TOOL_NO_VERDICT
    # a typed slug, then a real one: the second ask rescues it
    v, _ = plan("x", MAILER, names("MAILER_LOOKUP", {}), names("MAILER_SEARCH", {}))
    assert v.chosen and v.tool == "MAILER_SEARCH" and v.asked == 2


def test_an_irreversible_hint_is_irreversible_whatever_the_model_declared():
    for declared in ("read", "write", "irreversible"):
        v, _ = plan("bin the old thread", MAILER,
                    names("MAILER_TRASH", {"id": "m1"}, effect=declared))
        assert v.effect == "irreversible", declared
        assert v.hint == "irreversible" and v.declared == declared
    # CONTROL: a readOnlyHint tool declared read stays read — and declared
    # write stays write, because a hint never loosens
    v, _ = plan("x", MAILER, names("MAILER_SEARCH", {}, effect="read"))
    assert v.effect == "read" and v.hint == "read"
    v, _ = plan("x", MAILER, names("MAILER_SEARCH", {}, effect="write"))
    assert v.effect == "write"
    # a tool with no hint tags says nothing: the declaration stands, and the
    # router's own effect is never loosened by the model's either
    v, _ = plan("x", MAILER, names("MAILER_PLAIN", {}, effect="read"))
    assert v.effect == "read" and v.hint == ""
    v, _ = plan("x", MAILER, names("MAILER_PLAIN", {}, effect="read"), effect="write")
    assert v.effect == "write"
    # the pure halves, pinned to api_hand.ts's table
    assert hands.hint_effect(("readOnlyHint",)) == "read"
    assert hands.hint_effect(("createHint",)) == "write"
    assert hands.hint_effect(("updateHint", "readOnlyHint")) == "write"
    assert hands.hint_effect(("readOnlyHint", "destructiveHint")) == "irreversible"
    assert hands.hint_effect(("important", "idempotentHint")) == ""
    assert hands.hint_effect(()) == ""
    assert hands.tighten("read", "write") == "write"
    assert hands.tighten("write", "read") == "write"
    assert hands.tighten("read", "") == "read"
    assert hands.tighten("", "read") == "read"
    assert hands.tighten("bogus", "") == "irreversible"
    assert hands.tighten("read", "bogus") == "irreversible"
    # THROUGH THE ROUTER: rule 3 — a step that cannot be undone never takes
    # the api hand on its own. Writes ON and rung 3 would license a write;
    # the tool's own tag makes it a hold, not the api lane, not the browser.
    ctx = connected_with(MAILER, ConnectedApp("mailer", writes_enabled=True), rung=3)
    v = choose_hand("bin the old thread from the landlord", ctx,
                    llm=ScriptedLLM(says(HAND_API, app="mailer", effect="write"),
                                    names("MAILER_TRASH", {"id": "m1"}, effect="write")))
    assert v.hand == HAND_HOLD and v.effect == "irreversible"
    assert v.tool == "MAILER_TRASH" and v.tool_verdict == hands.TOOL_CHOSEN
    assert "cannot be undone" in v.reason
    assert lane_for(v) == "research"


def test_a_create_hint_tightens_a_read_and_the_floors_run_again():
    """An args object the model invents for a write tool is not enough: the
    effect comes from the tool's hint, tightened never loosened, and floor 2
    is applied again to the corrected effect — exactly as api_hand.ts does."""
    def llm():
        return ScriptedLLM(says(HAND_API, app="mailer", effect="read"),
                           names("MAILER_SEND", {"to": "d@x", "body": "hi"},
                                 effect="read"))
    # writes OFF: the tightened write is refused by the floor, and the row
    # says why, with the tool on it for the audit line
    v = choose_hand("reply to Dana", connected_with(MAILER, ConnectedApp("mailer")),
                    llm=llm())
    assert v.hand == HAND_BROWSER and v.effect == "write"
    assert "writes are off" in v.reason and v.tool == "MAILER_SEND"
    assert lane_for(v) == ""
    # writes ON, rung 0: the ladder
    v = choose_hand("reply to Dana",
                    connected_with(MAILER, ConnectedApp("mailer", writes_enabled=True)),
                    llm=llm())
    assert v.hand == HAND_BROWSER and "rung 0" in v.reason and v.effect == "write"
    # CONTROL: writes ON, rung 3 — the api hand, as a write, with the tool
    v = choose_hand("reply to Dana",
                    connected_with(MAILER, ConnectedApp("mailer", writes_enabled=True),
                                   rung=3), llm=llm())
    assert v.hand == HAND_API and v.effect == "write"
    assert v.tool == "MAILER_SEND" and v.args == {"to": "d@x", "body": "hi"}
    assert lane_for(v) == "api"


def test_no_catalog_is_no_verdict_and_the_api_lane_is_not_taken(monkeypatch, offline):
    """The live shape today: the Worker serves no catalog to the brain, so
    read_catalog is UNKNOWN. No verdict; the api lane is NOT taken; the step
    goes to the browser lane — where the Worker's own tool_required handback
    was already sending it, one hop later — with the reason on the row."""
    goal = "what did Dana send me this week"
    # backend_url "" -> read_catalog reads nothing (the offline tripwire holds)
    ctx = HandContext(connections=(ConnectedApp("mailer"),), browser_online=True)
    got, params, llm = route(monkeypatch, goal,
                             says(HAND_API, app="mailer", effect="read"), ctx=ctx)
    assert got == ""
    note = params["_hand"]
    assert note["hand"] == HAND_BROWSER and note["lane"] == ""
    assert note["tool_verdict"] == hands.TOOL_NO_VERDICT
    assert note["tool"] == "" and note["args"] is None and note["tool_asked"] == 0
    assert "could not be read" in note["reason"]
    assert len(llm.asked) == 1              # no catalog, no tool question
    # catalogs in hand that lack this toolkit are UNKNOWN too, not empty
    ctx = HandContext(connections=(ConnectedApp("mailer"),), browser_online=True,
                      catalogs={"other": MAILER})
    got, params, llm = route(monkeypatch, goal,
                             says(HAND_API, app="mailer", effect="read"), ctx=ctx)
    assert got == "" and params["_hand"]["tool_verdict"] == hands.TOOL_NO_VERDICT
    assert len(llm.asked) == 1
    # an EMPTY catalog is the vendor's own answer: none, no ask, browser
    ctx = HandContext(connections=(ConnectedApp("mailer"),), browser_online=True,
                      catalogs={"mailer": ()})
    got, params, llm = route(monkeypatch, goal,
                             says(HAND_API, app="mailer", effect="read"), ctx=ctx)
    assert got == "" and params["_hand"]["tool_verdict"] == hands.TOOL_NONE
    assert params["_hand"]["hand"] == HAND_BROWSER and len(llm.asked) == 1
    # none and unclear FROM THE MODEL: browser, with the model's reason
    for verdict in (hands.TOOL_NONE, hands.TOOL_UNCLEAR):
        ctx = connected_with(MAILER, ConnectedApp("mailer"))
        got, params, llm = route(monkeypatch, goal,
                                 says(HAND_API, app="mailer", effect="read"),
                                 names(None, verdict=verdict, reason="because so"),
                                 ctx=ctx)
        assert got == "", verdict
        assert params["_hand"]["hand"] == HAND_BROWSER
        assert params["_hand"]["tool_verdict"] == verdict
        assert "because so" in params["_hand"]["reason"]
        assert len(llm.asked) == 2
    # THE CONTROL: the same row with a catalog and a named tool takes the lane
    ctx = connected_with(MAILER, ConnectedApp("mailer"))
    got, params, _ = route(monkeypatch, goal,
                           says(HAND_API, app="mailer", effect="read"),
                           names("MAILER_SEARCH", {"query": "Dana"}), ctx=ctx)
    assert got == "api" and params["_hand"]["tool"] == "MAILER_SEARCH"


def test_missing_required_arguments_are_asked_again_then_no_verdict():
    v, llm = plan("reply to Dana", MAILER,
                  names("MAILER_SEND", {"to": "d@x"}, effect="write"),
                  names("MAILER_SEND", {}, effect="write"))
    assert v.verdict == hands.TOOL_NO_VERDICT and v.asked == 2
    assert "MAILER_SEND" in llm.asked[1][1] and "body" in llm.asked[1][1]
    assert "to" in v.reason and "body" in v.reason
    # CONTROL: both required keys, chosen on the first ask
    v, llm = plan("reply to Dana", MAILER,
                  names("MAILER_SEND", {"to": "d@x", "body": "hi"}, effect="write"))
    assert v.chosen and v.asked == 1
    # a second ask that answers "unclear" instead is that verdict
    v, _ = plan("reply to Dana", MAILER, names("MAILER_SEND", {}, effect="write"),
                names(None, verdict="unclear", effect="write"))
    assert v.verdict == hands.TOOL_UNCLEAR and v.asked == 2
    # a tool with no schema requires nothing
    v, _ = plan("x", MAILER, names("MAILER_PLAIN", {}))
    assert v.chosen and v.asked == 1


def test_arguments_are_never_printed(capsys):
    """`args` can hold the text of a person's mail; a log line is the one
    place in a server guaranteed to be read by somebody it was not addressed
    to (api_hand.ts). The note carries them; nothing prints them."""
    secret = "SECRET-PAYLOAD-7f3a"
    ctx = connected_with(MAILER, ConnectedApp("mailer", writes_enabled=True), rung=3)
    v = choose_hand("reply to Dana", ctx,
                    llm=ScriptedLLM(says(HAND_API, app="mailer", effect="write"),
                                    names("MAILER_SEND", {"to": "d@x", "body": secret},
                                          effect="write")))
    assert v.hand == HAND_API and v.args["body"] == secret
    assert secret not in capsys.readouterr().out
    # the miss-and-retry path prints the slug and the missing NAMES, not values
    plan("reply to Dana", MAILER,
         names("MAILER_SEND", {"to": secret}, effect="write"),
         names("MAILER_SEND", {"to": secret, "body": secret}, effect="write"))
    assert secret not in capsys.readouterr().out
    # and an UNREADABLE reply that still carries args is printed as a shape,
    # never as itself (the hand question never had args to leak; this one does)
    plan("reply to Dana", MAILER,
         json.dumps({"verdict": "shadow", "tool": "MAILER_SEND",
                     "args": {"body": secret}, "effect": "write"}),
         json.dumps({"verdict": "tool", "tool": "MAILER_SEND",
                     "args": {"to": secret, "body": secret}}))       # no effect
    out = capsys.readouterr().out
    assert secret not in out and "unreadable reply to the tool question" in out


def test_control_calendar_tomorrow_is_find_event_read(monkeypatch, offline):
    """THE CONTROL: "what's on my calendar tomorrow" with the app's REAL
    49-row catalog (captured live 2026-09-06) -> GOOGLECALENDAR_FIND_EVENT,
    effect read, lane api — and every one of the 49 slugs reached the model,
    once, with the vendor's tags, the DEPRECATED marks and the required
    stars, so the choice was the model's over the vendor's list."""
    args = {"timeMin": "2026-09-07T00:00:00-07:00",
            "timeMax": "2026-09-07T23:59:59-07:00"}
    ctx = HandContext(connections=(ConnectedApp("googlecalendar"),),
                      browser_online=True, catalogs={"googlecalendar": CALENDAR},
                      source="what do I have tomorrow?")
    got, params, llm = route(monkeypatch, "what's on my calendar tomorrow",
                             says(HAND_API, app="googlecalendar", effect="read"),
                             names("googlecalendar_find_event", args), ctx=ctx)
    assert got == "api"
    note = params["_hand"]
    assert note["tool"] == "GOOGLECALENDAR_FIND_EVENT"      # the catalog's spelling
    assert note["effect"] == "read" and note["args"] == args
    system, user, temperature = llm.asked[1]
    assert system == hands.TOOLS_SYSTEM and temperature == 0.0
    assert "STEP: what's on my calendar tomorrow" in user
    assert "HEARD: what do I have tomorrow?" in user
    assert "APP: googlecalendar" in user and "as a read" in user
    assert "CATALOG (49 tools" in user
    for row in CALENDAR:
        assert user.count(f"- {row.slug}  tags:") == 1, row.slug
    # the vendor's own flag, on the head line of exactly the four rows that
    # carry it (their descriptions say DEPRECATED too; that is theirs)
    assert sum(1 for line in user.splitlines()
               if line.startswith("- ") and line.endswith("  DEPRECATED")) == 4
    assert "- GOOGLECALENDAR_FIND_EVENT  tags: readOnlyHint, idempotentHint, openWorldHint, important, Events Management" in user
    assert "calendar_id*: string" in user                    # a required parameter, starred
    assert "default 'primary'" in user                       # the vendor's own default
    assert len(user) <= hands.CATALOG_CHARS_MAX + 2_000
    # the real tags tighten: a destructive tool declared read is irreversible,
    # a create tool declared read is a write
    v, _ = plan("x", CALENDAR, names("GOOGLECALENDAR_DELETE_EVENT",
                                     {"event_id": "e1"}, effect="read"),
                toolkit="googlecalendar")
    assert v.chosen and v.effect == "irreversible"
    v, _ = plan("x", CALENDAR, names("GOOGLECALENDAR_CREATE_EVENT",
                                     {"start_datetime": "2026-09-07T12:00:00"},
                                     effect="read"), toolkit="googlecalendar")
    assert v.chosen and v.effect == "write"
    # and the required list is the vendor's: CREATE_EVENT without its one
    # required key is asked again
    v, llm = plan("x", CALENDAR, names("GOOGLECALENDAR_CREATE_EVENT", {"summary": "lunch"}),
                  names(None, verdict="unclear"), toolkit="googlecalendar")
    assert v.verdict == hands.TOOL_UNCLEAR and "start_datetime" in llm.asked[1][1]


def test_the_catalog_rendering_never_drops_a_row(monkeypatch):
    full = hands.catalog_block(CALENDAR)
    assert full == hands.render_catalog(CALENDAR, 0)
    assert 60_000 < len(full) <= hands.CATALOG_CHARS_MAX   # measured 2026-09-06: 68.7k
    lean = hands.render_catalog(CALENDAR, 1)
    leanest = hands.render_catalog(CALENDAR, 2)
    assert len(leanest) < len(lean) < len(full)
    monkeypatch.setattr(hands, "CATALOG_CHARS_MAX", len(lean))
    assert hands.catalog_block(CALENDAR) == lean
    monkeypatch.setattr(hands, "CATALOG_CHARS_MAX", len(leanest))
    assert hands.catalog_block(CALENDAR) == leanest
    monkeypatch.setattr(hands, "CATALOG_CHARS_MAX", 10)
    assert hands.catalog_block(CALENDAR) == leanest        # leaner, never shorter
    order = [row.slug for row in CALENDAR]
    for text in (full, lean, leanest):
        assert [line.split()[1] for line in text.splitlines()
                if line.startswith("- ")] == order          # the vendor's order
    assert "pageToken*" not in full and "event_id*" in full   # stars are the vendor's required list
    assert "Lower bound" in full and "Lower bound" not in lean   # descriptions go first
    assert "event_id*" in leanest                            # names and stars stay


def test_the_catalog_is_read_through_the_records_client(monkeypatch):
    seen = {}

    def fake_get(url, params=None, timeout=None, **kw):
        seen["url"], seen["params"], seen["timeout"] = url, params, timeout
        return _R(items=[
            # the Worker's spelling (provider.ts CatalogTool)
            {"slug": "MAILER_SEARCH", "toolkit": "mailer", "tags": ["readOnlyHint"],
             "inputParameters": {"properties": {"q": {"type": "string"}}},
             "deprecated": False},
            # the vendor's raw spelling
            {"slug": "MAILER_SEND", "toolkit": {"slug": "mailer"}, "tags": ["createHint"],
             "input_parameters": {"required": ["to"]}, "is_deprecated": True},
            {"toolkit": "mailer"},                           # no slug: not an entry
            "not a row",
        ])
    monkeypatch.setattr(hands.pb, "get", fake_get)
    rows = hands.read_catalog("Mailer", "https://api.example/")
    assert seen["url"] == "https://api.example" + hands.API_HAND_TOOLS_PATH
    assert seen["url"].endswith("/hands/api/tools")
    assert seen["params"] == {"toolkit": "mailer"}
    assert seen["timeout"] == hands.CATALOG_TIMEOUT
    assert [r.slug for r in rows] == ["MAILER_SEARCH", "MAILER_SEND"]
    assert rows[0].hint == "read" and rows[0].deprecated is False
    assert rows[0].input_parameters == {"properties": {"q": {"type": "string"}}}
    assert rows[1].hint == "write" and rows[1].required == ("to",)
    assert rows[1].deprecated is True and rows[1].toolkit == "mailer"
    # UNKNOWN, never "no tools": the refused route (the live shape today), a
    # fault, a body with no items, a row naming another toolkit, a page of
    # rows none of which can be read
    monkeypatch.setattr(hands.pb, "get", lambda *a, **k: _R(ok=False, status=404))
    assert hands.read_catalog("mailer", "https://api.example") is None
    monkeypatch.setattr(hands.pb, "get", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("timeout")))
    assert hands.read_catalog("mailer", "https://api.example") is None
    class NoItems:
        ok = True

        def json(self):
            return {"ok": True}
    monkeypatch.setattr(hands.pb, "get", lambda *a, **k: NoItems())
    assert hands.read_catalog("mailer", "https://api.example") is None
    monkeypatch.setattr(hands.pb, "get", lambda *a, **k: _R(items=[
        {"slug": "MAILER_SEARCH", "toolkit": "mailer"},
        {"slug": "OTHER_THING", "toolkit": "other"}]))
    assert hands.read_catalog("mailer", "https://api.example") is None
    monkeypatch.setattr(hands.pb, "get", lambda *a, **k: _R(items=[{"toolkit": "mailer"}, 7]))
    assert hands.read_catalog("mailer", "https://api.example") is None
    # an empty list IS an answer: the vendor lists nothing for this toolkit
    monkeypatch.setattr(hands.pb, "get", lambda *a, **k: _R(items=[]))
    assert hands.read_catalog("mailer", "https://api.example") == ()
    # nothing is asked with no toolkit or no backend
    def tripwire(*a, **k):
        raise AssertionError("read attempted with no toolkit or no backend")
    monkeypatch.setattr(hands.pb, "get", tripwire)
    assert hands.read_catalog("", "https://api.example") is None
    assert hands.read_catalog("mailer", "") is None


def test_gather_context_carries_the_backend_for_the_catalog(monkeypatch):
    reads = []
    monkeypatch.setattr(hands.pb, "get", lambda *a, **k: reads.append(a) or _R(items=[]))
    monkeypatch.setenv("ANTICIPY_PB", "https://api.example")
    monkeypatch.setattr(hands, "active_owner_ref", lambda owner_ref="": "own1")
    ctx = hands.gather_context({"source": "s"})
    assert ctx.backend_url == "https://api.example" and ctx.catalogs is None
    assert len(reads) == 2                  # connections and agents; the catalog waits for a verdict
    # catalog_for: rows in hand first, else the read; dict rows are read too
    ctx = HandContext(catalogs={"Mailer": ({"slug": "MAILER_SEARCH", "toolkit": "mailer"},)})
    rows = hands.catalog_for(ctx, "mailer")
    assert [r.slug for r in rows] == ["MAILER_SEARCH"]
    assert hands.catalog_for(ctx, "other") is None
    assert hands.catalog_for(HandContext(backend_url="https://api.example"), "mailer") == ()
    assert len(reads) == 3
    # the note's keys are always the same nine, so the Worker reads one shape
    assert set(HandVerdict(HAND_RESEARCH, "r").as_note()) == {
        "hand", "reason", "app", "effect", "asked", "tool", "args",
        "tool_verdict", "tool_asked"}


def test_choose_hand_asks_the_tool_question_exactly_once():
    """The mutation literal: the fourth question is asked in one place, after
    the floors, and job_lane's one call to the router is untouched."""
    assert inspect.getsource(hands.choose_hand).count("plan_api_step(") == 1
    assert inspect.getsource(hands.plan_api_step).count("choose_tool(") == 1
    assert inspect.getsource(job_lane).count("hands.choose_hand(") == 1
    assert "choose_tool" not in inspect.getsource(job_lane)
    # every verdict that is not api passes through untouched: no catalog
    # read, no ask
    for hand in (HAND_BROWSER, HAND_RESEARCH, HAND_HOLD, HAND_UNASKED, HAND_UNANSWERED):
        v = HandVerdict(hand, "r", app="mailer", effect="read")
        llm = ScriptedLLM(names("MAILER_SEARCH"))
        assert hands.plan_api_step(v, "x", HandContext(catalogs={"mailer": MAILER}),
                                   llm=llm) is v
        assert llm.asked == []


# ---------------------------------------------------------------- LIVE, the tool
# The tool question against the real model over the REAL 49-row catalog
# (CALENDAR). `ok` is what a reader of the spec would accept; anything else is
# flagged LOOKS WRONG and never fails the run — except the two CONTROLS.
#
# MEASURED 2026-09-06, google/gemini-2.5-flash over OpenRouter, the brain's
# own LLM class, .env.local key, the catalog at full detail (68.7k chars, ~2 s
# a call). Four prompt drafts, each a Law-5 step-3 fix rather than a rule:
#
#   draft 1  hint tags only in the rendering: the CONTROL picked EVENTS_LIST
#            (a sibling read) and "what did I promise Marcus" got a calendar
#            search with q="promise Marcus" instead of none. The vendor's own
#            "important" tag never reached the model.
#   draft 2  every vendor tag verbatim + the memory case taught: memory ->
#            none. "clear my calendar for Friday" planned a FIRST call of a
#            two-call job (list events "to get their IDs").
#   draft 3  "one call does the whole step": clear -> CLEAR_CALENDAR, whose
#            destructiveHint makes it irreversible -> a HOLD (rule 3 working),
#            but the pick over-reaches the step (it clears everything).
#   draft 4  "...and no more than the step asked" — shipped; the table below.
#
#   SHIPPED (draft 4, measured through this leg, 2026-09-06 13:xx PT):
#     C      tool     EVENTS_LIST              read   keys timeMin, timeMax
#     free   tool     FIND_FREE_SLOTS          read   keys items, time_min, time_max
#     add    tool     CREATE_EVENT             write  keys attendees, start_datetime, summary
#     move   unclear  -                        write  "does not provide an event ID"
#     clear  unclear  -                        write  "no tool to clear events for a specific day"
#     C      none     -                        read   "a personal memory"
#     chain  api read EVENTS_LIST lane 'api'   asked 1+1
#   7 verdicts, 0 look wrong. The hand probe's connected rows, the same
#   minute: "what do I have tomorrow" -> api, EVENTS_LIST_ALL_CALENDARS,
#   read; "am I free Thursday afternoon", Mac offline -> api,
#   FIND_FREE_SLOTS, read. 22 hand verdicts, 0 flagged, both controls held.
#
#   THE CONTROL'S SLUG. In the scratch runs before this leg existed the
#   control came back EVENTS_LIST on 3/3 (drafts 1-3) and
#   EVENTS_LIST_ALL_CALENDARS on 3/3 (draft 4), byte-identical args each
#   time: tomorrow's whole day with an offset. FIND_EVENT, EVENTS_LIST and
#   EVENTS_LIST_ALL_CALENDARS are all readOnlyHint reads that list
#   tomorrow's events; the model saw every vendor tag, "important" among
#   them, and chose. No preference of ours for one slug over another is
#   written down anywhere — that would be a keyword-to-tool table — so the
#   live control accepts the read-only event-listing tools and pins the
#   verdict, the effect and the lane; the scripted control above pins
#   FIND_EVENT by identity. Still wrong and recorded: "add" puts a first
#   name where an email address goes (attendees: [{email: "sam"}]) on every
#   draft — the vendor's schema would refuse it (schema -> nothing ran ->
#   browser), and the next lever is model tier, not a rule.
TOOL_PROBE = [
    # (tag, goal, heard, routed effect, ok verdicts, ok tools, ok effects)
    ("C", "what's on my calendar tomorrow", "what do I have tomorrow?", "read",
     {"tool"}, {"GOOGLECALENDAR_FIND_EVENT", "GOOGLECALENDAR_EVENTS_LIST",
                "GOOGLECALENDAR_EVENTS_LIST_ALL_CALENDARS"}, {"read"}),
    ("free", "am I free Thursday afternoon", "am I free thursday afternoon?", "read",
     {"tool"}, {"GOOGLECALENDAR_FIND_FREE_SLOTS", "GOOGLECALENDAR_FREE_BUSY_QUERY",
                "GOOGLECALENDAR_FIND_EVENT", "GOOGLECALENDAR_EVENTS_LIST"}, {"read"}),
    ("add", "add lunch with Sam at noon tomorrow to the calendar",
     "lunch with sam tomorrow at noon, put it in", "write",
     {"tool"}, {"GOOGLECALENDAR_CREATE_EVENT", "GOOGLECALENDAR_QUICK_ADD"}, {"write"}),
    ("move", "move the call to Monday 3pm on the calendar", "call moved to monday 3pm",
     "write", {"unclear"}, set(), {"write"}),
    ("clear", "clear my calendar for Friday", "just clear friday, all of it", "write",
     {"unclear", "none"}, set(), {"write", "irreversible"}),
    ("C", "what did I promise Marcus", "what did I promise Marcus", "read",
     {"none"}, set(), {"read"}),
]


@pytest.mark.skipif(os.environ.get("ANTICIPY_HANDS_LIVE") != "1",
                    reason="the measurement: set ANTICIPY_HANDS_LIVE=1 with a "
                           "model key to drive the real model")
def test_live_tool_probe_against_the_real_model():
    from brain.llm import LLM
    llm = LLM()
    assert llm.live, "ANTICIPY_HANDS_LIVE=1 but no model key in the environment"
    print(f"\nLIVE TOOL PROBE  model={llm.model}  catalog={len(CALENDAR)} rows, "
          f"{len(hands.catalog_block(CALENDAR))} chars")
    wrong, rows = [], []
    for tag, goal, heard, effect, ok_v, ok_t, ok_e in TOOL_PROBE:
        v = hands.choose_tool(goal, "googlecalendar", CALENDAR, llm=llm,
                              heard=heard, effect=effect)
        fine = v.verdict in ok_v and (not v.chosen or v.tool in ok_t) \
            and (not v.chosen or v.effect in ok_e)
        flag = "" if fine else "  LOOKS WRONG"
        if flag:
            wrong.append((tag, goal, v.verdict, v.tool))
        keys = sorted(v.args) if isinstance(v.args, dict) else None
        rows.append(f"  [{tag:<5}] {v.verdict:<10} {v.tool or '-':<42} {v.effect:<12} "
                    f"asked={v.asked} keys={keys}{flag}\n        {v.reason[:150]}")
    # and the whole chain once, through the router, with the calendar connected
    v = choose_hand("what's on my calendar tomorrow",
                    HandContext(connections=(ConnectedApp("googlecalendar"),),
                                browser_online=True, source="what do I have tomorrow?",
                                catalogs={"googlecalendar": CALENDAR}), llm=llm)
    rows.append(f"  [chain] {v.hand} {v.effect} tool={v.tool or '-'} lane={lane_for(v)!r} "
                f"asked={v.asked}+{v.tool_asked}\n        {v.reason[:150]}")
    print("\n".join(rows))
    print(f"  {len(rows)} verdicts, {len(wrong)} look wrong: {wrong}")
    control = [w for w in wrong if w[0] == "C"]
    assert not control, f"a CONTROL moved: {control}"
    assert v.hand == HAND_API and v.effect == "read" and lane_for(v) == "api"
