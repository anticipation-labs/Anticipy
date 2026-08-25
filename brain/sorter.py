"""SORTER — judge closed conversations, not lines.

Spec: docs/superpowers/specs/2026-08-25-sorter-conversation-granularity.md

The unit of judgment in this file is a CLOSED CONVERSATION. Everything here is
either pure arithmetic over capture time (Tier 0 — decides *when* to call, and
never what a word means) or the one strong call itself. Nothing in between: the
spec refuses a cheap filter in front of the judge, because three commits have
already shipped one that excluded the exact case the feature existed for, and a
filter's false negative is a lost errand with nothing in the record saying so.

HARNESS-LAWS Law 1, read against this file:

  * `closable`, `late_disposition`, `render_payload`, `parse_verdict` and the
    flush counters read clocks, ordinals and word COUNTS. None of them reads a
    word for its sense.
  * `unevidenced_tokens` is a PROVENANCE check — does this goal spend
    vocabulary its own evidence never held — and it is the surviving half of
    `shard_too_thin` (§7). It sits in the same declared-backstop category as
    the digit guard and `unsupported_names`. It is not allowed to decide what
    anything MEANS, and it never sees a line the model has not already judged.
  * the judging question is asked ON ITS OWN, gets a four-state answer, and
    points like a FLOOR: with no verdict, nothing acts and nothing is stamped.

THE RULE THIS FILE INHERITS FROM segmenter.py: every boundary decision keys off
CAPTURE time. Arrival time appears here exactly once, as `SETTLE_S`, and it
answers a different question — has the transport finished delivering.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Optional

from .segmenter import (CONTINUE_S, LATE_MAX_S, MAX_SEGMENT_S, capture_span,
                        is_late, parse_ts)

# --- parameters -----------------------------------------------------------
# SETTLE_S is a TRANSPORT parameter, not a boundary one. It asks "has the
# offline queue finished handing us what he already said", and it is derived
# from the phone's own flush behaviour: AnticipyBackend posts a batch and
# retries, so a segment whose last row landed within one flush interval may
# still be growing. It is deliberately far below CONTINUE_S — waiting on
# transport must never be the thing that decides a conversation is over.
SETTLE_S = 20.0

# A late thought inserted into a closed segment re-opens the judgement ONCE,
# after this much quiet from further inserts. Longer than SETTLE_S because a
# backfill is a lump, not a trickle.
BACKFILL_SETTLE_S = 60.0

# The mid-conversation flush trigger, counted in WORDS and never in seconds
# (§9): a 90-second flush re-sends a growing transcript 22 times on the one
# real conversation on file, for 5.8x the close-only cost. 400 words is about
# three minutes of continuous speech and produces three flushes on that same
# conversation. Counting words is not reading them.
FLUSH_WORDS = 400

# --- the four-state answer ------------------------------------------------
# "no" and "nobody answered" are different things and a bool can only carry
# two of them (HARNESS-LAWS Law 1, the shape of the four worked examples).
JUDGED = "judged"
UNASKED = "unasked"          # no model to ask
UNANSWERED = "unanswered"    # asked, and nothing readable came back

DECISIONS = ("ignore", "ask", "act", "answer")
MAX_ITEMS = 4


def _arrival(segment: dict) -> Optional[datetime]:
    """When did the last row for this conversation LAND. PocketBase stamps
    `updated` on every append, which is exactly the fact we want; the explicit
    column is read first so a caller can carry the value itself."""
    for key in ("last_arrival_at", "updated", "created"):
        got = parse_ts((segment or {}).get(key))
        if got is not None:
            return got
    return None


def closable(segment: dict, now: datetime,
             session_ended: bool = False) -> tuple[bool, str]:
    """Is this conversation over? TWO keys, and either one alone is a
    recorded bug.

    CAPTURE quiet asks *did the person stop talking* — the only question that
    has ever been allowed to move a boundary. ARRIVAL quiet asks *has the
    transport finished delivering what they said*, which is a fact about BLE
    and an offline queue and not about words at all.

    Closing on capture time alone means a three-minute pendant backlog lands
    into a conversation we have already judged. Closing on arrival time alone
    is Omi #6551 reproduced in our own code — the bug segmenter.py's module
    docstring calls the rule that must never be broken.

    `session_ended` — the phone reporting that listening stopped — is evidence
    of quiet arriving EARLY, never evidence a conversation continues. It
    substitutes for the capture leg and for nothing else; the queue still has
    to drain.
    """
    spoke = parse_ts((segment or {}).get("last_speech_at"))
    if spoke is None:
        return False, "no speech recorded yet"

    started = parse_ts((segment or {}).get("started_at"))
    if started and (now - started).total_seconds() >= MAX_SEGMENT_S:
        # A storage bound, not a human boundary: the successor carries
        # parent_segment, so speech still arriving is threaded, not lost.
        return True, (f"ran {MAX_SEGMENT_S}s — force-closing, will relink "
                      f"onto a successor")

    capture_quiet = (now - spoke).total_seconds()
    if not session_ended and capture_quiet < CONTINUE_S:
        return False, (f"he spoke {capture_quiet:.0f}s ago, under "
                       f"{CONTINUE_S:.0f}s — still the same breath")

    landed = _arrival(segment)
    arrival_quiet = (now - landed).total_seconds() if landed else None
    if arrival_quiet is None:
        return False, "nothing says when the last row arrived"
    if arrival_quiet < SETTLE_S:
        return False, (f"a row arrived {arrival_quiet:.0f}s ago, under "
                       f"{SETTLE_S:.0f}s — the queue is still draining")

    if session_ended:
        return True, (f"the phone says listening stopped; nothing has arrived "
                      f"for {arrival_quiet:.0f}s")
    return True, (f"quiet for {capture_quiet:.0f}s and nothing arriving for "
                  f"{arrival_quiet:.0f}s")


# --- §3 what happens to a thought that arrives after the close ------------
# Enumerated by CAPTURE time, with NO DEFAULT BRANCH. This is where "can't
# miss" breaks, so every path is named and every path says why.
LATE_INSERT = "insert"                # backfill into the closed segment
LATE_MEMORY_ONLY = "memory_only"      # ingested, never judged
LATE_NEW_THREAD = "new_thread"        # a successor carrying parent_segment
LATE_UNPLACEABLE = "unplaceable"      # no readable capture time
LATE_DISPOSITIONS = (LATE_INSERT, LATE_MEMORY_ONLY, LATE_NEW_THREAD,
                     LATE_UNPLACEABLE)


def late_disposition(event: dict, segment: dict,
                     now: datetime) -> tuple[str, str]:
    """Where does a turn go when the conversation nearest it is already
    closed? Returns (disposition, why) and the why is never empty — a turn
    that is not judged has to leave a record saying so, or it is a silence,
    and silences are what this product is measured on.

    `segment` is the CLOSED segment nearest this turn in capture time; the
    caller picks it, exactly as `place_turn` already picks one.

    AGE IS CHECKED BEFORE PLACEMENT, deliberately. A seven-hour-old turn that
    lands squarely inside a seven-hour-old conversation is still too old to
    act on; checking placement first would insert it and re-judge the whole
    segment around intent nobody is carrying any more.
    """
    start, end = capture_span(event or {})
    if start is None:
        return LATE_UNPLACEABLE, ("no readable capture time — the turn cannot "
                                  "be put in time and will not be guessed at")
    if is_late(event, now):
        return LATE_MEMORY_ONLY, (
            f"spoken more than {LATE_MAX_S // 3600}h ago — remembered, never "
            f"acted on")

    opened = parse_ts((segment or {}).get("started_at"))
    ended = (parse_ts((segment or {}).get("ended_at"))
             or parse_ts((segment or {}).get("last_speech_at")))
    if opened is None or ended is None:
        return LATE_NEW_THREAD, "no closed conversation to fall inside"

    # "Inside or adjacent" — within one CONTINUE_S of either edge is the same
    # breath by every other rule in this file, and a backfilled row must not
    # be exiled from its own conversation by a second's difference.
    if (opened - (end or start)).total_seconds() <= CONTINUE_S \
            and (start - ended).total_seconds() <= CONTINUE_S:
        return LATE_INSERT, ("falls inside a closed conversation — inserted, "
                             "marked dirty, re-judged once")
    return LATE_NEW_THREAD, ("spoken outside that conversation — a successor "
                             "carries the thread forward instead")


def backfill_ready(segment: dict, now: datetime) -> tuple[bool, str]:
    """A segment dirtied by a backfill is re-judged ONCE, after the inserts
    stop. Twice is a loop, and `supersedes` is the record that it happened."""
    if not (segment or {}).get("dirty"):
        return False, "nothing was backfilled into it"
    if (segment or {}).get("supersedes"):
        return False, "already re-judged once, and once is the whole rule"
    landed = _arrival(segment)
    if landed is None:
        return False, "nothing says when the last insert arrived"
    quiet = (now - landed).total_seconds()
    if quiet < BACKFILL_SETTLE_S:
        return False, (f"an insert arrived {quiet:.0f}s ago, under "
                       f"{BACKFILL_SETTLE_S:.0f}s — the backfill is still landing")
    return True, f"backfill settled {quiet:.0f}s ago"


# The ONLY state a re-judgement may revise. Anything released, running, done
# or already texted about is never retracted — a second opinion may change its
# mind, it may not change the world back.
REVISABLE = ("awaiting_confirm",)


def may_revise(row: dict) -> bool:
    return (row or {}).get("status") in REVISABLE


# --- §4 what the one strong call sees -------------------------------------
# The whole closed segment, rendered as TURNS. Today the conversation reaches
# the model as `" | ".join(convo[-16:])` inside a parenthesis (anticipy_core
# :2574) — no timestamps, no gap markers, no turn boundaries, no voice
# verdicts. A model cannot tell a two-second gap from a four-minute one, or
# three speakers from one, and then gets told to judge only the current line.

NO_VERDICT = "no verdict"
UNKNOWN_SOURCE = "unknown"


def _clock(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%H:%M:%S")


def render_payload(turns: list[dict], triaged_through_seq: int = 0,
                   roster: Optional[list] = None,
                   parent: Optional[dict] = None,
                   facts: Optional[list] = None,
                   posture: str = "",
                   held: Optional[list] = None) -> dict:
    """One closed conversation, as structure rather than as a sentence.

    Ordering is by CAPTURE time and by nothing else. Turns with no readable
    capture time are left OUT and named in `unplaceable` — an unplaceable turn
    that is silently dropped is the same shape as a finding marked delivered
    and never sent.

    Nothing here reads a word for its sense. The voice verdict is the PHONE's,
    carried as evidence and never inferred from wording; the capture source
    decides nothing and exists to be compared; an absent value for either says
    so in words rather than arriving as a blank that reads like a measured
    result.
    """
    placed: list[tuple[datetime, datetime, dict]] = []
    unplaceable: list[str] = []
    for row in turns or []:
        if not isinstance(row, dict):
            continue
        start, end = capture_span(row)
        if start is None:
            unplaceable.append(str(row.get("id") or ""))
            continue
        placed.append((start, end or start, row))
    placed.sort(key=lambda p: (p[0], p[1], str(p[2].get("id") or "")))

    rendered: list[dict] = []
    prev_end: Optional[datetime] = None
    for i, (start, end, row) in enumerate(placed):
        seq = row.get("seq")
        ordinal = int(seq) if isinstance(seq, int) else i + 1
        rendered.append({
            "ordinal": ordinal,
            "at": _clock(start),
            "gap_s": (None if prev_end is None
                      else int(round((start - prev_end).total_seconds()))),
            "voice": str(row.get("speaker") or "").strip() or NO_VERDICT,
            "source": str(row.get("source") or "").strip() or UNKNOWN_SOURCE,
            "text": row.get("text") or "",
            "new": ordinal > int(triaged_through_seq or 0),
            "id": str(row.get("id") or ""),
        })
        prev_end = end

    # Which voices actually appear, as evidence beside the roster's own
    # vocabulary. Never a claim about who is in the room.
    voices = sorted({r["voice"] for r in rendered if r["voice"] != NO_VERDICT})

    memory = ""
    if facts:
        from .anticipy_core import memory_notes   # lazy: core is heavy
        memory = memory_notes(facts)

    payload = {
        "turns": rendered,
        "ordinals": [r["ordinal"] for r in rendered],
        "new_ordinals": [r["ordinal"] for r in rendered if r["new"]],
        "unplaceable": unplaceable,
        "voices": voices,
        "roster": list(roster or []),
        "parent": parent or None,
        "memory": memory,
        "posture": posture or "",
        "held": list(held or []),
        "words": sum(len((r["text"] or "").split()) for r in rendered),
    }
    payload["text"] = _payload_text(payload)
    return payload


def _payload_text(p: dict) -> str:
    out: list[str] = []
    if p["roster"] or p["voices"]:
        out.append("PARTICIPANTS (evidence, not a claim about who is present)")
        if p["roster"]:
            out.append(f"  people he knows: {', '.join(map(str, p['roster']))}")
        out.append("  voices the phone tagged in this conversation: "
                   + (", ".join(p["voices"]) if p["voices"]
                      else "none — every turn arrived with no verdict"))
    if p["parent"]:
        par = p["parent"]
        out.append("EARLIER THREAD this conversation carries on from")
        if par.get("summary"):
            out.append(f"  {par['summary']}")
        try:
            ents = json.loads(par.get("entities") or "[]")
        except Exception:
            ents = []
        if ents:
            out.append(f"  names in it: {', '.join(map(str, ents))}")
        if par.get("open_question"):
            out.append(f"  we asked and he has not answered: "
                       f"{par['open_question']}")
    if p["memory"]:
        out.append("WHAT SHE REMEMBERS (not approved values)")
        out.append(f"  {p['memory']}")
    if p["posture"]:
        out.append(f"POSTURE right now: {p['posture']}")
    if p["held"]:
        out.append("AWAITING HIS ANSWER — a yes in this conversation lands on "
                   "one of these, or on nothing")
        for h in p["held"]:
            out.append(f"  - {h.get('goal') or ''}"
                       + (f"  (we asked: {h['question']})"
                          if h.get("question") else ""))
    if p["unplaceable"]:
        out.append(f"NOT SHOWN: {len(p['unplaceable'])} turn(s) had no "
                   f"readable capture time and could not be placed in order")
    out.append("THE CONVERSATION")
    for r in p["turns"]:
        gap = "" if r["gap_s"] is None else f" [gap: {r['gap_s']}s]"
        new = " [NEW]" if r["new"] else ""
        out.append(f"  #{r['ordinal']} [{r['at']}]{gap} "
                   f"[voice: {r['voice']}] [source: {r['source']}]{new} "
                   f"{r['text']}")
    return "\n".join(out)


def needs_flush(words: int) -> bool:
    """Mid-conversation flush, counted in WORDS (§9). Counting words is not
    reading them: this decides WHEN to call the judge, never what anything
    means, and being wrong costs one extra call."""
    return int(words or 0) >= FLUSH_WORDS


# --- §4 what it returns ---------------------------------------------------
# Two output rules that are STRUCTURAL, not stylistic:
#   1. every item names its evidence turns by ordinal, and every ordinal must
#      be a turn in this payload. An out-of-range ordinal is discarded — the
#      same discipline the numbered link question already uses, so a
#      hallucinated answer lands out of range and is DROPPABLE rather than
#      followable.
#   2. every [NEW] turn is accounted for. A turn named by no item is stamped
#      ignore explicitly, with a reason. Nothing is left in "Thinking…"
#      forever and nothing is silently unjudged.

UNACCOUNTED_REASON = ("judged with its conversation and carried no thought of "
                      "its own")


def _blank(state: str, why: str) -> dict:
    """A verdict that does not exist. It accounts for NOTHING — no items, no
    stamps, no cursor.

    THE NAMED KILLER (§3): a sweep that stamps never-judged turns "ignore
    (judged with its conversation)" is a FALSE DELIVERY CLAIM, the same shape
    as findings marked delivered and never sent. The turns stay claimed with
    `mark_processed(ev, "processing")` — the exact stamp
    `release_stranded_claims` already sweeps — so a dead worker's segment
    members come back on their own. The cursor advances only on a verdict.
    """
    return {"state": state, "why": why, "summary": "", "entities": [],
            "splits_after": [], "items": [], "dropped": [],
            "unaccounted": [], "unaccounted_reason": "",
            "advance_cursor": False}


def _side_of(ordinal: int, splits: list[int]) -> int:
    return sum(1 for s in splits if ordinal > s)


def parse_verdict(raw, payload: dict) -> dict:
    """Read one judging reply against the payload it was asked about.

    Everything the model could not have meant is dropped rather than repaired,
    and every drop says why. Nothing here interprets the model's WORDS — it
    checks that the ordinals it named are turns that exist, that the decision
    it used is one of the four the schema has, and that an item does not claim
    evidence from both sides of a boundary the model itself reported.
    """
    if isinstance(raw, (str, bytes)):
        try:
            raw = json.loads(raw)
        except Exception:
            return _blank(UNANSWERED, "the reply was not readable JSON")
    if not isinstance(raw, dict):
        return _blank(UNANSWERED, f"the reply was a {type(raw).__name__}")
    if not isinstance(raw.get("items"), list):
        # A live model that replied without the key did not say "nothing
        # here" — it said nothing this code can read, and the two are
        # different things (party_verdict's wall, same reason).
        return _blank(UNANSWERED, "the reply carried no items list")

    known = set(payload.get("ordinals") or [])
    dropped: list[tuple[str, str]] = []

    splits = []
    for s in raw.get("splits_after") or []:
        if isinstance(s, int) and s in known:
            splits.append(s)
        else:
            dropped.append((f"split after {s!r}", "not a turn in this payload"))
    splits.sort()

    items: list[dict] = []
    for entry in raw["items"]:
        if not isinstance(entry, dict):
            dropped.append((repr(entry), "not an object"))
            continue
        decision = entry.get("decision")
        if decision not in DECISIONS:
            dropped.append((repr(decision),
                            f"not one of {'/'.join(DECISIONS)}"))
            continue
        evidence = [e for e in (entry.get("evidence") or [])
                    if isinstance(e, int) and e in known]
        if not evidence:
            dropped.append((str(entry.get("goal") or decision),
                            "named no evidence turn that exists in this payload"))
            continue
        if len({_side_of(e, splits) for e in evidence}) > 1:
            dropped.append((str(entry.get("goal") or decision),
                            "its evidence straddles a split the model itself read"))
            continue
        if len(items) >= MAX_ITEMS:
            dropped.append((str(entry.get("goal") or decision),
                            f"more than {MAX_ITEMS} items in one conversation"))
            continue
        kept = dict(entry)
        kept["evidence"] = sorted(evidence)
        items.append(kept)

    named = {e for i in items for e in i["evidence"]}
    unaccounted = [o for o in (payload.get("new_ordinals") or [])
                   if o not in named]
    entities = [str(e) for e in (raw.get("entities") or [])
                if isinstance(e, (str, int, float))]
    return {"state": JUDGED, "why": "", "summary": str(raw.get("summary") or ""),
            "entities": entities, "splits_after": splits, "items": items,
            "dropped": dropped, "unaccounted": unaccounted,
            "unaccounted_reason": UNACCOUNTED_REASON if unaccounted else "",
            "advance_cursor": True}


# --- §7 the shard floor's surviving half ----------------------------------
# `shard_too_thin` is NOT a brevity rule and reading it as one is why it looks
# harder to remove than it is. Its own docstring: "A thin line may act on its
# own words; it may not act on words the model added." The provenance half is
# the protection; the word count in front of it is the tape.
#
# What changes here: the word count is gone, so invention is caught at EVERY
# length; and "the evidence" is the ITEM'S OWN evidence turns, not the whole
# conversation. That second half is load-bearing — the whole conversation as
# allowed vocabulary resurrects the recorded invented-number failure, where
# "At 5:15" spoken by the other party becomes a legal digit in a text about a
# different dinner.
#
# LAW 1, honestly: this is a token-provenance backstop in the same declared
# category as the digit guard and `unsupported_names` (HARNESS-LAWS, "Not
# tape, but adjacent"). It runs AFTER the model, on a goal the model wrote,
# and it never decides what a human's words mean — only whether a generated
# goal spent vocabulary its own cited evidence never held. NOVEL_TOLERANCE is
# inherited verbatim from the predicate it replaces; a goal legitimately
# rewords what it heard, and the recorded failure invented six.
NOVEL_TOLERANCE = 2


def unevidenced_tokens(goal: str, evidence_texts: list[str]) -> set:
    from .anticipy_core import goal_tokens   # lazy: core is heavy
    heard = " ".join(x for x in (evidence_texts or []) if x)
    return goal_tokens(goal or "") - goal_tokens(heard)


def evidence_texts(item: dict, payload: dict) -> list[str]:
    want = set((item or {}).get("evidence") or [])
    return [r["text"] for r in (payload.get("turns") or [])
            if r["ordinal"] in want]


def invents_beyond_evidence(item: dict, payload: dict,
                            explicit: bool = False) -> bool:
    """Does this item's goal say more than its own evidence ever said?

    Never runs on a verdict that touches nothing (`ignore`), and never on an
    instruction the owner typed himself — the two carve-outs the predicate it
    replaces already had, for the same reasons.
    """
    if explicit or (item or {}).get("decision") not in ("act", "ask", "answer"):
        return False
    novel = unevidenced_tokens(item.get("goal") or "",
                               evidence_texts(item, payload))
    return len(novel) > NOVEL_TOLERANCE


# --- §10 the flag, and what shadow means ----------------------------------
MODE_OFF, MODE_SHADOW, MODE_ON = "off", "shadow", "on"
MODES = (MODE_OFF, MODE_SHADOW, MODE_ON)


def mode() -> str:
    """`ANTICIPY_SEGMENT_TRIAGE = off | shadow | on`, defaulting off, and an
    unreadable value is OFF — a typo must not switch a whole lane on."""
    want = (os.environ.get("ANTICIPY_SEGMENT_TRIAGE") or "").strip().lower()
    return want if want in MODES else MODE_OFF


def writes_back(current: str) -> bool:
    """In shadow the judge writes NOTHING — in particular not the `summary`
    back onto the segment row. The live per-line path reads that row as thread
    context (`decide_link`, segmenter.py:132), so a shadow that edits it is
    not a shadow, it is a second live path nobody is watching."""
    return current == MODE_ON


# --- §4 the one strong call ----------------------------------------------
SEGMENT_SYSTEM = """You are listening to somebody's day. Below is ONE
conversation that has now finished, written out as numbered turns.

