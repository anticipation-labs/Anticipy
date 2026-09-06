"""THE OVERWATCH ROUTER — which hand takes this step, asked of a model.

The Two Hands spec (docs/spec-connections.txt, "Router policy", PDF page 29)
gives the assistant a browser hand, an API hand, and five generic rules for
choosing between them per step: match, connected?, ledger prior, side-effect
class, device online?. No rule names an app. The spike at
spike/two-hands/src/router.ts holds those rules behind 102 tests and nothing in
production imports it; in production `job_lane` (brain/anticipy_core.py)
decided the hand with three regexes over the goal's wording — one of them
registered standing tape, one an audited violation (item 18), and the third
the deny list that Law 1 permits as a seatbelt.

"Which hand" is a question of MEANING — does this step need an app's own
endpoint, is it a website anyone drives, is it a plain lookup, or is it
nothing a hand should touch — so it goes to a model, in the house shape
(HARNESS-LAWS.md Law 1, and brain/orchestrator.py's party_verdict /
ends_in_the_world / calendar_plan_verdict):

  ONE question, asked on its own.       `choose_hand` sends nothing but this.
  A FOUR-STATE verdict.                 browser / api / research / hold.
  Two honest non-answers.               unasked (no goal, no live model) and
                                        unanswered (asked, twice, unreadable).
  The caller compares the verdict.      `lane_for` maps it; `job_lane` holds
                                        the seatbelt AFTER it.

THE POLARITY IS A FLOOR. The browser hand is the default and the API hand is
the privilege, and "does anything authorize this hand?" must refuse when
nobody answered or it lifts itself. Concretely: hold, unasked and unanswered
all land on the research lane — the one lane a browser may not claim
(anticipy_core.RESEARCH_LANE) and the one hand that cannot change the world —
never on the browser and never on the api hand. That is the trade Law 1 asks
for and its cost is written down here: a write the model never got to judge
becomes a read-only lookup rather than a browser errand, visible in the row's
`_hand` note and in the log line this module prints, instead of a job that
acts without a verdict.

THE FACTS ARE HANDED TO THE MODEL, NOT GUESSED FROM WORDS. `gather_context`
reads which apps this owner has connected and whether writes are switched on
for each (the `connections` table, through the same records client the brain
uses for every other collection) and whether his Mac is there (the `agents`
heartbeat, the same row worker.browser_reachable reads). A fact that could not
be read is UNKNOWN and says so in the prompt — and unknown never licenses the
api hand, because rule 2 needs a connection the code can see.

THE STRUCTURAL FLOORS live in `_floors`, after the verdict, and they read
facts rather than wording: the api hand only for an app whose row says
connected; a write over the api hand only when that row's writes are on AND
the ledger rung is high enough (spec: writes start at rung 3; there is no
ledger yet, so every pair sits at rung 0 and no write reaches the api hand
today). The irreversible-verb deny list stays where it is, in `job_lane`,
as the seatbelt Law 1 permits — and it holds after the verdict, never instead
of it.

THIS FILE MAY NEVER NAME AN APP. Not in a rule, a constant, or the prompt;
tests/test_hands_router.py reads this source back and fails on one. The
router sees the owner's own connection rows as data.

WHERE AN API VERDICT GOES. `lane="api"` (LANE_API), since 2026-09-06 — the
executor exists: brain/worker.py `run_api_jobs` claims a queued api-lane row
under `worker-api` with the extension's own doctrine (stamp, read back, run
only if the stamp survived) and POSTs its id to the Worker's
`/hands/api/run` (migration/workers/src/routes/hands_api.ts), which reads the
step off the ROW and runs it on src/connections/api_hand.ts behind its four
floors. The verdict rides on the row as `params["_hand"]`; the executor reads
`app`, `effect`, `tool` and `args` from it and refuses a row whose `hand` or
`lane` is not "api". Until 2026-09-06 an `api` verdict mapped to the browser
lane because nothing could run it; that mapping is gone and its test moved.

WHICH TOOL is the fourth house-shape question, since 2026-09-06 (`choose_tool`).
Until then nothing wrote `tool` or `args` onto the note — this file asked
WHICH HAND and nothing asked which tool — so every api-lane row reached the
hand without a slug, was refused `tool_required` before any vendor call
(migration/workers/test/hands-api.test.ts pins that refusal) and bounced to
the browser one hop late: the wire was a pipe to nowhere. Reproduced
2026-09-06 before this section was written: the note on an api row read
{hand, reason, app, effect, asked, lane} and nothing else.

Now, once an `api` verdict has held the floors, `plan_api_step` reads that
app's CATALOG — the vendor's own tool rows for the toolkit, in the shape the
Worker's provider.tools() returns, through the records client the way
`read_connections` reads rows — and asks ONE question on its own: which ONE
slug from this list does the step, with what arguments. Four states:
tool / none / unclear / no-verdict. The slug is compared BY IDENTITY against
the catalog rows and the catalog's own spelling goes on the note; a slug the
model typed that is not in the list is no verdict, never trusted. The effect
comes from the tool's own hint tags, TIGHTENED and never loosened, exactly as
api_hand.ts does it — an args object a model invents for a write tool buys
it nothing — and the floors are applied again to the tightened effect. Only
a chosen tool takes the api lane. None, unclear and no-verdict hand the step
to the browser: the default hand, the spec's own "browser now" for a step the
api hand cannot take, and where the Worker's `tool_required` handback was
already sending it — one hop earlier, with the reason on the row. An
irreversible effect, declared or tightened, is a HOLD, because rule 3 says a
step that cannot be undone never takes the api hand on its own, and job_lane
turns a hold into a card the owner sees.

WHAT STILL DOES NOT EXIST, said here rather than discovered: the Worker
serves no catalog to the brain. `read_catalog` GETs API_HAND_TOOLS_PATH
(`/hands/api/tools?toolkit=…`) with the service token and expects
`{items: [...]}` in provider.tools()' shape; that route is not in
src/index.ts, so on live the read is UNKNOWN, no tool verdict is reached,
and an api verdict still lands on the browser lane — with `tool_verdict:
"no-verdict"` and the reason on the row — until the route ships. That is the
next wire, and overnight/is_connect_live.py is where its leg belongs. The
catalog the planner was measured against is a live capture, in
tests/fixtures/, never read by this file.

THE EXTENSION'S CLAIM FILTER, measured 2026-09-06: `workflow_id!="" &&
lane!="research"` (extension/background.js:82). It NAMES `lane`, so the
Worker's research_lane hook does not append its exclusions to it, and it does
not exclude "api" — a shipped extension that polls before the brain claims
WOULD list an api-lane row. What keeps two hands off one row is the workflow
guard's lease (src/policy/workflow_guard.ts: a running row may only be moved
by the lease it holds), not the filter, and what it costs is the api hand
being bypassed by a browser that won the race. tests/test_api_lane.py pins
the measured filter so the day it changes is a visible day. THAT DAY IS THE
SAME DAY, in the working tree: the extension's filter gains `&& lane!="api"`
and research_lane.ts refuses a non-worker claim on lane api
(extension/tests/test_api_lane_is_not_browser_work.mjs proves it). Until that
extension ships, the shipped one still lists the row and the lease is still
what holds; tests/test_api_lane.py's leg on the filter is red between the
measurement and its own update, which is the visible day it was for.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Optional

from . import pb
from .llm import LLM

# ---------------------------------------------------------------- the states
HAND_BROWSER = "browser"
HAND_API = "api"
HAND_RESEARCH = "research"
HAND_HOLD = "hold"
VERDICTS = (HAND_BROWSER, HAND_API, HAND_RESEARCH, HAND_HOLD)

# The two non-answers, kept apart because they mean different things to a
# reader of the log: UNASKED is the documented inert mode (no goal, no live
# model — nothing was asked), UNANSWERED is a live model that gave nothing
# this code could read, twice.
HAND_UNASKED = "unasked"
HAND_UNANSWERED = "unanswered"
NO_VERDICT = (HAND_UNASKED, HAND_UNANSWERED)

EFFECT_READ = "read"
EFFECT_WRITE = "write"
EFFECT_IRREVERSIBLE = "irreversible"
EFFECTS = (EFFECT_READ, EFFECT_WRITE, EFFECT_IRREVERSIBLE)

# The promotion ladder (spec PDF page 31). A write over the api hand needs the
# "assisted writes" rung or above. Nothing keeps a ledger yet, so every
# (step, app) pair is at rung 0 — which is the spec's own starting point:
# "the ledger starts every new signature at browser only".
API_WRITE_MIN_RUNG = 3
NO_LEDGER_RUNG = 0

# How fresh the extension's heartbeat must be to count the Mac as online.
# The same number as brain/worker.py AGENT_FRESH_SECONDS, pinned equal by a
# test, because two different ideas of "online" in one process is how a step
# gets parked on a machine the other half of the brain says is awake.
AGENT_FRESH_SECONDS = 90

# A fact read is a network call inside a decision the owner may be waiting
# on. Short, and a miss is UNKNOWN rather than an exception.
FACT_TIMEOUT = 5

# The lane each verdict lands on. `""` is the browser lane, `"research"` is
# anticipy_core.RESEARCH_LANE (spelled here rather than imported because this
# module must never import anticipy_core — that file imports this one), and
# `"api"` is the lane brain/worker.py run_api_jobs polls and the Worker's
# /hands/api/run route refuses anything else from. The Worker's copy is
# routes/hands_api.ts API_LANE, pinned equal by test/hands-api.test.ts.
LANE_BROWSER = ""
LANE_RESEARCH = "research"
LANE_API = "api"
# THE POLARITY OF "NO VERDICT" IS RESEARCH, and it was nearly flipped. On
# 2026-09-06 the parent moved hold/unasked/unanswered to "" (the browser lane),
# arguing "" is the HELD lane where a card appears. The verifier then showed
# the hole: "" is only held when is_consequential says so, and for a read-only
# goal it says no -- so an unreadable reply on "look up the ferry schedule"
# would have RUN in the owner's own browser with no verdict and no card.
# Research cannot change the world. A verdict nobody gave licenses nothing.
LANE_FOR = {
    HAND_BROWSER: LANE_BROWSER,
    HAND_API: LANE_API,
    HAND_RESEARCH: LANE_RESEARCH,
    HAND_HOLD: LANE_RESEARCH,
    HAND_UNASKED: LANE_RESEARCH,
    HAND_UNANSWERED: LANE_RESEARCH,
}

# ---------------------------------------------------------------- the tool
# The fourth question's states. "tool" names one slug from the catalog; "none"
# is the model saying no tool in this catalog does the step; "unclear" is a
# tool that exists for a step that does not carry what its call needs; and
# "no-verdict" is nobody having answered — no catalog, no live model, an
# unreadable reply twice, or a slug that is not in the list. Only "tool" can
# take the api lane: a FLOOR, in the hand question's own sense.
TOOL_CHOSEN = "tool"
TOOL_NONE = "none"
TOOL_UNCLEAR = "unclear"
TOOL_NO_VERDICT = "no-verdict"
TOOL_VERDICTS = (TOOL_CHOSEN, TOOL_NONE, TOOL_UNCLEAR)

# The MCP-style hint tags the live catalog carries (api_hand.ts READ_ONLY_HINT
# … UPDATE_HINT, measured 2026-09-06). Exact identifier matches against the
# vendor's own tag strings; no word inside a description is read.
READ_ONLY_HINT = "readOnlyHint"
DESTRUCTIVE_HINT = "destructiveHint"
CREATE_HINT = "createHint"
UPDATE_HINT = "updateHint"
HINT_TAGS = (READ_ONLY_HINT, DESTRUCTIVE_HINT, CREATE_HINT, UPDATE_HINT)

# api_hand.ts SIDE_EFFECT_ORDER: a hint may only make a step STRICTER.
SIDE_EFFECT_ORDER = {EFFECT_READ: 0, EFFECT_WRITE: 1, EFFECT_IRREVERSIBLE: 2}

# Where the brain reads a toolkit's catalog: a service-token GET beside the
# run door (routes/hands_api.ts HANDS_API_RUN_PATH is "/hands/api/run"),
# answering {items: [...]} in provider.tools()' shape. NOT YET SERVED — the
# module docstring says so. One constant, so the day it ships is one edit
# here and one leg in overnight/is_connect_live.py.
API_HAND_TOOLS_PATH = "/hands/api/tools"
# A catalog read is the Worker walking up to ten vendor pages: longer than a
# fact read, still bounded, and a miss is UNKNOWN rather than an exception.
CATALOG_TIMEOUT = 20
# The most catalog the tool question may carry, in characters. Measured
# 2026-09-06 on two live catalogs at full detail (every parameter with its
# description): 49 tools -> 66k chars, 63 tools -> 60k. Over the budget the
# rendering gets LEANER — parameter descriptions go first, then parameter
# detail — and never SHORTER: dropping a row would be this file deciding
# which tools exist, which is the vendor's to say and the model's to choose.
CATALOG_CHARS_MAX = 120_000
# Per-row bounds inside the rendering. Plumbing, not a decision.
TOOL_DESCRIPTION_CHARS = 400
PARAM_DESCRIPTION_CHARS = 200
PARAM_ENUM_MAX = 8


# ---------------------------------------------------------------- the facts
@dataclass(frozen=True)
class ConnectedApp:
    """One row of the owner's `connections` table, as the router reads it.
    `toolkit` is the vendor's slug for the app — data, never a constant."""
    toolkit: str
    alias: str = ""
    status: str = "connected"
    writes_enabled: bool = False

    @property
    def usable(self) -> bool:
        return self.status == "connected"


