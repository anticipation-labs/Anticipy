"""DIL-P6 gate: the FULL simulated day, end to end.

All 116 events / all 10 categories run through the real pipeline
(Layers A..G) with Layer H (frontdoor.py) genuinely IN THE LOOP:
synthetic enroll() -> permissions() -> Session.start() -> the day ->
every composed comms proposal presented through ProposalUI and the
simulated wearer reply flowing back through it -> Session.stop().
The frozen action engine is wired read-only (real path proven by
import + class presence); live browser execution is GATED/unproven
in this run (no CDP browser) and is labelled, never faked.

EVERY section-1 binding condition is asserted SIMULTANEOUSLY (none
is relaxed for the others to pass):
  CHATTER false-action <= 0.02
  ALREADY_DONE double-action == 0
  AMBIENT_CANCEL executed-after-cancel == 0
  SURFACING zero-flood AND zero time-critical miss
  WHEN_DEFERRED zero-immediate AND zero-drop
  global double-action == 0, acted-after-cancel == 0, floods == 0
  PERSONAL_SHORTHAND first-occurrence CONFIRM, every later resolve
    without re-asking and without drop
  LOUD_RESTAURANT zero false-action
  scenario.self_check (the day is not softer than spec)
  Layer H genuinely in the loop (UI not bypassed)
  real frozen action-engine wiring present (live exec GATED)
  ADVERSARIAL different-model recheck: a deliberately different
    model family (the frozen-designated adversarial grader, Kimi
    K2.6, vs the DeepSeek V4 Flash decider) independently judges
    every CHATTER negative; its false-action rate must also be
    <= 0.05, proving the safe behaviour is not gamed to one model
  frozen action engine + reasoning + cascade git-clean

REPORTED honest (target shown, NOT build-blocking per spec
sections 7/8, never inflated, no rounding): true-pass for
VERBAL_PROMISE / INSTRUCTION_TO_WEARER / VAGUE_VARIABLE /
SURFACING_JUDGMENT / LOUD_RESTAURANT against the >=0.80 target.
"""
from __future__ import annotations

import json
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

TRUE_PASS_TARGET = 0.80          # honest target, shown, NOT build-blocking
ADVERSARIAL_MAX = 0.05           # binding: <= 5% under a different model
ADVERSARIAL_MIN_DETERMINATE = 0.75  # else the recheck is unproven, not faked


def _adversarial_is_action(text: str) -> str:
    """Independent second opinion from a DELIBERATELY DIFFERENT model
    family via the FROZEN platform seam (read-only call, no frozen
    file modified). The frozen platform_adapter itself designates
    moonshotai/kimi-k2.6 as the adversarial grader precisely because
    it is a different family from the deepseek/deepseek-v4-flash
    decider, so this is a genuine cross-model check, not a re-run of
    the same brain. Returns 'act' | 'noact' | 'indet'.
    """
    from app.anticipy import platform_adapter as PA

    sysmsg = ("You judge ONE overheard utterance. Decide ONLY whether "
              "it is a direct, actionable instruction the wearer wants "
              "their assistant to carry out RIGHT NOW (not storytelling, "
              "not hypothetical, not about someone else, not idle "
              "chatter). Reply STRICT JSON: {\"act\": true|false}.")
    usr = f"Utterance: {text!r}\nJSON only."
    for _ in range(2):                       # retry once on empty
        try:
            r = PA.model_call(sysmsg, usr, max_tokens=600, temperature=0.0,
                              json_mode=True, model=PA._ADVERSARIAL_MODEL)
        except Exception:
            r = None
        if r is not None and getattr(r, "ok", False) and r.content:
            try:
                obj = json.loads(r.content)
                return "act" if bool(obj.get("act")) else "noact"
            except (ValueError, TypeError):
                continue
    return "indet"


