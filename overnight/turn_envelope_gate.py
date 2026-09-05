#!/usr/bin/env python3
"""Do the two ends of a spoken line reach the server as two different instants?

THE THING THAT MAKES THIS GATE DIFFERENT FROM THE ONE ANYBODY WOULD WRITE.

The obvious check is "is `capture_started_at` populated?". That check is GREEN
TODAY, and has been for months, on the exact column this gate exists to prove.
All 137 stored production rows carry a non-empty `capture_started_at`. Every one
of them is the POSTMARK: measured against `created` it is

    min 0.047 s   p50 0.053 s   p90 0.057 s   max 0.065 s

— because `pushEvent` called `Date()` at push time and wrote that one instant
into `capture_started_at`, `spoken_at` and `capture_ended_at` alike. Three
columns, one number, informationally identical to arrival time.

Present-but-meaningless is strictly harder to see than absent. So:

    ******************************************************************
    NO LEG IN THIS FILE MAY CHECK THAT A FIELD IS NON-EMPTY.
    Every leg asserts a RELATIONSHIP BETWEEN TWO INSTANTS, with floors
    above anything push-time stamping can physically produce.
    ******************************************************************

Softening a floor here to reach green re-admits the exact defect. The floors are
not taste: an honest `wordsAppearedAt` is at minimum one utterance gap
(`TranscriptFlushPolicy.utteranceGap = 2.6 s`) behind the POST for a gap flush,
and up to `maxHold = 8 s` for a ceiling cut. The broken population tops out at
0.065 s. Two orders of magnitude separate them, and the floors sit in the gap.

WHY THIS IS NOT A LAW 1 VIOLATION. Law 1 forbids a regex, word list or threshold
deciding what words MEAN, and permits thresholds in deterministic gates. Every
number here is arithmetic over CLOCKS — how far apart two timestamps are — and
never over content. This file never requests the `text` column at all (see
`FIELDS`), so it cannot read a word of anybody's speech even by accident. It
cannot be measuring meaning with a threshold when it cannot see the words.

Read-only. It creates nothing, patches nothing, touches no job.

    python3 overnight/turn_envelope_gate.py
    python3 overnight/turn_envelope_gate.py --hours 48 --min-build 88
    python3 overnight/turn_envelope_gate.py --self-test
    python3 overnight/turn_envelope_gate.py --replay research/evals/call-2026-08-23-tejas/call_transcripts.json

Exit code is the verdict:

    0   the envelope is proven true against live rows
    1   FAILED — a leg's invariant is violated
    2   UNPROVEN — too few qualifying rows, deaf ears, or the backend could not
        be read. A leg that cannot be tested does not pass.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics
import sys

import os as _os, sys as _sys  # noqa: E402
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _env  # noqa: E402  sibling module; gates are run as scripts
_ENV_LOADED = _env.load_and_announce(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

import requests  # noqa: E402

PB = (os.environ.get("ANTICIPY_PB")
      or os.environ.get("ANTICIPY_BACKEND_URL")
      or "https://api.anticipy.ai").rstrip("/")

# THE ONLY COLUMNS THIS GATE EVER ASKS FOR. `text` is deliberately absent and
# must stay absent: it is the mechanical guarantee behind the Law 1 paragraph
# above, and it is the same discipline `are_the_ears_live.py` states for itself.
FIELDS = "id,created,device_id,source,capture_started_at,capture_ended_at"

# The build that first sent two instants. Rows from below it are the broken
# population by construction, and mixing them in would drag every median
# toward the defect and make the gate report on history instead of on now.
MIN_BUILD = 88

# Below this the gate cannot speak. An empty table is not a passing grade, and
# a median over four rows is an anecdote.
MIN_ROWS = 20

# Leg 1. Above every value push-time stamping can physically produce (max
# 0.065 s measured over 137 rows) and below the smallest honest one
# (utteranceGap = 2.6 s). Nothing lands between these two populations.
LEG1_MEDIAN_FLOOR_S = 2.0
LEG1_ONE_ROW_FLOOR_S = 2.6

# Leg 2. An aliasing implementation scores 0% here, and so does an empty
# `capture_ended_at` — which is how the presence check comes free without ever
# being the check. 90% rather than 100% because a typed line and a
# backwards-stepping clock both legitimately collapse to one instant.
LEG2_MIN_FRACTION = 0.90
LEG2_MEDIAN_SPAN_FLOOR_S = 0.5

# Leg 4. Only a line that was buffered and flushed later, carrying its original
# instant, can put a minute between the two. This is Omi #6551 stated as an
# assertion about Anticipy's own queue.
LEG4_MIN_DELAY_S = 60.0

# Leg 5. A queue flush arrives as a burst: several rows whose `created` values
# are seconds apart. If the queue re-stamped at flush time their capture
# instants would be seconds apart too.
LEG5_BURST_MIN_ROWS = 3
LEG5_BURST_WINDOW_S = 2.0
LEG5_MIN_SPAN_S = 30.0

# Leg 6, the precondition, borrowed whole from are_the_ears_live.py: a silent
# night is silent on BOTH halves, deaf ears are silent on one.
SERVER_DEVICE = "anticipy-brain"

PASS, FAIL, UNPROVEN = 0, 1, 2
MARK = {PASS: "PASS", FAIL: "FAIL", UNPROVEN: "...."}


def headers() -> dict:
    h = {"X-Anticipy-Worker": "1"}
    token = os.environ.get("ANTICIPY_SERVICE_TOKEN")
    if token:
        h["X-Anticipy-Token"] = token
    return h


def parse_ts(value):
    """PocketBase hands back 'YYYY-MM-DD HH:MM:SS.mmmZ'; the phone writes
    'YYYY-MM-DDTHH:MM:SS.mmmZ'. Tolerate both and always return an AWARE
    datetime, so nothing is ever read in the zone of whatever laptop ran this.

    An empty string returns None. That is the ONLY place emptiness appears in
    this file, and it is a parse result, never a verdict: a row whose stamp
    will not parse is excluded from the population, and the legs then report on
    how few rows they had rather than on how many fields were filled in.
    """
    if not value:
        return None
    v = str(value).replace("Z", "+00:00").replace(" ", "T", 1)
    try:
        parsed = dt.datetime.fromisoformat(v)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def build_of(device_id: str):
    """`iphone-b75` -> 75. Plumbing on a device label, not a judgement."""
    if not device_id:
        return None
    tail = str(device_id).rsplit("-b", 1)
    if len(tail) != 2:
        return None
    digits = "".join(c for c in tail[1] if c.isdigit())
    return int(digits) if digits else None


def qualifying(rows: list, min_build: int = MIN_BUILD) -> list:
    """Rows this gate can speak about: transcripts from a build that sends two
    instants, spoken rather than typed, with a readable arrival and start.

    Typed lines are excluded because a typed line HAS no speaking duration —
    `CaptureEnvelope` collapses it to one instant on purpose, and counting
    those against Leg 2 would measure how much somebody typed today.
    """
    out = []
    for r in rows:
        if r.get("kind", "transcript") != "transcript":
            continue
        if r.get("source") == "typed":
            continue
        b = build_of(r.get("device_id", ""))
        if b is None or b < min_build:
            continue
        created, start = parse_ts(r.get("created")), parse_ts(r.get("capture_started_at"))
        if created is None or start is None:
            continue
        out.append({"id": r.get("id", ""), "created": created, "start": start,
                    "end": parse_ts(r.get("capture_ended_at"))})
    return out


# --------------------------------------------------------------------- legs

def leg1_stamp_is_not_the_postmark(rows: list) -> tuple[int, str]:
    """The start is when the words appeared, not when the row was posted."""
    delays = sorted(( r["created"] - r["start"]).total_seconds() for r in rows)
    med, top = statistics.median(delays), max(delays)
    if med >= LEG1_MEDIAN_FLOOR_S and top >= LEG1_ONE_ROW_FLOOR_S:
        return PASS, (f"median start-to-arrival {med:.2f}s (floor {LEG1_MEDIAN_FLOOR_S}), "
                      f"widest {top:.2f}s — not a postmark")
    return FAIL, (f"median start-to-arrival {med:.2f}s and widest {top:.2f}s. "
                  f"Push-time stamping measured p50 0.053s / max 0.065s, so this "
                  f"is the POSTMARK, not the moment anybody spoke.")


def leg2_two_different_instants(rows: list) -> tuple[int, str]:
    """Strictly two instants, and far enough apart to be a real utterance."""
    spans = [(r["end"] - r["start"]).total_seconds()
             for r in rows if r["end"] is not None]
    bracketed = [s for s in spans if s > 0]
    frac = len(bracketed) / len(rows)
    if not bracketed:
        return FAIL, (f"0 of {len(rows)} rows have an end AFTER their start. "
                      f"Either capture_ended_at is empty or one instant is still "
                      f"being aliased onto both columns — every capture span is zero.")
    med = statistics.median(bracketed)
    if frac >= LEG2_MIN_FRACTION and med >= LEG2_MEDIAN_SPAN_FLOOR_S:
        return PASS, (f"{frac:.0%} of rows bracket a span, median {med:.2f}s")
    return FAIL, (f"only {frac:.0%} of rows bracket a span (floor "
                  f"{LEG2_MIN_FRACTION:.0%}), median span {med:.2f}s "
                  f"(floor {LEG2_MEDIAN_SPAN_FLOOR_S}s)")


def leg3_cannot_finish_after_posting(rows: list) -> tuple[int, str]:
    """A phone cannot stop speaking after it posted. Catches a timezone bug, a
    format bug and a wrong-clock device, and it is the invariant that
    `capture_key`'s skew fallback exists to survive."""
    bad = [r for r in rows if r["end"] is not None and r["end"] > r["created"]]
    if not bad:
        return PASS, f"all {len(rows)} rows finished speaking before they posted"
    worst = max((r["end"] - r["created"]).total_seconds() for r in bad)
    return FAIL, (f"{len(bad)} row(s) claim to have finished up to {worst:.2f}s "
                  f"AFTER the server received them (e.g. {bad[0]['id']})")


