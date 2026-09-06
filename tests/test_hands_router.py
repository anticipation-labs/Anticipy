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
    # api -> the browser lane, FOR NOW: there is no api executor, and a new
    # lane string would be claimed by every extension whose filter reads
    # lane!="research". Pinned with its reason; change it with the executor.
    assert lane_for(HandVerdict(HAND_API, "")) == ""
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
    v = choose_hand("reply to the landlord", at_zero,
                    llm=ScriptedLLM(says(HAND_API, app="mailer", effect="write")))
    assert v.hand == HAND_BROWSER
    assert "rung 0" in v.reason
    at_three = HandContext(connections=(row,), rung=3)
    v = choose_hand("reply to the landlord", at_three,
                    llm=ScriptedLLM(says(HAND_API, app="mailer", effect="write")))
    assert v.hand == HAND_API, "the floor must be a floor, not a wall"


def test_a_read_on_a_connected_app_is_licensed():
    """Control for the floors: the api hand can be reached, so a test that
    never sees it is testing a floor and not a router that always says no."""
    ctx = connected(ConnectedApp("mailer", status="connected"))
    v = choose_hand("what did Dana send this week", ctx,
                    llm=ScriptedLLM(says(HAND_API, app="Mailer", effect="read")))
    assert v.hand == HAND_API
    assert v.app == "mailer"                # the row's spelling, not the model's
    assert v.effect == "read"


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
#   m11 send the revised quote by Thursday ... hold     irreversible research*
#   m11 move the call to Monday 3pm .......... browser  write        lane ''
#   m25 book the 7pm table at Santouka ....... browser  write        lane ''
#   m27 email the landlord re the heater ..... browser  write        lane ''
#   m29 find a dentist open Saturdays ........ research read         research
#   m34 what's the wifi at the cabin ......... research read         research
#   m36 wire $2,000 to the account ........... hold     irreversible research*
#   m37 book my usual haircut ................ browser  write        lane ''
#   m39 text Laura I'm running late .......... hold     irreversible research*
#   m41 cancel that .......................... hold     irreversible research*
#   m43 what do I have tomorrow .............. research read         research
#   m47 check in for the flight .............. browser  write        lane ''
#   C   open example.net in my browser ....... browser  read         lane ''
#   C   what did I promise Marcus ............ research read         research
#   read on a connected mail app ............. api      read   (lane '' today)
#   write on it, writes OFF .................. browser  write
#   write on it, writes ON, rung 0 ........... hold     irreversible
#   read on a connected calendar, Mac offline  api      read
#
#   * the router's lane; job_lane's seatbelt then holds send/wire/text/cancel
#     on the browser lane ("") whatever the verdict, as the parametrised leg
#     above pins.
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
    ("read on a connected app",
     "what did Dana send me this week", ConnectedApp("gmail"), {"api"}),
    ("write on a connected app, writes OFF",
     "reply to Dana that the form is attached", ConnectedApp("gmail"),
     {"browser", "hold"}),
    ("write on a connected app, writes ON, rung 0",
     "reply to Dana that the form is attached",
     ConnectedApp("gmail", writes_enabled=True), {"browser", "hold"}),
    ("read on a connected calendar, Mac offline",
     "what do I have tomorrow", ConnectedApp("googlecalendar"), {"api"}),
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
                                          source=goal), llm=llm)
        flag = "" if v.hand in ok else "  LOOKS WRONG"
        if flag:
            wrong.append((label, goal, v.hand))
        rows.append(f"  [{label}] {v.hand:<9} {v.effect:<12} app={v.app!r} "
                    f"asked={v.asked} {goal!r}{flag}\n        {v.reason}")
    print("\n".join(rows))
    print(f"  {len(rows)} verdicts, {len(wrong)} look wrong: {wrong}")
    control = {g: h for m, g, _s, ok in PROBE_GOALS if m == "C"
               for (_m, _g, h) in wrong if _g == g}
    assert not control, f"a CONTROL moved: {control}"