@dataclass(frozen=True)
class CatalogTool:
    """One row of a toolkit's catalog, as the Worker's provider.tools()
    returns it (CatalogTool in provider.ts): the vendor's own tool, in the
    vendor's spelling. `input_parameters` is the vendor's JSON schema for the
    call, carried whole for the model and read here only for the shape a
    schema is — its property names and its `required` list."""
    slug: str
    name: str = ""
    description: str = ""
    toolkit: str = ""
    deprecated: bool = False
    tags: tuple = ()
    input_parameters: Optional[dict] = None

    @classmethod
    def from_row(cls, row) -> Optional["CatalogTool"]:
        """A row in either spelling — the Worker's (`inputParameters`,
        `deprecated`) or the vendor's raw (`input_parameters`,
        `is_deprecated`, `toolkit: {slug}`). None when the row cannot be an
        allow-list entry (no slug), as provider.ts readCatalogTool answers."""
        if not isinstance(row, dict):
            return None
        slug = str(row.get("slug") or "").strip()
        if not slug:
            return None
        toolkit = row.get("toolkit")
        if isinstance(toolkit, dict):
            toolkit = toolkit.get("slug")
        params = row.get("inputParameters")
        if params is None:
            params = row.get("input_parameters")
        deprecated = row.get("deprecated")
        return cls(
            slug=slug,
            name=str(row.get("name") or slug),
            description=str(row.get("description") or ""),
            toolkit=str(toolkit or "").strip().lower(),
            deprecated=(deprecated is True or row.get("is_deprecated") is True
                        or (isinstance(deprecated, dict)
                            and deprecated.get("is_deprecated") is True)),
            tags=tuple(t for t in (row.get("tags") or ()) if isinstance(t, str)),
            input_parameters=params if isinstance(params, dict) else None,
        )

    @property
    def hint(self) -> str:
        return hint_effect(self.tags)

    @property
    def required(self) -> tuple:
        req = (self.input_parameters or {}).get("required")
        if not isinstance(req, list):
            return ()
        return tuple(k for k in req if isinstance(k, str))


