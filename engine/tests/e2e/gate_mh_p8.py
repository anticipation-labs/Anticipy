"""MH-P8 gate: cost + rate control at scale.

Virtual clock (deterministic). Binds on:
  CAPPED RUNAWAY    a deliberately looping scenario is killed and
    its cumulative spend NEVER exceeds the per-user ceiling.
  CEILING PRE-AUTH  distinct-op overspend is refused before it
    crosses the ceiling (spend at kill <= ceiling).
  SPIKE KILL        a spend-velocity spike is hard-killed.
  NORMAL UNAFFECTED a modest legitimate load completes fully: zero
    false kill, zero false throttle.
  frozen action engine + reasoning + cascade git-clean.
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


def main() -> int:
    from app.costctl.guard import CostGuard, HardKill, Throttled

    print("== MH-P8 GATE (cost + rate control at scale) ==")
    log, ok = [], True

    # ---- 1. looping runaway: same op forever, cheap each ----
    clk = {"t": 0.0}
    g = CostGuard("u-loop", ceiling_usd=1.00, clock=lambda: clk["t"])
    loop_spend_at_kill = None
    for i in range(100000):
        clk["t"] += 0.10                       # 10 calls/s
        try:
            g.authorize("same_search_op", 0.01)
            g.charge(0.01)
        except HardKill as e:
            loop_spend_at_kill = e.spend
            loop_reason = e.reason
            break
        except Throttled:
            pass
    loop_ok = (loop_spend_at_kill is not None
               and loop_spend_at_kill <= 1.00
               and "loop" in loop_reason)
    log.append(f"  BINDING looping runaway killed, spend_at_kill="
               f"{loop_spend_at_kill} (<= ceiling 1.00) reason="
               f"{loop_reason!r} -> {loop_ok}")
    ok &= loop_ok

    # ---- 2. ceiling pre-auth on distinct ops (no loop trip) ----
    clk2 = {"t": 0.0}
    g2 = CostGuard("u-ceil", ceiling_usd=1.00, clock=lambda: clk2["t"])
    spend_seen = 0.0
    killed2 = False
    for i in range(1000):
        clk2["t"] += 30.0                      # far apart: no loop/rate
        try:
            g2.authorize(f"distinct_op_{i}", 0.05)
            g2.charge(0.05)
            spend_seen = g2.spend
        except HardKill as e:
            killed2 = True
            ceil_spend = e.spend
            break
    ceil_ok = (killed2 and ceil_spend <= 1.00
               and spend_seen <= 1.00 and g2.spend <= 1.00)
    log.append(f"  BINDING ceiling pre-auth: killed at spend="
               f"{ceil_spend} final_spend={g2.spend} (never > 1.00) "
               f"-> {ceil_ok}")
    ok &= ceil_ok

    # ---- 3. spike kill: huge velocity ----
    clk3 = {"t": 0.0}
    g3 = CostGuard("u-spike", ceiling_usd=100.0,
                   spike_usd_per_s=0.50, clock=lambda: clk3["t"])
    spike_killed = False
    for i in range(50):
        clk3["t"] += 0.01                      # 0.30 usd in ~0.03s
        try:
            g3.authorize(f"op{i}", 0.30)
            g3.charge(0.30)
        except HardKill as e:
            spike_killed = "spike" in e.reason
            break
        except Throttled:
            pass
    log.append(f"  BINDING spike kill triggered -> {spike_killed}")
    ok &= spike_killed

    # ---- 4. normal load completely unaffected ----
    clk4 = {"t": 0.0}
    g4 = CostGuard("u-normal", ceiling_usd=1.00, clock=lambda: clk4["t"])
    done = 0
    false_stop = False
    for i in range(20):
        clk4["t"] += 5.0                       # 1 call / 5s: calm
        try:
            g4.authorize(f"varied_op_{i % 7}", 0.01)
            g4.charge(0.01)
            done += 1
        except (HardKill, Throttled):
            false_stop = True
            break
    normal_ok = (done == 20 and not false_stop
                 and abs(g4.spend - 0.20) < 1e-9 and not g4.killed)
    log.append(f"  BINDING normal load unaffected: completed={done}/20 "
               f"spend={g4.spend:.2f} killed={g4.killed} -> {normal_ok}")
    ok &= normal_ok

    fr = subprocess.run(["git", "status", "--porcelain"] + FROZEN,
                         cwd=str(ENGINE.parent), capture_output=True,
                         text=True)
    fc = fr.stdout.strip() == ""
    log.append(f"  BINDING frozen paths clean -> {fc}")
    ok &= fc

    for ln in log:
        print(ln)
    print(f"MH_P8_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
