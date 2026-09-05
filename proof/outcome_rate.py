#!/usr/bin/env python3
"""Of the lines that arrived, what fraction produced anything at all.

Nobody has this number. `proof/capture_day.py` says what the ears DELIVERED;
this says what the brain DID with it, and the two are the only pair that can
tell a deaf day from an inert one. Measured against production on 2026-08-25:
5.7% over 48h, 9.0% over 168h, and ZERO LINES AT ALL in the last 24.

WHY IT DOES NOT ALREADY EXIST. `overnight/is_the_brain_live.py` is the
liveness checker, and it reads `anticipy_says` rows only. Every leg it has is
an OVER-speaking check — asked too often, spoke in quiet hours, sent the same
sentence twice — so it is structurally incapable of catching "a line arrived
and produced nothing", and a totally deaf day exits 0 with a note that says
"not a pass" beside a passing exit code. This file is the other half: it is
denominated in what he SAID, not in what she said back.

THE REST IS THE INTERESTING HALF. A line can arrive and produce nothing for
very different reasons and they need different fixes, so the report buckets
them instead of subtracting them:

    acted / asked / quiet_work / job_only     she did something
    never_processed                           the worker never reached it
    in_flight                                 claimed, not yet finished
    refused                                   she stamped a reason
    echo_of_her                               his own reading-back, recomputed
    unexplained_silence                       everything else

A REPORT THAT CANNOT TELL "CORRECTLY IGNORED" FROM "SILENTLY DROPPED" IS NOT
WORTH BUILDING, and the honest answer is that the stored rows can only tell
them apart part of the way. `mark_processed` writes three things onto a
transcript row — decision, addressee, goal — and every `Decision` the core
builds carries a fourth, `reason`, which is where "a shard with no thread to
continue" and "stays ambient" and "not his to do" all live. NOTHING WRITES
`reason` DOWN. So `unexplained_silence` is a genuine mixture, and this file
prints that fact in the output rather than picking a flattering reading of it.
See `CANNOT_DISTINGUISH` for exactly which guards vanish and what brain/ would
have to record for each to become visible.

Two of the six guards named in the brief turned out NOT to be in that mixture,
and both corrections came from the code rather than from the card:

  * THE MEETING LATCH DOES NOT SILENCE THE LINE. It stamps decision="act"
    with the goal and holds the TEXT for the digest (anticipy_core, "held for
    the digest after his conversation"). It shows up here as an outcome; what
    it delays is delivery, which is a different measurement.
  * THE PARKED ASK IS INVISIBLE FOR A REASON NOBODY WROTE DOWN. It returns
    decision="ask" with goal="" and says nothing yet — and `stamp_for` then
    rewrites an ask that asked nothing into "ignore", because an "ask" the
    app renders as "Quick question for you" with no question under it is a
    lie. The rewrite is right and the record it leaves is byte-identical to a
    line she correctly let pass.

Read-only. It creates nothing, patches nothing, and touches no job. Safe to
run against production, which is the only place a real day exists.

    python3 proof/outcome_rate.py                    # today, every owner
    python3 proof/outcome_rate.py --hours 48 --owner <owner_ref>
    python3 proof/outcome_rate.py --min-lines 1      # a gate: she was not deaf

Exit code: 0 when the window was read and any floor given was met; 1 when a
floor was missed; 1 when the window could not be READ at all. A window with no
floor is never failed for being thin — a measurement is not a gate — but a
read that threw is not a quiet day, and exiting 0 on it would be exactly the
silent failure this file exists to prevent. Zero lines yields `outcome_rate:
null`, never 0.0 and never 1.0: there is no rate of a day that held nothing,
and any floor is missed rather than met by it.

ONE EDGE, STATED: the echo recomputation looks thirty minutes back from each
line, and the read starts at the window's edge. A line in the first half hour
that read back something she said just BEFORE the window opened cannot be
recognised, and lands in `unexplained_silence`. That direction is the safe
one — it over-fills the bucket that means "we do not know" rather than
explaining a silence away.
"""
from __future__ import annotations

import argparse
import datetime as dt
import inspect
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests  # noqa: E402

