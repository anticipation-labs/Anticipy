"""THE CONSOLIDATION GATE. Does the nightly pass actually run, in production?

Two waves of memory work now ride on one unproven precondition, and this file
is the leg that stops it being unproven quietly.

WHAT RIDES ON IT

  * `profile_facts.kind` — "stable" or "situation" — is what the ranker's decay
    term reads (brain/memory.py `_HALF_LIFE_DAYS`). It exists to fix a measured
    6x inversion: a 90-day-old importance-5 "allergic to shellfish" scoring
    0.625 against 3.909 for a 1-day-old importance-4 "mom is in hospital", on
    the ranker that feeds the briefing and every prompt's memory block.
  * `retired_ts` — supersession — is what stops "partner is Sarah" being an
    input to a booking four months after he said they broke up.

`Memory.consolidate()` is the SOLE WRITER of both. It returns
`{"ran": False, "reason": "no llm"}` with no key and `"llm is not live"` with a
dead one, and `worker.run_nightly_consolidation` swallows every failure by
design so it can never take hearing down with it — the only trace is a
`print()` into a log nobody queries. So both fixes can be perfectly green in
the repository and completely inert on the deployed brain, with nothing
anywhere going red. That is the exact Law-3 failure this repo has already paid
for twice (extension 0.3.3 live against 0.3.9 in source; a brain acting on
"Dr. Evans" while the repo's own guard would have caught it).

The leg was specified in `.superpowers/sdd/library-wave-1b-report.md` and in
the module docstring of `tests/test_worker_consolidation.py`, by a wave whose
scope did not include `overnight/`. This is that specification, written.

--------------------------------------------------------------------------
HOW THIS AVOIDS BEING SATISFIED BY SILENCE
--------------------------------------------------------------------------
A leg that passes because nothing ran is the bug, not the pass. Three separate
legs in this repo already had that shape, and one of them is why
`overnight/tape_gate.py` argues about it at length. Every door is nailed shut
here on purpose:

  * NO STORE FOUND IS A FAILURE, not a skip. Run this on a laptop and it fails
    saying so — the answer only exists where the brain runs. "A leg that cannot
    be tested does not pass" (done_gate.py's doctrine).
  * EVERY STORE HAVING NOTHING IN IT IS A FAILURE. A deployment that has heard
    nothing gives consolidation nothing to do, so a pass over it proves
    nothing; leg 1 says so rather than counting an empty store as evidence.
  * BOTH HALVES ARE REQUIRED AND NEITHER IS SUFFICIENT. `last_run_ts` alone
    goes green on a store with nothing to distill — the pass "ran" and wrote
    nothing. A written `kind` alone goes green on one ancient pass and would
    never notice consolidation dying afterwards. Together they say the thing
    the wave-1 report could only assert in prose.
  * THE COLUMNS COME FIRST (leg 2). If the deployed brain predates the ranking
    fix, the store has no `kind` column at all, and a leg reading it would
    error rather than report the truth: prod is serving stale code. The store
    is the fingerprint — the retrofit runs on every `Memory()` open, so the
    column's presence is proof the deployed brain opened it.

RED HERE IS CORRECT UNTIL A DEPLOY AND ONE QUIET-HOURS NIGHT WITH A LIVE MODEL.
That is the property Law 3 wants: a leg that does not forget.

--------------------------------------------------------------------------
READ-ONLY, AND IT HAS TO BE
--------------------------------------------------------------------------
This opens the live per-owner databases with `mode=ro` and raw SQL. It
deliberately does NOT use `brain.memory.Memory`, because `Memory.__init__`
runs `executescript(SCHEMA)` and `_retrofit_columns()` — so merely measuring
production would WRITE to it, and worse, would add the very columns leg 2
exists to find missing. A gate that fixes what it is measuring measures
nothing.

Run, on the host where the brain runs:

    python3 overnight/consolidation_gate.py
    python3 overnight/consolidation_gate.py --db /data/owners/<ref>/memory.db
    ANTICIPY_STATE_ROOT=/data/owners python3 overnight/consolidation_gate.py
"""
from __future__ import annotations

import argparse
import glob
import os
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# One SQLite file per owner, mode 0o700 — brain/supervisor.py:31 and :92.
# The env var is read the same way the supervisor reads it so this gate and
# the brain cannot disagree about where the stores are.
DEFAULT_STATE_ROOT = "/data/owners"

