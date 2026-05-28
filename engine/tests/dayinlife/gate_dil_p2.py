"""DIL-P2 gate: the timing engine (Layer B).

Scoped to WHEN_DEFERRED + CHATTER + ALREADY_DONE + AMBIENT_CANCEL,
run through the real pipeline.

BINDING (hard):
  WHEN_DEFERRED zero immediate execution (no deferred item ACTED
    now) AND zero silent drop (no deferred item LIFE_LOG'd) - a
    deferred action must end DEFERRED or HELD(CONFIRMED), both
    non-immediate and non-dropped.
  CHATTER false-action <= 0.02 ; double-action == 0 ;
    acted-after-cancel == 0 (no regression).
  frozen action engine + reasoning + cascade git-clean.
REPORTED honest (no rounding):
  WHEN_DEFERRED scheduled-correctly rate (DEFERRED / n).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

CATS = ["WHEN_DEFERRED", "CHATTER", "ALREADY_DONE", "AMBIENT_CANCEL"]
FROZEN = ["engine/app/action_engine", "desktop", "engine/app/anticipy",
          "engine/app/proactive/demand_detection.py",
          "engine/app/proactive/hedge_filter.py",
          "engine/app/proactive/intent_extraction.py",
          "engine/app/proactive/llm_adapter.py"]


def main() -> int:
    from app.proactive_day import metrics as M
    from app.proactive_day import pipeline, scenario
    from app.proactive_day import world as W

    print("== DIL-P2 GATE (timing engine, Layer B) ==")
    full = scenario.assemble(scale=1.0)
    man = dict(full)
    man["events"] = [e for e in full["events"] if e["category"] in CATS]
    man["n"] = len(man["events"])
    world = W.populated()
    res = pipeline.run_day(man, world)
    sb = M.scoreboard(res)
    print(M.render(sb))

    wd = [r for r in res if r.category == "WHEN_DEFERRED"]
    n = len(wd)
    immediate = sum(1 for r in wd if r.outcome == "ACTED")
    dropped = sum(1 for r in wd if r.outcome == "LIFE_LOG")
    sched = sum(1 for r in wd if r.outcome == "DEFERRED")
    held = sum(1 for r in wd if r.outcome == "CONFIRMED")

    log, ok = [], True
    bind = (immediate == 0 and dropped == 0)
    log.append(f"  BINDING WHEN_DEFERRED n={n} immediate_exec={immediate} "
               f"(==0) silent_drop={dropped} (==0) -> {bind}")
    log.append(f"  REPORTED WHEN_DEFERRED scheduled={sched} held(confirm)="
               f"{held} of n={n} (scheduled-correctly rate="
               f"{(sched / n) if n else 0.0!r}, honest)")
    ok &= bind

    cfa = sb["chatter_false_action"]
    log.append(f"  BINDING CHATTER false_action={cfa!r} (<=0.02) "
               f"-> {cfa <= 0.02}")
    ok &= cfa <= 0.02
    da, ac = sb["total_double_actions"], sb["total_acted_after_cancel"]
    log.append(f"  BINDING double_actions={da} (==0) "
               f"acted_after_cancel={ac} (==0) -> {da == 0 and ac == 0}")
    ok &= (da == 0 and ac == 0)

    fr = subprocess.run(["git", "status", "--porcelain"] + FROZEN,
                        cwd=str(ENGINE.parent), capture_output=True, text=True)
    fc = fr.stdout.strip() == ""
    log.append(f"  BINDING frozen paths clean -> {fc}")
    ok &= fc

    for ln in log:
        print(ln)
    print(f"DIL_P2_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
