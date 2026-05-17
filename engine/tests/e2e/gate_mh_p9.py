"""MH-P9 gate: observability per-decision trace.

A synthetic WRONG action is recorded through the trace, the live
state is then DISCARDED, and the complaint must be fully answered
from the persisted trace bytes alone. Binds on:

  RECONSTRUCTABLE  every stage of the wrong decision is present in
    the persisted trace; the reconstruction names what was heard,
    how attributed, how resolved, why acted, and what was sent.
  ROOT CAUSE       the single decisive wrong step is identified
    from the trace alone.
  USER-SCOPED      the trace is queryable for exactly one user's
    one complaint.
  frozen action engine + reasoning + cascade git-clean.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

FROZEN = ["engine/app/action_engine", "desktop", "engine/app/anticipy",
          "engine/app/proactive/demand_detection.py",
          "engine/app/proactive/hedge_filter.py",
          "engine/app/proactive/intent_extraction.py",
          "engine/app/proactive/llm_adapter.py"]


def main() -> int:
    from app.observ.trace import DecisionTrace, TraceStore

    print("== MH-P9 GATE (observability per-decision trace) ==")
    log, ok = [], True
    store = TraceStore()

    # A synthetic WRONG action: a low-confidence object ref was
    # resolved from a stale memory draw and the action proceeded
    # anyway, sending the wrong file to the wrong person.
    t = DecisionTrace(user_id="complainant")
    did = t.decision_id
    (t.record("heard", text="send her the deck", speaker="WEARER",
              ts=101.0)
      .record("attributed", label="WEARER", anchor_score=0.81)
      .record("gate", decision="ACT")
      .record("resolved", refs=[
          {"surface": "the deck", "value": "Q2_OLD.pdf",
           "conf": 0.52, "source": "memory_draw"},
          {"surface": "her", "value": "dana@investor.example",
           "conf": 0.55, "source": "recency"}])
      .record("timing", when="now")
      .record("reconcile", result="none")
      .record("comms", channel="email", to="dana@investor.example",
              body="Here is the deck: Q2_OLD.pdf")
      .record("outcome", outcome="ACTED",
              why="proceeded despite sub-threshold refs"))
    store.put(t)

    # discard the live object: only the persisted store remains.
    del t

    # --- USER-SCOPED query for the one complaint ---
    rows = store.for_user("complainant")
    other = store.for_user("someone-else")
    scoped_ok = len(rows) == 1 and other == [] and rows[0].decision_id == did
    log.append(f"  BINDING user-scoped query: rows={len(rows)} "
               f"other_user={len(other)} -> {scoped_ok}")
    ok &= scoped_ok

    rec = store.get(did)               # fetched from persisted bytes

    # --- RECONSTRUCTABLE ---
    complete = rec.is_complete()
    narrative = rec.reconstruct()
    has_all = all(k in narrative for k in
                  ["heard", "attributed", "frozen gate", "ref ",
                   "SENT via email", "outcome ACTED"])
    log.append(f"  BINDING reconstructable from persisted trace alone: "
               f"complete={complete} all_stages_in_narrative={has_all} "
               f"-> {complete and has_all}")
    ok &= complete and has_all

    # --- ROOT CAUSE from the trace alone ---
    rc = rec.root_cause()
    rc_ok = rc is not None and "low-confidence ref" in rc and \
        "0.52" in rc
    log.append(f"  BINDING root cause identified: {rc!r} -> {rc_ok}")
    ok &= rc_ok

    log.append("  --- reconstruction (from persisted bytes) ---")
    for ln in narrative.splitlines():
        log.append(f"    {ln}")

    fr = subprocess.run(["git", "status", "--porcelain"] + FROZEN,
                         cwd=str(ENGINE.parent), capture_output=True,
                         text=True)
    fc = fr.stdout.strip() == ""
    log.append(f"  BINDING frozen paths clean -> {fc}")
    ok &= fc

    for ln in log:
        print(ln)
    print(f"MH_P9_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
