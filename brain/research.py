"""The server-side research arm (roadmap §6).

Read-only goals never touch the owner's browser. The 2026-08-02 tab flood
happened because ALL work — even "look up opening hours" — ran through the
paired Chrome extension on his machine. Research belongs here, in the
worker: Brave Search for candidate pages, a plain fetch for the top few,
and the LLM to summarize with citations. The extension keeps only the jobs
that genuinely need HIS logged-in browser (bookings, forms, purchases),
always behind the confirmation gate.

No key, no drama: without BRAVE_API_KEY the caller routes the job to the
browser lane instead — this module never crashes the worker over a missing
secret, and never logs one either.
"""
from __future__ import annotations

import json
import re
import time
from html import unescape
from typing import Callable, Optional
from urllib.parse import urlsplit

import requests

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"

# Descriptions alone answer many questions; reading more than a few pages is
# latency without new evidence.
TOP_RESULTS = 5
PAGES_TO_READ = 3
PAGE_CHARS = 4000

RESEARCH_SYSTEM = """You are Anticipy's research arm, answering the owner's
question from web sources gathered for you. Use ONLY the numbered sources
given — never your own knowledge, and never invent an hour, a price, a date
or a name that a source does not state. Answer in 2-5 plain sentences,
specifics first, citing the source number in square brackets after each
claim, e.g. "Open until 5pm daily [2]." If the sources disagree, say which
says what. If they do not contain the answer, say plainly what you did and
did not find. No preamble, no headings — just the answer."""

# The search query is the goal minus its instruction verb — Brave does better
# with "opening hours of the Vancouver aquarium" than with "research: opening
# hours of the Vancouver aquarium".
_QUERY_PREFIX = re.compile(
    r"^\s*(research|look\s*up|find(?:\s+out)?|check|search(?:\s+for)?|"
    r"compare|price|tell\s+me(?:\s+about)?)\s*[:\-—]?\s+",
    re.IGNORECASE)


def query_from_goal(goal: str) -> str:
    g = (goal or "").strip()
    return _QUERY_PREFIX.sub("", g, count=1).strip() or g


class BraveClient:
    """Thin Brave Search wrapper — injectable so tests never hit the network."""

    def __init__(self, api_key: str):
        self._key = api_key

    def search(self, query: str, count: int = TOP_RESULTS) -> list[dict]:
        r = requests.get(
            BRAVE_URL,
            params={"q": query, "count": count},
            headers={"X-Subscription-Token": self._key,
                     "Accept": "application/json"},
            timeout=15,
        )
        r.raise_for_status()
        out = []
        for item in ((r.json().get("web") or {}).get("results") or [])[:count]:
            url = (item.get("url") or "").strip()
            if not url:
                continue
            # Brave decorates descriptions with <strong> markers.
            desc = unescape(re.sub(r"<[^>]+>", "", item.get("description") or ""))
            out.append({"title": (item.get("title") or "").strip(),
                        "url": url, "description": desc.strip()})
        return out

    def __repr__(self):  # the key must never ride into a log line via repr
        return "BraveClient(key=…)"


def fetch_page(url: str) -> str:
    """Visible text of one page, best effort. Empty string on any failure —
    a page that will not load is a missing source, not a crashed job."""
    try:
        r = requests.get(url, timeout=12, headers={
            "User-Agent": "Mozilla/5.0 (compatible; AnticipyResearch/1.0)"})
        if not r.ok or "html" not in (r.headers.get("content-type") or "html"):
            return ""
        html = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>",
                      " ", r.text)
        text = unescape(re.sub(r"(?s)<[^>]+>", " ", html))
        return re.sub(r"\s+", " ", text).strip()[:PAGE_CHARS]
    except Exception:
        return ""


def _summarize(query: str, sources: list[dict], llm=None) -> str:
    if llm is not None and getattr(llm, "live", False):
        try:
            res = llm.chat(RESEARCH_SYSTEM,
                           json.dumps({"question": query, "sources": [
                               {"n": s["n"], "title": s["title"],
                                "url": s["url"], "content": s["content"]}
                               for s in sources]}))
            text = (res.text or "").strip()
            if text:
                return text
        except Exception as e:
            print(f"research: summarize failed ({type(e).__name__}) — "
                  "falling back to the sources' own words")
    # No model (or a broken one): the honest fallback is the sources' own
    # words, attributed — never an invented sentence.
    parts = []
    for s in sources[:3]:
        snippet = (s.get("description") or s.get("content") or "")[:280].strip()
        if snippet:
            parts.append(f"{snippet} [{s['n']}]")
    return " ".join(parts) or f"Couldn't read anything useful about: {query}"


