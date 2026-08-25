#!/usr/bin/env python3
"""What the ears actually delivered in a day, measured from the rows themselves.

The number this exists to move is the one in the Brief's §9: on the recorded
2026-08-23 call the phone captured roughly one word in three, and 54% of the
lines it did send were four words or fewer. Everything downstream is capped by
that. Eight capture commits have landed since, and NOTHING HAS RE-MEASURED IT —
so "better" is currently a belief.

This is the server-side half of the instrument. `ListenTally` says what the
PHONE thinks happened; this says what actually arrived, which is the only side
that can be wrong in the direction that matters. Read them together: a day where
the phone recorded eight hours of listening and the server holds forty lines is
a delivery failure, and neither number alone can tell you that.

THE SHARD RATE COUNTS A STITCHED CHAIN AS ONE LINE, and that is the whole
subtlety. A `ceiling` flush cuts a sentence at eight seconds and marks the
NEXT line as its continuation (`parent_line`), so counting raw rows would score
one long thought as three shards and report a fix as a regression. The honest
number is the number of THOUGHTS that were short, not rows.

Read-only. It creates nothing, patches nothing, and touches no job. Safe to run
against production, which is the only place a real day exists.

    python3 proof/capture_day.py                 # today, every owner, blended
    python3 proof/capture_day.py --hours 24 --owner <owner_ref>

It reads the WHOLE window page by page and prints how many rows it could not
reach. With no `--owner` it reads every owner, names them, and prints each
one's numbers separately, because one owner talking fills another's silence and
a blended longest gap therefore cannot show a dead day.

Exit code: 0 when the day was read and any floor given was met; 1 when
`--min-words` was given and the day came in under it; 1 when the day could not
be READ at all. A day with no floor is never failed for being thin — a
measurement is not a gate — but a read that threw is not a thin day, and
exiting 0 on it would be exactly the silent failure this file exists to
prevent.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections import Counter
from typing import NamedTuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests  # noqa: E402

# IMPORTED, not copied. brain/worker.py is where the rule for reading a phone's
# timestamp lives; this file used to describe that rule in a comment while
# implementing a different one, and the drift was invisible until an auditor
# fed it a phone with a reset clock. A shared constant cannot drift.
from brain.worker import CLOCK_SKEW_MAX_S  # noqa: E402

PB = (os.environ.get("ANTICIPY_PB")
      or os.environ.get("ANTICIPY_BACKEND_URL")
      or "https://backend-production-61e0a.up.railway.app").rstrip("/")

# A line of four words or fewer is the shard the Brief counts, and it is the
# shape "At 5:15" had — two words of somebody else's schedule that minted a
# meeting with a person who does not exist.
SHARD_WORDS = 4

# A real always-on day runs well past one page of any size, so the read below
# pages instead of taking the first 500 and calling it a day. MAX_PAGES exists
# only so a server that never returns a short page cannot loop this forever;
# when it bites, the report SAYS so rather than quietly measuring what it
# reached. 100k rows is far past any real day.
PAGE_SIZE = 500
MAX_PAGES = 200


def headers() -> dict:
    # Same shape brain/pb.py uses. Without the token every read is 403 and this
    # file would report a perfect day by reading nothing.
    h = {"X-Anticipy-Worker": "1"}
    token = os.environ.get("ANTICIPY_SERVICE_TOKEN")
    if token:
        h["X-Anticipy-Token"] = token
    return h


def parse_ts(value: str) -> dt.datetime | None:
    """PocketBase hands back UTC, sometimes without the Z. Always aware."""
    if not value:
        return None
    v = str(value).replace("Z", "+00:00").replace(" ", "T", 1)
    try:
        parsed = dt.datetime.fromisoformat(v)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def spoken_at(row: dict) -> dt.datetime | None:
    """When it was SAID, falling back to when it arrived — the same rule, in the
    same order, as brain/worker.py's capture_key, clock-skew clamp included.

    Both halves are load-bearing and each closes a different wrong answer.
    Ordering a flushed backlog by ARRIVAL shuffles a conversation and invents
    gaps that never happened. And believing a stamp from a phone whose clock has
    been reset drags one line months out of place: one such row next to a normal
    one measured longest_gap_seconds = 20307630 — 235 days of silence on a day
    that held two lines thirty seconds apart.

    tests/test_capture_day.py drives this and capture_key over the same rows, so
    the claim in this docstring stays checked rather than merely written.

    One deliberate difference: capture_key returns 0.0 when nothing parses, and
    0.0 is a real instant. Handing 1970 to the gap would report fifty-six years
    of silence, so a row with no usable stamp is None here and report() skips
    the pair rather than inventing a gap.
    """
    spoken = (parse_ts(row.get("capture_started_at"))
              or parse_ts(row.get("spoken_at")))
    arrived = parse_ts(row.get("created"))
    if spoken is None:
        return arrived
    if arrived is not None:
        skew = abs((spoken - arrived).total_seconds())
        if skew > CLOCK_SKEW_MAX_S:
            return arrived
    return spoken


def owner_of(row: dict) -> str:
    """`owner_ref` is the canonical account column; `owner` is the older one
    brain/worker.py still writes beside it, so rows carrying only that are not
    stateless. An unattributed row is named "unknown" rather than folded into
    somebody else's day."""
    return (str(row.get("owner_ref") or "").strip()
            or str(row.get("owner") or "").strip()
            or "unknown")