def leg4_queue_preserved_the_stamp(rows: list) -> tuple[int, str]:
    """UNPROVEN, never pass, when nobody ran the procedure. The leg cannot
    manufacture a buffered row; it can only detect one."""
    delayed = [r for r in rows
               if (r["created"] - r["start"]).total_seconds() > LEG4_MIN_DELAY_S]
    if delayed:
        worst = max((r["created"] - r["start"]).total_seconds() for r in delayed)
        return PASS, (f"{len(delayed)} row(s) arrived up to {worst / 60:.1f} min after "
                      f"the words — the queue kept the instant across a flush")
    return UNPROVEN, ("no row arrived more than "
                      f"{LEG4_MIN_DELAY_S:.0f}s after its words. Airplane mode on, "
                      f"speak two sentences, wait a minute, airplane mode off. An "
                      f"unrun procedure is not evidence.")


def leg5_a_flush_burst_did_not_collapse(rows: list) -> tuple[int, str]:
    """Omi #6551 as an assertion. Rows that ARRIVED together must not have been
    SPOKEN together."""
    by_arrival = sorted(rows, key=lambda r: r["created"])
    best = None
    for i in range(len(by_arrival)):
        group = [by_arrival[i]]
        for j in range(i + 1, len(by_arrival)):
            if (by_arrival[j]["created"] - by_arrival[i]["created"]).total_seconds() \
                    <= LEG5_BURST_WINDOW_S:
                group.append(by_arrival[j])
            else:
                break
        if len(group) >= LEG5_BURST_MIN_ROWS:
            span = (max(g["start"] for g in group)
                    - min(g["start"] for g in group)).total_seconds()
            if best is None or span > best:
                best = span
    if best is None:
        return UNPROVEN, (f"no burst of {LEG5_BURST_MIN_ROWS}+ rows arriving within "
                          f"{LEG5_BURST_WINDOW_S:.0f}s of each other — no queue flush "
                          f"in this window to inspect")
    if best > LEG5_MIN_SPAN_S:
        return PASS, (f"a flush burst spans {best:.0f}s of speech — the queue did "
                      f"not re-stamp what it was holding")
    return FAIL, (f"a burst of rows that ARRIVED together was also SPOKEN within "
                  f"{best:.0f}s (floor {LEG5_MIN_SPAN_S:.0f}s). The queue re-stamped "
                  f"at flush time — a whole buffered conversation collapsed into "
                  f"one moment and will be read back shuffled.")