# IMPORTED, not copied, for capture_day.py's own stated reason: a rule
# described in one file and implemented in another drifts silently. spoken_at
# is the worker's capture_key including the clock-skew clamp, owner_of knows
# that `owner` is the older column beside `owner_ref`, and SHARD_WORDS is the
# Brief's four.
from proof.capture_day import (  # noqa: E402
    MAX_PAGES,
    PAGE_SIZE,
    SHARD_WORDS,
    owner_of,
    parse_ts,
    spoken_at,
)

# The echo guard, imported whole rather than re-implemented. This is the ONE
# of the named guards that reads a durable record — the same anticipy_says
# rows this report already holds — so it is the one silence that can be
# recomputed from outside instead of guessed at. Re-typing its threshold here
# would make this file's answer drift away from production's the first time
# either moved.
from brain.worker import (  # noqa: E402
    ECHO_FRACTION,
    ECHO_RUN,
    _words,
    is_echo_of_her,
    longest_shared_run,
)

PB = (os.environ.get("ANTICIPY_PB")
      or os.environ.get("ANTICIPY_BACKEND_URL")
      or "https://api.anticipy.ai").rstrip("/")

# How far back the worker looks for something of hers he might be reading
# back. Read off the function's own signature so it cannot drift: the worker
# calls is_echo_of_her(line, before=capture_key(ev)) and takes this default.
ECHO_MINUTES = float(
    inspect.signature(is_echo_of_her).parameters["minutes"].default)

# What the app writes and what the brain writes. Her own rows are NOT lines
# that arrived — counting them would let a chatty day flatter its own rate,
# which is the existing checker's blind spot wearing a new name.
HEARD_KIND = "transcript"
HER_KINDS = ("anticipy_says", "anticipy_text")

# A line produced something. `quiet_work` is decision=ignore carrying a goal:
# the feed renders exactly that as "Looking into it — I'll text you what I
# find", so a goal on the row is a promise that work exists.
OUTCOME_BUCKETS = ("acted", "asked", "quiet_work", "job_only")
# A line produced nothing. Only the last of these is a mixture.
SILENCE_BUCKETS = ("never_processed", "in_flight", "refused", "echo_of_her",
                   "unexplained_silence")

# Printed whatever the numbers say, because these are properties of what
# brain/ RECORDS, not of today's window. Each line names the guard, what it
# leaves behind, and what would have to be written down for it to become
# visible from out here. The fix in every case is in brain/, which this file
# does not hold.
CANNOT_DISTINGUISH = [
    "shard_too_thin (<=4 words, invented goal): returns ignore + goal='' and "
    "the reason is printed to a log, never stored. Only an upper bound is "
    "possible here. FIX: persist Decision.reason onto the row.",
    "the parked ask: returns ask + goal='', then stamp_for() rewrites it to "
    "ignore because an ask that asked nothing is not an ask. Identical in the "
    "record to a line she correctly let pass. FIX: a parked_ask flag, or "
    "Decision.reason.",
    "already_raised / already_said: they fire at the SAYING site, not at the "
    "line, and a refused say writes no row at all. Nothing anywhere records "
    "that she wanted to speak and was stopped. FIX: write the refusal.",
    "the parked-ask gauntlet (120s of total silence before a parked question "
    "may go out): a question that never found its quiet moment leaves the "
    "same ignore + goal='' as one that was never formed.",
    "no live LLM: every line falls to llm.py's heuristic engine and nothing "
    "on the row says which engine judged it. A silently-deaf model day is "
    "indistinguishable from a discerning one. FIX: stamp the LLM mode.",
    "correctly ignored (a TV, a joke, somebody else's errand) is the same "
    "ignore + goal='' as all of the above. This is why the bucket is named "
    "unexplained rather than ignored.",
]


def headers() -> dict:
    # Same shape brain/pb.py uses. Without the token every read is 403 and
    # this file would report a perfect day by reading nothing.
    h = {"X-Anticipy-Worker": "1"}
    token = os.environ.get("ANTICIPY_SERVICE_TOKEN")
    if token:
        h["X-Anticipy-Token"] = token
    return h