def run_research(goal: str, params: Optional[dict] = None, llm=None,
                 brave: Optional[BraveClient] = None,
                 fetcher: Callable[[str], str] = fetch_page,
                 api_key: Optional[str] = None) -> dict:
    """One research job, end to end: search -> read -> summarize with
    citations. Returns {"ok": bool, "result": str} and never raises — a
    crashed pass would leave the job stuck at `running` forever."""
    query = query_from_goal(goal)
    client = brave or (BraveClient(api_key) if api_key else None)
    if client is None:
        return {"ok": False, "result": "No search backend is configured."}
    try:
        results = client.search(query)
    except Exception as e:
        # Log the class only: exception text can quote the request, and
        # nothing from this call belongs in a log beyond "it failed".
        print(f"research: search failed ({type(e).__name__})")
        return {"ok": False, "result": f"Search failed for: {query}"}
    if not results:
        return {"ok": False, "result": f"Found nothing for: {query}"}
    sources = []
    for i, res in enumerate(results, 1):
        content = fetcher(res["url"]) if i <= PAGES_TO_READ else ""
        sources.append({"n": i, "title": res["title"], "url": res["url"],
                        "description": res["description"],
                        "content": content or res["description"]})
    summary = _summarize(query, sources, llm=llm)
    listed = "\n".join(f"[{s['n']}] {s['title']} — {s['url']}" for s in sources)
    return {"ok": True, "result": f"{summary}\n\nSources:\n{listed}"}


# ===========================================================================
# HANDS 1 — THE RESEARCH GATE, AND THE PROCEDURE STORE IT RECALLS FROM
#
# Spec: docs/superpowers/specs/2026-08-25-hands1-skills-reach.md §5, §8.
#
# The card asked for "any plan that will touch the world gets a research pass
# first, server-side, before the browser opens". Two things were wrong with how
# that was built, and only one of them is the gate.
#
# 1. RECALL AND SPEND WERE ONE CONDITION. In the extension, reading the cache
#    and paying for research both sat behind `plan.unfamiliar` — a planner
#    self-report produced by a prompt that argues against researching. Reading
#    a cache costs nothing, so putting it behind the most expensive judgement
#    in the file meant a cached procedure was silently discarded whenever the
#    second run's planner happened to feel familiar — which is more likely on
#    the second run than the first, because that is what having done a thing
#    once feels like. "Never pay for the same learning twice" failed in exactly
#    the case it exists for. Recall is now unconditional and keyed on shape.
#
# 2. THE GATE'S KEY DID NOT NEED INVENTING. "Is this goal unfamiliar" is a
#    question about MEANING, and HARNESS-LAWS law 1 says no pattern may answer
#    one — but neither may a fresh model self-report, which is the same design
#    wearing better prose. The key is `touches`: declared by the triage model
#    with full context, validated against a closed three-value set
#    (orchestrator.TOUCHES), and already the release condition for the
#    analogous question in is_consequential(). This gate keys on that and on
#    one fact — is there a live cached answer for this shape — and it is not
#    given the goal's words at all, so no later edit can quietly start reading
#    them.
#
# WHY AN UNDECLARED GOAL RESEARCHES. The hold gate defaults an undeclared goal
# to HELD, because the cost of guessing wrong there is something leaving the
# owner's world. Here the polarity is the opposite: researching unnecessarily
# costs money and latency, while NOT researching costs a run that spends
# eighteen steps on a marketing page and parks (learn.js:5-9 records that
# failure, live). So undeclared researches — and that is the specific reason
# this gate never has to consult `_READ_ONLY_RE` and never inherits its tape
# (HARNESS-LAWS.md:126, `[tape:read_only_re]`).
# ===========================================================================

from typing import NamedTuple

from .orchestrator import TOUCHES

# The channels that leave no mark on the world. Derived from the closed set
# the triage model is validated against rather than typed out again — one
# list, one meaning, and a fourth channel cannot appear in one file and not
# the other.
_LEAVES_NO_MARK = tuple(t for t in TOUCHES if t != "world")

# The four things the gate can say. Distinct strings on purpose: "we had the
# knowledge" and "we gave up looking for it" must never be recorded as one
# outcome, because the second is the one worth counting.
GATE_SATISFIED = "satisfied"        # a live cached procedure — free, no model
GATE_NOT_REQUIRED = "not_required"  # touches read/compute: nothing to gate
GATE_RESEARCH = "research"          # world, or undeclared: look first
GATE_OPEN = "open"                  # the gate itself cannot run — let it through


