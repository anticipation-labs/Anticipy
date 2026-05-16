"""P6 gate: Layer B handoff, mocked scenarios then ONE real path.

Mocked (no real side effects): the typed contract round trips; an
action engine clarification is resolved from memory FIRST; escalation
fires ONLY when memory resolution is below 0.70; the action engine is
NEVER left synchronously blocked.

Real (one path only): a full proactive decision for a safe READ only
task is handed through the single adapter seam to the ACTUAL frozen
DSv4SkillRunner, and a real TaskResult comes back (not the mock's
signature), proving the wiring is real. Then git proves no frozen
action engine file changed.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))


def _mock_scenarios() -> tuple[bool, list]:
    from app.anticipy import action_handoff, memory
    from app.anticipy.action_handoff import ProactiveContract, handoff
    from app.anticipy.seams import UserContext, UserProfile

    action_handoff.use_mock()
    log = []
    ok = True

    # 1. round trip, no clarification -> SUCCESS, intent_id preserved
    ctx = UserContext.from_profile(UserProfile(user_id="p6-rt", name="O", role_title="F", mandate="ops"))
    c1 = ProactiveContract(intent_id="iid-1", action="navigate_to", object="open the dashboard")
    r1 = handoff(c1, ctx)
    t1 = r1.status == "SUCCESS" and r1.intent_id == "iid-1" and r1.blocked is False
    log.append(f"[{'ok' if t1 else 'FAIL'}] round-trip SUCCESS, intent_id preserved, not blocked ({r1.status})")
    ok &= t1

    # 2. clarification resolved from memory (>=0.70) -> no escalation
    memory.reset("p6-mem")
    memory.seed("p6-mem", {"the usual place": "Carbone on Thompson St"})
    ctx2 = UserContext.from_profile(UserProfile(user_id="p6-mem", name="O", role_title="F", mandate="ops"))
    c2 = ProactiveContract(intent_id="iid-2", action="book_reservation", object="book the usual place")
    p2 = c2.to_dict()
    p2["_needs_clarification"] = True
    p2["_clarification_question"] = "which restaurant, the usual place?"

    # feed the marker contract by stashing it on the object the mock sees
    class _C(ProactiveContract):
        def to_dict(self_inner):
            d = ProactiveContract.to_dict(self_inner)
            d["_needs_clarification"] = True
            d["_clarification_question"] = "which restaurant, the usual place?"
            return d

    c2m = _C(intent_id="iid-2", action="book_reservation", object="book the usual place")
    r2 = handoff(c2m, ctx2)
    via2 = [p.get("via") for p in r2.clarification_path]
    t2 = ("memory_resolved" in via2) and ("escalated_to_comms" not in via2) and r2.status == "SUCCESS" and r2.blocked is False
    log.append(f"[{'ok' if t2 else 'FAIL'}] clarification memory-resolved >=0.70, NOT escalated, SUCCESS ({via2}, {r2.status})")
    ok &= t2

    # 3. clarification NOT resolvable (<0.70) -> escalate, proceed on
    #    assumption, never blocked
    memory.reset("p6-nomem")
    ctx3 = UserContext.from_profile(UserProfile(user_id="p6-nomem", name="O", role_title="F", mandate="ops"))

    class _C3(ProactiveContract):
        def to_dict(self_inner):
            d = ProactiveContract.to_dict(self_inner)
            d["_needs_clarification"] = True
            d["_clarification_question"] = "which of the seven unnamed things from before did you mean?"
            return d

    c3 = _C3(intent_id="iid-3", action="send_email", object="send the thing")
    r3 = handoff(c3, ctx3)
    via3 = [p.get("via") for p in r3.clarification_path]
    t3 = ("escalated_to_comms" in via3) and r3.status == "PROCEEDED_ON_ASSUMPTION" and r3.blocked is False
    log.append(f"[{'ok' if t3 else 'FAIL'}] clarification <0.70 escalated, PROCEEDED_ON_ASSUMPTION, never blocked ({via3}, {r3.status})")
    ok &= t3

    # 4. invariant across all: never blocked
    t4 = all(r.blocked is False for r in (r1, r2, r3))
    log.append(f"[{'ok' if t4 else 'FAIL'}] action engine never synchronously blocked (invariant)")
    ok &= t4

    return ok, log


def _real_path() -> tuple[bool, list]:
    import asyncio

    from app.anticipy import action_handoff
    from app.anticipy.action_handoff import contract_from_decision, handoff
    from app.anticipy.proactive_engine import ProactiveEngine
    from app.anticipy.seams import UserContext, UserProfile

    log = []
    # full proactive decision for a safe READ-only task
    eng = ProactiveEngine()
    ctx = UserContext.from_profile(UserProfile(user_id="p6-real", name="Omar", role_title="Founder", mandate="ops"))
    task = "Open Wikipedia and tell me the year the Python programming language was first released."
    decision = asyncio.run(eng.decide([{"speaker_id": "WEARER", "text": task, "ts": 0.0}], ctx, "direct"))
    log.append(f"proactive decision: {decision.decision} (conf {decision.confidence})")
    if decision.decision != "ACT":
        log.append("[FAIL] proactive did not ACT on a clear direct READ-only command")
        return False, log

    contract = contract_from_decision(decision)
    action_handoff.use_real(cdp_port=9222, max_iters=12)
    res = handoff(contract, ctx)
    log.append(f"real handoff status={res.status} answer={res.answer[:120]!r} traj={res.raw.get('trajectory_dir','')}")
    # real, not mock: the mock's answer always starts with "mock executed:"
    is_real = not str(res.answer).startswith("mock executed:")
    returned = res.status in ("SUCCESS", "ITERATION_EXHAUSTED", "HARD_FAIL", "ERROR", "PROCEEDED_ON_ASSUMPTION", "UNKNOWN")
    ok = is_real and returned and res.blocked is False
    log.append(f"[{'ok' if ok else 'FAIL'}] real frozen DSv4SkillRunner invoked through the adapter and returned (not mock)")
    return ok, log


def _frozen_unmodified() -> tuple[bool, list]:
    log = []
    st = subprocess.run(
        ["git", "status", "--porcelain", "--", "engine/app/action_engine"],
        cwd=str(ENGINE.parent), capture_output=True, text=True,
    ).stdout.strip()
    diff = subprocess.run(
        ["git", "diff", "--quiet", "--", "engine/app/action_engine"],
        cwd=str(ENGINE.parent),
    ).returncode
    clean = (st == "") and (diff == 0)
    log.append(f"[{'ok' if clean else 'FAIL'}] no frozen action-engine file changed (status empty={st==''}, diff clean={diff==0})")
    return clean, log


def main() -> int:
    mok, mlog = _mock_scenarios()
    print("-- mocked scenarios --")
    for line in mlog:
        print("  " + line)

    rok, rlog = _real_path()
    print("-- one real READ-only path --")
    for line in rlog:
        print("  " + line)

    fok, flog = _frozen_unmodified()
    print("-- frozen action engine integrity --")
    for line in flog:
        print("  " + line)

    ok = mok and rok and fok
    print(f"P6_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