def job_event_ids(jobs: list[dict]) -> set:
    """Every transcript id that a job says it came from.

    THIS IS THE ONE OUTCOME A LINE'S OWN ROW CANNOT SHOW, and it is also where
    this file was wrong first. Grepping the params string for
    "source_event_id" matched 63 of 65 production jobs — and not one of them
    carries that key at the top level. It lives inside `_workflow`, which is
    a JSON string nested inside the params JSON string (workflow.py's Plan,
    serialised). A substring match would have reported a join that does not
    exist; measured properly, 53 of 65 jobs name at least one line, and two
    of the lines they name carry decision=ignore and no goal on their own row.

    The top-level keys are honoured too, because anticipy_core writes
    params["source_event_ids"] on the recognizer-continuation path.

    Never raises. The report is what you reach for when something is already
    wrong, so a job with unreadable params costs that job, not the report.
    """
    out: set = set()

    def take(value) -> None:
        if isinstance(value, str) and value.strip():
            out.add(value.strip())
        elif isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, str) and item.strip():
                    out.add(item.strip())

    for jobrow in jobs or []:
        try:
            params = json.loads(jobrow.get("params") or "{}")
        except Exception:
            continue
        if not isinstance(params, dict):
            continue
        take(params.get("source_event_id"))
        take(params.get("source_event_ids"))
        workflow = params.get("_workflow")
        if isinstance(workflow, str):
            try:
                workflow = json.loads(workflow)
            except Exception:
                workflow = None
        if isinstance(workflow, dict):
            take(workflow.get("source_event_id"))
            take(workflow.get("source_event_ids"))
    return out


def echo_positions(lines: list[dict], said: list[dict]) -> set:
    """Which of these lines are him reading her own words back at her.

    The same rule the worker runs, over the same rows, at the same threshold:
    six words shared IN ORDER (gaps allowed) at 0.6 of his line, against
    anything of hers from the last thirty minutes. Deliberately faithful down
    to the two clocks it compares, which are not the same clock: the worker
    passes `before=capture_key(ev)` — SPOKEN time for his line — and filters
    her rows on `created`, which is arrival. Correcting that here would make
    this report disagree with the guard it is measuring.

    Scoped to the owner, as production is: main() binds one worker to one
    owner, so `_active_owner_ref` narrows the read. Unscoped, one account's
    messages would explain away another account's silence — the same defect
    capture_day's blended longest gap has.

    Positions, not ids: an id is a thing the server gave us, not a thing we
    may rely on to be unique or present.
    """
    hers = []
    for row in said or []:
        if (row.get("kind") or "") not in HER_KINDS:
            continue
        at = parse_ts(row.get("created"))
        if at is None:
            continue
        hers.append((at, owner_of(row), row.get("text") or ""))

    out: set = set()
    if not hers:
        return out
    window = dt.timedelta(minutes=ECHO_MINUTES)
    for i, row in enumerate(lines):
        text = row.get("text") or ""
        mine = len(_words(text))
        # The guard's own first gate: too short to be a recognisable echo.
        if mine < ECHO_RUN:
            continue
        at = spoken_at(row)
        if at is None:
            continue
        who = owner_of(row)
        floor = at - window
        for said_at, said_who, said_text in hers:
            if said_who != who or not (floor <= said_at <= at):
                continue
            shared = longest_shared_run(text, said_text)
            if shared >= ECHO_RUN and shared / max(1, mine) >= ECHO_FRACTION:
                out.add(i)
                break
    return out


def classify(row: dict, job_ids: set, echo: bool) -> str:
    """Which single bucket this line belongs in.

    THE ORDER IS LOAD-BEARING. Outcomes are tested first, so a four-word line
    that nevertheless produced a card is an outcome rather than a shard;
    reversed, every short line that worked would be filed as a silence and the
    rate would fall for the lines that prove it works.

    A decision stamp this file has never heard of is a REFUSAL, not a silence:
    an unknown stamp is the brain having said something, and defaulting it into
    `unexplained_silence` would grow the one bucket that means "we do not know"
    every time the brain learns a new word.
    """
    decision = str(row.get("decision") or "").strip()
    goal = str(row.get("goal") or "").strip()

    if decision == "act":
        return "acted"
    if decision == "ask":
        return "asked"
    if goal:
        return "quiet_work"
    if str(row.get("id") or "") and row["id"] in job_ids:
        return "job_only"

    if not decision:
        return "never_processed"
    if decision == "processing":
        return "in_flight"
    if decision == "ignore":
        return "echo_of_her" if echo else "unexplained_silence"
    return "refused"


# The guard counts words with `re.findall(r"[\w']+", line)`, which splits
# "5:15" into two. tests/test_outcome_rate.py drives this against the real
# shard_too_thin over the same lines, so the claim stays checked rather than
# merely written.
_GUARD_WORDS = re.compile(r"[\w']+")


