#!/usr/bin/env python3
"""Is the BRAIN that is running the brain I have?

`is_it_live.py` byte-verifies the extension: it fetches the served zip and
compares it to the tree. The worker has no served artifact, so it had no such
check — and that gap cost real money on 2026-08-18.

WHAT HAPPENED, since this file exists because of it:

  e4ab18ec, 2026-08-17 23:43   "One stuck task must not text him 63 times in a day"
                               added STUCK_ASKS_CEILING = 2 and the guard at
                               worker.py:1997.
  2026-08-18 16:21             a job stopped on a question and started asking.
  16:21 → 05:10 next morning   it asked EIGHTEEN more times, every ~45 minutes,
                               straight through quiet hours.

The guard was committed seventeen hours before that job even existed, and the
guard is correct: run against the live rows, asks_for_goal() returns 18 for that
exact goal and owner, and 18 >= 2. The code in the tree would have gone quiet
after the second ask. So the ceiling was not missing and not wrong — it was not
RUNNING. docs Part 3: "Fixed means live and byte-verified. 'Fixed in source' is
not fixed."

WHY THIS CHECKS BEHAVIOUR RATHER THAN A HASH:

worker.py already computes `_brain_fingerprint()` and prints it at startup, but
prints it to a log nobody queries — so proving liveness meant reading Railway's
console, which is exactly why eighteen texts went out unnoticed. A published
hash would help, but it would also pass while the behaviour was broken: the hash
says which bytes loaded, not what they did. These checks read the durable record
the brain itself writes and ask whether the RULES held. A violation here is
proof the deployed brain is not this brain, whatever any hash says.

Read-only. It creates nothing, patches nothing, and touches no job. Safe to run
against production, which is the only place the answer exists.

    python3 overnight/is_the_brain_live.py
    python3 overnight/is_the_brain_live.py --hours 48

Exit code is the verdict, like the gate: non-zero means something the brain
promises is not true in production.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from collections import Counter, defaultdict

# The credentials were always next to the gate and nothing loaded them.
import os as _os, sys as _sys  # noqa: E402
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _env  # noqa: E402  sibling module; gates are run as scripts
_ENV_LOADED = _env.load_and_announce(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests  # noqa: E402

from zoneinfo import ZoneInfo  # noqa: E402

from brain.worker import (  # noqa: E402
    CLOCK_QUIET_END,
    CLOCK_QUIET_START,
    CLOCK_TZ,
    STUCK_ASKS_CEILING,
    UNINVITED_TEXTS_PER_DAY,
    _brain_fingerprint,
)

PB = (os.environ.get("ANTICIPY_PB")
      or os.environ.get("ANTICIPY_BACKEND_URL")
      or "https://backend-production-61e0a.up.railway.app").rstrip("/")

OK, BAD, INFO = "PASS", "FAIL", "...."
rows: list[tuple[str, str, str]] = []


def check(name: str, good: bool, detail: str = "") -> bool:
    rows.append((OK if good else BAD, name, detail))
    return good


def note(name: str, detail: str = "") -> None:
    rows.append((INFO, name, detail))


def headers() -> dict:
    # Same shape brain/pb.py uses. X-Anticipy-Worker is a routing marker; the
    # token is what authenticates. Without it every read is 403 and this file
    # would report a healthy brain by reading nothing.
    h = {"X-Anticipy-Worker": "1"}
    token = os.environ.get("ANTICIPY_SERVICE_TOKEN")
    if token:
        h["X-Anticipy-Token"] = token
    return h


def fetch(collection: str, params: dict) -> list[dict]:
    r = requests.get(f"{PB}/api/collections/{collection}/records",
                     headers=headers(), params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("items", [])


def parse_ts(value: str) -> dt.datetime | None:
    """PocketBase hands back 'YYYY-MM-DD HH:MM:SS.mmmZ' — tolerate both forms.

    Always returns an AWARE datetime in UTC. PocketBase stores `created` in
    UTC and the trailing Z is sometimes absent, so a naive parse used to hand
    back a datetime carrying no zone at all — which `.astimezone()` then reads
    as the zone of whatever laptop happened to run the checker. Anchoring it
    here means every caller below is converting from a known clock.
    """
    if not value:
        return None
    v = value.replace("Z", "+00:00").replace(" ", "T", 1)
    try:
        parsed = dt.datetime.fromisoformat(v)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def owner_zone(zones: dict | None, owner_ref: str):
    """The zone the BRAIN judged this owner's hours in.

    One worker process per account, and each sets CLOCK_TZ from that owner's
    profile (worker.py's owner-context refresh). An owner with no timezone on
    file leaves their worker on the module default, so an unknown owner falls
    back to exactly the same CLOCK_TZ rather than to UTC — otherwise the
    checker judges by a clock the brain never used.
    """
    name = (zones or {}).get((owner_ref or "").strip())
    if not name:
        return CLOCK_TZ
    try:
        return ZoneInfo(name)
    except Exception:
        return CLOCK_TZ


def evaluate_rules(said: list[dict],
                   zones: dict | None = None) -> list[tuple[str, str, str]]:
    """Judge a list of anticipy_says rows against the rules the brain promises.

    Pure: no network, no clock beyond the timestamps in the rows themselves. The
    fetching lives in main(), so these rules can be driven with synthetic events
    in tests/test_brain_liveness.py — a checker that has never been shown to
    fail is indistinguishable from one that cannot.

    `zones` maps owner_ref -> IANA name, because the two rules below are about
    the OWNER'S hours and `created` is UTC. See owner_zone().
    """
    out: list[tuple[str, str, str]] = []

    def check(name: str, good: bool, detail: str = "") -> None:
        out.append((OK if good else BAD, name, detail))

    # ---- ex 18 / ex 64: one question, one second chance, then quiet ---------
    # "The wording of the obstacle changing does NOT reset the count", so this
    # counts the GOAL, exactly as asks_for_goal() does.
    asks = Counter((e.get("goal") or "").strip()
                   for e in said if e.get("decision") == "needs_user"
                   and (e.get("goal") or "").strip())
    over = {g: n for g, n in asks.items() if n > STUCK_ASKS_CEILING}
    worst = max(over.values()) if over else 0
    check(f"no task asked more than {STUCK_ASKS_CEILING}x (ex 18, ex 64)",
          not over,
          f"{len(over)} task(s) over, worst {worst}x: "
          f"{next(iter(over))[:44]!r}" if over else f"most-asked task: {max(asks.values()) if asks else 0}x")

    # ---- ex 69: nothing uninvited between 22:00 and 08:00 -------------------
    # Scoped to clock-initiated messages, which are uninvited BY DEFINITION. A
    # blocked errand of his own may legitimately text early (ex 21), so counting
    # those here would raise a false alarm — their bound is the ceiling above.
    #
    # IN HIS HOURS, NOT THE SERVER'S. `created` is UTC; the promise is in the
    # owner's zone, because that is the clock worker.py's guard uses
    # (datetime.fromtimestamp(now, CLOCK_TZ).hour). Comparing a UTC hour to an
    # owner-local constant asks a different question: Vancouver is UTC-7 in
    # summer, so everything sent 15:00-00:59 local read as "night". On
    # 2026-08-24 that reported two breaches — 21:34 and 17:31 his time, both
    # legal — and concluded the deployed brain was not this brain.
    night = []
    for e in said:
        if e.get("decision") != "clock":
            continue
        ts = parse_ts(e.get("created", ""))
        if not ts:
            continue
        local = ts.astimezone(owner_zone(zones, e.get("owner_ref", "")))
        if local.hour >= CLOCK_QUIET_START or local.hour < CLOCK_QUIET_END:
            night.append(e)
    check(f"nothing uninvited between {CLOCK_QUIET_START}:00 and "
          f"{CLOCK_QUIET_END}:00 (ex 69)",
          not night,
          f"{len(night)} sent in quiet hours" if night else "quiet hours respected")

    # ---- ex 28 / ex 112: the daily uninvited budget is absolute -------------
    # Bucketed by HIS midnight for the same reason, and worker.py counts the
    # day the same way (`datetime.now(CLOCK_TZ).replace(hour=0, ...)`). On a
    # UTC boundary one Vancouver day splits across two dates, so a day spent
    # exactly at the limit reads as two quiet ones — the same defect wearing
    # the opposite sign, and the direction that hides a real breach.
    per_day: dict[tuple[str, str], int] = defaultdict(int)
    for e in said:
        if e.get("decision") == "clock":
            ts = parse_ts(e.get("created", ""))
            if ts:
                ref = (e.get("owner_ref") or "").strip()
                local = ts.astimezone(owner_zone(zones, ref))
                per_day[(ref, local.date().isoformat())] += 1
    busiest = max(per_day.values()) if per_day else 0
    check(f"no more than {UNINVITED_TEXTS_PER_DAY} uninvited message(s) a day (ex 28)",
          busiest <= UNINVITED_TEXTS_PER_DAY,
          f"busiest day: {busiest}" if per_day else "none sent")

    # ---- ex 24: a follow-up says something new ------------------------------
    # "The same sentence twice is not a follow-up, it's a malfunction he can
    # see." Identical TEXT for one goal is the shape that bug takes.
    dupes = Counter(((e.get("goal") or "").strip(), (e.get("text") or "").strip())
                    for e in said if (e.get("text") or "").strip())
    repeated = {k: n for k, n in dupes.items() if n > 1}
    check("no message sent twice word for word (ex 24)",
          not repeated,
          f"{len(repeated)} repeated: {next(iter(repeated))[1][:40]!r}"
          if repeated else "every message was newly worded")

    # ---- ex 30: a message recorded as told must have actually landed --------
    unsent = [e for e in said if e.get("notified") is False]
    if unsent:
        check("nothing recorded as told that never landed (ex 30)", False,
              f"{len(unsent)} row(s) marked not-notified")

    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24.0,
                    help="how far back to read (default 24)")
    args = ap.parse_args()

    since = (dt.datetime.now(dt.timezone.utc)
             - dt.timedelta(hours=args.hours)).strftime("%Y-%m-%d %H:%M:%S")

    # A checker that reads nothing passes everything, so a failed read is a
    # failure rather than an empty clean bill of health.
    try:
        said = fetch("events", {"perPage": 500, "sort": "-created",
                                "filter": f'kind="anticipy_says" && created>="{since}"'})
    except Exception as e:
        check("the backend answers, with a token that can read", False, str(e)[:88])
        print("\n  nothing can be checked without reads. Set ANTICIPY_SERVICE_TOKEN.\n")
        return 1
    check("the backend answers, with a token that can read", True,
          f"{len(said)} message(s) in {args.hours:g}h")
    if not said:
        note("no messages in the window, so no rule could be broken", "not a pass")

    # The owner's own hours are what the quiet-hours and per-day rules are
    # about, so read the same profile column the worker reads. A failure here
    # must not fail the run: every unknown owner falls back to CLOCK_TZ, which
    # is what their worker would also have used with no timezone on file.
    zones: dict[str, str] = {}
    try:
        for p in fetch("owner_profile", {"perPage": 500}):
            ref = (p.get("owner_ref") or "").strip()
            tzname = (p.get("timezone") or "").strip()
            if ref and tzname:
                zones[ref] = tzname
        note("owner hours read from their profiles",
             f"{len(zones)} zone(s); the rest use {CLOCK_TZ}")
    except Exception as e:
        note("could not read owner timezones", f"{str(e)[:60]} — using {CLOCK_TZ}")

    rows.extend(evaluate_rules(said, zones))

    # The fingerprint cannot be fetched: worker.py prints it at startup and
    # publishes it nowhere. So state the expected value and how to compare it,
    # rather than pretending to have verified it.
    note("brain fingerprint of THIS tree", _brain_fingerprint())
    note("compare against the worker's startup log line", "grep 'brain=' in Railway")

    width = max(len(r[1]) for r in rows) + 2
    print(f"\n  IS THE BRAIN LIVE?   {PB}")
    print("  " + "-" * (width + 30))
    for status, name, detail in rows:
        print(f"  [{status}] {name.ljust(width)} {detail}")
    print("  " + "-" * (width + 30))
    failed = [r for r in rows if r[0] == BAD]
    if failed:
        print(f"  {len(failed)} RULE(S) BROKEN IN PRODUCTION")
        print("  The code in this tree enforces them, so the deployed brain is "
              "not this brain.\n")
        return 1
    print("  THE DEPLOYED BRAIN IS KEEPING ITS PROMISES\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