# HOW STALE IS DEAD. The pass runs during quiet hours, at most once a night
# (worker.CONSOLIDATE_MIN_GAP_SECONDS), so 24h is the healthy interval and 48h
# is one whole missed night plus slack for a deploy or a restart. Tighter and
# the gate cries wolf over a single redeploy; looser and a brain that stopped
# consolidating on Friday reads healthy until Monday.
STALE_AFTER_SECONDS = 48 * 3600

# The source label consolidate() writes. A `kind` on a row sourced "interview"
# or "supervised_mail" would prove nothing about the nightly pass: those paths
# take `kind` as a parameter and nobody passes one.
CONSOLIDATION_SOURCE = "consolidation"


class LegFailed(Exception):
    """The message is what the owner reads. Say what is wrong and what it
    costs, never just that an assertion failed."""


def state_root() -> str:
    return os.environ.get("ANTICIPY_STATE_ROOT", DEFAULT_STATE_ROOT)


def find_stores(explicit: str = "") -> list[str]:
    """Every per-owner memory.db this host holds, newest-looking first.

    `ANTICIPY_MEMORY_DB` is included because the founder's account keeps its
    original path through the multi-owner migration (brain/supervisor.py:87-94)
    — it is the one store with the longest history and the one most likely to
    have something to consolidate, so leaving it out would measure everybody
    except the person who has been using this longest."""
    if explicit:
        return [explicit]
    found = []
    legacy = (os.environ.get("ANTICIPY_MEMORY_DB") or "").strip()
    if legacy and legacy != ":memory:" and os.path.exists(legacy):
        found.append(legacy)
    for path in sorted(glob.glob(os.path.join(state_root(), "*", "memory.db"))):
        if path not in found:
            found.append(path)
    return found


def open_ro(path: str) -> sqlite3.Connection:
    """Read-only, by URI. See the module docstring: opening these through
    brain.memory.Memory would run the schema and the column retrofit against
    production, which would silently repair the exact thing leg 2 looks for."""
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def columns(db: sqlite3.Connection, table: str) -> set:
    return {r[1] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}


def state_value(db: sqlite3.Connection, key: str) -> str:
    row = db.execute(
        "SELECT value FROM consolidation_state WHERE key=?", (key,)).fetchone()
    return row[0] if row else ""


# --------------------------------------------------------------------------
# THE SHARED PRECONDITION.
#
# EVERY leg asks this first, not just leg 1. A gate is read one line at a time
# and its legs get run in isolation, so "there was nothing to look at" has to
# be a failure INSIDE each leg rather than a fact established once at the top —
# the first draft of this file had leg 2 printing "every live store carries
# kind, retired_ts and retired_by" against a list of zero stores, which is a
# green light produced by an empty for-loop. That is precisely the shape this
# whole gate exists to refuse.
# --------------------------------------------------------------------------
def measurable(stores: list[str]) -> list[tuple]:
    """The stores that can testify: (path, episode count) for each one holding
    at least one episode. Raises rather than returning empty.

    A store with zero episodes is excluded rather than failed, because a
    brand-new owner who has not been heard yet is a normal state and a gate
    that went red the day somebody signed up would be turned off within a
    week. It is only ALL of them being empty that means nothing was measured.
    """
    if not stores:
        raise LegFailed(
            f"no owner memory database found under {state_root()!r} and "
            "ANTICIPY_MEMORY_DB names none either. This gate asks whether the "
            "nightly pass RAN, and that answer only exists where the brain "
            "runs — on a laptop there is nothing here to read. Run it on the "
            "deploy host, or point it at a copy with --db. A leg that cannot "
            "be tested does not pass")
    out = []
    for path in stores:
        try:
            db = open_ro(path)
        except sqlite3.Error as e:
            raise LegFailed(
                f"{path} exists but will not open read-only ({e}), so this "
                "gate cannot say anything about it either way")
        try:
            n = db.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
        except sqlite3.Error as e:
            raise LegFailed(
                f"{path} has no readable episodes table ({e}) — that is not a "
                "memory database this brain wrote")
        finally:
            db.close()
        if n:
            out.append((path, n))
    if not out:
        raise LegFailed(
            f"{len(stores)} owner database(s) found and every one of them has "
            "ZERO episodes. Consolidation distills episodes, so a pass over "
            "these would correctly do nothing and prove nothing. Either the "
            "deployment has never heard a word — which is its own emergency — "
            "or this gate is pointed at fresh files rather than the live "
            "ones. Nothing was measured, so nothing passes")
    return out