def evaluate(rows: list, min_rows: int = MIN_ROWS) -> tuple[int, list]:
    """Every leg runs; the exit code is the worst verdict. Pure, so --self-test
    and --replay exercise the same code the live run does."""
    results = []
    if len(rows) < min_rows:
        return UNPROVEN, [(UNPROVEN, "scope",
                           f"only {len(rows)} qualifying row(s), need {min_rows}. "
                           f"An empty table is not a passing grade.")]
    for name, fn in (("leg 1  the stamp is not the postmark", leg1_stamp_is_not_the_postmark),
                     ("leg 2  start and end are two instants", leg2_two_different_instants),
                     ("leg 3  it cannot finish after posting", leg3_cannot_finish_after_posting),
                     ("leg 4  the queue preserved the stamp", leg4_queue_preserved_the_stamp),
                     ("leg 5  a flush burst did not collapse", leg5_a_flush_burst_did_not_collapse)):
        code, why = fn(rows)
        results.append((code, name, why))
    worst = FAIL if any(c == FAIL for c, _, _ in results) else \
        (UNPROVEN if any(c == UNPROVEN for c, _, _ in results) else PASS)
    return worst, results


def report(code: int, results: list) -> int:
    print("")
    for c, name, why in results:
        print(f"  [{MARK[c]}] {name}")
        print(f"         {why}")
    print("")
    print({PASS: "  ENVELOPE PROVEN — the two ends of a line survive the wire.",
           FAIL: "  FAILED — a leg's invariant is violated. Read the FAIL lines.",
           UNPROVEN: "  UNPROVEN — not enough evidence. This is not a pass."}[code])
    return code


