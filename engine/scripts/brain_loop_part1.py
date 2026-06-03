"""brain_loop part 1: drive the brain through one full goal against stubs and
assert sections 2-5, 7, 8. Then park a second goal in 'waiting' on disk for the
restart test (part 2). Shares ANTICIPY_DATA_DIR with part 2.
"""
import asyncio

from anticipy_engine.core.control_core import ControlCore
from anticipy_engine.core.envelopes import Goal, GoalState, JobStatus, Result, Risk, Step, StepState
from anticipy_engine.core.workers import FAIL, SUCCESS

EVENT = "I'll send Sarah the Q3 deck on Friday and book us lunch."


async def main() -> None:
    core = ControlCore()  # data dir from ANTICIPY_DATA_DIR

    # (4) script a still-stub worker (write_memory -> memory_stub) to fail once,
    # then succeed. (create_event is now handled by the real ApiHand, not a stub.)
    core.bus.worker_for("write_memory").script("write_memory", FAIL, SUCCESS)

    await core.start()
    try:
        out = await core.feed("mac_mic", EVENT)  # (1) feed the event
    finally:
        await core.stop()

    # (2) the gate triaged it actionable and decided; goal handed off
    assert out["decision"] == "do_and_notify" and out["goal_id"], out
    goal = core.store.load(out["goal_id"])

    # (3) planned into the three stub-backed steps, in order
    intents = [s.intent for s in goal.steps]
    assert intents == ["send_email", "create_event", "write_memory"], intents

    # (4) the scripted worker failed once and was retried to success
    wm = next(s for s in goal.steps if s.intent == "write_memory")
    assert wm.attempts >= 2 and wm.state == StepState.done, wm

    # (5) goal done, and NO step is done without proof
    assert goal.state == GoalState.done, goal.state
    for s in goal.steps:
        assert s.state == StepState.done and s.result and s.result.proof, s

    # (7) the smart model was used exactly twice: gate + plan
    callers = sorted(c["caller"] for c in core.gateway.smart_calls)
    assert callers == ["gate", "plan"], callers

    # (8) glass-box has the full trail; scorecard recorded the decision + outcome
    entries = core.glassbox.entries()
    kinds = {e["kind"] for e in entries}
    for need in ("event", "decision", "job", "result", "goal_done"):
        assert need in kinds, (need, sorted(kinds))
    n_jobs = sum(1 for e in entries if e["kind"] == "job")
    n_results = sum(1 for e in entries if e["kind"] == "result")
    assert n_jobs >= 4 and n_results >= 4, (n_jobs, n_results)
    ro = core.scorecard.readout()
    assert ro["decisions"].get("do_and_notify") == 1, ro
    assert ro["goal_outcomes"].get("success") == 1, ro

    # (6 setup) park a second goal in 'waiting', persisted, for the restart test
    parked = Goal(
        intent="waiting goal",
        description="resume me after restart",
        state=GoalState.waiting,
        steps=[
            Step(intent="send_email", risk=Risk.low, state=StepState.done,
                 result=Result(job_id="prev", status=JobStatus.success, proof={"message_id": "prev"})),
            Step(intent="create_event", risk=Risk.low),
        ],
    )
    core.store.save(parked)

    print("PART1 PASS")
    print(f"  goal1={goal.id[:8]} state={goal.state.value} steps={intents} write_memory_attempts={wm.attempts}")
    print(f"  smart_calls={callers} model_cost={core.gateway.total_cost()}")
    print(f"  glassbox kinds={sorted(kinds)} jobs={n_jobs} results={n_results}")
    print(f"  scorecard={ro}")
    print(f"  parked_waiting_goal={parked.id[:8]}")


if __name__ == "__main__":
    asyncio.run(main())
