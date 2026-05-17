"""MH-P7 gate: multi-action conflict resolution.

Scripted conflict scenarios. Binds on:
  ZERO STALE EXECUTION  no action invalidated by a newer action,
    a cancel, or a world-satisfaction is ever executed.
  ZERO DOUBLE-BOOKING   at most one action executes per resource.
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
    from app.recovery.conflicts import (PendingAction, reconcile,
                                        safe_to_execute)

    print("== MH-P7 GATE (multi-action conflict resolution) ==")
    log, ok = [], True

    # Scenario: dinner booked 7pm, then "make it 8pm", then "actually
    # 8:30"; a separate flowers order; an old email the world already
    # sent; and a cancelled cab.
    pend = [
        PendingAction("dinner-7pm", "dinner", "reserve", seq=1,
                      detail={"time": "19:00"}),
        PendingAction("dinner-8pm", "dinner", "reserve", seq=2,
                      detail={"time": "20:00"}),
        PendingAction("dinner-830", "dinner", "reserve", seq=3,
                      detail={"time": "20:30"}),
        PendingAction("flowers", "flowers", "order", seq=1),
        PendingAction("old-email", "q3-email", "email", seq=1,
                      world_satisfied=True),
        PendingAction("cab", "cab", "reserve", seq=1, cancelled=True),
    ]
    recon = reconcile(pend)

    # zero stale execution: every stale/cancelled/killed action fails
    # the executor guard.
    by_id = {a.action_id: a for a in pend}
    stale_like = (recon.stale + recon.cancelled + recon.killed)
    none_exec = all(not safe_to_execute(by_id[i], recon)
                    for i in stale_like)
    log.append(f"  stale={recon.stale} cancelled={recon.cancelled} "
               f"killed={recon.killed}")
    log.append(f"  BINDING zero stale execution (all "
               f"{len(stale_like)} blocked by the guard) -> {none_exec}")
    ok &= none_exec

    # the only dinner that may run is the newest (8:30)
    dinner_winner = recon.bookings.get("dinner")
    dinner_ok = (dinner_winner == "dinner-830"
                 and safe_to_execute(by_id["dinner-830"], recon)
                 and not safe_to_execute(by_id["dinner-7pm"], recon)
                 and not safe_to_execute(by_id["dinner-8pm"], recon))
    log.append(f"  BINDING dinner winner={dinner_winner} (newest only) "
               f"-> {dinner_ok}")
    ok &= dinner_ok

    # zero double-booking: one execution per resource, exactly
    execed = recon.executed
    per_resource = {}
    for aid in execed:
        per_resource.setdefault(by_id[aid].resource, []).append(aid)
    no_double = all(len(v) == 1 for v in per_resource.values())
    # flowers (no conflict) still executes; old-email killed; cab
    # cancelled; so executed == {dinner-830, flowers}
    expected_exec = sorted(execed) == ["dinner-830", "flowers"]
    log.append(f"  BINDING zero double-booking: per-resource="
               f"{ {k: len(v) for k, v in per_resource.items()} } "
               f"executed={sorted(execed)} -> "
               f"{no_double and expected_exec}")
    ok &= no_double and expected_exec

    fr = subprocess.run(["git", "status", "--porcelain"] + FROZEN,
                         cwd=str(ENGINE.parent), capture_output=True,
                         text=True)
    fc = fr.stdout.strip() == ""
    log.append(f"  BINDING frozen paths clean -> {fc}")
    ok &= fc

    for ln in log:
        print(ln)
    print(f"MH_P7_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
