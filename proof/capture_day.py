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

    python3 proof/capture_day.py                 # today, every owner
    python3 proof/capture_day.py --hours 24 --owner <owner_ref>

Exit code is the verdict when a floor is given: non-zero means the day came in
under it. With no floor it always exits 0 — a measurement is not a gate.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests  # noqa: E402

PB = (os.environ.get("ANTICIPY_PB")
      or os.environ.get("ANTICIPY_BACKEND_URL")
      or "https://backend-production-61e0a.up.railway.app").rstrip("/")

# A line of four words or fewer is the shard the Brief counts, and it is the
# shape "At 5:15" had — two words of somebody else's schedule that minted a
# meeting with a person who does not exist.
SHARD_WORDS = 4


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
    """When it was SAID, falling back to when it arrived — the same order and
    the same reason as brain/worker.py's capture_key. Ordering a flushed
    backlog by arrival shuffles a conversation, and a day scored on shuffled
    turns reports gaps that never happened."""
    return (parse_ts(row.get("capture_started_at"))
            or parse_ts(row.get("spoken_at"))
            or parse_ts(row.get("created")))


def stitch(rows: list[dict]) -> list[list[dict]]:
    """Group rows into THOUGHTS, following the phone's own continuation marks.

    A `ceiling` flush hands the next line a `parent_line` pointing back at the
    one it was cut from. Following that chain is what makes the shard rate mean
    "how many thoughts were short" instead of "how many rows were short" — and
    the difference is the entire measurement, because the cut-marking work was
    done precisely to make long thoughts survivable.
    """
    by_id = {r.get("id"): r for r in rows}
    # A row is a continuation when it names a parent we actually have. A parent
    # we do NOT have (rotated away, another day, a deleted row) makes it the
    # head of its own thought rather than an orphan we silently drop.
    child_of: dict[str, str] = {}
    for r in rows:
        parent = (r.get("parent_line") or "").strip()
        if parent and parent in by_id and parent != r.get("id"):
            child_of[r["id"]] = parent

    heads = [r for r in rows if r.get("id") not in child_of]
    children: dict[str, list[dict]] = {}
    for rid, pid in child_of.items():
        children.setdefault(pid, []).append(by_id[rid])

    chains = []
    for head in heads:
        chain, cursor, guard = [head], head, 0
        # Bounded: a cycle in parent_line would otherwise hang the report, and
        # the report is the thing you reach for when something is already wrong.
        while guard < 200:
            nxt = children.get(cursor.get("id"), [])
            if not nxt:
                break
            nxt.sort(key=lambda r: spoken_at(r) or dt.datetime.min.replace(
                tzinfo=dt.timezone.utc))
            cursor = nxt[0]
            chain.append(cursor)
            guard += 1
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

    return {
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
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--owner", default="", help="owner_ref; omit for all")
    ap.add_argument("--min-words", type=int, default=0,
                    help="fail if fewer words than this arrived")
    args = ap.parse_args()

    since = (dt.datetime.now(dt.timezone.utc)
             - dt.timedelta(hours=args.hours)).strftime("%Y-%m-%d %H:%M:%S")
    filt = f'kind="transcript" && created>="{since}"'
    if args.owner:
        filt += f' && owner_ref="{args.owner}"'

    try:
        r = requests.get(f"{PB}/api/collections/events/records",
                         headers=headers(),
                         params={"filter": filt, "perPage": 500, "sort": "-created"},
                         timeout=30)
        r.raise_for_status()
        rows = r.json().get("items", [])
    except Exception as e:
        # A reader that fails silently would report a perfect day, which is the
        # one wrong answer a measuring stick must never give.
        print(f"\n  could not read the day: {str(e)[:100]}")
        print("  set ANTICIPY_SERVICE_TOKEN, or the report is of nothing.\n")
        return 1

    day = report(rows)
    print(f"\n  WHAT THE EARS DELIVERED   last {args.hours:g}h   {PB}")
    print("  " + "-" * 62)
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
    print("  " + "-" * 62)
    if not day["lines"]:
        print("  NOTHING ARRIVED. That is a finding, not an empty report:")
        print("  it is what a suspended app and a deaf recognizer both look")
        print("  like from here. Read the phone's own journal next.\n")
    else:
        print("  Read this next to the phone's Listening screen. The phone says")
        print("  what it THINKS it heard; this says what actually arrived, and")
        print("  a gap between the two is a delivery failure.\n")
    print(json.dumps({"report": "capture_day", **day}))

    if args.min_words and day["words"] < args.min_words:
        print(f"\n  under the floor: {day['words']} words < {args.min_words}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