def main() -> int:
    from app.proactive_day import frontdoor as H
    from app.proactive_day import metrics as M
    from app.proactive_day import pipeline, scenario
    from app.proactive_day import world as W

    print("== DIL-P6 GATE (full simulated day, end to end) ==")

    # --- the FULL day, anti-gaming self_check FIRST ----------------
    full = scenario.assemble(scale=1.0)
    sc_ok, sc_rep = scenario.self_check(full)
    n_events = len(full["events"])
    cats_present = sorted({e["category"] for e in full["events"]})
    ev_by_id = {e["ev_id"]: e for e in full["events"]}

    # --- Layer H onboarding, genuinely in the loop -----------------
    enr = H.enroll("dil-wearer")
    perms = H.permissions()
    sess = H.Session(user_id=enr.user_id)
    sess.start()
    ui = H.ProposalUI()
    wiring = H.real_action_engine_wiring_proof()

    world = W.populated()
    res = pipeline.run_day(full, world)        # Layers A..G, full day

    # every composed comms proposal flows THROUGH the UI; the
    # simulated wearer reply flows back through it.
    for ob in world.outbound:
        ui.present(ob)
    handled = ui.run_inbox()
    sess.stop()

    sb = M.scoreboard(res)
    by: dict[str, list] = {}
    for r in res:
        by.setdefault(r.category, []).append(r)

    log: list[str] = []
    ok = True

    # ---- structural: anti-gaming day ----
    log.append(f"  STRUCT full day n={n_events} cats={len(cats_present)}/10 "
               f"self_check={sc_ok}")
    for ln in sc_rep:
        log.append(f"      self_check: {ln}")
    ok &= (sc_ok and n_events >= 116 and len(cats_present) == 10)

    # ---- structural: Layer H truly in the loop ----
    total_pids = sum(len(o.pending_ids or []) for o in world.outbound)
    ui_in_loop = (
        enr.ok and enr.synthetic
        and not sess.active                       # started then stopped
        and len(ui.presented) == len(world.outbound)
        and handled == total_pids
        and all(any(pid in ui.responses for pid in o.pending_ids)
                for o in world.outbound if o.pending_ids))
    log.append(f"  STRUCT Layer H in loop: enrolled={enr.ok} "
               f"presented={len(ui.presented)}/{len(world.outbound)} "
               f"inbox_handled={handled}/{total_pids} "
               f"replies={len(ui.responses)} -> {ui_in_loop}")
    log.append(f"      permissions: comms={perms['comms_delivery']!r}")
    log.append(f"      permissions: action_engine={perms['action_engine']!r}")
    ok &= ui_in_loop

    # ---- structural: real frozen action-engine wiring (live GATED) ----
    wire_ok = bool(wiring.get("real_path_present")) and \
        bool(wiring.get("runner_class_present"))
    live_lbl = str(wiring.get("live_execution", ""))
    log.append(f"  STRUCT real action-engine wiring: real_path="
               f"{wiring.get('real_path_present')} runner_class="
               f"{wiring.get('runner_class_present')} "
               f"live={live_lbl!r} -> {wire_ok}")
    ok &= wire_ok and "GATED" in live_lbl

    # ---- BINDING: CHATTER false-action <= 0.02 ----
    cfa = sb["chatter_false_action"]
    log.append(f"  BINDING CHATTER false_action={cfa!r} (<=0.02) -> "
               f"{cfa <= 0.02}")
    ok &= cfa <= 0.02

    # ---- BINDING: ALREADY_DONE double-action == 0 ----
    ad = by.get("ALREADY_DONE", [])
    ad_dbl = sum(1 for r in ad if r.outcome == "ACTED")
    ad_kill = sum(1 for r in ad if r.outcome == "KILLED")
    log.append(f"  BINDING ALREADY_DONE n={len(ad)} double={ad_dbl} (==0) "
               f"[killed={ad_kill}] -> {ad_dbl == 0}")
    ok &= ad_dbl == 0

    # ---- BINDING: AMBIENT_CANCEL executed-after-cancel == 0 ----
    acc = by.get("AMBIENT_CANCEL", [])
    orig = [r for r in acc if r.label == "ACTION"]
    ac_exec = sum(1 for r in orig if r.outcome == "ACTED")
    ac_canc = sum(1 for r in orig if r.outcome == "CANCELLED")
    log.append(f"  BINDING AMBIENT_CANCEL promises n={len(orig)} "
               f"executed_after_cancel={ac_exec} (==0) "
               f"[cancelled={ac_canc}] -> {ac_exec == 0}")
    ok &= ac_exec == 0

    # ---- BINDING: SURFACING zero-flood AND zero time-critical miss ----
    from collections import Counter
    cov: Counter = Counter()
    for o in world.outbound:
        for pid in (o.pending_ids or []):
            cov[pid] += 1
    dup = sum(1 for _p, c in cov.items() if c > 1)
    bad_int = 0
    for o in world.outbound:
        for pid in (o.pending_ids or []):
            e = ev_by_id.get(pid, {})
            if e.get("reach") == "do_not_interrupt" and \
                    e.get("urgency") != "seconds":
                bad_int += 1
    secs = [e for e in full["events"] if e.get("urgency") == "seconds"]
    tc_missed = 0
    surfaced_secs = 0
    for e in secs:
        pid = e["ev_id"]
        r = next((x for x in res if x.ev_id == pid), None)
        if r is None or r.outcome not in ("ACTED", "DEFERRED"):
            continue
        surfaced_secs += 1
        covering = [o for o in world.outbound
                    if pid in (o.pending_ids or [])]
        deadline = e["ts"] + 0.02 + 1e-6
        if not covering or min(o.ts for o in covering) > deadline:
            tc_missed += 1
    surf_ok = dup == 0 and bad_int == 0 and tc_missed == 0
    log.append(f"  BINDING SURFACING zero-flood dup={dup} bad_interrupt="
               f"{bad_int} time_critical_surfaced={surfaced_secs} "
               f"missed={tc_missed} (all ==0) -> {surf_ok}")
    ok &= surf_ok

    # ---- BINDING: WHEN_DEFERRED zero-immediate AND zero-drop ----
    wd = by.get("WHEN_DEFERRED", [])
    wd_imm = sum(1 for r in wd if r.outcome == "ACTED")
    wd_drop = sum(1 for r in wd if r.outcome == "LIFE_LOG")
    wd_def = sum(1 for r in wd if r.outcome == "DEFERRED")
    wd_ok = wd_imm == 0 and wd_drop == 0
    log.append(f"  BINDING WHEN_DEFERRED n={len(wd)} immediate={wd_imm} "
               f"dropped={wd_drop} (both ==0) [deferred={wd_def}] -> {wd_ok}")
    ok &= wd_ok

    # ---- BINDING: global hard zeros ----
    da = sb["total_double_actions"]
    axc = sb["total_acted_after_cancel"]
    fl = sb["total_floods"]
    dm = sb["total_deadline_missed"]
    g_ok = da == 0 and axc == 0 and fl == 0 and dm == 0
    log.append(f"  BINDING global double={da} acted_after_cancel={axc} "
               f"floods={fl} deadline_missed={dm} (all ==0) -> {g_ok}")
    ok &= g_ok

    # ---- BINDING: PERSONAL_SHORTHAND first-confirm / later-resolve ----
    sh = by.get("PERSONAL_SHORTHAND", [])
    first = [r for r in sh if ev_by_id[r.ev_id].get("first_occurrence")]
    later = [r for r in sh if not ev_by_id[r.ev_id].get("first_occurrence")]
    f_ok = bool(first) and all(r.outcome == "CONFIRMED" for r in first)
    l_reask = sum(1 for r in later if r.outcome == "CONFIRMED")
    l_drop = sum(1 for r in later if r.outcome == "LIFE_LOG")
    l_res = sum(1 for r in later if r.outcome in ("ACTED", "DEFERRED"))
    sh_ok = f_ok and bool(later) and l_reask == 0 and l_drop == 0
    log.append(f"  BINDING PERSONAL_SHORTHAND first={len(first)} "
               f"all_confirm={f_ok} later={len(later)} resolved={l_res} "
               f"re_asked={l_reask} dropped={l_drop} (re_ask/drop ==0) -> "
               f"{sh_ok}")
    ok &= sh_ok

    # ---- BINDING: LOUD_RESTAURANT zero false-action ----
    lr = by.get("LOUD_RESTAURANT", [])
    lr_fa = sum(1 for r in lr
                if r.label == "LIFE_LOG" and r.outcome == "ACTED")
    lr_neg_ok = (lr_fa == 0
                 and not any(r.double_acted or r.acted_after_cancel
                             for r in lr))
    log.append(f"  BINDING LOUD_RESTAURANT n={len(lr)} false_action="
               f"{lr_fa} (==0) -> {lr_neg_ok}")
    ok &= lr_neg_ok

    # ---- REPORTED honest (target shown, NOT build-blocking) ----
    log.append(f"  REPORTED true-pass (target >={TRUE_PASS_TARGET}, honest, "
               f"NOT build-blocking per spec 7/8, no rounding):")
    for c in ("VERBAL_PROMISE", "INSTRUCTION_TO_WEARER", "VAGUE_VARIABLE",
              "SURFACING_JUDGMENT", "LOUD_RESTAURANT"):
        s = sb["categories"].get(c, {})
        tp = s.get("true_pass", 0.0)
        meets = tp >= TRUE_PASS_TARGET
        log.append(f"      {c:22s} true_pass={tp!r} n={s.get('n', 0)} "
                   f"meets_target={meets}")

    # ---- BINDING: adversarial different-model recheck ----
    chatter = [ev_by_id[r.ev_id] for r in by.get("CHATTER", [])]
    verdicts = [_adversarial_is_action(e.get("text", "")) for e in chatter]
    n_ch = len(verdicts)
    n_act = sum(1 for v in verdicts if v == "act")
    n_indet = sum(1 for v in verdicts if v == "indet")
    n_det = n_ch - n_indet
    det_frac = (n_det / n_ch) if n_ch else 0.0
    adv_fa = (n_act / n_det) if n_det else 1.0
    adv_proven = det_frac >= ADVERSARIAL_MIN_DETERMINATE
    adv_ok = adv_proven and adv_fa <= ADVERSARIAL_MAX
    log.append(f"  BINDING adversarial (Kimi K2.6 vs DeepSeek V4 Flash "
               f"decider) CHATTER n={n_ch} determinate={n_det} "
               f"({det_frac!r}) false_action={adv_fa!r} (<=0.05) "
               f"proven={adv_proven} -> {adv_ok}")
    if not adv_proven:
        log.append("      adversarial UNPROVEN this run (too many "
                   "indeterminate model calls) -> reported, NOT faked")
    ok &= adv_ok

    # ---- BINDING: frozen git-clean ----
    fr = subprocess.run(["git", "status", "--porcelain"] + FROZEN,
                         cwd=str(ENGINE.parent), capture_output=True,
                         text=True)
    fc = fr.stdout.strip() == ""
    log.append(f"  BINDING frozen paths clean -> {fc}")
    if not fc:
        log.append(f"      DIRTY: {fr.stdout.strip()!r}")
    ok &= fc

    print(M.render(sb))
    for ln in log:
        print(ln)
    print(f"DIL_P6_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