def could_be_a_shard(text: str) -> bool:
    """Short enough that shard_too_thin COULD have fired on this line.

    NECESSARY, NOT SUFFICIENT, and that is the whole point of the name. The
    guard also requires the model to have wanted to act or ask, to have had no
    thread to continue, and to have minted a goal carrying more than two words
    the audio never held — none of which is stored. Reported only as a
    ceiling, never as a count.

    NO LOWER BOUND, unlike capture_day's shard rate, and the test that pins
    this against the real guard is what found the difference. `> 4` means the
    guard fires on a line of ZERO words too. capture_day is computing a rate,
    where a wordless thought is not a short thought; this is computing a
    ceiling, where excluding something the guard would catch is the one error
    it may not make. (Production never routes an empty line here — worker.py
    marks it "ignore" before it can be claimed — so the looser ceiling costs
    nothing real and stays faithful to the rule it is quoting.)
    """
    return len(_GUARD_WORDS.findall(text or "")) <= SHARD_WORDS


def report(rows: list[dict], jobs: list[dict]) -> dict:
    """Pure: no network, no clock beyond the rows' own stamps. Driven with
    synthetic rows by tests/test_outcome_rate.py, because a measuring stick
    nobody has ever seen give a wrong answer is not a measuring stick."""
    heard = [r for r in rows if (r.get("kind") or "") == HEARD_KIND]
    said = [r for r in rows if (r.get("kind") or "") in HER_KINDS]
    floor = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    ordered = sorted(heard, key=lambda r: spoken_at(r) or floor)

    job_ids = job_event_ids(jobs)
    echoes = echo_positions(ordered, said)

    buckets = {name: 0 for name in (*OUTCOME_BUCKETS, *SILENCE_BUCKETS)}
    marks: list = []
    for i, row in enumerate(ordered):
        mark = classify(row, job_ids, i in echoes)
        marks.append(mark)
        if mark in buckets:
            buckets[mark] += 1

    outcomes = sum(buckets[name] for name in OUTCOME_BUCKETS)
    unexplained = [r for r, m in zip(ordered, marks)
                   if m == "unexplained_silence"]

    out = {
        "lines": len(ordered),
        "outcomes": outcomes,
        # None, never 0.0 and never 1.0. Zero of zero is not a rate, and a
        # report that answered "100%" to a day that held nothing would be a
        # worse instrument than the one it replaces.
        "outcome_rate": (round(outcomes / len(ordered), 3) if ordered
                         else None),
        "heard_nothing": not ordered,
        "buckets": buckets,
        "unexplained": {
            "total": len(unexplained),
            "at_most_shard_too_thin": sum(
                1 for r in unexplained if could_be_a_shard(r.get("text") or "")),
            # addressee IS stored, and it is the only thing inside this bucket
            # the brain actually wrote down. "person" is the lane that is
            # SUPPOSED to be quiet; an empty one means triage never classified
            # the line at all, which is a different animal entirely.
            "by_addressee": dict(Counter(
                str(r.get("addressee") or "").strip() or "unclassified"
                for r in unexplained)),
        },
        # Her side, counted separately and never folded into the denominator.
        # A window with no lines and three messages is a real production shape
        # (the 24h to 2026-08-25) and it is the shape the existing checker
        # cannot see.
        "she_spoke": len(said),
        "spoke_to": dict(Counter(owner_of(r) for r in said)),
        "cannot_distinguish": list(CANNOT_DISTINGUISH),
        # Every line lands in exactly one bucket. Carrying the count means a
        # future regression that loses lines shows up as a visible
        # disagreement with `lines` instead of as a quietly different rate
        # that nobody has any reason to doubt.
        "rows_bucketed": sum(buckets.values()),
    }

    owners = sorted({owner_of(r) for r in ordered} | {owner_of(r) for r in said})
    # A blended rate cannot show a dead account: measured over 168h of
    # production the blend read 9%, and under it sat one owner at 5%, one at
    # 43%, and one with no lines at all — an account that heard nothing while
    # she sent it three messages. The blend stays — it is the headline — but
    # each owner's own
    # numbers go beside it so the blend is never the only thing on offer. One
    # owner per sub-report, so this recurses exactly one level.
    if len(owners) > 1:
        per: dict = {}
        for name in owners:
            sub = report([r for r in (*ordered, *said) if owner_of(r) == name],
                         jobs)
            # The blind spot is a property of what brain/ records, not of one
            # owner's window, so it is stated ONCE. Repeating the paragraph
            # per owner made the JSON line — the thing a gate greps — six
            # times longer than the numbers in it.
            sub.pop("cannot_distinguish", None)
            per[name] = sub
        out["per_owner"] = per
    return out