@dataclass(frozen=True)
class HandContext:
    """What the model is told besides the step. None means UNKNOWN — the fact
    could not be read — and the prompt says so in those words."""
    connections: Optional[tuple] = None
    browser_online: Optional[bool] = None
    source: str = ""
    rung: int = NO_LEDGER_RUNG
    # Where a catalog is read from once a verdict names an app; "" reads
    # nothing and the catalog is UNKNOWN.
    backend_url: str = ""
    # Catalogs already in hand, toolkit -> rows, for a caller that read them
    # itself (the tests, the live probe). None means read over backend_url.
    catalogs: Optional[dict] = None

    def connected(self, toolkit: str) -> Optional[ConnectedApp]:
        want = (toolkit or "").strip().lower()
        if not want or not self.connections:
            return None
        for row in self.connections:
            if row.toolkit.lower() == want and row.usable:
                return row
        return None


@dataclass(frozen=True)
class HandVerdict:
    hand: str
    reason: str
    app: str = ""
    effect: str = ""
    asked: int = 0
    # The fourth question's answer, filled only after an api verdict held the
    # floors: the catalog's spelling of the slug, the arguments the model
    # built (NEVER logged by this module — they can hold the text of a
    # person's mail), which of the four states it was, and how many asks.
    tool: str = ""
    args: Optional[dict] = None
    tool_verdict: str = ""
    tool_asked: int = 0

    @property
    def decided(self) -> bool:
        return self.hand in VERDICTS

    def as_note(self) -> dict:
        """What rides on the row as params["_hand"]. The Worker's
        stepFromRow reads app, tool, args and effect off exactly these keys."""
        return {"hand": self.hand, "reason": self.reason, "app": self.app,
                "effect": self.effect, "asked": self.asked,
                "tool": self.tool, "args": self.args,
                "tool_verdict": self.tool_verdict,
                "tool_asked": self.tool_asked}


@dataclass(frozen=True)
class ToolVerdict:
    """The fourth question's answer on its own. `effect` is FINAL — the
    router's effect, the model's declaration and the tool's own hint,
    tightened together and never loosened. `declared` and `hint` are kept so
    a reader of the log can see which of the three made it what it is."""
    verdict: str
    reason: str
    tool: str = ""
    args: Optional[dict] = None
    effect: str = ""
    declared: str = ""
    hint: str = ""
    asked: int = 0

    @property
    def chosen(self) -> bool:
        return self.verdict == TOOL_CHOSEN