class GateVerdict(NamedTuple):
    """The verdict and the line that explains it in the run's trace. §5.5 asks
    for the reason specifically: a gate that opened because it was broken must
    be visible afterwards, or a lane that is quietly down reads as a lane that
    quietly decided nothing needed looking up."""
    verdict: str
    why: str


def gate_holds_the_browser(verdict: str) -> bool:
    """The one property callers depend on, written once. A world-touching job
    must not be claimable by a browser until a research answer is attached or
    the pass has honestly returned nothing — and every other verdict, including
    the broken one, lets the errand proceed."""
    return verdict == GATE_RESEARCH


def research_gate(touches, procedure=None, gate_can_run: bool = True) -> GateVerdict:
    """Does this job need a research pass before a browser may claim it?

    THERE IS NO PARAMETER FOR THE GOAL, AND THAT IS THE POINT. You cannot
    pattern-match on prose you were never handed. The inputs are an effect
    channel the model declared and a cache lookup's result — two facts, no
    opinions, checkable from either side of the wire.

    `procedure` is the recalled record or None. Only its SHAPE is read (is
    there a stamp, are there steps); never a word of it, because everything
    inside it is distilled from the open web and a page that could talk its
    way past this check would have found a way to skip being read.
    """
    # A cached answer needs no lane, so this outranks even a dead gate.
    if procedure_is_live(procedure):
        return GateVerdict(GATE_SATISFIED,
                           "already know how — a live procedure for this shape")
    # A read IS the research lane's own job; routing it there is what job_lane
    # already does. There is nothing to gate in front of it.
    if isinstance(touches, str) and touches in _LEAVES_NO_MARK:
        return GateVerdict(GATE_NOT_REQUIRED,
                           f"touches={touches} — nothing leaves his world")
    # A gate that cannot run must OPEN, not hold, and say so. The precedent is
    # the existing keyless fallback in run_research_jobs, which hands a job
    # back to the browser lane rather than letting it sit forever.
    if not gate_can_run:
        return GateVerdict(GATE_OPEN,
                           "research lane unavailable — letting the browser "
                           "through unresearched rather than parking the errand")
    if touches == "world":
        return GateVerdict(GATE_RESEARCH, "touches=world — look it up first")
    # Anything that is not one of the three declared channels is NO
    # DECLARATION, exactly as orchestrator.py:549-550 treats it. A second
    # reader of that field must not be more credulous than the first.
    return GateVerdict(GATE_RESEARCH,
                       "no effect channel declared — look it up first")


# ---------------------------------------------------------------------------
# The procedure store, server-side
#
# §4.2: PROCEDURES TRAVEL, RECIPES STAY. The shape of a task travels; the route
# through a page does not. A procedure is the distilled output of reading the
# public web — it holds no owner value by construction, `needs` names a
# CATEGORY ("an account number") and never a value — so LOCAL-FIRST's own
# scoreboard already blesses it in the cloud. A recipe is slot indexes and
# control labels against one logged-in session on one machine: the server
# cannot execute one, and a server-side copy would be a standing index of which
# sites the owner operates and how his account pages are laid out. That one
# stays in chrome.storage.local and this module has no opinion about it.
#
# §4.3: OWNER-SCOPED FIRST, shared later or never. The scoping is whichever
# store the caller injects, so sharing is a decision someone has to make out
# loud — with an argument about what changed — rather than something that
# happens because a default was convenient.
# ---------------------------------------------------------------------------

PROCEDURE_KEY = "procedures"
# A month: long enough to compound across the errands that repeat, short enough
# that a moved help centre does not become permanent folklore. Same number as
# learn.js PROCEDURE_TTL_MS, for the same reason.
PROCEDURE_TTL_MS = 30 * 24 * 60 * 60 * 1000
MAX_PROCEDURES = 60
MAX_PROCEDURE_STEPS = 8

# The whole record, declared. Nothing else survives a write.
PROCEDURE_FIELDS = ("startUrl", "needs", "steps", "caveats", "sources",
                    "learnedAt", "question")


def _now_ms() -> int:
    return int(time.time() * 1000)


