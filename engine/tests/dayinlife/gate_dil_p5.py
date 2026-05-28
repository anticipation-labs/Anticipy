"""DIL-P5 gate: personalization (Layer G).

Scoped to PERSONAL_SHORTHAND + CHATTER, run through the real
pipeline. The SAME wearer shorthand recurs through the day.

BINDING (hard):
  first occurrence of an unknown shorthand -> CONFIRMED (asked
    once, never a blind guess on unknown shorthand).
  every LATER occurrence -> resolved WITHOUT asking again
    (outcome ACTED or DEFERRED, never CONFIRMED, never LIFE_LOG).
  CHATTER false-action <= 0.02 ; double-action == 0 ;
    acted-after-cancel == 0 (no regression).
  frozen action engine + reasoning + cascade git-clean.
REPORTED honest: first-confirm rate, later-resolve rate.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

CATS = ["PERSONAL_SHORTHAND", "CHATTER"]
FROZEN = ["engine/app/action_engine", "desktop", "engine/app/anticipy",
          "engine/app/proactive/demand_detection.py",
          "engine/app/proactive/hedge_filter.py",
          "engine/app/proactive/intent_extraction.py",
          "engine/app/proactive/llm_adapter.py"]


def main() -> int:
    from app.proactive_day import metrics as M
    from app.proactive_day import pipeline, scenario
    from app.proactive_day import world as W

    print("== DIL-P5 GATE (personalization, Layer G) ==")
    full = scenario.assemble(scale=1.0)
    man = dict(full)
    man["events"] = [e for e in full["events"] if e["category"] in CATS]
    man["n"] = len(man["events"])
    ev_by_id = {e["ev_id"]: e for e in man["events"]}
    world = W.populated()
    res = pipeline.run_day(man, world)
    sb = M.scoreboard(res)

    sh = [r for r in res if r.category == "PERSONAL_SHORTHAND"]
    first = [r for r in sh if ev_by_id[r.ev_id].get("first_occurrence")]
    later = [r for r in sh if not ev_by_id[r.ev_id].get("first_occurrence")]

    log, ok = [], True
    f_conf = sum(1 for r in first if r.outcome == "CONFIRMED")
    f_ok = bool(first) and f_conf == len(first)
    log.append(f"  BINDING first-occurrence n={len(first)} CONFIRMED="
               f"{f_conf} (all) -> {f_ok}")
    ok &= f_ok

    l_resolved = sum(1 for r in later
                     if r.outcome in ("ACTED", "DEFERRED"))
    l_reasked = sum(1 for r in later if r.outcome == "CONFIRMED")
    l_dropped = sum(1 for r in later if r.outcome == "LIFE_LOG")
    l_ok = bool(later) and l_reasked == 0 and l_dropped == 0
    log.append(f"  BINDING later-occurrence n={len(later)} resolved_without_"
               f"asking={l_resolved} re_asked={l_reasked} (==0) "
               f"dropped={l_dropped} (==0) -> {l_ok}")
    ok &= l_ok
    log.append(f"  REPORTED first_confirm_rate="
               f"{(f_conf / len(first)) if first else 0.0!r} "
               f"later_resolve_rate="
               f"{(l_resolved / len(later)) if later else 0.0!r} (honest)")

    cfa = sb["chatter_false_action"]
    da, ac = sb["total_double_actions"], sb["total_acted_after_cancel"]
    log.append(f"  BINDING CHATTER false_action={cfa!r} (<=0.02) "
               f"double={da} cancelX={ac} -> "
               f"{cfa <= 0.02 and da == 0 and ac == 0}")
    ok &= (cfa <= 0.02 and da == 0 and ac == 0)

    fr = subprocess.run(["git", "status", "--porcelain"] + FROZEN,
                        cwd=str(ENGINE.parent), capture_output=True, text=True)
    fc = fr.stdout.strip() == ""
    log.append(f"  BINDING frozen paths clean -> {fc}")
    ok &= fc

    for ln in log:
        print(ln)
    print(f"DIL_P5_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