def _page(collection: str, filt: str) -> tuple[list[dict], int, bool]:
    """Every row matching `filt`, page by page, plus whether we ran out of
    pages before we ran out of rows.

    ASCENDING `created`, not `-created`, for capture_day's reason: under
    `-created` a row landing while we page shifts every later page down by one
    and a row falls through the boundary unread. Ascending only ever appends
    past the end, and the id de-dupe covers what is left.
    """
    rows: list[dict] = []
    seen: set = set()
    total, page, capped = 0, 1, False
    while True:
        if page > MAX_PAGES:
            capped = True
            break
        r = requests.get(f"{PB}/api/collections/{collection}/records",
                         headers=headers(),
                         params={"filter": filt, "perPage": PAGE_SIZE,
                                 "page": page, "sort": "created"},
                         timeout=30)
        r.raise_for_status()
        body = r.json()
        items = body.get("items") or []
        total = max(total, int(body.get("totalItems") or 0))
        for item in items:
            rid = item.get("id")
            if rid and rid in seen:
                continue
            if rid:
                seen.add(rid)
            rows.append(item)
        if len(items) < PAGE_SIZE:
            break
        page += 1
    return rows, total, capped


def read_window(hours: float, owner: str = "") -> dict:
    """Everything the report needs: his lines, her messages, and the jobs.

    The events read is the one that may not fail: without it there is no
    denominator and no report. The JOBS read is allowed to fail — the
    collection may be closed to this token, and losing it costs only the
    `job_only` bucket — but it is never allowed to fail SILENTLY, because
    losing it understates the rate and understating is the direction that gets
    believed.
    """
    since = (dt.datetime.now(dt.timezone.utc)
             - dt.timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    kinds = " || ".join(f'kind="{k}"' for k in (HEARD_KIND, *HER_KINDS))
    scope = f' && owner_ref="{owner}"' if owner else ""

    rows, total, capped = _page("events", f'({kinds}) && created>="{since}"{scope}')
    unread = None if (capped and not total) else max(0, total - len(rows))

    jobs: list | None
    jobs_error = ""
    try:
        jobs, _, _ = _page("jobs", f'created>="{since}"{scope}')
    except Exception as e:
        jobs, jobs_error = None, str(e)[:88]
    return {"rows": rows, "total": max(total, len(rows)), "unread": unread,
            "jobs": jobs, "jobs_error": jobs_error}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--owner", default="", help="owner_ref; omit for all")
    ap.add_argument("--min-lines", type=int, default=0,
                    help="fail if fewer lines than this arrived (a deafness gate)")
    ap.add_argument("--min-rate", type=float, default=0.0,
                    help="fail if the outcome rate came in under this")
    args = ap.parse_args()

    try:
        read = read_window(args.hours, args.owner)
    except Exception as e:
        # A reader that fails silently would report a perfect day, which is
        # the one wrong answer a measuring stick must never give.
        print(f"\n  could not read the window: {str(e)[:100]}")
        print("  set ANTICIPY_SERVICE_TOKEN, or the report is of nothing.\n")
        return 1

    day = report(read["rows"], read["jobs"] or [])
    rate = day["outcome_rate"]

    print(f"\n  WHAT THE BRAIN DID WITH IT   last {args.hours:g}h   {PB}")
    print("  " + "-" * 66)
    if read["unread"] is None:
        print(f"  !! DID NOT READ ALL OF IT: stopped at the {MAX_PAGES}-page cap")
        print("     and the server did not say how many rows the window holds,")
        print("     so how much is missing is UNKNOWN. Everything below is of")
        print("     a subset.")
    elif read["unread"]:
        print(f"  !! DID NOT READ {read['unread']} OF {read['total']} ROWS in "
              "this window.")
        print("     Everything below is of a subset, and the lines it dropped")
        print("     are not a random sample of anything.")
    if read["jobs"] is None:
        print(f"  !! COULD NOT READ THE JOBS: {read['jobs_error']}")
        print("     A job is the only evidence of an outcome a line's own row")
        print("     cannot show, so the rate below is a FLOOR, not the rate.")
    if day["rows_bucketed"] != day["lines"]:
        print(f"  !! BUCKETING LOST LINES: {day['lines']} in, "
              f"{day['rows_bucketed']} landed in a")
        print("     bucket. Every number below is computed from the survivors")
        print("     only, so none of them is sound. This is a bug in classify().")

    print(f"  lines that arrived            {day['lines']}")
    if day["heard_nothing"]:
        print("  outcome rate                  n/a — no lines, so no rate")
    else:
        print(f"  produced something            {day['outcomes']}"
              f"   ({rate:.0%})   <- THE NUMBER")
    print("  " + "-" * 66)
    print("  what came of them")
    for name in OUTCOME_BUCKETS:
        print(f"    {name:<24} {day['buckets'][name]}")
    print("  and what did not")
    for name in SILENCE_BUCKETS:
        print(f"    {name:<24} {day['buckets'][name]}")
    print("  " + "-" * 66)

    unex = day["unexplained"]
    if unex["total"]:
        print(f"  the {unex['total']} unexplained silences are a MIXTURE. What the")
        print("  rows can say about them, and nothing more:")
        print(f"    at most {unex['at_most_shard_too_thin']} were short enough for "
              "shard_too_thin to fire")
        print(f"    who she judged he was talking to: {unex['by_addressee']}")
        print("  " + "-" * 66)
    print("  WHAT THIS REPORT CANNOT TELL APART, whatever the numbers say:")
    for reason in day["cannot_distinguish"]:
        first, *rest = reason.split(": ", 1)
        head, *tail = _wrap(first, 62)
        print(f"    - {head}")
        for chunk in tail:
            print(f"      {chunk}")
        if rest:
            for chunk in _wrap(rest[0], 62):
                print(f"        {chunk}")
    print("  " + "-" * 66)

    if day.get("per_owner"):
        print(f"  !! BLENDED: {len(day['per_owner'])} owners share the rate above."
              " One owner's")
        print("     working day fills another's dead one. Pass --owner. Each:")
        for name, sub in day["per_owner"].items():
            shown = "n/a  " if sub["outcome_rate"] is None \
                else f"{sub['outcome_rate']:.0%}".rjust(5)
            print(f"       {name:<20} lines {sub['lines']:<6} produced "
                  f"{sub['outcomes']:<5} {shown}   she spoke {sub['she_spoke']}")
        print("  " + "-" * 66)

    if day["heard_nothing"]:
        print("  NOTHING WAS HEARD IN THIS WINDOW. That is the headline, not an")
        print(f"  empty table — and she sent {day['she_spoke']} message(s) anyway.")
        print("  is_the_brain_live.py exits 0 on exactly this shape, because")
        print("  every rule it has is an over-speaking rule. Read this next to")
        print("  proof/capture_day.py: deaf ears and an inert brain look the")
        print("  same from here and different from there.\n")
    else:
        print("  Read this next to proof/capture_day.py. That says what")
        print("  ARRIVED; this says what came of it. A good capture rate with")
        print("  a bad outcome rate is a brain problem; both bad is an ears")
        print("  problem, and the ears come first.\n")

    print(json.dumps({"report": "outcome_rate", **day,
                      "rows_unread": read["unread"],
                      "jobs_read": None if read["jobs"] is None
                      else len(read["jobs"])}))

    missed = []
    if args.min_lines and day["lines"] < args.min_lines:
        missed.append(f"{day['lines']} lines < {args.min_lines}")
    # A window that heard nothing MISSES a rate floor rather than meeting it.
    # Treating zero-of-zero as a pass would let the deaf day through the one
    # gate written to catch it — the existing checker's bug, re-implemented
    # inside its replacement.
    if args.min_rate and (rate is None or rate < args.min_rate):
        shown = "n/a (nothing was heard)" if rate is None else f"{rate:.0%}"
        missed.append(f"outcome rate {shown} < {args.min_rate:.0%}")
    if missed:
        print(f"\n  under the floor: {'; '.join(missed)}\n")
        return 1
    return 0


def _wrap(text: str, width: int) -> list:
    out, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out


if __name__ == "__main__":
    raise SystemExit(main())