# ---------------------------------------------------------------- the prompt
HANDS_SYSTEM = """An assistant listened to its owner's day and wrote down ONE step of work
it means to do for him. It has two hands that act in the world, one arm that
only reads, and the choice to touch nothing. Pick the one that takes this step.

  browser  — drive the owner's own signed-in browser on his Mac. Works on any
             website, including the ones with no app behind them. Needs the
             Mac awake. Slow.
  api      — call an app's own endpoint through an account the owner has
             CONNECTED to the assistant. Fast, runs with the laptop shut, but
             it exists only for an app in the CONNECTED list below, and it may
             change things in that app only when that row says writes are ON.
  research — read-only, on the server: look something up, read pages, or
             recall what the assistant itself heard him say, and tell him.
             Needs no account and no app. Changes nothing anywhere.
  hold     — no hand should touch this: it is not a step anyone can run, or it
             must wait for the owner's own word (money, deleting things,
             messages to people) and nothing should be prepared toward it.

ONE QUESTION: which of the four takes this step?

Five rules, in this order. No rule names an app.
1. MATCH. Does the step need an app's own endpoint — his mail, his calendar,
   his notes, a chat workspace, a customer record — or is it a website anyone
   drives in a browser, or a plain lookup that needs no account at all?
2. CONNECTED? The api hand exists only for an app in the CONNECTED list whose
   status is "connected". A step that needs an app not in that list goes to
   the browser.
3. SIDE EFFECT. Say whether the step reads, writes, or cannot be undone.
   A read on a connected app may take the api hand. A write may take it only
   when that app's writes are ON. A step that cannot be undone — paying,
   deleting, sending something to a person — never takes the api hand on its
   own.
4. LEDGER PRIOR. The browser is the default and the api hand is the
   privilege: with no track record for this kind of step, anything that
   changes the world prefers the browser.
5. DEVICE ONLINE? If the Mac is offline, a read on a connected app may take
   the api hand, and a read that needs no account is research. A write with
   the Mac offline still goes to the browser, where it waits.

And two from the house:
- When the owner asked to see something in HIS browser — "open it in my
  browser", "pull it up in a new tab" — that is browser work even though it
  only reads.
- The browser is for DOING things on websites — accounts, forms, bookings,
  payments, pages he asked to see. Finding, comparing or checking something
  on the open web needs no account and is research, not the browser, even
  though a browser could do it.
- A question about his own life — what he promised, said, was told, owes, or
  where something is — is answered from what the assistant heard, never by
  opening an app or a website for it. That is research too, whether or not
  anything is connected. Answering him is not a hand.

Worked examples, nothing connected unless it says so:
  "find a plumber who works weekends"                  -> research, read
  "compare ferry times to the island on Friday"        -> research, read
  "what did I tell Sam about Friday"                   -> research, read
  "pull the article up in a new tab"                   -> browser, read
  "reserve the table for six on Saturday"              -> browser, write
  "what's in my inbox from the landlord" (mail app connected)
                                                       -> api, read
  "delete the old account"                             -> hold, irreversible

Reply ONLY with one compact JSON object, nothing before or after it:
{"hand": "browser"|"api"|"research"|"hold",
 "app": "the toolkit name exactly as it appears in the CONNECTED list, or null",
 "effect": "read"|"write"|"irreversible",
 "reason": "one short sentence"}"""

RETRY_SUFFIX = ("\n\nYour previous reply could not be read. Reply with ONLY "
                "the JSON object — no explanation before or after it, and no "
                "code fence.")


def _extract_json(text: str) -> str:
    """Same tolerance as brain/orchestrator.py: a fenced or prose-wrapped
    object is still an object. Copied rather than imported so this module
    depends on nothing that depends on anticipy_core."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        return text[start:end + 1]
    return text


def facts_block(ctx: HandContext) -> str:
    """The facts, spelled for the model. UNKNOWN is a word here, never a
    silent omission: a list that could not be read must not look like an
    owner who connected nothing."""
    if ctx.connections is None:
        apps = ("  unknown — the list could not be read. Treat it as empty: "
                "the api hand is not available for this step.")
    elif not ctx.connections:
        apps = "  none — the owner has connected nothing."
    else:
        rows = []
        for row in ctx.connections:
            alias = f" ({row.alias})" if row.alias else ""
            rows.append(f"  - {row.toolkit}{alias} — status {row.status}, "
                        f"writes {'ON' if row.writes_enabled else 'OFF'}")
        apps = "\n".join(rows)
    if ctx.browser_online is None:
        mac = "unknown"
    else:
        mac = "yes" if ctx.browser_online else "no"
    return (f"CONNECTED APPS:\n{apps}\n"
            f"MAC ONLINE: {mac}\n"
            f"LEDGER: rung {ctx.rung} of 4 for this kind of step"
            + (" — no track record yet" if ctx.rung <= NO_LEDGER_RUNG else ""))


def _read_reply(raw) -> Optional[tuple]:
    """(hand, app, effect, reason) from a parsed reply, or None when the
    reply does not carry a verdict this code can read. A hand outside the
    four is not a fifth state; it is unreadable."""
    if not isinstance(raw, dict):
        return None
    hand = raw.get("hand")
    if not isinstance(hand, str) or hand.strip().lower() not in VERDICTS:
        return None
    app = raw.get("app")
    app = app.strip() if isinstance(app, str) else ""
    effect = raw.get("effect")
    effect = effect.strip().lower() if isinstance(effect, str) else ""
    if effect not in EFFECTS:
        # An effect nobody recognises is read as the most severe one there
        # is, so a garbled value cannot make a step look gentle.
        effect = EFFECT_IRREVERSIBLE
    reason = raw.get("reason")
    reason = reason.strip() if isinstance(reason, str) else ""
    return hand.strip().lower(), app, effect, reason


def _floors(hand: str, app: str, effect: str, reason: str,
            ctx: HandContext, asked: int) -> HandVerdict:
    """Rules 2, 3 and 4 as STRUCTURE, applied to the verdict. They read the
    owner's connection rows and the ledger rung, never the goal's wording —
    what a step TOUCHES is the seatbelt Law 1 permits."""
    if hand != HAND_API:
        return HandVerdict(hand, reason, app, effect, asked)
    if ctx.connections is None:
        return HandVerdict(HAND_BROWSER, f"{reason} — floor: the connected "
                           "apps could not be read, so nothing licenses the "
                           "api hand", app, effect, asked)
    row = ctx.connected(app)
    if row is None:
        return HandVerdict(HAND_BROWSER, f"{reason} — floor: {app or 'no app'} "
                           "is not a connected app of this owner", app,
                           effect, asked)
    if effect != EFFECT_READ:
        if not row.writes_enabled:
            return HandVerdict(HAND_BROWSER, f"{reason} — floor: writes are "
                               f"off for {row.toolkit}", row.toolkit, effect,
                               asked)
        if ctx.rung < API_WRITE_MIN_RUNG:
            return HandVerdict(HAND_BROWSER, f"{reason} — floor: rung "
                               f"{ctx.rung} is below {API_WRITE_MIN_RUNG}, "
                               "the first rung that may write over the api "
                               "hand", row.toolkit, effect, asked)
    return HandVerdict(HAND_API, reason, row.toolkit, effect, asked)


def _default_llm():
    """The brain's own client, from the process environment — the same
    construction brain/worker.py main() uses. Not live without a key."""
    try:
        return LLM()
    except Exception:
        return None


def choose_hand(goal: str, context: Optional[HandContext] = None,
                llm=None) -> HandVerdict:
    """Which hand takes this step. One question, four states, two honest
    non-answers; see the module docstring for the polarity."""
    goal = (goal or "").strip()
    ctx = context or HandContext()
    if not goal:
        return HandVerdict(HAND_UNASKED, "no step to route")
    if llm is None:
        llm = _default_llm()
    if not llm or not getattr(llm, "live", False):
        return HandVerdict(HAND_UNASKED, "no live model to ask")
    user = (f"STEP: {goal}\n"
            f"HEARD: {ctx.source.strip() if ctx.source else '(nothing recorded)'}\n"
            + facts_block(ctx))
    asked = 0
    for attempt in range(2):
        asked += 1
        try:
            # THE SECOND ASK IS A DIFFERENT ASK (triage's lesson): the client
            # pins a seed, so an identical replay at temperature 0 would
            # reproduce the reply that just failed to parse.
            if attempt:
                res = llm.chat(HANDS_SYSTEM, user + RETRY_SUFFIX,
                               temperature=0.2)
            else:
                res = llm.chat(HANDS_SYSTEM, user, temperature=0.0)
        except Exception as exc:
            print(f"hands: the hand question went unanswered — {exc!r}; "
                  f"{goal[:60]!r} takes the research lane")
            return HandVerdict(HAND_UNANSWERED, f"model unreachable: {exc!r}",
                               asked=asked)
        try:
            raw = json.loads(_extract_json(getattr(res, "text", "")))
        except Exception:
            raw = None
        read = _read_reply(raw)
        if read is not None:
            hand, app, effect, reason = read
            verdict = _floors(hand, app, effect, reason, ctx, asked)
            # THE FOURTH QUESTION, only for a hand the floors licensed, and
            # asked exactly once here (the mutation literal).
            verdict = plan_api_step(verdict, goal, ctx, llm)
            print(f"hands: {verdict.hand} ({verdict.effect or '?'}"
                  f"{', ' + verdict.app if verdict.app else ''}"
                  f"{', ' + verdict.tool if verdict.tool else ''}) — "
                  f"{verdict.reason[:160]}")
            return verdict
        print(f"hands: unreadable reply to the hand question "
              f"(attempt {attempt + 1}) -> {raw!r}")
    return HandVerdict(HAND_UNANSWERED, "unreadable reply, twice",
                       asked=asked)


def lane_for(verdict: HandVerdict) -> str:
    """The lane a verdict lands on. Anything that is not one of the six
    known states is treated as no verdict, which is the research lane."""
    return LANE_FOR.get(getattr(verdict, "hand", None), LANE_RESEARCH)


# ---------------------------------------------------------------- which tool
TOOLS_SYSTEM = """An assistant listened to its owner's day and wrote down ONE step of work
it means to do for him. A router has already decided this step runs through
an app the owner has CONNECTED, over that app's own API. Below is that app's
TOOL CATALOG exactly as the vendor publishes it: every tool, what it does,
the tags the vendor gave it, and the parameters its call takes.

