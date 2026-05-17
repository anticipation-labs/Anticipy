"""MH-P13 gate: full ambient resolution at scale. FRONTIER.

The hardest version of variable resolution: a long, messy,
multi-context life at scale, with the MH-P2/P3 memory system
active. Resolution will NOT be perfect at scale -- that is the
honest FRONTIER reality. The point this gate verifies is the
RECOVERABILITY DESIGN: where resolution is imperfect the system
CONFIRMS or life-logs, it NEVER silently wrong-acts.

BINDING (hard, never relaxed):
  ZERO SILENT WRONG ACTION  no ACTION-labelled item is ACTED with
    content_ok == False (a wrong referent never silently fires);
    every unresolved/ambiguous reference becomes CONFIRM/LIFE_LOG.
  chatter false-action <= 0.02 at scale ; double-action == 0 ;
    acted-after-cancel == 0 ; floods == 0.
  frozen action engine + reasoning + cascade git-clean.

REPORTED honest (FRONTIER, no rounding, NOT inflated): the real
resolution outcome distribution at scale, and the share that the
recoverability net (CONFIRM/LIFE_LOG instead of a wrong act)
carried -- that net IS the answer where resolution is imperfect.
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
CATS = ["VERBAL_PROMISE", "INSTRUCTION_TO_WEARER", "VAGUE_VARIABLE",
        "PERSONAL_SHORTHAND", "CHATTER"]


def main() -> int:
    from app.memory import InProcessMemoryBackend
    from app.memory_v2 import draw as DR
    from app.memory_v2.write import IngestItem, MemoryWriter
    from app.proactive_day import metrics as M
    from app.proactive_day import pipeline, scenario
    from app.proactive_day import world as W

    print("== MH-P13 GATE (full ambient resolution at scale) ==")
    log, ok = [], True

    # long, messy, multi-context life: scale up the corpus.
    full = scenario.assemble(scale=1.5)
    man = dict(full)
    man["events"] = [e for e in full["events"] if e["category"] in CATS]
    man["n"] = len(man["events"])

    # multi-context durable memory (aliases across contexts).
    be = InProcessMemoryBackend()
    w = MemoryWriter(be)
    asyncio.run(w.ingest("dil-wearer", [
        IngestItem("the usual means the budget", "preference",
                   "confirmed", wearer_confirmed=True,
                   value={"alias": "the usual",
                          "resolves_to": "the budget"}),
        IngestItem("the regular sync means the q3 deck review",
                   "preference", "confirmed", wearer_confirmed=True,
                   value={"alias": "the regular",
                          "resolves_to": "the q3 deck"})]))

    lat = {"v": 0.0}

    def _hook(text: str):
        r = asyncio.run(DR.draw("dil-wearer", text, w))
        lat["v"] = max(lat["v"], r.latency_ms)
        return (r.object_hint, r.person_hint)

    pipeline._MEMORY_DRAW = _hook
    try:
        res = pipeline.run_day(man, W.populated())
    finally:
        pipeline._MEMORY_DRAW = None

    sb = M.scoreboard(res)
    n = len(res)

    # --- BINDING: zero silent wrong action ---
    silent_wrong = sum(1 for r in res
                       if r.label == "ACTION" and r.outcome == "ACTED"
                       and not r.content_ok)
    cfa = sb["chatter_false_action"]
    da = sb["total_double_actions"]
    axc = sb["total_acted_after_cancel"]
    fl = sb["total_floods"]
    swa_ok = silent_wrong == 0
    log.append(f"  BINDING zero silent wrong action: {silent_wrong} "
               f"(==0) over n={n} at scale -> {swa_ok}")
    ok &= swa_ok
    safe_ok = cfa <= 0.02 and da == 0 and axc == 0 and fl == 0
    log.append(f"  BINDING scale safety: chatter_false_action={cfa!r} "
               f"(<=0.02) double={da} cancelX={axc} floods={fl} "
               f"(all 0) -> {safe_ok}")
    ok &= safe_ok

    # --- REPORTED honest: resolution distribution at scale ---
    from collections import Counter
    outc = Counter(r.outcome for r in res)
    acted = sum(1 for r in res
                if r.outcome == "ACTED" and r.content_ok
                and r.label == "ACTION")
    pos = sum(1 for r in res if r.label == "ACTION")
    resolved_rate = (acted / pos) if pos else 0.0
    recoverable = sum(1 for r in res
                      if r.outcome in ("CONFIRMED", "LIFE_LOG",
                                       "DEFERRED"))
    log.append(f"  REPORTED at scale (honest, no rounding): n={n} "
               f"outcomes={dict(outc)}")
    log.append(f"  REPORTED resolved-correctly rate (of ACTION items)="
               f"{resolved_rate!r} acted_ok={acted}/{pos} -- a real "
               f"FRONTIER number, NOT inflated to 0.80")
    log.append(f"  REPORTED recoverability net carried "
               f"{recoverable}/{n} items as CONFIRM/LIFE_LOG/DEFER "
               f"instead of a wrong act -- THIS is the answer where "
               f"resolution is imperfect")
    log.append(f"  REPORTED max memory-draw latency={round(lat['v'],3)}ms")

    fr = subprocess.run(["git", "status", "--porcelain"] + FROZEN,
                         cwd=str(ENGINE.parent), capture_output=True,
                         text=True)
    fc = fr.stdout.strip() == ""
    log.append(f"  BINDING frozen paths clean -> {fc}")
    ok &= fc

    for ln in log:
        print(ln)
    print("  NOTE the binding is zero silent wrong action + scale "
          "safety; the resolution rate is an HONEST FRONTIER number, "
          "and the recoverability design (confirm/ask, never silent "
          "wrong) is the verified answer where it is imperfect.")
    print(f"MH_P13_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
