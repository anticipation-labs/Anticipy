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
      or "https://api.anticipy.ai").rstrip("/")

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


def reservation_link(e: dict) -> str:
    """The slot a said row was sent on ("uninvited:<owner>:<day>:<n>"), or ""."""
    link = str(e.get("external_event_id") or "")
    if link.startswith("uninvited:") and link.endswith(":said"):
        return link[:-len(":said")]
    return ""


def uninvited_door(e: dict, by_decision_only: bool = False) -> bool:
    """Did this said row leave through an uninvited door? Judged by the DOOR
    (a field's closed value, or a field's emptiness), never by the words.

    decision "clock" is the clock loop; "ask" with an EMPTY goal is the parked
    ambient question (a sufficiency question carries its job's goal and is the
    opposite of uninvited — he set the work in motion); "digest" is the
    meeting digest. Any row carrying a reservation link counts too — that is
    how the overheard-plan receipt (decision "act") is seen at all.
    """
    decision = str(e.get("decision") or "")
    if decision in ("clock", "digest"):
        return True
    if decision == "ask" and not str(e.get("goal") or "").strip():
        return True
    return (not by_decision_only) and bool(reservation_link(e))


def slot_key(row: dict) -> tuple[str, str] | None:
    """(owner_ref, owner-local day) from a slot id the brain minted."""
    link = str(row.get("external_event_id") or "")
    parts = link.split(":")
    if len(parts) != 4 or parts[0] != "uninvited":
        return None
    return parts[1], parts[2]


