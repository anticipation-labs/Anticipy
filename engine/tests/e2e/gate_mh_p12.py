"""MH-P12 gate: loud-room understanding past the dil-p7 ceiling.
FRONTIER.

Same scoped loud corpus as dil-p7, run through the real pipeline
with loudroom.harden swapped (gate-scoped, no pipeline/frozen
edit) for the MH-P12 joint life-consistent recovery.

BINDING (hard, never relaxed):
  loud-tier false-action <= 0.02 measured ADVERSARIALLY (every
    CHATTER negative forced to the loud tier AND garbled).
  loud-scoped double/cancel/flood/deadline == 0.
  v2 must not make loud true-pass WORSE than the dil-p7 hardened
    baseline (a harmful change is a fail).
  frozen action engine + reasoning + cascade git-clean.

REPORTED honest (FRONTIER, NOT inflated to the 0.80 target, no
rounding): dil-p7 hardened baseline vs MH-P12 v2 loud true-pass on
the identical fixed corpus, plus the explicit
assembled-corpus-vs-real-two-mic-hardware gap statement.
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


def _run(cats, force_loud=False):
    from app.proactive_day import metrics as M
    from app.proactive_day import pipeline, scenario
    from app.proactive_day import world as W

    full = scenario.assemble(scale=1.0)
    evs = [dict(e) for e in full["events"] if e["category"] in cats]
    if force_loud:
        for e in evs:
            e["snr_tier"] = "loud"
            e["place"] = "restaurant"
    man = dict(full)
    man["events"] = evs
    man["n"] = len(evs)
    res = pipeline.run_day(man, W.populated())
    return M.scoreboard(res)


def main() -> int:
    from app.proactive_day import loudroom as LR
    from app.proactive_day import loudroom_v2 as LV2

    print("== MH-P12 GATE (loud-room understanding, FRONTIER) ==")
    log, ok = [], True

    # dil-p7 hardened baseline (the existing loudroom.harden)
    sb_base = _run(["LOUD_RESTAURANT"])
    tp_base = sb_base["categories"].get("LOUD_RESTAURANT", {}).get(
        "true_pass", 0.0)

    # MH-P12: swap in the joint life-consistent recovery (gate-scoped)
    _orig = LR.harden
    LR.harden = LV2.harden_v2
    try:
        sb_v2 = _run(["LOUD_RESTAURANT"])
        sb_chat = _run(["CHATTER"], force_loud=True)
    finally:
        LR.harden = _orig                      # never leak the swap

    tp_v2 = sb_v2["categories"].get("LOUD_RESTAURANT", {}).get(
        "true_pass", 0.0)
    cfa = sb_chat["chatter_false_action"]
    da = sb_chat["total_double_actions"]
    axc = sb_chat["total_acted_after_cancel"]
    fl = sb_chat["total_floods"]
    dm = sb_chat["total_deadline_missed"]
    da2 = sb_v2["total_double_actions"]
    axc2 = sb_v2["total_acted_after_cancel"]
    fl2 = sb_v2["total_floods"]

    adv_ok = cfa <= 0.02
    log.append(f"  BINDING adversarial loud-chatter false_action="
               f"{cfa!r} (<=0.02) -> {adv_ok}")
    ok &= adv_ok

    zeros_ok = (da == 0 and axc == 0 and fl == 0 and dm == 0
                and da2 == 0 and axc2 == 0 and fl2 == 0)
    log.append(f"  BINDING loud-scoped hard zeros: chat(d={da} c={axc} "
               f"f={fl} dl={dm}) loud(d={da2} c={axc2} f={fl2}) all==0 "
               f"-> {zeros_ok}")
    ok &= zeros_ok

    not_worse = tp_v2 >= tp_base
    log.append(f"  BINDING v2 not harmful: dil-p7_hardened={tp_base!r} "
               f"-> mh-p12_v2={tp_v2!r} (v2 >= baseline) -> {not_worse}")
    ok &= not_worse

    improved = tp_v2 > tp_base
    log.append(f"  REPORTED loud true-pass (FRONTIER, honest, NOT "
               f"inflated to 0.80, no rounding): dil-p7 hardened "
               f"baseline={tp_base!r} -> MH-P12 joint-recovery="
               f"{tp_v2!r} improved={improved}")
    log.append(f"  REPORTED hardware gap: {LV2.hardware_gap_statement()}")

    fr = subprocess.run(["git", "status", "--porcelain"] + FROZEN,
                         cwd=str(ENGINE.parent), capture_output=True,
                         text=True)
    fc = fr.stdout.strip() == ""
    log.append(f"  BINDING frozen paths clean -> {fc}")
    ok &= fc

    for ln in log:
        print(ln)
    print("  NOTE the binding is loud false-action + hard zeros + "
          "no-harm; the loud true-pass number is an HONEST FRONTIER "
          "ceiling, reported as measured, not asserted to target.")
    print(f"MH_P12_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