def _named(path: str) -> str:
    """The owner ref a store belongs to, for output that fits on a line."""
    return os.path.basename(os.path.dirname(path)) or os.path.basename(path)


# --------------------------------------------------------------------------
# LEG 1 — THERE IS SOMETHING TO MEASURE
#
# The precondition, stated as its own leg so the failure reads as what it is.
# A gate run where no brain runs, or against a deployment that has never heard
# a word, has no evidence either way — and reporting "no problems found" from
# no evidence is how a fix stays inert for a month.
# --------------------------------------------------------------------------
def leg_1_a_store_exists(stores: list[str]) -> str:
    active = measurable(stores)
    return (f"{len(active)} of {len(stores)} owner store(s) hold episodes ("
            + ", ".join(f"{_named(p)}:{n}" for p, n in active) + ")")


# --------------------------------------------------------------------------
# LEG 2 — THE DEPLOYED BRAIN IS THIS BRAIN
#
# Law 3, checked the only honest way available here: by what the deployed code
# leaves behind, not by a hash of what somebody meant to upload. `_ADDED_COLUMNS`
# is replayed on EVERY Memory() open, so if the worker touching this store
# carried the ranking and supersession code, the columns are there. If they are
# not, prod is serving code older than both fixes and legs 3 and 4 would be
# measuring a brain that cannot pass them.
# --------------------------------------------------------------------------
def leg_2_columns_present(stores: list[str]) -> str:
    measurable(stores)
    missing = {}
    for path in stores:
        db = open_ro(path)
        try:
            have = columns(db, "profile_facts")
        finally:
            db.close()
        gone = {"kind", "retired_ts", "retired_by"} - have
        if gone:
            missing[path] = sorted(gone)
    if missing:
        lines = "; ".join(f"{p} lacks {', '.join(c)}"
                          for p, c in missing.items())
        raise LegFailed(
            f"the live store does not carry the columns this brain writes: "
            f"{lines}. The column retrofit runs on every Memory() open, so a "
            "missing column means the worker touching this store is OLDER "
            "than the fix — the ranking decay term and supersession are not "
            "merely unproven in production, they are not deployed. Deploy, "
            "then run this again")
    return (f"all {len(stores)} live store(s) carry kind, retired_ts and "
            "retired_by")


