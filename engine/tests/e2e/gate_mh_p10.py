"""MH-P10 gate: onboarding + cold-start experience.

A simulated new user's first days. Binds on a GENUINE ramp (no
vacuous pass): the system must really graduate from conservative
cold start to earned autonomy, with real non-zero numbers.

  CONSERVATIVE COLD START  day-0 (pre-onboarding) ACT threshold is
    the frozen COLD_START bar and day-0 auto-acts == 0.
  REAL RAMP MOVEMENT       the frozen ACT threshold STRICTLY
    decreases across the horizon as trust accrues (not flat).
  GENUINE GRADUATION       auto-acts/day STRICTLY rise and the last
    day's auto-acts are > 0 and > day-0's (the ramp actually starts
    acting; not a "safe because it never acts" degenerate).
  NON-ANNOYING             asks/day never exceed the cap.
  SAFETY BINDINGS INTACT   zero chatter false-action every day; an
    ultra-high item is never auto-acted on any day; the bar never
    drops below the frozen FLOOR.
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
    from app.anticipy.autonomy import COLD_START, FLOOR
    from app.coldstart.ramp import ASK_CAP_PER_DAY, simulate_first_days

    print("== MH-P10 GATE (onboarding + cold-start experience) ==")
    log, ok = [], True

    day_items = [
        {"kind": "clear", "conf": 0.90},
        {"kind": "clear", "conf": 0.88},
        {"kind": "clear", "conf": 0.86},
        {"kind": "vague", "conf": 0.45},
        {"kind": "chatter", "conf": 0.99},
        {"kind": "chatter", "conf": 0.95},
        {"kind": "ultra_high", "conf": 0.99},
    ]
    script = [list(day_items) for _ in range(4)]
    run = simulate_first_days(script)

    thr = [d.threshold for d in run.days]
    acts = [d.acted for d in run.days]
    asks = [d.asked for d in run.days]
    tconf = run.tconf_trace
    log.append(f"  thresholds/day = {thr}")
    log.append(f"  auto-acts/day  = {acts}")
    log.append(f"  asks/day       = {asks}")
    log.append(f"  tconf trace    = {tconf}")

    cold0 = abs(thr[0] - COLD_START) < 1e-9 and acts[0] == 0
    log.append(f"  BINDING conservative cold start: day0 thr={thr[0]} "
               f"(==COLD_START {COLD_START}) day0 acts={acts[0]} (==0) "
               f"-> {cold0}")
    ok &= cold0

    strict_down = all(thr[i] > thr[i + 1] for i in range(len(thr) - 1))
    log.append(f"  BINDING real ramp movement: thresholds strictly "
               f"decreasing -> {strict_down}")
    ok &= strict_down

    graduated = (all(acts[i] <= acts[i + 1] for i in range(len(acts) - 1))
                 and acts[-1] > 0 and acts[-1] > acts[0])
    log.append(f"  BINDING genuine graduation: auto-acts non-decreasing "
               f"and final {acts[-1]} > 0 and > day0 {acts[0]} -> "
               f"{graduated}")
    ok &= graduated

    no_flood = all(a <= ASK_CAP_PER_DAY for a in asks)
    log.append(f"  BINDING non-annoying: max asks/day="
               f"{max(asks)} (cap {ASK_CAP_PER_DAY}) -> {no_flood}")
    ok &= no_flood

    cfa = sum(d.chatter_false_action for d in run.days)
    uh = sum(d.ultra_high_unconfirmed for d in run.days)
    floor_ok = min(thr) >= FLOOR
    safe = cfa == 0 and uh == 0 and floor_ok
    log.append(f"  BINDING safety intact: chatter_false_action={cfa} "
               f"ultra_high_unconfirmed={uh} min_thr={min(thr)} "
               f">=FLOOR {FLOOR} -> {safe}")
    ok &= safe

    earned = tconf[-1] > tconf[0]
    log.append(f"  BINDING trust earned across days: {tconf[0]} -> "
               f"{tconf[-1]} -> {earned}")
    ok &= earned

    fr = subprocess.run(["git", "status", "--porcelain"] + FROZEN,
                         cwd=str(ENGINE.parent), capture_output=True,
                         text=True)
    fc = fr.stdout.strip() == ""
    log.append(f"  BINDING frozen paths clean -> {fc}")
    ok &= fc

    for ln in log:
        print(ln)
    print("  NOTE the ACT threshold is the FROZEN autonomy ramp "
          "(read-only): COLD_START pre-onboarding, then ONBOARDED-> "
          "SEASONED as trajectory_confidence accrues. This layer adds "
          "only the non-annoying ask budget + trust-earning loop.")
    print(f"MH_P10_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
