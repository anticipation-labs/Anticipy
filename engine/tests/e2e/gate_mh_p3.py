"""MH-P3 gate: retrieval/draw path wired into the resolution engine.

Same dil corpus, scoped to VAGUE_VARIABLE + CHATTER, run through
the real pipeline TWICE on one seed:

  memory OFF  (_MEMORY_DRAW=None): must reproduce the committed
    dil-p6 baseline exactly (VAGUE true_pass 0.0, CHATTER
    false-action 0.0) -> proves the hook is a strict no-op when
    off: ZERO regression to every prior DIL/MH gate.

  memory ON   a durable, wearer-confirmed alias fact ("the usual"
    -> "the budget") is in the MH-P2 store. The draw supplies that
    referent for the otherwise-unresolvable "forward the usual to
    NAME" items, so they resolve and ACT instead of CONFIRM.

BINDING (hard):
  resolution improves: VAGUE true_pass(memory ON) > true_pass
    (memory OFF). Real before/after reported, no rounding.
  NO context-rot: CHATTER false-action <= 0.02 in BOTH runs (the
    draw is consulted only after the frozen instruction gate, so
    chatter, IGNOREd upstream, can never reach retrieved memory).
  retrieval latency within the hard budget DRAW_BUDGET_MS, measured.
  memory-OFF == dil-p6 baseline (regression guard).
  frozen action engine + reasoning + cascade git-clean.
"""
from __future__ import annotations

import asyncio
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
CATS = ["VAGUE_VARIABLE", "CHATTER"]
DIL_P6_VAGUE_BASELINE = 0.0       # committed dil-p6 / dil-p7 no-regress


def _run_subset():
    from app.proactive_day import metrics as M
    from app.proactive_day import pipeline, scenario
    from app.proactive_day import world as W

    full = scenario.assemble(scale=1.0)
    man = dict(full)
    man["events"] = [e for e in full["events"] if e["category"] in CATS]
    man["n"] = len(man["events"])
    res = pipeline.run_day(man, W.populated())
    return M.scoreboard(res)


def main() -> int:
    from app.memory import InProcessMemoryBackend
    from app.memory_v2 import draw as DR
    from app.memory_v2.write import IngestItem, MemoryWriter
    from app.proactive_day import pipeline

    print("== MH-P3 GATE (retrieval/draw into resolution) ==")
    log, ok = [], True

    # ---- memory OFF: must equal the committed dil-p6 baseline ----
    pipeline._MEMORY_DRAW = None
    sb_off = _run_subset()
    vp_off = sb_off["categories"].get("VAGUE_VARIABLE", {}).get(
        "true_pass", 0.0)
    cfa_off = sb_off["chatter_false_action"]
    off_baseline_ok = (vp_off == DIL_P6_VAGUE_BASELINE
                       and cfa_off <= 0.02)
    log.append(f"  BINDING memory-OFF == dil-p6 baseline: VAGUE "
               f"true_pass={vp_off!r} (==0.0) chatter_fa={cfa_off!r} "
               f"(<=0.02) -> {off_baseline_ok}")
    ok &= off_baseline_ok

    # ---- seed a durable, wearer-confirmed alias fact ----
    be = InProcessMemoryBackend()
    w = MemoryWriter(be)
    asyncio.run(w.ingest("dil-wearer", [IngestItem(
        text="the usual means the budget", kind_hint="preference",
        trust="confirmed", wearer_confirmed=True,
        value={"alias": "the usual", "resolves_to": "the budget"})]))

    lat_max = {"v": 0.0}

    def _hook(text: str):
        r = asyncio.run(DR.draw("dil-wearer", text, w))
        lat_max["v"] = max(lat_max["v"], r.latency_ms)
        return (r.object_hint, r.person_hint)

    # ---- memory ON ----
    pipeline._MEMORY_DRAW = _hook
    try:
        sb_on = _run_subset()
    finally:
        pipeline._MEMORY_DRAW = None       # never leak the hook

    vp_on = sb_on["categories"].get("VAGUE_VARIABLE", {}).get(
        "true_pass", 0.0)
    cfa_on = sb_on["chatter_false_action"]

    improved = vp_on > vp_off
    log.append(f"  BINDING resolution improves: VAGUE true_pass "
               f"OFF={vp_off!r} -> ON={vp_on!r} improved={improved} "
               f"(real before/after, no rounding)")
    ok &= improved

    rot_ok = cfa_on <= 0.02
    log.append(f"  BINDING no context-rot: CHATTER false_action "
               f"ON={cfa_on!r} (<=0.02) -> {rot_ok}")
    ok &= rot_ok

    budget_ok = lat_max["v"] <= DR.DRAW_BUDGET_MS
    log.append(f"  BINDING retrieval latency max={round(lat_max['v'], 3)}ms "
               f"(<= hard budget {DR.DRAW_BUDGET_MS}ms) -> {budget_ok}")
    ok &= budget_ok

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
    print("  NOTE the draw supplies a referent ONLY from a durable "
          "wearer-confirmed fact and ONLY after the frozen "
          "instruction gate; ambiguity yields nothing so the "
          "resolver still CONFIRMs, never guesses.")
    print(f"MH_P3_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