# ------------------------------------------------------------------ offline

def self_test() -> int:
    """Pin the legs to the shapes production actually had and will have.

    The first case is the one that matters: the 137 real rows must make Leg 1
    RED. A gate that goes green on today's data is written wrong, and this is
    where that is caught rather than in a month.
    """
    t0 = dt.datetime(2026, 8, 25, 12, 0, 0, tzinfo=dt.timezone.utc)

    def row(delay_s, span_s, arrive_s=0.0, rid="x"):
        created = t0 + dt.timedelta(seconds=arrive_s)
        start = created - dt.timedelta(seconds=delay_s)
        end = None if span_s is None else start + dt.timedelta(seconds=span_s)
        return {"id": rid, "created": created, "start": start, "end": end}

    # Today's production shape: push-time stamping, no end at all.
    broken = [row(0.053, None, arrive_s=i * 30) for i in range(30)]
    # An honest build: words appear, 3 s of speech, flushed after the 2.6 s gap.
    honest = [row(3.2, 3.0, arrive_s=i * 30) for i in range(30)]
    aliased = [row(3.2, 0.0, arrive_s=i * 30) for i in range(30)]

    cases = [
        ("the 137 stored rows, in shape: postmark start, no end",
         broken, FAIL, "leg 1  the stamp is not the postmark"),
        ("an honest build, no queue flush in the window",
         honest, UNPROVEN, "leg 4  the queue preserved the stamp"),
        ("one instant written into both columns — the likeliest wrong fix",
         aliased, FAIL, "leg 2  start and end are two instants"),
        ("four rows on a fresh build: not enough to speak",
         honest[:4], UNPROVEN, "scope"),
    ]
    bad = 0
    print("\n  SELF-TEST — the legs against the shapes production has and will have")
    print("  " + "-" * 76)
    for why, rows, expected, expect_leg in cases:
        code, results = evaluate(rows)
        named = [n for c, n, _ in results if c == expected and expect_leg in n]
        ok = code == expected and (named or expect_leg == "any")
        bad += 0 if ok else 1
        print(f"  [{'PASS' if ok else 'FAIL'}] exit {code} (want {expected}) "
              f"via '{expect_leg}'   {why}")
    # Leg 3 and Leg 5 need their own shapes.
    future = honest[:] + [row(3.2, 40.0, arrive_s=900, rid="future")]
    code, results = evaluate(future)
    ok3 = any(c == FAIL and "leg 3" in n for c, n, _ in results)
    bad += 0 if ok3 else 1
    print(f"  [{'PASS' if ok3 else 'FAIL'}] leg 3 catches a row that finished "
          f"speaking after the server received it")

    # A queue flush that KEPT its stamps: three rows arriving together, spoken
    # minutes apart. And the same burst re-stamped at flush, which must be red.
    # Three rows that ARRIVE 0.3s apart and were SPOKEN five minutes apart:
    # the shape of a tunnel emptying. The delays must differ by minutes, not by
    # seconds — an earlier version of this fixture spread them 1.4s and made
    # leg 5 look broken when it was reading a burst that really had collapsed.
    kept = honest[:] + [row(600 + i * 300, 3.0, arrive_s=1000 + i * 0.3, rid=f"k{i}")
                        for i in range(3)]
    code, results = evaluate(kept)
    ok5 = any(c == PASS and "leg 5" in n for c, n, _ in results)
    restamped = honest[:] + [row(1.0 + i * 0.2, 3.0, arrive_s=1000 + i * 0.3, rid=f"r{i}")
                             for i in range(3)]
    _, results_r = evaluate(restamped)
    ok5b = any(c == FAIL and "leg 5" in n for c, n, _ in results_r)
    bad += 0 if ok5 else 1
    bad += 0 if ok5b else 1
    print(f"  [{'PASS' if ok5 else 'FAIL'}] leg 5 passes a burst that kept its stamps")
    print(f"  [{'PASS' if ok5b else 'FAIL'}] leg 5 catches a burst re-stamped at flush")
    print("  " + "-" * 76)
    print(f"  {7 - bad}/7 cases correct\n")
    return 1 if bad else 0