def stitch(rows: list[dict]) -> list[list[dict]]:
    """Group rows into THOUGHTS, following the phone's own continuation marks.

    A `ceiling` flush hands the next line a `parent_line` pointing back at the
    one it was cut from. Following that chain is what makes the shard rate mean
    "how many thoughts were short" instead of "how many rows were short" — and
    the difference is the entire measurement, because the cut-marking work was
    done precisely to make long thoughts survivable.

    EVERY ROW LANDS IN EXACTLY ONE CHAIN: `sum(len(c) for c in stitch(rows))`
    equals `len(rows)` for any input, cycles and repeated ids included. That is
    the invariant the rates rest on. A row that falls out of the fold leaves
    BOTH the numerator and the denominator, so losing one moves the shard rate
    in whichever direction that row happened to point — and the flattering
    direction is the one nobody goes looking for.

    Rows are tracked by POSITION, not by `id`: two rows sharing an id, or a row
    carrying none, must still each land somewhere.
    """
    # First row wins a repeated id, matching what a chain of pointers into it
    # would resolve to anyway.
    first_at: dict[str, int] = {}
    for i, r in enumerate(rows):
        rid = r.get("id")
        if rid and rid not in first_at:
            first_at[rid] = i

    # A row is a continuation when it names a parent we actually have. A parent
    # we do NOT have (rotated away, another day, a deleted row) makes it the
    # head of its own thought rather than an orphan we silently drop.
    child_of: dict[int, int] = {}
    children: dict[int, list[int]] = {}
    for i, r in enumerate(rows):
        parent = str(r.get("parent_line") or "").strip()
        pi = first_at.get(parent)
        if pi is None or pi == i:
            continue
        child_of[i] = pi
        children.setdefault(pi, []).append(i)

    def spoken_key(i: int):
        return spoken_at(rows[i]) or dt.datetime.min.replace(tzinfo=dt.timezone.utc)

    heads = [i for i in range(len(rows)) if i not in child_of]
    # Heads first, then a SWEEP over every row still unplaced. The sweep is what
    # makes both of the shapes that lost rows safe, and it is the only thing
    # standing between this file and a flattering number:
    #
    #   * a later sibling. `cursor = kids[0]` below walks one child, so the rest
    #     are never reached from a head — and they are in `child_of`, so they
    #     are not heads either. Measured without the sweep: an 11-word row that
    #     shared its parent left the fold entirely, and a day whose one thought
    #     ran 13 words reported 100% short thoughts.
    #   * a `parent_line` cycle. Every node in a cycle is somebody's child, so a
    #     cycle contains no head at all. Measured without the sweep: two rows
    #     in, `chains == []`, `thoughts == 0`, `shard_rate == 0.0` — a perfect
    #     day reported out of total row loss.
    order = [*heads, *range(len(rows))]

    chains: list[list[dict]] = []
    placed: set[int] = set()
    for start in order:
        if start in placed:
            continue
        chain: list[dict] = []
        cursor: int | None = start
        # The bound is `placed`: no row is ever walked twice, so the walk cannot
        # run longer than the rows it was handed however tangled the pointers
        # are. The bound it replaces was a bare `guard < 200`, which could not
        # fire on a cycle at all (a cycle has no head, so the loop was never
        # entered) and whose only real effect was to cut a legitimate 259-row
        # chain down to 201 without saying so.
        while cursor is not None and cursor not in placed:
            placed.add(cursor)
            chain.append(rows[cursor])
            kids = sorted((k for k in children.get(cursor, []) if k not in placed),
                          key=spoken_key)
            # A cut has exactly ONE continuation, so a parent with two children
            # is a broken pointer rather than two continuations: pushEvent
            # returns "" for a SUCCESSFUL post whose response id is unreadable,
            # and the app only advances lastTranscriptEventID on a non-empty id,
            # so the next two lines both name the same parent. The
            # earliest-SPOKEN child is the one that really resumed the cut; the
            # later ones inherited a stale pointer, and the sweep above gives
            # each of them its own thought. Absorbing them into the parent's
            # chain instead would fuse unrelated lines into one long thought and
            # report a shard-free day.
            cursor = kids[0] if kids else None
        chains.append(chain)
    return chains