ONE QUESTION: which ONE tool from the catalog does this step, and with what
arguments?

How to answer it:
- Name a tool only by copying its slug from the catalog, exactly. A slug that
  is not in the catalog is not an answer.
- Arguments are a JSON object using the tool's own parameter names, filled
  from the STEP and from what was HEARD. Every parameter marked required must
  be present. Leave optional ones out unless the step needs them.
- Never invent a fact the call needs. An event or message id, a person's
  address, a place, a time that neither the step nor what was heard supplies
  is not yours to make up, and a person's name is not an address or an id:
  if a required one is missing, the verdict is "unclear", and the reason
  says which.
- Name only a tool whose ONE call does the whole step and no more than the
  step asked. A step that would take a lookup first and a change after is
  not one call, and a tool that would also touch what the step did not name
  is not that step's tool: the verdict is "unclear", and the reason says
  what the lookup would have to find or what the tool would touch besides.
- Relative times ("tomorrow", "Thursday afternoon") are resolved from the
  current date, time and time zone you were given, and written the way the
  parameter asks (an RFC3339 timestamp with an offset when it asks for one).
  A whole day runs from its first moment to its last.
- Prefer the tool that does the whole step in one call; prefer a tool not
  marked DEPRECATED; between two tools that would both do it, prefer the one
  the vendor tags "important"; when the step only asks to know something,
  prefer the tool that reads.
- "none": no tool in this catalog does this step — it belongs to another app,
  to a website, or to the assistant's own memory. A question about what the
  owner himself said, promised, was told or owes is answered from what the
  assistant heard, never by searching an app for it: that is "none".
- "unclear": a tool exists but the step does not carry what its call needs,
  or the step could mean two different calls and nothing here says which.

Two worked examples, with a calendar app connected:
  "what did I tell Sam about Friday"   -> none: it is answered from what was
                                          heard, not from any app.
  "move the call to Tuesday 3pm", when nothing heard says which event
                                       -> unclear: the update needs an event
                                          id nobody supplied; say so.
- effect is what the CALL does to the app: "read" changes nothing, "write"
  creates or changes something that can be changed back, "irreversible"
  deletes, sends, or cannot be undone. The vendor's hints will tighten this
  and never loosen it — calling a write a read buys nothing.