def procedure_is_live(procedure, now_ms: Optional[int] = None) -> bool:
    """Structure only: a stamp inside the TTL and at least one step.

    An empty steps list is the honest blank learn.js's prompt asks for when the
    pages did not actually say how. It is deliberately not cached and
    deliberately not counted as an answer — a hollow record that satisfied this
    check would stop its shape ever being researched again.
    """
    if not isinstance(procedure, dict):
        return False
    steps = procedure.get("steps")
    if not isinstance(steps, list) or not steps:
        return False
    stamp = procedure.get("learnedAt")
    if not isinstance(stamp, (int, float)) or isinstance(stamp, bool):
        return False
    return (now_ms if now_ms is not None else _now_ms()) - stamp <= PROCEDURE_TTL_MS


def recall_procedure(shape: str, store, now_ms: Optional[int] = None):
    """The free half. No model, no network, no judgement — a dict lookup on a
    shape key. A cache that cannot be read is a miss and never an exception:
    breaking an errand over a storage failure is worse than paying for the
    research again."""
    if not shape or store is None:
        return None
    try:
        all_of_them = store.get(PROCEDURE_KEY) or {}
        hit = all_of_them.get(shape)
    except Exception:
        return None
    return hit if procedure_is_live(hit, now_ms) else None


def _trim(values, count: int, chars: int) -> list:
    if not isinstance(values, list):
        return []
    return [str(v)[:chars] for v in values[:count]]


def remember_procedure(shape: str, procedure: dict, store,
                       limit: int = MAX_PROCEDURES) -> None:
    """The write door, and it is a door rather than a passthrough.

    A procedure reaching the server was authored by the extension, out of text
    authored by the open web. guard.pb.js's whole doctrine is that
    client-authored values trusted as proof about the world is the shape of
    every hole that file has closed — so this is recipes.js rule 3's discipline
    applied to the uplink: every field is copied by name, there is no spread,
    and anything the writer did not declare (an injected `approved`, an owner
    value, a second start URL) does not survive the write.
    """
    if not shape or store is None or not isinstance(procedure, dict):
        return
    steps = _trim(procedure.get("steps"), MAX_PROCEDURE_STEPS, 240)
    # An honest blank is refused at the WRITE door too, not only the read one:
    # a blank that got stored would still occupy one of the bounded slots and
    # evict something real.
    if not steps:
        return
    stamp = procedure.get("learnedAt")
    record = {
        # RE-CHECKED, NOT TRUSTED. learn.js validated this before caching it
        # locally; a record arriving here rode an uplink whose payload the
        # extension authored out of web page text, and "the portal is at
        # http://127.0.0.1:8090/admin" is a sentence any page can contain. A
        # bad address costs the field and nothing else — steps that may be
        # perfectly good are not thrown away over where somebody said to start.
        "startUrl": str(procedure["startUrl"])[:500]
                    if is_researchable(procedure.get("startUrl")) else None,
        "needs": _trim(procedure.get("needs"), 5, 160),
        "steps": steps,
        "caveats": _trim(procedure.get("caveats"), 3, 160),
        "sources": _trim(procedure.get("sources"), 5, 500),
        "learnedAt": int(stamp) if isinstance(stamp, (int, float))
                     and not isinstance(stamp, bool) else _now_ms(),
        "question": str(procedure.get("question") or "")[:200],
    }
    try:
        all_of_them = dict(store.get(PROCEDURE_KEY) or {})
        all_of_them[shape] = record
        # Bounded, oldest first. Nothing here is precious enough to be worth an
        # unbounded table on a volume that has filled once and taken production
        # down, and every stored byte is charged roughly eight times by the
        # backup rotation.
        if len(all_of_them) > limit:
            ordered = sorted(all_of_them,
                             key=lambda k: all_of_them[k].get("learnedAt") or 0)
            for key in ordered[:len(all_of_them) - limit]:
                del all_of_them[key]
        store.set(PROCEDURE_KEY, all_of_them)
    except Exception:
        # A cache that cannot write must not break a run.
        pass


# ---------------------------------------------------------------------------
# The cache key, and where research may go: a PORT of learn.js, not a variant
#
# `recipes.js` imports taskShape from learn.js rather than copying it, on
# purpose, so the two browser caches can never key differently (recipes.js:53).
# The server is a third reader of that key and cannot import a JS module, so
# what follows is a port — and a port is precisely the second copy that import
# was avoiding. It is only honest because tests/test_research_shape_parity.py
# runs the real extension/learn.js under node over a shared corpus and compares
# it character by character, including the two word lists. Drift fails there
# rather than showing up months later as a cache that silently forked and paid
# for the same research twice.
#
# NOT A LAW-1 PROBLEM, and worth saying why: this decides nothing about what
# the owner MEANT and nothing about what happens to his errand. It is a
# normalising cache key — a hash with the instance filed off — and a wrong
# answer costs one extra lookup, never an action. The gate above is the thing
# that decides, and it never sees a word of the goal.
# ---------------------------------------------------------------------------