def report(rows: list[dict]) -> dict:
    """Pure: no network, no clock beyond the rows' own stamps. Driven with
    synthetic rows by tests/test_capture_day.py, because a measuring stick
    nobody has ever seen give a wrong answer is not a measuring stick."""
    transcripts = [r for r in rows if (r.get("kind") or "") == "transcript"]
    ordered = sorted(
        transcripts,
        key=lambda r: spoken_at(r) or dt.datetime.min.replace(tzinfo=dt.timezone.utc))

    words = sum(len((r.get("text") or "").split()) for r in ordered)
    chains = stitch(ordered)
    thought_words = [
        sum(len((r.get("text") or "").split()) for r in chain) for chain in chains
    ]
    shards = sum(1 for w in thought_words if 0 < w <= SHARD_WORDS)

    # Speaker coverage: the share of lines carrying ANY verdict. On build 75
    # this was 3% — 97% of lines carried none — which is why an unattributed
    # line may not mint an action today.
    tagged = sum(1 for r in ordered if (r.get("speaker") or "").strip())

    # The longest gap between things HEARD. On the phone side ListenTally
    # measures the same shape; a large gap here with a small one there means
    # the phone heard and the server never got it.
    longest_gap = 0.0
    for a, b in zip(ordered, ordered[1:]):
        ta, tb = spoken_at(a), spoken_at(b)
        if ta and tb:
            longest_gap = max(longest_gap, (tb - ta).total_seconds())

    owners = sorted({owner_of(r) for r in ordered})
    day = {
        "lines": len(ordered),
        "thoughts": len(chains),
        "words": words,
        "shard_thoughts": shards,
        "shard_rate": round(shards / len(chains), 3) if chains else 0.0,
        "raw_shard_rate": round(
            sum(1 for r in ordered
                if 0 < len((r.get("text") or "").split()) <= SHARD_WORDS)
            / len(ordered), 3) if ordered else 0.0,
        "speaker_coverage": round(tagged / len(ordered), 3) if ordered else 0.0,
        "longest_gap_seconds": int(longest_gap),
        "sources": dict(Counter((r.get("source") or "unknown") for r in ordered)),
        "owners": owners,
        # stitch() promises every row lands in exactly one chain. Carrying the
        # count in the output means a future regression that loses rows shows
        # up here as a visible disagreement with `lines`, instead of as a
        # quietly nicer shard rate that nobody has any reason to doubt.
        "rows_stitched": sum(len(c) for c in chains),
    }
    # A blended timeline cannot show a dead day: owner B talking through the
    # afternoon fills owner A's silence, and A's twelve-hour gap is reported as
    # six. The blend stays — it is the headline — but each owner's own numbers
    # go beside it so the blend can never be the only thing on offer. One owner
    # per sub-report, so this recurses exactly one level.
    if len(owners) > 1:
        day["per_owner"] = {
            name: report([r for r in ordered if owner_of(r) == name])
            for name in owners
        }
    return day


class DayRead(NamedTuple):
    rows: list[dict]
    total: int
    # None means: we stopped at the page cap AND the server never said how big
    # the window is, so we do not know what we missed. Reporting 0 there would
    # be a guess in the flattering direction.
    unread: int | None