def replay(path: str, min_build: int) -> int:
    """Run the legs against a stored dump. Used to prove the gate goes RED on
    the rows production already has, which is the only claim about this work
    that can be checked without a phone."""
    rows = json.load(open(path))
    if isinstance(rows, dict):
        rows = rows.get("items") or rows.get("rows") or []
    builds = sorted({build_of(r.get("device_id", "")) for r in rows} - {None})
    print(f"\n  replaying {len(rows)} stored row(s) from {path}")
    print(f"  builds present: {builds}   scope floor: build {min_build}")
    scoped = qualifying(rows, min_build=min_build)
    if not scoped:
        # Deliberate: say what the answer WOULD be on this dump's own build, so
        # a replay of pre-fix rows still reports on them instead of shrugging.
        floor = min(builds) if builds else 0
        print(f"  no row is at or above build {min_build}; re-scoping to build "
              f"{floor} so the stored rows can still be measured")
        scoped = qualifying(rows, min_build=floor)
    print(f"  {len(scoped)} qualifying row(s)")
    code, results = evaluate(scoped)
    return report(code, results)


# --------------------------------------------------------------------- live

def fetch(filter_expr: str, per_page: int = 500) -> list:
    r = requests.get(f"{PB}/api/collections/events/records",
                     headers=headers(), timeout=45,
                     params={"perPage": per_page, "filter": filter_expr,
                             "sort": "-created", "fields": FIELDS})
    r.raise_for_status()
    return r.json().get("items", [])


def count(filter_expr: str) -> int:
    r = requests.get(f"{PB}/api/collections/events/records",
                     headers=headers(), timeout=30,
                     params={"perPage": 1, "filter": filter_expr, "fields": "id"})
    r.raise_for_status()
    return int(r.json().get("totalItems", 0))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--min-build", type=int, default=MIN_BUILD)
    ap.add_argument("--min-rows", type=int, default=MIN_ROWS)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--replay", metavar="PATH",
                    help="run the legs against a stored dump instead of live")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if args.replay:
        return replay(args.replay, args.min_build)

    now = dt.datetime.now(dt.timezone.utc)
    since = (now - dt.timedelta(hours=args.hours)).strftime("%Y-%m-%d %H:%M:%S")

    try:
        rows = fetch(f'kind="transcript" && created >= "{since}"')
        server_writes = count(f'device_id="{SERVER_DEVICE}" && created >= "{since}"')
    except Exception as e:
        print(f"\n  [....] the backend could not be read: {type(e).__name__}: {e}")
        print("  UNPROVEN — a gate that cannot read is not a gate that passes.")
        return UNPROVEN

    # LEG 6, the precondition. Without it a deaf phone produces a gate that
    # finds no violations and prints a clean bill of health — which is exactly
    # the failure are_the_ears_live.py was written for.
    if not rows:
        print(f"\n  [....] leg 6  the ears are alive at all")
        print(f"         ZERO transcripts in {args.hours:.0f}h while the server "
              f"wrote {server_writes} row(s) of its own.")
        print("  UNPROVEN — nothing was heard, so there is nothing to measure. "
              "Run overnight/are_the_ears_live.py.")
        return UNPROVEN

    scoped = qualifying(rows, min_build=args.min_build)
    builds = sorted({build_of(r.get("device_id", "")) for r in rows} - {None})
    print(f"\n  {len(rows)} transcript row(s) in {args.hours:.0f}h; builds {builds}")
    print(f"  {len(scoped)} qualifying (build >= {args.min_build}, not typed)")
    if rows and not scoped:
        print(f"\n  [....] no row comes from build {args.min_build} or newer.")
        print("  UNPROVEN — the phone is delivering, but not from a build that "
              "sends two instants. Install it.")
        return UNPROVEN
    code, results = evaluate(scoped, min_rows=args.min_rows)
    return report(code, results)


if __name__ == "__main__":
    sys.exit(main())
