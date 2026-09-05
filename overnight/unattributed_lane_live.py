#!/usr/bin/env python3
"""Did an UNATTRIBUTED act or ask take the governed lane, live?

Omi port 10a (2026-09-05): a transcript line whose triage verdict said "act"
or "ask" but carried NO addressee — the field absent or unreadable — used to
take the direct lane: an immediate text with no quiet hours, no meeting
posture and no shard floor, the lane reserved for a line the model positively
says was aimed at her. On 2026-08-23 attribution was the field absent on all
137 lines. Since the port such a line takes the AMBIENT lane: one held card
whose params carry `lane`, one text through the SPEAK_ONCE `ambient_act` kind
(quiet hours -> defer, meeting -> digest), or a goalless question parked in the
valve and asked by the worker after ASK_QUIET_S of silence.

This leg reads the durable record and reports whether that held, in
production, over the last N days. It is a TRIPWIRE, not a gate that can go
green by itself: the control — act/ask rows with addressee "" and explicit
false — was ZERO on the one measured day (94/94 non-fallback Tejas rows carried
an addressee), so it reads UNPROVEN until an unattributed act/ask actually
happens live. The proof of record until then is the offline mutation suite,
tests/test_no_verdict_is_below_the_floor.py. Green here is never earned by
absence.

WHAT IT READS, and why none of it is a word of anybody's speech:

  control      events: kind="transcript", decision in (act, ask),
               addressee="", explicit=false. mark_processed stamps addressee
               only when truthy, so a None verdict reads "" on the row. Fields
               requested: id, created, updated, goal, decision. Never `text`.
  direct sign  jobs created within 90s of the control row's `updated` (the
               moment the worker stamped it) whose `goal` equals the row's
               stamped goal and whose params JSON carries NO "lane" key. Every
               ambient job carries lane "ambient" or "desk"; the direct lane
               never sets one (brain/anticipy_core.py, the direct-lane
               params). A goalless direct ask is caught by the second sign.
  direct sign  events: kind="anticipy_says", decision="ask", goal="" created
               within 15s of a control row's `updated`. A parked ask posts the
               same shape but only after ASK_QUIET_S (120s) of silence, so a
               goalless ask row on the heels of the stamp is the direct
               branch's "Quick question".
  Law 3        the code the live worker runs must be the code this tree holds.
               brain/worker.py prints `_brain_fingerprint()` at startup; pass
               it as --fingerprint and it is compared to the tree's. Absent or
               mismatched, the leg can report RED but never GREEN — `railway
               up` reports success while failing.

A second number is printed and is NOT a verdict: the size of the "quiet
ambient ignore" bucket — transcript rows with decision="ignore" and goal=""
whose addressee is "", person, self or dictation. The port's hands floor
(an absent `owes` on an overheard line withholds her hands) returns exactly
that shape, and the reason it writes begins "no verdict" — but reason is not
stamped on the row, only printed in the worker log (`heard: ... [reason]`), so
the bucket is an UPPER BOUND on owes-blank drops and the log is where the
exact count lives: `grep -c "no verdict on whose errand" <worker log>`. A
model that starts omitting `owes` moves this bucket within a day.

Read-only. It creates nothing, patches nothing and touches no job.

    python3 overnight/unattributed_lane_live.py
    python3 overnight/unattributed_lane_live.py --days 7 --fingerprint 1a2b3c4d5e6f
    python3 overnight/unattributed_lane_live.py --self-test

Exit code is the verdict:

    0   GREEN — at least one unattributed act/ask occurred, none of them took
        the direct lane, and the live fingerprint matches this tree
    1   RED — an unattributed act/ask took the direct lane
    2   UNPROVEN — the backend could not be read, no unattributed act/ask
        occurred in the window, or the fingerprint is unverified
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

import os as _os, sys as _sys  # noqa: E402
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import _env  # noqa: E402  sibling module; gates are run as scripts
_ENV_LOADED = _env.load_and_announce(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

import requests  # noqa: E402

PB = (os.environ.get("ANTICIPY_PB")
      or os.environ.get("ANTICIPY_BACKEND_URL")
      or "https://backend-production-61e0a.up.railway.app").rstrip("/")

# Seconds between the worker stamping a transcript row and the job it minted
# from it, or the text it sent about it. One poll cycle is 2s; a hearing pass
# that also spends model calls can take tens of seconds. Ninety is generous
# and still an order of magnitude under ASK_QUIET_S.
JOB_WINDOW_S = 90.0
# A goalless direct ask is posted in the SAME cycle as the stamp. The parked
# ask waits ASK_QUIET_S = 120s of silence first, so 15s separates the two
# populations with room on both sides.
ASK_WINDOW_S = 15.0
DEFAULT_DAYS = 7

OK, BAD, INFO = "PASS", "FAIL", "...."

# The addressee values that reach the ambient lane's do-nothing verdicts,
# plus "" for a None verdict. Read as labels, never as words.
QUIET_BUCKET_ADDRESSEES = ("", "person", "self", "dictation")


def headers() -> dict:
    h = {"X-Anticipy-Worker": "1"}
    token = os.environ.get("ANTICIPY_SERVICE_TOKEN")
    if token:
        h["X-Anticipy-Token"] = token
    return h


def parse_ts(value: str):
    if not value:
        return None
    v = value.replace("Z", "+00:00").replace(" ", "T", 1)
    try:
        parsed = dt.datetime.fromisoformat(v)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def fetch_all(collection: str, filter_expr: str, fields: str) -> list:
    """Every matching row, paged, carrying only the named fields."""
    out: list = []
    page = 1
    while True:
        r = requests.get(f"{PB}/api/collections/{collection}/records",
                         headers=headers(), timeout=30,
                         params={"perPage": 500, "page": page,
                                 "filter": filter_expr, "fields": fields,
                                 "sort": "created"})
        r.raise_for_status()
        body = r.json()
        items = body.get("items", [])
        out.extend(items)
        if page >= int(body.get("totalPages", 1)) or not items:
            return out
        page += 1


def count(collection: str, filter_expr: str) -> int:
    r = requests.get(f"{PB}/api/collections/{collection}/records",
                     headers=headers(), timeout=30,
                     params={"perPage": 1, "filter": filter_expr, "fields": "id"})
    r.raise_for_status()
    return int(r.json().get("totalItems", 0))


def _params_of(job: dict) -> dict:
    raw = job.get("params")
    if isinstance(raw, dict):
        return raw
    try:
        got = json.loads(raw or "{}")
    except Exception:
        return {}
    return got if isinstance(got, dict) else {}


def direct_lane_hits(control: list, jobs: list, asks: list) -> list:
    """Pure: which control rows show a direct-lane signature. Each hit is
    (event_id, why). Reads labels, timestamps and the presence of a key —
    never a word."""
    hits = []
    for ev in control:
        stamped = parse_ts(ev.get("updated") or ev.get("created") or "")
        if stamped is None:
            continue
        goal = (ev.get("goal") or "").strip()
        if goal:
            for job in jobs:
                if (job.get("goal") or "").strip() != goal:
                    continue
                when = parse_ts(job.get("created") or "")
                if when is None or abs((when - stamped).total_seconds()) > JOB_WINDOW_S:
                    continue
                if "lane" not in _params_of(job):
                    hits.append((ev.get("id"), f"job {job.get('id')} minted with no "
                                               f"params.lane {int((when - stamped).total_seconds())}s "
                                               "after the stamp — the direct lane's signature"))
                    break
        for say in asks:
            if (say.get("goal") or "").strip():
                continue
            when = parse_ts(say.get("created") or "")
            if when is None:
                continue
            delta = (when - stamped).total_seconds()
            if 0 <= delta <= ASK_WINDOW_S:
                hits.append((ev.get("id"), f"a goalless ask was sent {int(delta)}s after "
                                           "the stamp — the direct branch, not the parked "
                                           f"valve (which waits {120}s of silence)"))
                break
    return hits


def verdict(control: int, hits: int, fingerprint_ok: bool) -> tuple[int, str, str]:
    """The whole decision as a pure function. Absence never earns green."""
    if control == 0:
        return 2, INFO, ("no unattributed act/ask occurred in the window — there "
                         "was nothing for the governed lane to govern. UNPROVEN, "
                         "not green: the offline mutation suite is the proof of "
                         "record until this fires")
    if hits:
        return 1, BAD, (f"{hits} of {control} unattributed act/ask line(s) took "
                        "the DIRECT lane — an uninvited text or an unheld job "
                        "with no verdict behind it")
    if not fingerprint_ok:
        return 2, INFO, (f"all {control} unattributed act/ask line(s) took the "
                         "governed lane, but the live worker's fingerprint is "
                         "unverified — pass --fingerprint from the worker's "
                         "startup log; Law 3 does not take a deploy's word")
    return 0, OK, (f"all {control} unattributed act/ask line(s) took the governed "
                   "lane, on code this tree holds")


def self_test() -> int:
    now = dt.datetime(2026, 9, 5, 12, 0, tzinfo=dt.timezone.utc)

    def ts(seconds: float) -> str:
        return (now + dt.timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S.000Z")

    ev = {"id": "e1", "updated": ts(0), "goal": "book a table at Earls", "decision": "act"}
    ambient_job = {"id": "j1", "goal": "book a table at Earls", "created": ts(3),
                   "params": json.dumps({"source": "x", "lane": "desk"})}
    direct_job = {"id": "j2", "goal": "book a table at Earls", "created": ts(3),
                  "params": json.dumps({"source": "x"})}
    late_direct_job = dict(direct_job, id="j3", created=ts(JOB_WINDOW_S + 30))
    parked_ask = {"id": "s1", "goal": "", "created": ts(130), "decision": "ask"}
    direct_ask = {"id": "s2", "goal": "", "created": ts(2), "decision": "ask"}
    goalless_ev = {"id": "e2", "updated": ts(0), "goal": "", "decision": "ask"}

    cases = [
        ("ambient held card: lane=desk", [ev], [ambient_job], [], 0),
        ("direct-lane job: no params.lane", [ev], [direct_job], [], 1),
        ("a same-goal job outside the window is not this line's", [ev], [late_direct_job], [], 0),
        ("parked ask after ASK_QUIET_S", [goalless_ev], [], [parked_ask], 0),
        ("direct goalless ask in the same cycle", [goalless_ev], [], [direct_ask], 1),
        ("no control rows at all", [], [direct_job], [direct_ask], 0),
    ]
    bad = 0
    print("\n  SELF-TEST — the direct-lane signature against the shapes the record can hold")
    print("  " + "-" * 76)
    for why, control, jobs, asks, want in cases:
        got = len(direct_lane_hits(control, jobs, asks))
        ok = got == want
        bad += 0 if ok else 1
        print(f"  [{'PASS' if ok else 'FAIL'}] hits={got} (want {want})   {why}")
    vcases = [
        (0, 0, True, 2, "no control: UNPROVEN, never green by absence"),
        (3, 0, False, 2, "governed but fingerprint unverified: UNPROVEN"),
        (3, 1, False, 1, "one direct-lane hit: RED whatever the fingerprint says"),
        (3, 0, True, 0, "governed, fingerprint matches: GREEN"),
    ]
    for control, hits, fp, want, why in vcases:
        code, _, _ = verdict(control, hits, fp)
        ok = code == want
        bad += 0 if ok else 1
        print(f"  [{'PASS' if ok else 'FAIL'}] exit {code} (want {want})   {why}")
    print("  " + "-" * 76)
    total = len(cases) + len(vcases)
    print(f"  {total - bad}/{total} cases correct\n")
    return 1 if bad else 0


def tree_fingerprint() -> str:
    try:
        from brain.worker import _brain_fingerprint
        return _brain_fingerprint()
    except Exception as e:  # pragma: no cover - import environment
        return f"unknown ({e.__class__.__name__})"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=float, default=DEFAULT_DAYS)
    ap.add_argument("--fingerprint", default="",
                    help="the _brain_fingerprint() the live worker printed at startup")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()

    rows: list[tuple[str, str, str]] = []
    now = dt.datetime.now(dt.timezone.utc)
    since = (now - dt.timedelta(days=args.days)).strftime("%Y-%m-%d %H:%M:%S")

    try:
        healthy = requests.get(f"{PB}/api/health", timeout=20).status_code == 200
    except Exception as e:
        healthy = False
        rows.append((INFO, "backend reachable", str(e)[:70]))
    if not healthy:
        print(f"\n  THE UNATTRIBUTED LANE, LIVE   {PB}")
        print("  [....] the backend could not be read, so nothing here was measured")
        print("  UNPROVEN — a leg that cannot be tested does not pass\n")
        return 2

    try:
        control = fetch_all(
            "events",
            f'kind="transcript" && (decision="act" || decision="ask") && '
            f'addressee="" && explicit=false && created >= "{since}"',
            "id,created,updated,goal,decision")
        jobs = fetch_all("jobs", f'created >= "{since}"',
                         "id,goal,params,created") if control else []
        asks = fetch_all(
            "events",
            f'kind="anticipy_says" && decision="ask" && created >= "{since}"',
            "id,goal,created,decision") if control else []
        quiet_bucket = count(
            "events",
            f'kind="transcript" && decision="ignore" && goal="" && '
            f'created >= "{since}" && ('
            + " || ".join(f'addressee="{a}"' for a in QUIET_BUCKET_ADDRESSEES) + ")")
        attributed = count(
            "events",
            f'kind="transcript" && (decision="act" || decision="ask") && '
            f'addressee!="" && created >= "{since}"')
    except Exception as e:
        print(f"\n  THE UNATTRIBUTED LANE, LIVE   {PB}")
        print(f"  [....] the collections could not be read: {str(e)[:70]}")
        print("  UNPROVEN — a leg that cannot be tested does not pass\n")
        return 2

    hits = direct_lane_hits(control, jobs, asks)
    tree_fp = tree_fingerprint()
    live_fp = (args.fingerprint or "").strip()
    fingerprint_ok = bool(live_fp) and live_fp == tree_fp

    rows.append((INFO, f"act/ask rows WITH an addressee in {args.days:g}d", str(attributed)))
    rows.append((INFO, f"act/ask rows with NO addressee in {args.days:g}d",
                 f"{len(control)} (the control)"))
    rows.append((INFO, "quiet ambient ignore bucket (ignore, no goal)",
                 f"{quiet_bucket} — an UPPER BOUND on owes-blank drops; the exact "
                 "count is the worker log's \"no verdict on whose errand\" lines"))
    for ev_id, why in hits:
        rows.append((BAD, f"event {ev_id}", why))
    rows.append((OK if fingerprint_ok else INFO, "live code is this tree (Law 3)",
                 f"tree {tree_fp}; live {live_fp or '(not given — pass --fingerprint)'}"))
    code, status, sentence = verdict(len(control), len(hits), fingerprint_ok)
    rows.append((status, "NO VERDICT IS BELOW THE FLOOR", sentence))

    width = max(len(r[1]) for r in rows) + 2
    print(f"\n  THE UNATTRIBUTED LANE, LIVE   {PB}")
    print("  " + "-" * (width + 34))
    for st, name, detail in rows:
        print(f"  [{st}] {name.ljust(width)} {detail}")
    print("  " + "-" * (width + 34))
    if code == 1:
        print("  AN UNATTRIBUTED LINE TOOK THE DIRECT LANE. Read the event and the job\n"
              "  it names; the lane gate in brain/anticipy_core.py compares against\n"
              "  DIRECT_ADDRESSEES and must not have been widened.\n")
    elif code == 2:
        print("  UNPROVEN — a leg that cannot be tested does not pass\n")
    else:
        print("  THE GOVERNED LANE HELD\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
