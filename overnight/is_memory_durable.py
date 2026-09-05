#!/usr/bin/env python3
"""Is the owner's mind actually being kept, where it is actually kept?

On Railway an owner's memory.db sat on a disk and `consolidation_gate.py`
could glob it. On Cloudflare the container's filesystem is scratch: it dies
with the instance. The durable copy is one object in R2 —
`anticipy-owner-state/owners/<ref>/memory.db` — written by the snapshot loop
in brain/container_entry.py every ANTICIPY_STATE_SNAPSHOT_SECONDS (60).

NOTHING MEASURED THAT OBJECT. Audit F29: `grep -rniE "anticipy-owner-state|r2
object|snapshot" overnight/*.py` found one hit, consolidation_gate.py globbing
`state_root()/*/memory.db` on the LOCAL host — which on Cloudflare is an empty
directory, so it reads green over nothing. The ledger line for memory said
`NOT HERE — the next morning's recall is the test`, and a leg-less organ gets
re-litigated by hand every time somebody wonders. Meanwhile the R2 half is
perfectly provable from a laptop, with no phone: it was proven by hand on
2026-09-05 (94,208 bytes, 37 episodes, newest 3 s before that owner's newest
decided row) and that hand-proof is what this file makes repeatable.

THE CONTROL, and why it is not a clock threshold in disguise. "Fresh" here is
not "recent by the wall clock" — an owner who said nothing all day SHOULD have
an old memory.db, and calling that a fault would be the same mistake
`is_the_brain_live.py` makes about silence. The control is the owner's own
newest DECIDED row on the backend: the server wrote it, so at that moment the
brain was alive and thinking. If she decided something and the durable copy of
her memory is older than that decision by more than one snapshot interval plus
slack, the snapshot loop is not keeping up — the container is writing to a disk
that dies. A quiet owner is quiet on both halves and this leg says UNPROVEN,
never green.

WHY THIS IS NOT A LAW 1 VIOLATION: every value here is structure — an object's
existence and byte count, a MAX(ts) out of a SQLite table, a row's `updated`
stamp, a subtraction between two timestamps. The `text` column is never
requested and the episodes' text is never read; the query is `max(ts)`, and
that is the whole of it.

READ-ONLY, on both halves: `wrangler r2 object get` (never a put, never a
delete) into a temporary file that is removed, and one GET per owner against
the backend. `--remote` is NOT optional — without it wrangler answers out of
local storage and reports a miss for an object that is plainly there, which is
a false negative that has already cost somebody an afternoon.

    python3 overnight/is_memory_durable.py
    python3 overnight/is_memory_durable.py --owner qeuy6sv1raof9rw
    python3 overnight/is_memory_durable.py --self-test

Exit code is the verdict:

    0   every served owner's mind is in R2 and no newer thinking is missing
    1   a served owner has NO memory.db in R2 (their container aborts at boot),
        or R2 is behind their newest decision by more than a snapshot window
    2   UNPROVEN — wrangler or the backend could not be read, or no owner has
        decided anything in the window, so there is nothing to be behind
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)
import _env  # noqa: E402  sibling module; gates are run as scripts

import requests  # noqa: E402

OK, BAD, INFO = "PASS", "FAIL", "...."

BUCKET = "anticipy-owner-state"
PREFIX = "owners"
MEMORY_NAME = "memory.db"
# migration/config/wrangler.brain.jsonc: ANTICIPY_STATE_SNAPSHOT_SECONDS.
SNAPSHOT_SECONDS = 60
# One missed snapshot is a tick that lost a race; two minutes past the interval
# is a loop that is not running. Slack, not a meaning threshold: it is the
# width of the crash-loss window the design already accepts.
SLACK_SECONDS = 180
BRAIN_CONFIG = os.path.join(ROOT, "migration", "config", "wrangler.brain.jsonc")
WORKERS_DIR = os.path.join(ROOT, "migration", "workers")


def backend_url() -> str:
    return (os.environ.get("ANTICIPY_PB")
            or os.environ.get("ANTICIPY_BACKEND_URL")
            or "https://api.anticipy.ai").rstrip("/")


def headers() -> dict:
    h = {"X-Anticipy-Worker": "1"}
    token = os.environ.get("ANTICIPY_SERVICE_TOKEN")
    if token:
        h["X-Anticipy-Token"] = token
    return h


def served_owners(config_path: str = BRAIN_CONFIG) -> list[str]:
    """Who this fleet serves, read from the deploy's own configuration.

    ANTICIPY_SERVE_OWNERS is the allowlist; with ANTICIPY_MAX_OWNER_WORKERS at
    0 it is the whole serve set (research/2026-09-05-brain-of-record.md). The
    cap is reported separately so a run against a fleet with discovery on says
    plainly that it did not enumerate the discovered owners — `wrangler r2
    object list` does not exist in this wrangler, so a leg cannot walk the
    bucket and must probe known refs.
    """
    try:
        with open(config_path, encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        return []
    hit = re.search(r'"ANTICIPY_SERVE_OWNERS"\s*:\s*"([^"]*)"', raw)
    if not hit:
        return []
    return [x.strip() for x in hit.group(1).split(",") if x.strip()]


def configured_cap(config_path: str = BRAIN_CONFIG) -> str:
    try:
        with open(config_path, encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        return "?"
    hit = re.search(r'"ANTICIPY_MAX_OWNER_WORKERS"\s*:\s*"([^"]*)"', raw)
    return hit.group(1) if hit else "?"


def _wrangler() -> list[str] | None:
    local = os.path.join(WORKERS_DIR, "node_modules", ".bin", "wrangler")
    if os.path.exists(local):
        return [local]
    if shutil.which("wrangler"):
        return ["wrangler"]
    if shutil.which("npx"):
        return ["npx", "wrangler"]
    return None


def fetch_memory(ref: str, dest: str) -> bool | None:
    """Pull one owner's memory.db out of R2. True written, False absent,
    None wrangler could not be run at all (which is not evidence of absence).
    """
    cmd = _wrangler()
    if cmd is None:
        return None
    key = f"{BUCKET}/{PREFIX}/{ref}/{MEMORY_NAME}"
    try:
        proc = subprocess.run(
            cmd + ["r2", "object", "get", key, "--remote", "--file", dest],
            capture_output=True, text=True, timeout=180, cwd=WORKERS_DIR)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode == 0 and os.path.exists(dest) and os.path.getsize(dest):
        return True
    blob = f"{proc.stdout}\n{proc.stderr}".lower()
    # Told apart on purpose: an object that is not there is a RED finding about
    # an owner; a credential that cannot read the bucket is UNPROVEN about the
    # gate. Reading the second as the first is exactly the confusion audit F28
    # found inside the container.
    if "not found" in blob or "does not exist" in blob or "404" in blob:
        return False
    return None


def newest_episode_ts(path: str) -> float | None:
    """MAX(ts) out of the snapshot. None when there are no episodes yet."""
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            row = db.execute("SELECT max(ts) FROM episodes").fetchone()
    except sqlite3.Error:
        return None
    return float(row[0]) if row and row[0] is not None else None


def newest_decision_ts(ref: str, pb: str = "") -> float | None:
    """When this owner's brain last decided something, off the backend. None
    when it never has, or could not be read."""
    pb = pb or backend_url()
    try:
        r = requests.get(f"{pb}/api/collections/events/records",
                         headers=headers(), timeout=30,
                         params={"perPage": 1, "sort": "-updated",
                                 "filter": f'owner_ref="{ref}" && decision!=""',
                                 "fields": "updated"})
        if r.status_code != 200:
            return None
        items = (r.json() or {}).get("items", [])
    except Exception:
        return None
    if not items:
        return None
    stamp = str(items[0].get("updated") or "")
    v = stamp.replace("Z", "+00:00").replace(" ", "T", 1)
    try:
        when = dt.datetime.fromisoformat(v)
    except ValueError:
        return None
    if not when.tzinfo:
        when = when.replace(tzinfo=dt.timezone.utc)
    return when.timestamp()


def owner_verdict(ref: str, present, episode_ts, decided_ts,
                  window: float = SNAPSHOT_SECONDS + SLACK_SECONDS) -> tuple:
    """One owner's answer, pure. (exit_code, status, sentence).

    POLARITY, written here because this is where it is decided:
      * absent object for a SERVED owner is RED, never "new owner" — the
        container refuses to boot without it (brain/container_entry.py) and
        the brain-deploy pre-flight refuses the deploy, so a leg that shrugged
        would contradict both.
      * unreadable ANYTHING is UNPROVEN. A leg that cannot be tested does not
        pass, and must not fail either: a red leg nobody can act on gets muted.
      * no decision anywhere is UNPROVEN even though the object exists: the
        object being there proves storage, not that the loop is keeping up.
    """
    if present is None:
        return 2, INFO, f"{ref}: R2 could not be read, so nothing was measured"
    if not present:
        return 1, BAD, (f"{ref}: NO {MEMORY_NAME} in R2 — this owner is served, "
                        "so their container aborts at boot and their mind is "
                        "not being kept anywhere")
    if decided_ts is None:
        return 2, INFO, (f"{ref}: the object is there, but this owner has "
                         "decided nothing to be behind — storage proven, "
                         "freshness unproven")
    if episode_ts is None:
        return 1, BAD, (f"{ref}: the durable copy holds NO episodes while the "
                        "backend shows decided work — nothing she thought is "
                        "being kept")
    behind = decided_ts - episode_ts
    if behind > window:
        return 1, BAD, (f"{ref}: the durable copy is {behind / 60:.1f} min "
                        f"behind this owner's newest decision (ceiling "
                        f"{window / 60:.0f} min) — the snapshot loop is not "
                        "keeping up and a lost container loses that gap")
    return 0, OK, (f"{ref}: memory in R2 is current with the newest decision "
                   f"({behind:+.0f}s)")


def roll_up(codes: list[int]) -> int:
    """RED beats UNPROVEN beats green, and an empty run is UNPROVEN."""
    if not codes:
        return 2
    if 1 in codes:
        return 1
    if 2 in codes:
        return 2
    return 0


def self_test() -> int:
    cases = [
        (("o1", True, 1000.0, 1010.0), 0, "snapshot 10s behind the decision"),
        (("o1", True, 1000.0, 900.0), 0, "memory ahead of the decision: fine"),
        (("o1", True, 1000.0, 1239.0), 0, "239s: inside the window"),
        (("o1", True, 1000.0, 1300.0), 1, "five minutes behind: the loop stalled"),
        (("o1", False, None, 1000.0), 1, "served owner with no object at all"),
        (("o1", False, None, None), 1, "no object, quiet owner: still red"),
        (("o1", True, None, 1000.0), 1, "object with no episodes, but she decided"),
        (("o1", True, None, None), 2, "brand-new owner, nothing to compare"),
        (("o1", True, 1000.0, None), 2, "no decision in the window: unproven"),
        (("o1", None, None, None), 2, "R2 unreadable: not a verdict about memory"),
    ]
    bad = 0
    print("\n  SELF-TEST — one owner's verdict against the shapes R2 can hold")
    print("  " + "-" * 76)
    for args, expected, why in cases:
        code = owner_verdict(*args)[0]
        ok = code == expected
        bad += 0 if ok else 1
        print(f"  [{'PASS' if ok else 'FAIL'}] present={str(args[1]):<5} "
              f"episode={str(args[2]):<7} decided={str(args[3]):<7} -> exit "
              f"{code} (want {expected})   {why}")
    roll = [(([0, 0], 0), "all green"), (([0, 2], 2), "one unproven"),
            (([0, 2, 1], 1), "one red"), (([], 2), "no owners at all")]
    for (codes, expected), why in roll:
        got = roll_up(codes)
        ok = got == expected
        bad += 0 if ok else 1
        print(f"  [{'PASS' if ok else 'FAIL'}] roll-up {str(codes):<12} -> exit "
              f"{got} (want {expected})   {why}")
    print("  " + "-" * 76)
    total = len(cases) + len(roll)
    print(f"  {total - bad}/{total} cases correct\n")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--owner", action="append", default=[],
                    help="owner ref to check (repeatable); defaults to the "
                         "brain deploy's ANTICIPY_SERVE_OWNERS")
    ap.add_argument("--self-test", action="store_true",
                    help="check the verdict logic offline and exit")
    args = ap.parse_args()
    if args.self_test:
        return self_test()

    _env.load_and_announce(ROOT)
    pb = backend_url()
    rows: list[tuple[str, str, str]] = []
    owners = args.owner or served_owners()
    cap = configured_cap()

    if not owners:
        print(f"\n  IS MEMORY DURABLE?   {BUCKET}")
        print("  [....] no served owners could be read from "
              "migration/config/wrangler.brain.jsonc")
        print("  UNPROVEN — a leg that cannot be tested does not pass\n")
        return 2

    rows.append((INFO, "owners this deploy serves",
                 f"{', '.join(owners)} (ANTICIPY_SERVE_OWNERS)"))
    # The cap in the config file is NOT the cap that ran: brain-deploy takes it
    # as a workflow input and research/2026-09-05-brain-of-record.md records
    # the live value as 0. So this row names its source and does not pretend to
    # know the fleet — it says what it could not enumerate, which is the honest
    # half. `wrangler r2 object list` does not exist in this wrangler, so a leg
    # cannot walk the bucket and must probe refs it was told about.
    rows.append((INFO, "owners this leg did NOT check",
                 f"any served by discovery — ANTICIPY_MAX_OWNER_WORKERS reads "
                 f"{cap} in wrangler.brain.jsonc, but the deploy input is the "
                 "authority; pass --owner <ref> to check one by name"))

    codes = []
    for ref in owners:
        with tempfile.TemporaryDirectory(prefix="anticipy-memory-check-") as tmp:
            dest = os.path.join(tmp, f"{ref}.db")
            present = fetch_memory(ref, dest)
            episode_ts = newest_episode_ts(dest) if present else None
            size = os.path.getsize(dest) if present and os.path.exists(dest) else 0
        decided_ts = newest_decision_ts(ref, pb)
        code, status, sentence = owner_verdict(ref, present, episode_ts, decided_ts)
        codes.append(code)
        if present:
            rows.append((INFO, f"{ref} memory.db in R2", f"{size} bytes"))
        rows.append((status, f"THE MIND OF {ref}", sentence))

    final = roll_up(codes)
    width = max(len(r[1]) for r in rows) + 2
    print(f"\n  IS MEMORY DURABLE?   {BUCKET} (control: {pb})")
    print("  " + "-" * (width + 34))
    for status, name, detail in rows:
        print(f"  [{status}] {name.ljust(width)} {detail}")
    print("  " + "-" * (width + 34))
    if final == 1:
        print("  A SERVED OWNER'S MIND IS NOT BEING KEPT. See the red row above.\n")
    elif final == 2:
        print("  UNPROVEN — a leg that cannot be tested does not pass\n")
    else:
        print("  EVERY SERVED OWNER'S MIND IS IN R2 AND CURRENT\n")
    return final


if __name__ == "__main__":
    sys.exit(main())
