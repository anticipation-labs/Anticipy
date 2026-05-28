"""DIL-P1 gate: the resolution engine (Layer A).

Scoped to VAGUE_VARIABLE + CHATTER + ALREADY_DONE + AMBIENT_CANCEL,
run through the real pipeline (FROZEN engine read-only judges
'is this an instruction', Layer A resolves the variables).

BINDING (hard):
  VAGUE_VARIABLE: zero act on an unresolved reference (an ACTED
    item must have all load-bearing refs resolved; structurally an
    unresolved ref -> CONFIRMED, never ACTED).
  CHATTER false-action <= 0.02 (frozen engine refuses chatter).
  ALREADY_DONE double-action == 0 ; AMBIENT_CANCEL
    executed-after-cancel == 0 (no regression; safe at P1).
  frozen action engine + reasoning + cascade git-clean.
REPORTED honest (target, not build-blocking, no rounding):
  VAGUE_VARIABLE resolved-or-confirmed-correctly, target >= 0.80.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

CATS = ["VAGUE_VARIABLE", "CHATTER", "ALREADY_DONE", "AMBIENT_CANCEL"]
FROZEN = ["engine/app/action_engine", "desktop", "engine/app/anticipy",
          "engine/app/proactive/demand_detection.py",
          "engine/app/proactive/hedge_filter.py",
          "engine/app/proactive/intent_extraction.py",
          "engine/app/proactive/llm_adapter.py"]


def main() -> int:
    from app.proactive_day import metrics as M
    from app.proactive_day import pipeline, scenario
    from app.proactive_day import world as W

    print("== DIL-P1 GATE (resolution engine, Layer A) ==")
    full = scenario.assemble(scale=1.0)
    man = dict(full)
    man["events"] = [e for e in full["events"] if e["category"] in CATS]
    man["n"] = len(man["events"])
    world = W.populated()
    res = pipeline.run_day(man, world)
    sb = M.scoreboard(res)
    print(M.render(sb))

    log: list[str] = []
    ok = True
    by: dict[str, list] = {}
    for r in res:
        by.setdefault(r.category, []).append(r)

    vv = by.get("VAGUE_VARIABLE", [])
    acted_unresolved = sum(1 for r in vv
                           if r.outcome == "ACTED" and not r.content_ok)
    n_vv = len(vv)
    rc = sum(1 for r in vv if (r.outcome == "ACTED" and r.content_ok)
             or r.outcome == "CONFIRMED")
    rc_rate = rc / n_vv if n_vv else 0.0
    vv_bind = acted_unresolved == 0
    log.append(f"  BINDING VAGUE_VARIABLE acted_on_unresolved="
               f"{acted_unresolved} (==0) -> {vv_bind}")
    note = "MEETS" if rc_rate >= 0.80 else ("HONEST CEILING - reported, "
            "safe direction (resolve or confirm), build continues")
    log.append(f"  REPORTED VAGUE_VARIABLE resolved_or_confirmed="
               f"{rc_rate!r} of n={n_vv} (target >=0.80; {note})")
    ok &= vv_bind

    cfa = sb["chatter_false_action"]
    cok = cfa <= 0.02
    log.append(f"  BINDING CHATTER false_action={cfa!r} (<=0.02) -> {cok}")
    ok &= cok

    da = sb["total_double_actions"]
    ac = sb["total_acted_after_cancel"]
    log.append(f"  BINDING double_actions={da} (==0) -> {da == 0}")
    log.append(f"  BINDING acted_after_cancel={ac} (==0) -> {ac == 0}")
    ok &= (da == 0 and ac == 0)

    fr = subprocess.run(["git", "status", "--porcelain"] + FROZEN,
                        cwd=str(ENGINE.parent), capture_output=True, text=True)
    fc = fr.stdout.strip() == ""
    log.append(f"  BINDING frozen paths clean -> {fc}")
    ok &= fc

    for ln in log:
        print(ln)
    print(f"DIL_P1_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