Reply ONLY with one compact JSON object, nothing before or after it:
{"verdict": "tool"|"none"|"unclear",
 "tool": "the slug, copied from the catalog, or null",
 "args": {the arguments, an object, or null},
 "effect": "read"|"write"|"irreversible",
 "reason": "one short sentence"}"""

NOT_IN_CATALOG_SUFFIX = ("\n\nYour previous reply named {slug}, which is not a "
                         "slug in the catalog above. Copy a slug exactly as it "
                         "appears there, or answer \"none\" or \"unclear\". "
                         "Reply with ONLY the JSON object.")
MISSING_ARGS_SUFFIX = ("\n\nYour previous reply chose {slug} without its required "
                       "parameter(s) {names}. Fill them from the step and what "
                       "was heard, or answer \"unclear\" if they are not there "
                       "to fill. Reply with ONLY the JSON object.")


def hint_effect(tags) -> str:
    """api_hand.ts sideEffectHint: what the tool says about its own effect,
    or "" when it says nothing. The strictest tag wins — destructiveHint is
    irreversible, createHint and updateHint are writes, readOnlyHint alone is
    a read. "" IS NOT "read": a row with no hint tags says nothing, and
    nothing tightens nothing."""
    hint = ""
    for tag in tags or ():
        if tag == DESTRUCTIVE_HINT:
            return EFFECT_IRREVERSIBLE
        if tag in (CREATE_HINT, UPDATE_HINT):
            hint = EFFECT_WRITE
        elif tag == READ_ONLY_HINT and not hint:
            hint = EFFECT_READ
    return hint


def tighten(planned: str, hint: str) -> str:
    """api_hand.ts tightenSideEffect: the stricter of the two. An effect
    nobody recognises is the most severe one there is, as _read_reply reads
    a garbled value; an empty hint changes nothing."""
    if planned and planned not in SIDE_EFFECT_ORDER:
        planned = EFFECT_IRREVERSIBLE
    if not hint:
        return planned
    if hint not in SIDE_EFFECT_ORDER:
        return EFFECT_IRREVERSIBLE
    if not planned:
        return hint
    return hint if SIDE_EFFECT_ORDER[hint] > SIDE_EFFECT_ORDER[planned] else planned


def _schema_type(spec: dict) -> str:
    kind = spec.get("type")
    if isinstance(kind, str):
        return kind
    if isinstance(kind, list):
        return "/".join(str(x) for x in kind)
    for key in ("anyOf", "oneOf"):
        alts = spec.get(key)
        if isinstance(alts, list):
            names = [a.get("type") for a in alts
                     if isinstance(a, dict) and isinstance(a.get("type"), str)]
            if names:
                return "/".join(names)
    return "any"


def render_catalog(rows, lean: int = 0) -> str:
    """The vendor's rows as lines for the model: the vendor's order, every
    row present, each with its slug, every tag the vendor gave it, its
    DEPRECATED mark, its description and its parameters (`*` = required). `lean` 0 carries every
    parameter with its description, 1 drops the descriptions, 2 lists names
    only. Rendering is plumbing: nothing here reads a word to decide."""
    lines = []
    for t in rows:
        # Every tag the vendor put on the row, verbatim and in its order —
        # the four effect hints among them, and whatever else the vendor
        # says about the tool (measured 2026-09-06: "important" marks the
        # rows the vendor itself surfaces first). Showing only the hints,
        # as the first draft did, hid the vendor's own ranking from the
        # model and it picked a sibling of the tool the vendor recommends.
        head = f"- {t.slug}  tags: {', '.join(t.tags) if t.tags else 'none'}"
        if t.deprecated:
            head += "  DEPRECATED"
        lines.append(head)
        desc = " ".join((t.description or "").split())
        if desc:
            lines.append("    " + desc[:TOOL_DESCRIPTION_CHARS])
        props = (t.input_parameters or {}).get("properties")
        props = props if isinstance(props, dict) else {}
        required = set(t.required)
        if not props:
            lines.append("    parameters: none")
            continue
        if lean >= 2:
            lines.append("    parameters (* = required): " + ", ".join(
                f"{k}{'*' if k in required else ''}" for k in props))
            continue
        lines.append("    parameters (* = required):")
        for key, spec in props.items():
            spec = spec if isinstance(spec, dict) else {}
            bits = [f"{key}{'*' if key in required else ''}: {_schema_type(spec)}"]
            enum = spec.get("enum")
            if isinstance(enum, list) and enum:
                bits.append("one of " + ", ".join(str(x) for x in enum[:PARAM_ENUM_MAX]))
            default = spec.get("default")
            if isinstance(default, (str, int, float, bool)):
                bits.append(f"default {default!r}")
            if lean < 1:
                pdesc = " ".join(str(spec.get("description") or "").split())
                if pdesc:
                    bits.append(pdesc[:PARAM_DESCRIPTION_CHARS])
            lines.append("      " + " — ".join(bits))
    return "\n".join(lines)


def catalog_block(rows) -> str:
    """The fullest rendering that fits CATALOG_CHARS_MAX — leaner when it
    must be, never shorter."""
    text = ""
    for lean in (0, 1, 2):
        text = render_catalog(rows, lean)
        if len(text) <= CATALOG_CHARS_MAX:
            break
    return text


def _read_tool_reply(raw) -> Optional[tuple]:
    """(verdict, slug, args, effect, reason) from a parsed reply, or None when
    it does not carry a verdict this code can read. A verdict outside the
    three is not a fourth state; it is unreadable. A chosen tool with no slug,
    with arguments that are not an object, or with no effect this code
    recognises is unreadable too — silence about the effect licenses nothing
    (api_hand.ts effect_required), and the second ask can say so."""
    if not isinstance(raw, dict):
        return None
    verdict = raw.get("verdict")
    verdict = verdict.strip().lower() if isinstance(verdict, str) else ""
    slug = raw.get("tool")
    slug = slug.strip() if isinstance(slug, str) else ""
    if not verdict and slug:
        verdict = TOOL_CHOSEN          # named a tool and forgot the word
    if verdict not in TOOL_VERDICTS:
        return None
    args = raw.get("args")
    if args is None:
        args = {}
    effect = raw.get("effect")
    effect = effect.strip().lower() if isinstance(effect, str) else ""
    if effect not in EFFECTS:
        effect = ""
    if verdict == TOOL_CHOSEN and (not slug or not isinstance(args, dict)
                                   or not effect):
        return None
    if not isinstance(args, dict):
        args = {}
    reason = raw.get("reason")
    reason = reason.strip() if isinstance(reason, str) else ""
    return verdict, slug, args, effect, reason


def _find_tool(rows, slug: str) -> Optional[CatalogTool]:
    """The catalog row a slug names, BY IDENTITY: the exact spelling first,
    then the case-folded identifier api_hand.ts sameSlug accepts. The row
    that comes back carries the catalog's spelling, which is what goes on the
    note and on the wire. A slug with whitespace in it is not an identifier."""
    want = (slug or "").strip()
    if not want or any(ch.isspace() for ch in want):
        return None
    for row in rows:
        if row.slug == want:
            return row
    folded = want.upper()
    for row in rows:
        if row.slug.strip().upper() == folded:
            return row
    return None


def _missing_required(row: CatalogTool, args: dict) -> tuple:
    """The vendor's own `required` list against the keys the model built —
    the shape a schema is, not a word in it."""
    return tuple(k for k in row.required if k not in args)


def choose_tool(goal: str, toolkit: str, catalog, llm=None, heard: str = "",
                effect: str = "") -> ToolVerdict:
    """Which ONE tool from this toolkit's catalog does the step, with what
    arguments. One question, three answers plus the honest fourth; see the
    module docstring for the polarity. `catalog` is the vendor's rows
    (CatalogTool, or dicts in either spelling); None is UNKNOWN and no
    verdict; () is the vendor saying there is nothing here, which is "none"
    and costs no ask. `effect` is the router's, tightened and never loosened
    by what the model declares and by the chosen tool's own hint."""
    goal = (goal or "").strip()
    toolkit = (toolkit or "").strip().lower()
    planned = effect if effect in EFFECTS else ("" if not effect else EFFECT_IRREVERSIBLE)
    if not goal or not toolkit:
        return ToolVerdict(TOOL_NO_VERDICT, "no step or no app to plan for",
                           effect=planned)
    if catalog is None:
        return ToolVerdict(TOOL_NO_VERDICT, f"the catalog for {toolkit} could "
                           "not be read, so no tool can be named", effect=planned)
    rows = []
    for row in catalog:
        row = row if isinstance(row, CatalogTool) else CatalogTool.from_row(row)
        if row is not None:
            rows.append(row)
    if not rows:
        return ToolVerdict(TOOL_NONE, f"the vendor lists no tools for {toolkit}",
                           effect=planned)
    if llm is None:
        llm = _default_llm()
    if not llm or not getattr(llm, "live", False):
        return ToolVerdict(TOOL_NO_VERDICT, "no live model to ask", effect=planned)
    user = (f"STEP: {goal}\n"
            f"HEARD: {heard.strip() if heard and heard.strip() else '(nothing recorded)'}\n"
            f"APP: {toolkit} — connected; the router sent this step to its API"
            f"{' as a ' + planned if planned else ''}\n"
            f"CATALOG ({len(rows)} tools, the vendor's own list, in the vendor's order):\n"
            + catalog_block(rows))
    suffix = ""
    why = "unreadable reply, twice"
    asked = 0
    for attempt in range(2):
        asked += 1
        try:
            # The second ask is a different ask, as choose_hand's is.
            res = llm.chat(TOOLS_SYSTEM, user + suffix,
                           temperature=0.2 if attempt else 0.0)
        except Exception as exc:
            print(f"hands: the tool question went unanswered — {exc!r}; "
                  f"{goal[:60]!r} does not take the api lane")
            return ToolVerdict(TOOL_NO_VERDICT, f"model unreachable: {exc!r}",
                               effect=planned, asked=asked)
        try:
            raw = json.loads(_extract_json(getattr(res, "text", "")))
        except Exception:
            raw = None
        read = _read_tool_reply(raw)
        if read is None:
            # The SHAPE of the reply, never its contents: an unreadable reply
            # can still carry `args`, and args can carry a person's mail.
            shape = (f"object with keys {sorted(str(k) for k in raw)}"
                     if isinstance(raw, dict) else type(raw).__name__)
            print(f"hands: unreadable reply to the tool question "
                  f"(attempt {attempt + 1}) -> {shape}")
            suffix = RETRY_SUFFIX
            why = "unreadable reply, twice"
            continue
        verdict, slug, args, declared, reason = read
        if verdict != TOOL_CHOSEN:
            final = tighten(planned, declared)
            print(f"hands: tool {verdict} ({final or '?'}, {toolkit}) — {reason[:120]}")
            return ToolVerdict(verdict, reason, effect=final, declared=declared,
                               asked=asked)
        row = _find_tool(rows, slug)
        if row is None:
            # A slug the model typed that is not in the list. Never trusted;
            # asked once more, in different words, then no verdict.
            print(f"hands: the model named {slug[:80]!r}, which is not in "
                  f"{toolkit}'s catalog (attempt {attempt + 1})")
            suffix = NOT_IN_CATALOG_SUFFIX.format(slug=slug[:80])
            why = f"named {slug[:80]!r}, which is not in the catalog"
            continue
        missing = _missing_required(row, args)
        if missing:
            print(f"hands: {row.slug} chosen without required "
                  f"{', '.join(missing)} (attempt {attempt + 1})")
            suffix = MISSING_ARGS_SUFFIX.format(slug=row.slug,
                                                names=", ".join(missing))
            why = f"chose {row.slug} without its required {', '.join(missing)}"
            continue
        hint = row.hint
        final = tighten(tighten(planned, declared), hint)
        print(f"hands: tool {row.slug} ({final}; declared {declared or '?'}, "
              f"hint {hint or 'none'}) — {reason[:120]}")
        return ToolVerdict(TOOL_CHOSEN, reason, tool=row.slug, args=args,
                           effect=final, declared=declared, hint=hint,
                           asked=asked)
    return ToolVerdict(TOOL_NO_VERDICT, why, effect=planned, asked=asked)


