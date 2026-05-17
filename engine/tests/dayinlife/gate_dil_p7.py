"""DIL-P7 gate: loud-room hardening (Layer I).

Loud-tier input is corrupted adversarially (function-word drop +
acoustically-confusable collapse + lowered ASR confidence) before
ANY decision. The hardening must earn back true-positives by
deterministic life-anchored recovery WITHOUT ever raising
loud-tier false-action.

BINDING (hard, never relaxed):
  loud-tier false-action <= 0.02 measured ADVERSARIALLY: every
    CHATTER negative is forced to the loud tier (garbled chatter at
    restaurant SNR, the hardest negative) and NONE may be ACTED.
  loud-scoped double-action == 0, acted-after-cancel == 0,
    floods == 0, deadline_missed == 0 (no regression in scope).
  degrade() is a STRICT no-op for any non-loud tier (so clean
    categories are byte-identical: structural no-regression proof,
    completed by the separate full-day DIL-P6 re-run).
  real two-mic front end labelled GATED/unproven, faked == False.
  frozen action engine + reasoning + cascade git-clean.

REPORTED honest (target >= 0.80 shown, NOT build-blocking per
spec 7/8, no rounding): LOUD_RESTAURANT true-pass with hardening
vs the degraded-naive baseline (harden disabled). The honest point
is the improvement is real, not that it reaches a clean-room
number.
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
TRUE_PASS_TARGET = 0.80


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
    return res, M.scoreboard(res)


def main() -> int:
    from app.proactive_day import loudroom as LR
    from app.proactive_day import metrics as M

    print("== DIL-P7 GATE (loud-room hardening, Layer I) ==")
    log: list[str] = []
    ok = True

    # ---- STRUCT: degrade is a strict no-op off the loud tier ----
    noop = (LR.degrade("send Dana the budget", "clean") ==
            ("send Dana the budget", 1.0)) and \
           (LR.degrade("x", "")[1] == 1.0)
    log.append(f"  STRUCT degrade no-op for non-loud -> {noop}")
    ok &= noop

    # ---- STRUCT: real two-mic front end GATED/unproven, not faked --
    fe = LR.real_two_mic_frontend()
    fe_ok = (fe.get("faked") is False
             and "GATED" in str(fe.get("status", "")))
    log.append(f"  STRUCT real two-mic front end: status="
               f"{fe.get('status')!r} faked={fe.get('faked')} -> {fe_ok}")
    ok &= fe_ok

    # ---- hardened loud run (Layer I fully active) ----
    res_h, sb_h = _run(["LOUD_RESTAURANT"])
    tp_h = sb_h["categories"].get("LOUD_RESTAURANT", {}).get(
        "true_pass", 0.0)

    # ---- degraded-naive baseline: same corruption, harden OFF ----
    orig = LR.harden
    LR.harden = lambda a, r, c, w, t: (a, r)        # identity
    try:
        res_n, sb_n = _run(["LOUD_RESTAURANT"])
    finally:
        LR.harden = orig
    tp_n = sb_n["categories"].get("LOUD_RESTAURANT", {}).get(
        "true_pass", 0.0)

    improved = tp_h >= tp_n
    log.append(f"  REPORTED LOUD_RESTAURANT true_pass: degraded_naive="
               f"{tp_n!r} hardened={tp_h!r} improved={improved} "
               f"(target >={TRUE_PASS_TARGET}, honest, NOT "
               f"build-blocking per spec 7/8)")
    # the binding part of the improvement: hardening must never make
    # it WORSE (that would mean the hardening is harmful).
    ok &= improved

    # ---- BINDING: adversarial loud false-action (garbled chatter) --
    res_c, sb_c = _run(["CHATTER"], force_loud=True)
    cfa = sb_c["chatter_false_action"]
    da = sb_c["total_double_actions"]
    axc = sb_c["total_acted_after_cancel"]
    fl = sb_c["total_floods"]
    dm = sb_c["total_deadline_missed"]
    adv_ok = cfa <= 0.02
    log.append(f"  BINDING adversarial loud-chatter n="
               f"{sb_c['n']} false_action={cfa!r} (<=0.02) -> {adv_ok}")
    log.append(f"  BINDING loud-scoped double={da} acted_after_cancel="
               f"{axc} floods={fl} deadline_missed={dm} (all ==0) -> "
               f"{da == 0 and axc == 0 and fl == 0 and dm == 0}")
    ok &= adv_ok and da == 0 and axc == 0 and fl == 0 and dm == 0

    # loud-scoped safety on the real LOUD_RESTAURANT run too
    da2 = sb_h["total_double_actions"]
    axc2 = sb_h["total_acted_after_cancel"]
    fl2 = sb_h["total_floods"]
    log.append(f"  BINDING LOUD_RESTAURANT run double={da2} "
               f"acted_after_cancel={axc2} floods={fl2} (all ==0) -> "
               f"{da2 == 0 and axc2 == 0 and fl2 == 0}")
    ok &= da2 == 0 and axc2 == 0 and fl2 == 0

    print(M.render(sb_h))

    fr = subprocess.run(["git", "status", "--porcelain"] + FROZEN,
                         cwd=str(ENGINE.parent), capture_output=True,
                         text=True)
    fc = fr.stdout.strip() == ""
    log.append(f"  BINDING frozen paths clean -> {fc}")
    if not fc:
        log.append(f"      DIRTY: {fr.stdout.strip()!r}")
    ok &= fc

    for ln in log:
        print(ln)
    print("  NOTE global no-regression is proven by the separate "
          "full-day DIL-P6 re-run (every binding simultaneously); "
          "Layer I is a guarded no-op off the loud tier.")
    print(f"DIL_P7_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