# --------------------------------------------------------------------------
# LEG 3 — THE NIGHTLY PASS RAN, RECENTLY   (half (a) of the specified leg)
#
# `last_run_ts` is stamped by consolidate() and by nothing else, and only on a
# pass that completed. Alone this is not enough — see leg 4 — but without it a
# brain whose model key expired months ago looks identical to a healthy one.
# --------------------------------------------------------------------------
def leg_3_it_ran_recently(stores: list[str], now: float) -> str:
    active = measurable(stores)
    ages, never = [], []
    for path, _n in active:
        db = open_ro(path)
        try:
            tables = {r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            raw = state_value(db, "last_run_ts") \
                if "consolidation_state" in tables else ""
        finally:
            db.close()
        try:
            ts = float(raw or 0)
        except ValueError:
            ts = 0.0
        (never if ts <= 0 else ages).append(path if ts <= 0
                                            else (path, (now - ts) / 3600.0))
    if never:
        raise LegFailed(
            f"{len(never)} owner store(s) with episodes in them have NEVER "
            f"completed a consolidation pass ({', '.join(_named(p) for p in never)}). "
            "consolidate() stamps last_run_ts on every pass that finishes, so "
            "no stamp means no pass has ever finished — no model, a dead "
            "model, or a quiet-hours window that is never reached. Every fact "
            "in those stores is unlabelled, so the decay half of the ranker "
            "is inert and no contradicted fact can ever be retired")
    stale = [(p, h) for p, h in ages if h > STALE_AFTER_SECONDS / 3600.0]
    if stale:
        worst = max(h for _p, h in stale)
        raise LegFailed(
            f"the last consolidation pass was {worst:.0f} hours ago "
            f"({len(stale)} of {len(ages)} store(s) past the "
            f"{STALE_AFTER_SECONDS // 3600}h line). The pass is nightly, so "
            "this is at least one missed night. While it is not running the "
            "profile stops learning, no fact gains a stability verdict, and "
            "no contradicted fact is retired — she goes on asserting things "
            "the owner has already corrected")
    return (f"every store with episodes consolidated within "
            f"{max(h for _p, h in ages):.0f}h "
            f"(freshest {min(h for _p, h in ages):.0f}h)")


# --------------------------------------------------------------------------
# LEG 4 — IT WROTE WHAT THE RANKER READS   (half (b))
#
# The half that catches a pass that runs and achieves nothing. `kind` is
# written by consolidate() alone, from a field only a model can fill, so a
# non-null `kind` on a row sourced "consolidation" is proof that a LIVE model
# answered — which is the whole question. Restricted to that source on purpose:
# remember_fact takes `kind` as a parameter, so a label on an interview or a
# supervised_mail row would prove somebody passed an argument, not that the
# nightly pass thought about anything.
# --------------------------------------------------------------------------
def leg_4_it_wrote_a_kind(stores: list[str]) -> str:
    active = measurable(stores)
    counts = []
    for path, _n in active:
        db = open_ro(path)
        try:
            labelled = db.execute(
                "SELECT COUNT(*) FROM profile_facts "
                "WHERE kind IS NOT NULL AND source=?",
                (CONSOLIDATION_SOURCE,)).fetchone()[0]
            total = db.execute(
                "SELECT COUNT(*) FROM profile_facts WHERE source=?",
                (CONSOLIDATION_SOURCE,)).fetchone()[0]
        finally:
            db.close()
        counts.append((path, labelled, total))
    if not any(labelled for _p, labelled, _t in counts):
        distilled = sum(t for _p, _l, t in counts)
        raise LegFailed(
            "not one consolidated fact in any live store carries a stability "
            f"verdict ({distilled} consolidated facts, 0 with a kind). "
            "consolidate() is the only writer of `kind` and it fills it from "
            "a field only the model can answer, so this is the pass running "
            "against a model that is not answering — or a `kind` the model "
            "omits every time, which the prompt allows and which means the "
            "same thing here. Until one lands, every fact decays on the "
            "default 30-day half-life and the measured shellfish inversion is "
            "still live in production, however green the repository is")
    best = max(counts, key=lambda c: c[1])
    return (f"{sum(l for _p, l, _t in counts)} consolidated fact(s) carry a "
            f"model-written kind (best store {_named(best[0])}: "
            f"{best[1]}/{best[2]})")


# --------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default="",
                    help="one memory.db to measure instead of scanning "
                         "ANTICIPY_STATE_ROOT")
    args = ap.parse_args(argv)

    stores = find_stores(args.db)
    now = time.time()

    legs = [
        (1, "THERE IS SOMETHING TO MEASURE", lambda: leg_1_a_store_exists(stores)),
        (2, "THE DEPLOYED BRAIN IS THIS BRAIN", lambda: leg_2_columns_present(stores)),
        (3, "THE NIGHTLY PASS RAN", lambda: leg_3_it_ran_recently(stores, now)),
        (4, "IT WROTE WHAT THE RANKER READS", lambda: leg_4_it_wrote_a_kind(stores)),
    ]

    print()
    print(f"  CONSOLIDATION GATE   tree: {ROOT}")
    print(f"                     stores: {state_root()}"
          f"{' + ' + args.db if args.db else ''}")
    print("  " + "-" * 62)
    first = None
    for num, name, fn in legs:
        try:
            detail = fn()
            print(f"  [{num}] PASS  {name}")
            print(f"        {detail}")
        except LegFailed as e:
            mark = "FAIL" if first is None else "fail"
            print(f"  [{num}] {mark}  {name}")
            print(f"        {e}")
            if first is None:
                first = (num, name, str(e))
        except Exception as e:  # noqa: BLE001
            # The gate erroring is a FAILURE, never a skip. A leg that cannot
            # be tested does not pass, and a gate that shrugs at its own
            # exceptions is the silence this file exists to close.
            print(f"  [{num}] FAIL  {name}")
            print(f"        gate itself errored: {type(e).__name__}: {e}")
            if first is None:
                first = (num, name, f"gate errored: {e}")
    print("  " + "-" * 62)
    if first is None:
        print("  RUNNING — the nightly pass is alive and writing what the "
              "ranker reads")
        print()
        return 0
    num, name, why = first
    print(f"  NOT RUNNING — first failing leg: {num} ({name})")
    print(f"  {why}")
    print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