def catalog_for(ctx: HandContext, toolkit: str) -> Optional[tuple]:
    """This toolkit's rows: the ones the caller already holds, else a read
    over the backend. None is UNKNOWN either way."""
    want = (toolkit or "").strip().lower()
    if not want:
        return None
    if ctx.catalogs is not None:
        rows = ctx.catalogs.get(want)
        if rows is None:
            for key, value in ctx.catalogs.items():
                if str(key).strip().lower() == want:
                    rows = value
                    break
        if rows is None:
            return None
        out = []
        for row in rows:
            row = row if isinstance(row, CatalogTool) else CatalogTool.from_row(row)
            if row is not None:
                out.append(row)
        return tuple(out)
    return read_catalog(want, ctx.backend_url)


def plan_api_step(verdict: HandVerdict, goal: str, ctx: HandContext,
                  llm=None) -> HandVerdict:
    """The fourth question, for a verdict the floors licensed for the api
    hand. Any other verdict passes through untouched. The polarity is in the
    module docstring: only a chosen tool keeps the api hand; none, unclear
    and no-verdict go to the browser with the reason; an irreversible
    effect is a hold; and the floors run again on the tightened effect."""
    if verdict.hand != HAND_API:
        return verdict
    app = verdict.app
    tv = choose_tool(goal, app, catalog_for(ctx, app), llm=llm,
                     heard=ctx.source, effect=verdict.effect)
    note = dict(tool=tv.tool, args=tv.args, tool_verdict=tv.verdict,
                tool_asked=tv.asked)
    if not tv.chosen:
        return replace(verdict, hand=HAND_BROWSER,
                       reason=f"{verdict.reason} — no tool for the api hand "
                              f"({tv.verdict}: {tv.reason})",
                       effect=tv.effect or verdict.effect, **note)
    if tv.effect == EFFECT_IRREVERSIBLE:
        return replace(verdict, hand=HAND_HOLD, effect=tv.effect,
                       reason=f"{verdict.reason} — {tv.tool} cannot be undone "
                              f"(declared {tv.declared or '?'}, hint "
                              f"{tv.hint or 'none'}); it waits for the owner's word",
                       **note)
    floored = _floors(HAND_API, app, tv.effect, verdict.reason, ctx,
                      verdict.asked)
    return replace(floored, effect=tv.effect,
                   reason=f"{floored.reason}; tool {tv.tool} ({tv.reason})",
                   **note)