def read_day(hours: float, owner: str = "") -> DayRead:
    """Every transcript row in the window, page by page, plus what we missed.

    A single `perPage: 500` read measured a 1300-row day as 500 lines under the
    banner WHAT THE EARS DELIVERED, with no indication that 800 rows existed —
    and chains crossing the cut lost their heads, which inflates `thoughts` and
    shifts `shard_rate` on top of the truncation. This file exists to replace a
    belief with a measurement, so measuring an undisclosed subset is the one
    failure it may not have.
    """
    since = (dt.datetime.now(dt.timezone.utc)
             - dt.timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    filt = f'kind="transcript" && created>="{since}"'
    if owner:
        filt += f' && owner_ref="{owner}"'

    rows: list[dict] = []
    seen: set[str] = set()
    total, page, capped = 0, 1, False
    while True:
        if page > MAX_PAGES:
            capped = True
            break
        # ASCENDING `created`, not `-created`. Under `-created` a row that lands
        # while we are paging shifts every later page down by one and a row
        # falls through the boundary unread; ascending order only ever appends
        # past the end. The id de-dupe below covers what is left.
        r = requests.get(f"{PB}/api/collections/events/records",
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

    if capped and not total:
        return DayRead(rows=rows, total=len(rows), unread=None)
    return DayRead(rows=rows, total=max(total, len(rows)),
                   unread=max(0, total - len(rows)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--owner", default="", help="owner_ref; omit for all")
    ap.add_argument("--min-words", type=int, default=0,
                    help="fail if fewer words than this arrived")
    args = ap.parse_args()

    try:
        read = read_day(args.hours, args.owner)
    except Exception as e:
        # A reader that fails silently would report a perfect day, which is the
        # one wrong answer a measuring stick must never give.
        print(f"\n  could not read the day: {str(e)[:100]}")
        print("  set ANTICIPY_SERVICE_TOKEN, or the report is of nothing.\n")
        return 1

    day = report(read.rows)
    print(f"\n  WHAT THE EARS DELIVERED   last {args.hours:g}h   {PB}")
    print("  " + "-" * 62)
    if read.unread is None:
        print(f"  !! DID NOT READ ALL OF IT: stopped at the {MAX_PAGES}-page cap")
        print("     and the server did not say how many rows the window holds,")
        print("     so how much is missing is UNKNOWN. Everything below is of a")
        print("     subset.")
    elif read.unread:
        print(f"  !! DID NOT READ {read.unread} OF {read.total} ROWS in this window.")
        print("     Everything below is of a subset, and a stitched chain that")
        print("     crossed the cut lost its head, which inflates `thoughts`")
        print("     and shifts `shard_rate` on top of the truncation.")
    if day["rows_stitched"] != day["lines"]:
        print(f"  !! STITCHING LOST ROWS: {day['lines']} lines in, "
              f"{day['rows_stitched']} landed in a")
        print("     thought. Every rate below is computed from the survivors")
        print("     only, so none of them is sound. This is a bug in stitch().")
    print(f"  lines that arrived            {day['lines']}")
    print(f"  thoughts, after stitching     {day['thoughts']}")
    print(f"  words                         {day['words']}")
    print(f"  short thoughts (<={SHARD_WORDS} words)     "
          f"{day['shard_thoughts']}  ({day['shard_rate']:.0%})")
    print(f"    same, counting raw rows     {day['raw_shard_rate']:.0%}"
          "   <- what it looks like without following the cut marks")
    print(f"  lines carrying a voice tag    {day['speaker_coverage']:.0%}")
    print(f"  longest gap between lines     {day['longest_gap_seconds']}s")
    print(f"  which ear                     {day['sources'] or 'none'}")
    print(f"  whose day                     {', '.join(day['owners']) or 'nobody'}")
    print("  " + "-" * 62)
    if day.get("per_owner"):
        print(f"  !! BLENDED: {len(day['owners'])} owners share every number above."
              " One owner talking")
        print("     fills another's silence, so the blended longest gap CANNOT")
        print("     show a dead day. Pass --owner to measure one person. Each:")
        for name, sub in day["per_owner"].items():
            print(f"       {name:<20} lines {sub['lines']:<6} words {sub['words']:<7}"
                  f" short {sub['shard_rate']:.0%}"
                  f"  longest gap {sub['longest_gap_seconds']}s")
        print("  " + "-" * 62)
    if not day["lines"]:
        print("  NOTHING ARRIVED. That is a finding, not an empty report:")
        print("  it is what a suspended app and a deaf recognizer both look")
        print("  like from here. Read the phone's own journal next.\n")
    else:
        print("  Read this next to the phone's Listening screen. The phone says")
        print("  what it THINKS it heard; this says what actually arrived, and")
        print("  a gap between the two is a delivery failure.\n")
    print(json.dumps({"report": "capture_day", **day,
                      "rows_unread": read.unread}))

    if args.min_words and day["words"] < args.min_words:
        print(f"\n  under the floor: {day['words']} words < {args.min_words}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