You are judging THE CONVERSATION, not any single line. A thought that started
three turns ago and finished in two words is one thought, and it is in scope.

WHAT EACH TURN CARRIES
  #n            the turn's number. Every claim you make points at these.
  [hh:mm:ss]    when it was SPOKEN, and [gap: Ns] since the previous turn.
                A two-second gap and a four-minute gap are different things.
  [voice: …]    what the PHONE decided about who spoke — the owner, a named
                person, or "no verdict". Never guess a speaker from wording;
                "no verdict" means nobody knows, and that is a real answer.
  [source: …]   which microphone produced it. It decides nothing.
  [NEW]         not yet judged. Everything else has already been judged once
                and is here only as context.

WHAT TO RETURN

  summary       one line: what this conversation was about.
  entities      the names, places and things in it.
  splits_after  turn numbers after which you read a NEW conversation
                starting. Empty if it was all one. The clock guessed at the
                boundary; you are reading it.
  items         0 to 4 finished thoughts worth a verdict. Nothing in this
                conversation may need one — an empty list is a real answer
                and a better one than an invented errand.

EACH ITEM
  decision   ignore | ask | act | answer
             ignore — remembered, nothing to do.
             ask    — something must be settled with him before anything can
                      be done, and it blocks something that matters.
             act    — there is work to go and do.
             answer — he asked YOU something you can answer from what you
                      know. That is a verdict, not a routing accident.
  goal       the work, in the plainest words. SAY ONLY WHAT THE TURNS YOU
             CITE ACTUALLY SAID. A name, a number, a date or a place that
             appears nowhere in your own cited turns is invented, and an
             invented detail is worse than no card at all.
  missing    what you would have to be told before this could be done.
  assumption anything you filled in that nobody said.
  touches    what carrying this out would reach: send, pay, delete, post,
             book, or nothing at all.
  addressee  who was being spoken to: you, a person, a dictation machine,
             or himself.
  owes       whose job this is: owner, other, nobody.
  owner_committed  true only if HE took this on. Somebody else's plan,
             said in front of him, is not his.
  evidence   the turn numbers this item is read off. REQUIRED. Every number
             must be a turn above. An item citing a turn that is not there
             is discarded whole.

