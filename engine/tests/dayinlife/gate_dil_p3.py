"""DIL-P3 gate: completion detector (C) + ambient cancel (D).
The safety-critical phase. Two HARD binding metrics, never relaxed.

Scoped to ALREADY_DONE + AMBIENT_CANCEL + CHATTER, run through the
real pipeline with the time-ordered completion+cancel
reconciliation.

BINDING (hard):
  ALREADY_DONE  double-action == 0  (every promise the world
    satisfied by other means is KILLED, never left ACTED).
  AMBIENT_CANCEL executed-after-cancel == 0  (every retracted
    queued promise ends CANCELLED, never ACTED).
  CHATTER false-action <= 0.02 (no regression).
  frozen action engine + reasoning + cascade git-clean.
REPORTED honest (no rounding): KILLED / CANCELLED rates.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

CATS = ["ALREADY_DONE", "AMBIENT_CANCEL", "CHATTER"]
FROZEN = ["engine/app/action_engine", "desktop", "engine/app/anticipy",
          "engine/app/proactive/demand_detection.py",
          "engine/app/proactive/hedge_filter.py",
          "engine/app/proactive/intent_extraction.py",
          "engine/app/proactive/llm_adapter.py"]


def main() -> int:
    from app.proactive_day import metrics as M
    from app.proactive_day import pipeline, scenario
    from app.proactive_day import world as W

    print("== DIL-P3 GATE (completion detector + ambient cancel) ==")
    full = scenario.assemble(scale=1.0)
    man = dict(full)
    man["events"] = [e for e in full["events"] if e["category"] in CATS]
    man["n"] = len(man["events"])
    world = W.populated()
    res = pipeline.run_day(man, world)
    sb = M.scoreboard(res)
    print(M.render(sb))

    log, ok = [], True
    by: dict[str, list] = {}
    for r in res:
        by.setdefault(r.category, []).append(r)

    ad = by.get("ALREADY_DONE", [])
    ad_double = sum(1 for r in ad if r.outcome == "ACTED")
    ad_killed = sum(1 for r in ad if r.outcome == "KILLED")
    ad_ok = ad_double == 0
    log.append(f"  BINDING ALREADY_DONE n={len(ad)} double_actions="
               f"{ad_double} (==0) -> {ad_ok}  [killed={ad_killed}]")
    ok &= ad_ok

    # AMBIENT_CANCEL: the promise originals (label ACTION) must end
    # CANCELLED; the cancel utterances (label CANCEL) are recorded.
    ac = by.get("AMBIENT_CANCEL", [])
    orig = [r for r in ac if r.label == "ACTION"]
    ac_exec = sum(1 for r in orig if r.outcome == "ACTED")
    ac_canc = sum(1 for r in orig if r.outcome == "CANCELLED")
    ac_ok = ac_exec == 0
    log.append(f"  BINDING AMBIENT_CANCEL promises n={len(orig)} "
               f"executed_after_cancel={ac_exec} (==0) -> {ac_ok}  "
               f"[cancelled={ac_canc}]")
    ok &= ac_ok

    cfa = sb["chatter_false_action"]
    log.append(f"  BINDING CHATTER false_action={cfa!r} (<=0.02) "
               f"-> {cfa <= 0.02}")
    ok &= cfa <= 0.02

    fr = subprocess.run(["git", "status", "--porcelain"] + FROZEN,
                        cwd=str(ENGINE.parent), capture_output=True, text=True)
    fc = fr.stdout.strip() == ""
    log.append(f"  BINDING frozen paths clean -> {fc}")
    ok &= fc

    for ln in log:
        print(ln)
    print(f"DIL_P3_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
