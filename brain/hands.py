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

WHAT IS NOT HERE, AND WHY. The api hand has no executor yet — the vendor
adapter (migration/workers/src/connections/provider.ts) can connect an app and
cannot execute a tool — and a fresh lane string would be claimed by every
shipped extension whose filter reads `lane!="research"`. So an `api` verdict
maps to the browser lane for now, with the verdict carried on the row so the
executor, when it exists, can find the steps the router licensed. That mapping
is pinned in a test with its reason, so it is a decision somebody made and not
a default nobody can see.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
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
# module must never import anticipy_core — that file imports this one).
#
# api -> "" is deliberate and temporary, see the module docstring: no
# executor, and a new lane string is claimable by every extension in the
# wild. The verdict still rides on the row.
LANE_BROWSER = ""
LANE_RESEARCH = "research"
# THE POLARITY OF "NO VERDICT" IS RESEARCH, and it was nearly flipped. On
# 2026-09-06 the parent moved hold/unasked/unanswered to "" (the browser lane),
# arguing "" is the HELD lane where a card appears. The verifier then showed
# the hole: "" is only held when is_consequential says so, and for a read-only
# goal it says no -- so an unreadable reply on "look up the ferry schedule"
# would have RUN in the owner's own browser with no verdict and no card.
# Research cannot change the world. A verdict nobody gave licenses nothing.
LANE_FOR = {
    HAND_BROWSER: LANE_BROWSER,
    HAND_API: LANE_BROWSER,
    HAND_RESEARCH: LANE_RESEARCH,
    HAND_HOLD: LANE_RESEARCH,
    HAND_UNASKED: LANE_RESEARCH,
    HAND_UNANSWERED: LANE_RESEARCH,
}


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
class HandContext:
    """What the model is told besides the step. None means UNKNOWN — the fact
    could not be read — and the prompt says so in those words."""
    connections: Optional[tuple] = None
    browser_online: Optional[bool] = None
    source: str = ""
    rung: int = NO_LEDGER_RUNG

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

    @property
    def decided(self) -> bool:
        return self.hand in VERDICTS

    def as_note(self) -> dict:
        return {"hand": self.hand, "reason": self.reason, "app": self.app,
                "effect": self.effect, "asked": self.asked}


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
            print(f"hands: {verdict.hand} ({verdict.effect or '?'}"
                  f"{', ' + verdict.app if verdict.app else ''}) — "
                  f"{verdict.reason[:120]}")
            return verdict
        print(f"hands: unreadable reply to the hand question "
              f"(attempt {attempt + 1}) -> {raw!r}")
    return HandVerdict(HAND_UNANSWERED, "unreadable reply, twice",
                       asked=asked)


def lane_for(verdict: HandVerdict) -> str:
    """The lane a verdict lands on. Anything that is not one of the six
    known states is treated as no verdict, which is the research lane."""
    return LANE_FOR.get(getattr(verdict, "hand", None), LANE_RESEARCH)


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
    )