def evaluate_slots(slots: list[dict], said: list[dict]) -> list[tuple[str, str, str]]:
    """Judge the uninvited_slot rows the brain wrote against what it promises
    about them. Pure, like evaluate_rules, and pinned offline the same way.

    Per (owner, day) — the day stamped INTO the slot id, which is the day the
    brain judged — at most UNINVITED_TEXTS_PER_DAY rows can exist (the unique
    index makes a fourth impossible, so a fourth is a different brain);
    linked said rows can never outnumber the slots they claim; and no slot
    may carry decision "released", because there is no release in this tree
    (a slot is burned, never given back) and one means the deployed brain is
    not this brain.
    """
    out: list[tuple[str, str, str]] = []

    def check(name: str, good: bool, detail: str = "") -> None:
        out.append((OK if good else BAD, name, detail))

    taken: dict[tuple[str, str], int] = defaultdict(int)
    for s in slots:
        key = slot_key(s)
        if key:
            taken[key] += 1
    busiest = max(taken.values()) if taken else 0
    check(f"no more than {UNINVITED_TEXTS_PER_DAY} slot row(s) per owner-day (port 10b)",
          busiest <= UNINVITED_TEXTS_PER_DAY,
          f"busiest day: {busiest}" if taken else "no slot rows")

    linked: dict[tuple[str, str], int] = defaultdict(int)
    for e in said:
        key = slot_key({"external_event_id": reservation_link(e)})
        if key:
            linked[key] += 1
    over = {k: n for k, n in linked.items() if n > taken.get(k, 0)}
    check("linked said rows never outnumber their slots (port 10b)",
          not over,
          (f"{len(over)} owner-day(s) with more said rows than slots, "
           f"worst {max(over.values())} said on "
           f"{taken.get(next(iter(over)), 0)} slot(s)")
          if over else
          f"{sum(linked.values())} said row(s) on {sum(taken.values())} slot(s)")

    released = [s for s in slots if str(s.get("decision") or "") == "released"]
    check("no slot was ever released (port 10b: burned, never given back)",
          not released,
          f"{len(released)} released slot(s)" if released else "none released")
    return out


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
    # Bucketed by HIS midnight for the same reason, and worker.py stamps the
    # slot day the same way (`_uninvited_day`, owner-local under CLOCK_TZ). On
    # a UTC boundary one Vancouver day splits across two dates, so a day
    # spent exactly at the limit reads as two quiet ones — the same defect
    # wearing the opposite sign, and the direction that hides a real breach.
    #
    # Omi port 10b (2026-09-05): "uninvited" is the DOOR a row left through,
    # never its words. Until this date only decision=="clock" was counted —
    # the one uninvited kind the brain's own counter excluded. Now every door
    # counts, each row once: see uninvited_door().
    per_day: dict[tuple[str, str], int] = defaultdict(int)
    for e in said:
        if uninvited_door(e):
            ts = parse_ts(e.get("created", ""))
            if ts:
                ref = (e.get("owner_ref") or "").strip()
                local = ts.astimezone(owner_zone(zones, ref))
                per_day[(ref, local.date().isoformat())] += 1
    busiest = max(per_day.values()) if per_day else 0
    check(f"no more than {UNINVITED_TEXTS_PER_DAY} uninvited message(s) a day (ex 28)",
          busiest <= UNINVITED_TEXTS_PER_DAY,
          f"busiest day: {busiest}" if per_day else "none sent")

    # ---- port 10b: every uninvited door row carries its reservation ---------
    # The brain in this tree reserves one uninvited_slot row BEFORE Twilio and
    # links the said row to it (external_event_id "uninvited:...:said"). A
    # clock, parked-ask or digest row with no link is a door that sent without
    # reserving — or a row written by a brain older than this tree. Either
    # reading is "the deployed brain is not this brain"; the second ages out
    # of the window within a day of the deploy. The overheard-plan receipt is
    # not distinguishable from an invited act by its fields (both are
    # decision "act"), so that door is pinned offline only, in
    # tests/test_uninvited_budget.py, and this rule says so rather than
    # pretending to see it.
    unlinked = [e for e in said if uninvited_door(e, by_decision_only=True)
                and not reservation_link(e)]
    check("every uninvited door row carries its reservation (port 10b)",
          not unlinked,
          (f"{len(unlinked)} row(s) sent without a slot: "
           f"{next(iter(unlinked)).get('decision')!r} "
           f"{(next(iter(unlinked)).get('text') or '')[:36]!r}")
          if unlinked else
          "clock/ask/digest rows all linked; the overheard-plan door is "
          "pinned offline only")

    # ---- port 10b: the two doors declared OFF the budget stay bounded -------
    # `welcome` is once per phone by durable stamp and invited by saving the
    # number; the deafness notice is a fault report bounded to one per 24h by
    # already_raised(DEAF_GOAL, decision="deaf"). Neither takes a slot, so
    # each gets its own row here — a regression in those guards must show as
    # itself, never laundered into the three.
    for decision, name in (("deaf", "the deafness notice"),
                           ("welcome", "the welcome")):
        exempt: dict[tuple[str, str], int] = defaultdict(int)
        for e in said:
            if e.get("decision") != decision:
                continue
            ts = parse_ts(e.get("created", ""))
            if ts:
                ref = (e.get("owner_ref") or "").strip()
                local = ts.astimezone(owner_zone(zones, ref))
                exempt[(ref, local.date().isoformat())] += 1
        worst_exempt = max(exempt.values()) if exempt else 0
        check(f"{name} at most once per owner-day (off the budget, port 10b)",
              worst_exempt <= 1,
              f"busiest day: {worst_exempt}" if exempt else "none sent")

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

    # The reservation rows (port 10b). Read from two hours before the said
    # window so a slot taken just before `since` for a said row just after it
    # is not reported as a said row with no slot.
    slot_since = (dt.datetime.now(dt.timezone.utc)
                  - dt.timedelta(hours=args.hours + 2)).strftime("%Y-%m-%d %H:%M:%S")
    slots: list[dict] | None
    try:
        slots = fetch("events", {"perPage": 500, "sort": "-created",
                                 "filter": f'kind="uninvited_slot" && created>="{slot_since}"'})
    except Exception as e:
        check("the uninvited_slot rows can be read (port 10b)", False, str(e)[:88])
        slots = None
    if slots is not None:
        rows.extend(evaluate_slots(slots, said))
        if not slots:
            note("uninvited_slot rows read back from production",
                 "0 — nothing uninvited in the window — not a pass")
        else:
            note("uninvited_slot rows read back from production", f"{len(slots)}")

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
    if not slots:
        # A leg that cannot be tested does not pass (are_the_ears_live.py's
        # convention). The rules above held on what was read, but until one
        # reservation row has been read back from production the reserved
        # budget has not been seen working live, and a night with nothing
        # uninvited is exactly the night a missing reservation looks like.
        print(f"  UNPROVEN — the reserved uninvited budget (port 10b) wrote no "
              f"slot row in {args.hours:g}h; the rules above were judged on "
              f"{len(said)} message(s), and this leg is green only once a slot "
              "row has been read back and the fingerprint matches\n")
        return 2
    print("  THE DEPLOYED BRAIN IS KEEPING ITS PROMISES\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