_STOP = {
    "the", "and", "for", "with", "from", "that", "this", "was", "are", "please",
    "can", "you", "get", "got", "would", "could", "should", "into", "about",
    "have", "has", "had", "our", "out", "off", "his", "her", "their", "them",
    "они", "next", "then", "than", "over", "under", "some", "any", "all",
}

# Words that name WHICH ONE, never WHAT KIND — stripped for the same reason
# digits are, so "the March bill" and "the April bill" are one procedure.
_INSTANCE_WORDS = {
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct",
    "nov", "dec",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
    "sunday",
    "mon", "tue", "tues", "wed", "thu", "thurs", "fri", "sat", "sun",
    "today", "tomorrow", "yesterday", "tonight", "morning", "afternoon",
    "evening",
    "week", "month", "year", "last", "this", "coming",
}

# The possessive goes with its apostrophe, not without it: stripping the
# apostrophe alone glues the s on and produces "tuesdays", which is not the
# weekday the instance list knows about — so "Tuesday's appointment" and
# "Thursday's appointment" forked the cache after all.
_POSSESSIVE = re.compile(r"[‘’']s\b")
_APOSTROPHE = re.compile(r"[‘’']")
_NOT_A_TOKEN = re.compile(r"[^a-z0-9]+")


def task_shape(goal) -> str:
    """The shape of a task, for caching. NOT its wording."""
    text = (str(goal) if goal else "").lower()
    text = _APOSTROPHE.sub("", _POSSESSIVE.sub("", text))
    words = [w for w in _NOT_A_TOKEN.sub(" ", text).split(" ") if w]
    words = [w for w in words
             if not w.isdigit() and len(w) > 2
             and w not in _STOP and w not in _INSTANCE_WORDS]
    # Sorted and de-duplicated so word order cannot fork the cache.
    return "-".join(sorted(set(words)))[:120]


_NEVER_RESEARCH = re.compile(
    r"(^|\.)(chase|bankofamerica|wellsfargo|citi(bank)?|rbc|td(bank|canadatrust)?"
    r"|scotiabank|bmo|cibc|tangerine|schwab|fidelity|vanguard|etrade|robinhood"
    r"|coinbase|binance|kraken|paypal|venmo|wise|revolut)\.", re.IGNORECASE)

_PRIVATE_HOST = re.compile(
    r"^127\.|^10\.|^192\.168\.|^169\.254\.|^0\.|^172\.(1[6-9]|2\d|3[01])\.|^\[?::1\]?$")

# What a hostname may be made of once it is parsed. Python's urlsplit is far
# more forgiving than the URL constructor learn.js relies on — it will hand
# back "foo bar" as a hostname — so anything outside this set is treated as the
# parse failure it would have been in the browser.
_HOST_CHARS = re.compile(r"^[a-z0-9._\-:\[\]]+$")


def is_researchable(url) -> bool:
    """May the research arm read this page? A port of learn.js isResearchable,
    kept in parity by tests/test_research_shape_parity.py.

    Two refusals, and both are about where research runs rather than what it
    is looking for. A place that holds money may not even be READ, because
    research happens with less supervision than an errand. And the owner's own
    machine is not the open web: everything here is derived from page text, so
    "go and read http://127.0.0.1:8090/admin" is a sentence any web page can
    contain, and research runs BEFORE the loop's loopback guard exists.
    """
    try:
        parts = urlsplit(str(url))
    except Exception:
        return False
    if parts.scheme not in ("http", "https"):
        return False
    try:
        host = (parts.hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    # The URL constructor punycodes an international hostname; urlsplit does
    # not. Do it here or "réserver.fr" is refused on this side alone.
    if not host.isascii():
        try:
            host = host.encode("idna").decode("ascii").lower()
        except Exception:
            return False
    if not _HOST_CHARS.match(host):
        return False
    if _NEVER_RESEARCH.search(host):
        return False
    if (host in ("localhost", "::1") or host.endswith(".localhost")
            or host.endswith(".local") or host.endswith(".internal")):
        return False
    return not _PRIVATE_HOST.match(host)
