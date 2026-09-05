#!/usr/bin/env python3
"""Is one decision bounded on the LIVE worker?

Omi port 06 put a wall-clock deadline and a call ceiling on every decision
(brain/llm.py, "the budget") and a hearing bound on every poll turn
(brain/worker.py TURN_HEARING_SECONDS). Repo-green proves the code; this leg
asks whether the worker that is actually running enforces it, because
production has served stale code twice (HARNESS-LAWS Law 3).

THE INSTRUMENT is two numbers the worker stamps on every decided transcript
row beside the decision: `heard_ms`, how long hear() took, and
`heard_calls`, how many model calls the budget counted. The second one is
the control that makes this more than weather: on a day with no slow
decision, heard_ms is green whether or not the bound is deployed — but a row
with heard_calls ABOVE the ceiling is impossible if the deployed code
enforces it, so any such row is positive proof it does not.

Firing is not failure. A row at the deadline (heard_ms >= 150 000) or at the
ceiling (heard_calls == 32) is the bound WORKING — the slow line that would
have held the thread for half an hour was cut. Those are counted and printed
as "bound fired", never reddened. Red is a row OVER the deadline plus one
attempt's inactivity timeout (the residual the design names: a provider that
dribbles bytes can overrun by at most one attempt, because the read timeout
is per read), or over the ceiling.

WHY THE NUMBERS BELOW ARE NOT A LAW 1 VIOLATION: every one is over a duration
and a count of requests, never over content. This file never requests the
`text` column (see `fields=`), so it cannot read a word of anybody's speech
even by accident.

Read-only. It creates nothing, patches nothing and touches no job.

    python3 overnight/is_the_decision_bounded.py
    python3 overnight/is_the_decision_bounded.py --hours 48
    python3 overnight/is_the_decision_bounded.py --self-test

Exit code is the verdict:

    0   every measured decision in the window stayed inside the bound
    1   a decision overran the deadline plus one attempt, or made more calls
        than the ceiling — the deployed worker is not enforcing the bound
    2   UNPROVEN — the backend could not be read, or no decided row carries a
        measurement (a stale deploy, or the migration not applied). A leg
        that cannot be tested does not pass.

Paired with the deploy proof: the live worker's startup line prints
`budget=150s/32calls/turn300s` beside a `brain=` fingerprint equal to
`_brain_fingerprint()` in the tree.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

# The credentials were always next to the gate and nothing loaded them.
import os as _os, sys as _sys  # noqa: E402
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _env  # noqa: E402  sibling module; gates are run as scripts
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_ENV_LOADED = _env.load_and_announce(_ROOT)

import requests  # noqa: E402

# The bound is read off the brain, not copied, so this file cannot drift from
# what the worker enforces.
_sys.path.insert(0, _ROOT)
from brain.llm import (DECISION_CALL_CEILING,  # noqa: E402
                       DECISION_DEADLINE_SECONDS,
                       _ATTEMPT_TIMEOUT_SECONDS)

PB = (os.environ.get("ANTICIPY_PB")
      or os.environ.get("ANTICIPY_BACKEND_URL")
      or "https://backend-production-61e0a.up.railway.app").rstrip("/")

# The deadline, plus the one attempt of dribble the read timeout allows.
ALLOWED_MS = (DECISION_DEADLINE_SECONDS + _ATTEMPT_TIMEOUT_SECONDS) * 1000
FIRED_MS = DECISION_DEADLINE_SECONDS * 1000
CEILING = DECISION_CALL_CEILING

FULL_CYCLE_HOURS = 24
PAGE = 500

OK, BAD, INFO = "PASS", "FAIL", "...."


def headers() -> dict:
    """Same shape brain/pb.py uses. Without the token every read is 403 and
    this file would report a bounded brain by reading nothing."""
    h = {"X-Anticipy-Worker": "1"}
    token = os.environ.get("ANTICIPY_SERVICE_TOKEN")
    if token:
        h["X-Anticipy-Token"] = token
    return h


def decided_rows(since_s: str) -> list[dict]:
    """Every decided transcript row of the window — metadata only, never
    `text`. Pages until a page comes back short."""
    rows: list[dict] = []
    page = 1
    while True:
        r = requests.get(
            f"{PB}/api/collections/events/records",
            headers=headers(), timeout=30,
            params={"perPage": PAGE, "page": page, "sort": "created",
                    "filter": (f'kind="transcript" && decision != "" '
                               f'&& decision != "processing" '
                               f'&& created >= "{since_s}"'),
                    "fields": "id,created,decision,heard_ms,heard_calls"})
        r.raise_for_status()
        items = r.json().get("items", [])
        rows.extend(items)
        if len(items) < PAGE:
            return rows
        page += 1


def _num(row: dict, key: str) -> int:
    try:
        return int(row.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]


def verdict(rows: list[dict], allowed_ms: int = ALLOWED_MS,
            fired_ms: int = FIRED_MS,
            ceiling: int = CEILING) -> tuple[int, str, str, dict]:
    """The whole decision, as a pure function so it can be tested without a
    network. Returns (exit_code, status, sentence, stats).

    A row is MEASURED when either number is above zero: the worker adds the
    keys only when it measured, and PocketBase reads an unset number as 0, so
    0/0 is an echo ignored before hear(), a pre-migration row, or a deploy
    without the stamp — never a free decision.
    """
    measured = [r for r in rows
                if _num(r, "heard_ms") > 0 or _num(r, "heard_calls") > 0]
    ms = [_num(r, "heard_ms") for r in measured]
    calls = [_num(r, "heard_calls") for r in measured]
    stats = {
        "rows": len(rows), "measured": len(measured),
        "unmeasured": len(rows) - len(measured),
        "max_ms": max(ms) if ms else 0, "p95_ms": _p95(ms),
        "max_calls": max(calls) if calls else 0, "p95_calls": _p95(calls),
        "fired": sum(1 for r in measured
                     if _num(r, "heard_ms") >= fired_ms
                     or _num(r, "heard_calls") >= ceiling),
    }
    if not measured:
        return 2, INFO, (f"{len(rows)} decided row(s) and not one carries a "
                         f"measurement — a stale deploy or an unapplied "
                         f"migration; nothing here was measured"), stats
    over_calls = [r for r in measured if _num(r, "heard_calls") > ceiling]
    over_ms = [r for r in measured if _num(r, "heard_ms") > allowed_ms]
    if over_calls:
        ids = ", ".join(f"{r.get('id')}={_num(r, 'heard_calls')}"
                        for r in over_calls[:8])
        return 1, BAD, (f"{len(over_calls)} decision(s) made MORE calls than "
                        f"the ceiling of {ceiling} — impossible if the deployed "
                        f"worker enforced it: {ids}"), stats
    if over_ms:
        ids = ", ".join(f"{r.get('id')}={_num(r, 'heard_ms')}ms"
                        for r in over_ms[:8])
        return 1, BAD, (f"{len(over_ms)} decision(s) overran the deadline plus "
                        f"one attempt ({allowed_ms} ms): {ids}"), stats
    return 0, OK, (f"{len(measured)} measured decision(s), every one inside "
                   f"{allowed_ms} ms and {ceiling} calls"), stats


def self_test() -> int:
    """Exercise the verdict on the shapes the record can contain."""
    def row(i, ms, calls):
        return {"id": f"r{i}", "heard_ms": ms, "heard_calls": calls}

    ordinary = [row(i, 2_000 + 700 * i, 8 + (i % 6)) for i in range(40)]
    cases = [
        # (rows, expected_exit, why)
        (ordinary, 0, "an ordinary day: 2-30 s, 8-13 calls"),
        (ordinary + [row(99, FIRED_MS, 12)], 0,
         "a line cut AT the deadline is the bound working, not a failure"),
        (ordinary + [row(99, 40_000, CEILING)], 0,
         "a line cut AT the ceiling is the bound working"),
        (ordinary + [row(99, ALLOWED_MS + 1, 12)], 1,
         "a line OVER the deadline plus one attempt"),
        (ordinary + [row(99, 30_000, CEILING + 1)], 1,
         "a line with more calls than the ceiling: the bound is not deployed"),
        ([row(i, 0, 0) for i in range(30)], 2,
         "thirty decided rows, none measured: stale deploy or no migration"),
        ([{"id": f"r{i}", "decision": "act"} for i in range(5)], 2,
         "the columns are absent from the rows entirely"),
        ([], 2, "nothing decided in the window"),
        (ordinary + [row(99, 0, 0)], 0,
         "one unmeasured row among measured ones (an echo) does not unprove"),
    ]
    bad = 0
    print("\n  SELF-TEST — the verdict against the shapes the rows can take")
    print("  " + "-" * 76)
    for rows, expected, why in cases:
        code, _, _, stats = verdict(rows)
        ok = code == expected
        bad += 0 if ok else 1
        print(f"  [{'PASS' if ok else 'FAIL'}] rows={stats['rows']:<3} "
              f"measured={stats['measured']:<3} fired={stats['fired']:<2} "
              f"-> exit {code} (want {expected})   {why}")
    print("  " + "-" * 76)
    print(f"  {len(cases) - bad}/{len(cases)} cases correct\n")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--hours", type=float, default=FULL_CYCLE_HOURS,
                    help="window to look back over (default 24)")
    ap.add_argument("--self-test", action="store_true",
                    help="check the verdict logic offline and exit")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    rows_out: list[tuple[str, str, str]] = []
    now = dt.datetime.now(dt.timezone.utc)
    since = now - dt.timedelta(hours=args.hours)
    since_s = since.strftime("%Y-%m-%d %H:%M:%S")

    try:
        health = requests.get(f"{PB}/api/health", timeout=20)
        healthy = health.status_code == 200
    except Exception as e:
        healthy = False
        rows_out.append((INFO, "backend reachable", str(e)[:70]))
    if not healthy:
        print(f"\n  IS THE DECISION BOUNDED?   {PB}")
        print("  [....] the backend could not be read, so nothing here was measured")
        print("  UNPROVEN — a leg that cannot be tested does not pass\n")
        return 2
    rows_out.append((INFO, "backend answers /api/health", "200"))

    try:
        rows = decided_rows(since_s)
    except Exception as e:
        print(f"\n  IS THE DECISION BOUNDED?   {PB}")
        print(f"  [....] the events collection could not be read: {str(e)[:70]}")
        print("  UNPROVEN — a leg that cannot be tested does not pass\n")
        return 2

    code, status, sentence, stats = verdict(rows)
    rows_out.append((INFO, f"decided transcript rows in the last {args.hours:g}h",
                     f"{stats['rows']} ({stats['measured']} measured, "
                     f"{stats['unmeasured']} not)"))
    rows_out.append((INFO, "heard_ms max / p95",
                     f"{stats['max_ms']} / {stats['p95_ms']} "
                     f"(deadline {FIRED_MS}, allowed {ALLOWED_MS})"))
    rows_out.append((INFO, "heard_calls max / p95",
                     f"{stats['max_calls']} / {stats['p95_calls']} "
                     f"(ceiling {CEILING})"))
    rows_out.append((INFO, "bound fired",
                     f"{stats['fired']} — a line cut at the bound is the bound "
                     f"working"))
    rows_out.append((status, "THE DECISION IS BOUNDED", sentence))

    width = max(len(r[1]) for r in rows_out) + 2
    print(f"\n  IS THE DECISION BOUNDED?   {PB}")
    print("  " + "-" * (width + 34))
    for st, name, detail in rows_out:
        print(f"  [{st}] {name.ljust(width)} {detail}")
    print("  " + "-" * (width + 34))
    if code == 1:
        print("  THE BOUND IS NOT HOLDING LIVE. Compare the worker's startup line "
              "(`budget=` beside `brain=`)\n  against _brain_fingerprint() in the "
              "tree before reading this as a code defect.\n")
    elif code == 2:
        print("  UNPROVEN — a leg that cannot be tested does not pass\n")
    else:
        print("  EVERY DECISION STAYED INSIDE ITS BUDGET\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