# ---------------------------------------------------------------- reading facts
def _escaped(value: str) -> str:
    return str(value or "").replace('"', '\\"')


def read_connections(owner_ref: str, backend_url: str) -> Optional[tuple]:
    """This owner's rows from the `connections` table, through the records
    client every other brain read uses. None when they could not be read —
    a backend that does not serve the table, a refused credential, a
    timeout — and None is UNKNOWN, never "connected nothing". The owner id
    is the process' own scope, never a body."""
    ref = str(owner_ref or "").strip()
    base = str(backend_url or "").strip().rstrip("/")
    if not ref or not base:
        return None
    try:
        r = pb.get(f"{base}/api/collections/connections/records",
                   params={"filter": f'user_id="{_escaped(ref)}"',
                           "perPage": 100},
                   timeout=FACT_TIMEOUT)
        if not r.ok:
            return None
        items = r.json().get("items", [])
    except Exception:
        return None
    rows = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        toolkit = str(item.get("toolkit") or "").strip()
        if not toolkit:
            continue
        rows.append(ConnectedApp(
            toolkit=toolkit,
            alias=str(item.get("alias") or "").strip(),
            status=str(item.get("status") or "").strip() or "disconnected",
            writes_enabled=item.get("writes_enabled") in (1, True, "1", "true"),
        ))
    return tuple(rows)


def read_catalog(toolkit: str, backend_url: str) -> Optional[tuple]:
    """One toolkit's tool rows from the Worker (API_HAND_TOOLS_PATH), through
    the records client every other brain read uses, with the service token
    riding on it. None when they could not be read — no route, a refused
    token, a timeout, a body with no `items` — and None is UNKNOWN, never
    "no tools". The vendor's global catalog names nobody, so no owner rides
    on the request. Two of provider.ts's own rules are kept: a row naming
    another toolkit means the scoping did not hold and nothing here is an
    allow-list for it; a page of rows none of which can be read is not an
    empty catalog."""
    want = str(toolkit or "").strip().lower()
    base = str(backend_url or "").strip().rstrip("/")
    if not want or not base:
        return None
    try:
        r = pb.get(f"{base}{API_HAND_TOOLS_PATH}", params={"toolkit": want},
                   timeout=CATALOG_TIMEOUT)
        if not r.ok:
            return None
        items = r.json().get("items")
    except Exception:
        return None
    if not isinstance(items, list):
        return None
    rows = []
    for item in items:
        row = CatalogTool.from_row(item)
        if row is None:
            continue
        if row.toolkit and row.toolkit != want:
            return None
        rows.append(row)
    if items and not rows:
        return None
    return tuple(rows)


def browser_is_online(owner_ref: str, backend_url: str) -> Optional[bool]:
    """Is his browser there? The same `agents` heartbeat
    worker.browser_reachable reads, scoped to this owner — with one
    difference: that function answers True when it cannot see (it decides
    whether to send bad news, and unknown is not absent); this one answers
    None, because a router fact that cannot be read must say so."""
    ref = str(owner_ref or "").strip()
    base = str(backend_url or "").strip().rstrip("/")
    if not ref or not base:
        return None
    try:
        r = pb.get(f"{base}/api/collections/agents/records",
                   params={"filter": f'(paired=true) && owner_ref="{_escaped(ref)}"',
                           "sort": "-updated", "perPage": 1},
                   timeout=FACT_TIMEOUT)
        if not r.ok:
            return None
        items = r.json().get("items", [])
        if not items:
            return False
        seen = (items[0].get("last_seen") or items[0].get("updated") or "")
        t = datetime.fromisoformat(seen.replace(" ", "T").replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - t).total_seconds() < AGENT_FRESH_SECONDS
    except Exception:
        return None


def active_owner_ref(owner_ref: str = "") -> str:
    """The owner this process serves. From the caller when it has one, else
    the worker's own scope — ANTICIPY_OWNER_REF, or the ACTIVE_OWNER_REF
    global brain/worker.py resolves at startup, read off the already-loaded
    module rather than imported (worker imports the brain, never the other
    way). NEVER from params or any request body."""
    ref = str(owner_ref or "").strip()
    if ref:
        return ref
    ref = os.environ.get("ANTICIPY_OWNER_REF", "").strip()
    if ref:
        return ref
    worker = sys.modules.get("brain.worker")
    return str(getattr(worker, "ACTIVE_OWNER_REF", "") or "").strip()


def gather_context(params: Optional[dict] = None, owner_ref: str = "",
                   backend_url: str = "") -> HandContext:
    """The facts for one step. With no owner or no backend nothing is asked
    of the network and every fact is UNKNOWN."""
    p = params if isinstance(params, dict) else {}
    ref = active_owner_ref(owner_ref)
    base = str(backend_url or os.environ.get("ANTICIPY_PB") or "").strip()
    return HandContext(
        connections=read_connections(ref, base),
        browser_online=browser_is_online(ref, base),
        source=str(p.get("source") or ""),
        rung=NO_LEDGER_RUNG,
        backend_url=base,
    )
