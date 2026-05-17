"""DIL-P4 gate: comms decision engine + rate limiter (E + F).

Scoped to SURFACING_JUDGMENT + VERBAL_PROMISE + CHATTER, run
through the real pipeline; the simulated sink (world.outbound) is
inspected.

BINDING (hard):
  ZERO flood: no pending item covered by >1 Outbound; no non-
    critical interrupt during a do_not_interrupt state.
  ZERO time-critical miss: every 'seconds'-urgency surfaced item
    has an Outbound within its deadline (debounce never blew it).
  CHATTER false-action <= 0.02 ; double-action == 0 ;
    acted-after-cancel == 0 (no regression).
  frozen action engine + reasoning + cascade git-clean.
REPORTED honest: channel distribution, batch/compose ratio.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

CATS = ["SURFACING_JUDGMENT", "VERBAL_PROMISE", "CHATTER"]
FROZEN = ["engine/app/action_engine", "desktop", "engine/app/anticipy",
          "engine/app/proactive/demand_detection.py",
          "engine/app/proactive/hedge_filter.py",
          "engine/app/proactive/intent_extraction.py",
          "engine/app/proactive/llm_adapter.py"]


def main() -> int:
    from app.proactive_day import comms as CM
    from app.proactive_day import metrics as M
    from app.proactive_day import pipeline, scenario
    from app.proactive_day import world as W

    print("== DIL-P4 GATE (comms decision + rate limiter) ==")
    full = scenario.assemble(scale=1.0)
    man = dict(full)
    man["events"] = [e for e in full["events"] if e["category"] in CATS]
    man["n"] = len(man["events"])
    ev_by_id = {e["ev_id"]: e for e in man["events"]}
    world = W.populated()
    res = pipeline.run_day(man, world)
    sb = M.scoreboard(res)

    obs = world.outbound
    log, ok = [], True

    # 1. flood: no pending id in >1 Outbound
    from collections import Counter
    cov = Counter()
    for o in obs:
        for pid in (o.pending_ids or []):
            cov[pid] += 1
    multi = [p for p, c in cov.items() if c > 1]
    flood_dup = len(multi)
    # non-critical interrupt during do_not_interrupt
    bad_interrupt = 0
    for o in obs:
        for pid in (o.pending_ids or []):
            e = ev_by_id.get(pid, {})
            if e.get("reach") == "do_not_interrupt" and \
                    e.get("urgency") != "seconds":
                bad_interrupt += 1
    flood_ok = (flood_dup == 0 and bad_interrupt == 0)
    log.append(f"  BINDING zero-flood: dup_covered={flood_dup} (==0) "
               f"bad_interrupt={bad_interrupt} (==0) -> {flood_ok}")
    ok &= flood_ok

    # 2. time-critical: every 'seconds' surfaced item -> Outbound
    # within deadline
    secs = [e for e in man["events"]
            if e.get("urgency") == "seconds"]
    surfaced_secs = 0
    missed = 0
    for e in secs:
        pid = e["ev_id"]
        covering = [o for o in obs if pid in (o.pending_ids or [])]
        r = next((x for x in res if x.ev_id == pid), None)
        # only items that became ACTED/DEFERRED are surfaceable
        if r is None or r.outcome not in ("ACTED", "DEFERRED"):
            continue
        surfaced_secs += 1
        deadline = e["ts"] + CM.SECONDS_DEADLINE_S + 1e-6
        if not covering or min(o.ts for o in covering) > deadline:
            missed += 1
    tc_ok = missed == 0
    log.append(f"  BINDING time-critical: surfaced_seconds={surfaced_secs} "
               f"deadline_missed={missed} (==0) -> {tc_ok}")
    ok &= tc_ok

    # 3. channel distribution (reported) + do_not_interrupt respected
    from collections import Counter as C2
    ch_dist = C2(o.channel for o in obs)
    batched = sum(1 for o in obs if len(o.pending_ids or []) > 1)
    log.append(f"  REPORTED channels={dict(ch_dist)} n_outbound={len(obs)} "
               f"batched_msgs={batched} (one composed proposal per batch)")

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
    print(f"DIL_P4_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
