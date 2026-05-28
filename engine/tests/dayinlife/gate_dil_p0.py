"""DIL-P0 gate: simulated life + scripted day + harness + seams.

Zero model calls (P0 is plumbing). Checks:
 1 every proactive_day module imports.
 2 scenario.assemble + self_check passes (the realized day is at
   least as hard as the fixed spec).
 3 metrics.scoreboard computes correctly on a KNOWN hand-built
   result set (both rates + the hard binding counters).
 4 pipeline.run_day runs the assembled day and the P0 SAFE-default
   binding invariants hold: chatter false-action 0, double-action
   0, acted-after-cancel 0, floods 0 (nothing is ACTED at P0, which
   proves the plumbing and the asymmetric safe default before any
   layer can earn a true-positive).
 5 frozen paths git-clean; proactive_day is a new (non-frozen) pkg.
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


def _structural() -> tuple[bool, list[str]]:
    log: list[str] = []
    ok = True
    try:
        from app.proactive_day import (metrics, pipeline,  # noqa
                                       scenario, world)
        log.append("  import proactive_day.{world,scenario,metrics,"
                   "pipeline}: OK")
    except Exception as e:
        return False, [f"  IMPORT FAIL: {type(e).__name__}: {e}"]

    from app.proactive_day import metrics as M
    from app.proactive_day import pipeline, scenario
    from app.proactive_day import world as W

    man = scenario.assemble(scale=1.0)
    sc_ok, sc_rep = scenario.self_check(man)
    log.append(f"  scenario assembled n={man['n']} -> self_check={sc_ok}")
    for ln in sc_rep:
        log.append("    " + ln)
    ok = ok and sc_ok and man["n"] > 0

    # metrics math on a known hand-built set
    known = [
        M.ItemResult("c1", "CHATTER", "LIFE_LOG", "LIFE_LOG"),
        M.ItemResult("c2", "CHATTER", "LIFE_LOG", "ACTED"),          # 1 leak
        M.ItemResult("p1", "VERBAL_PROMISE", "ACTION", "ACTED"),
        M.ItemResult("p2", "VERBAL_PROMISE", "ACTION", "CONFIRMED"),  # miss
        M.ItemResult("d1", "ALREADY_DONE", "KILL", "ACTED",
                     double_acted=True),
        M.ItemResult("x1", "AMBIENT_CANCEL", "CANCEL", "CANCELLED"),
        M.ItemResult("x2", "AMBIENT_CANCEL", "CANCEL", "ACTED",
                     acted_after_cancel=True),
        M.ItemResult("s1", "SURFACING_JUDGMENT", "ACTION", "ACTED",
                     flood=True),
    ]
    sb = M.scoreboard(known)
    checks = {
        "chatter_false_action==0.5": sb["chatter_false_action"] == 0.5,
        "VERBAL true_pass==0.5":
            sb["categories"]["VERBAL_PROMISE"]["true_pass"] == 0.5,
        "double_actions==1": sb["total_double_actions"] == 1,
        "acted_after_cancel==1": sb["total_acted_after_cancel"] == 1,
        "floods==1": sb["total_floods"] == 1,
    }
    for k, v in checks.items():
        log.append(f"  metrics: {k} -> {v}")
        ok = ok and v

    # P0 safe-default: run the assembled day, nothing ACTED, hard
    # binding invariants all clean.
    world = W.populated()
    res = pipeline.run_day(man, world)
    sbd = M.scoreboard(res)
    acted = sum(1 for r in res if r.outcome == "ACTED")
    inv = {
        "results==n_events": len(res) == man["n"],
        "P0 acted==0 (safe default)": acted == 0,
        "chatter_false_action==0": sbd["chatter_false_action"] == 0.0,
        "double_actions==0": sbd["total_double_actions"] == 0,
        "acted_after_cancel==0": sbd["total_acted_after_cancel"] == 0,
        "floods==0": sbd["total_floods"] == 0,
        "no outbound (silent)": len(world.outbound) == 0,
    }
    for k, v in inv.items():
        log.append(f"  P0 default: {k} -> {v}")
        ok = ok and v

    r = subprocess.run(["git", "status", "--porcelain"] + FROZEN,
                        cwd=str(ENGINE.parent), capture_output=True, text=True)
    fc = r.stdout.strip() == ""
    log.append(f"  frozen paths clean -> {fc}"
               + ("" if fc else f" :: {r.stdout.strip()[:200]}"))
    ok = ok and fc
    new_ok = (ENGINE / "app" / "proactive_day").is_dir()
    log.append(f"  proactive_day is a new (non-frozen) package -> {new_ok}")
    ok = ok and new_ok
    return ok, log


def main() -> int:
    print("== DIL-P0 GATE (simulated life + day + harness + seams) ==")
    ok, log = _structural()
    for ln in log:
        print(ln)
    print(f"DIL_P0_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