Reply ONLY with compact JSON:
{"summary": "...", "entities": [...], "splits_after": [...], "items": [...]}"""


def judge_segment(llm, payload: dict) -> dict:
    """ONE question, asked on its own, about one closed conversation.

    Four states, because "there was nothing here" and "nobody answered" are
    different things and the caller acts differently on each. This check
    points like a FLOOR — does anything in this conversation authorize doing
    something — so an absent verdict REFUSES: no items, no stamps, and the
    cursor stays where it was. A floor that lifts itself when the model is
    down is not a floor.
    """
    if not payload or not payload.get("turns"):
        return _blank(UNASKED, "nothing was said in this conversation")
    if not llm or not getattr(llm, "live", False):
        return _blank(UNASKED, "no model to ask")
    try:
        res = llm.chat(SEGMENT_SYSTEM, payload["text"], temperature=0.0)
        raw = res.text
    except Exception as exc:
        # NEVER SILENT. A model that times out every night must not look
        # exactly like a model that answers "nothing here" every night.
        print(f"sorter: the conversation went unjudged — {exc!r}; "
              f"{len(payload.get('new_ordinals') or [])} new turn(s) stay "
              f"claimed and come back on the next sweep")
        return _blank(UNANSWERED, repr(exc))
    out = parse_verdict(_json_slice(raw), payload)
    if out["state"] != JUDGED:
        print(f"sorter: unreadable reply to the judging question -> "
              f"{out['why']}; nothing stamped")
    return out


def _json_slice(text) -> str:
    if not isinstance(text, str):
        return text
    body = text.strip()
    if body.startswith("```"):
        body = body.strip("`")
        if body.startswith("json"):
            body = body[4:]
    start, end = body.find("{"), body.rfind("}")
    return body[start:end + 1] if start != -1 and end != -1 else body


# --- §6 the fast lane, which may only ACCELERATE --------------------------

def fast_lane(line: str, explicit: bool = False,
              already_fired: bool = False) -> tuple[bool, str]:
    """Fire the judge on the conversation-so-far, early, at most once.

    THE TRIGGER MAY ONLY BE ADDRESSING OR TRANSPORT. The wake name is
    addressing — did he say her name to her — and an explicit channel is a
    fact about how the words arrived. It may NOT be `remind me`, `can you`,
    `look up` or any sibling: CAPTURE-ARCHITECTURE's Trigger A proposed
    exactly those, and they are word lists deciding meaning.

    The asymmetry is the whole argument. A fast-lane MISS costs latency and
    the thought is still judged at close. A filter's false negative costs the
    errand, permanently, with nothing in the record saying so. The trigger is
    therefore allowed to be wrong in only one direction, and this one is.
    """
    if already_fired:
        return False, "this conversation has already had its early look"
    if explicit:
        return True, "an explicit channel — he put this in himself"
    from .anticipy_core import addressed_by_name   # lazy: core is heavy
    if addressed_by_name(line or ""):
        return True, "he said her name to her"
    return False, "nothing addressed her, so it waits for the close"


# --- §11 defect 2: context borrowed from a conversation already over ------

def context_segment(segment: Optional[dict],
                    now: datetime) -> Optional[dict]:
    """The open segment, but only if it is still the conversation he is in.

    `open_segment()` runs at worker.py:3282 and `place_turn` at :3363 — AFTER
    hear(). `should_close` is evaluated only inside `place_turn`. So today the
    FIRST LINE OF A NEW CONVERSATION is judged with the previous
    conversation's last eight lines sitting in its prompt. That is
    over-context, and it is the exact failure `inherited_errand`
    (orchestrator.py:563 — the largest word-list machine in the repo) exists
    to veto after the fact.

    A conversation whose rows are still LANDING is not over, however quiet his
    clock says he has been: that is a backlog draining, and dropping its
    context would strip a question of what it was about.
    """
    if not segment:
        return None
    over, _why = closable(segment, now)
    return None if over else segment
