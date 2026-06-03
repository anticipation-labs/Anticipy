"""Piece 4 test: the orchestrator (plan, dispatch, verify, retry, reroute, persist, resume).

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_orchestrator.py
"""
import asyncio
import tempfile
from pathlib import Path

from anticipy_engine.core.bus import Bus
from anticipy_engine.core.envelopes import Goal, GoalState, JobStatus, Result, Risk, Step, StepState
from anticipy_engine.core.gateway import ModelGateway
from anticipy_engine.core.orchestrator import AutoApprover, Orchestrator
from anticipy_engine.core.store import GoalStore
from anticipy_engine.core.workers import BrowserStub, ChannelStub, ConnectorStub, MemoryStub, FAIL, SUCCESS, SUCCESS_NO_PROOF


def make_env():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-orch-"))
    channel, memory, connector, browser = ChannelStub(), MemoryStub(), ConnectorStub(), BrowserStub()
    bus = Bus()
    for w in (channel, memory, connector, browser):
        bus.register_worker(w)
    return tmp, bus, ModelGateway(), GoalStore(data_dir=tmp), (channel, memory, connector, browser)


async def test_happy_path_with_retry():
    tmp, bus, gw, store, (channel, memory, connector, browser) = make_env()
    connector.script("create_event", FAIL, SUCCESS)  # fail once, then succeed
    orch = Orchestrator(bus, gw, store, approver=AutoApprover(True))
    await bus.start()
    try:
        goal = Goal(intent="favor", description="I'll send Sarah the Q3 deck on Friday and book us lunch.")
        goal = await orch.start_goal(goal)
    finally:
        await bus.stop()

    assert goal.state == GoalState.done, goal.state
    assert [s.intent for s in goal.steps] == ["send_email", "create_event", "write_memory"]
    for s in goal.steps:
        assert s.state == StepState.done and s.result and s.result.proof, s
    ce = next(s for s in goal.steps if s.intent == "create_event")
    assert ce.attempts >= 2, ce.attempts            # retried after the scripted failure
    assert len(gw.smart_calls) == 1                 # plan only (no gate in this test)
    # persisted as done
    assert store.load(goal.id).state == GoalState.done
    print("  happy path: done; create_event attempts =", ce.attempts, "; smart calls =", len(gw.smart_calls))


async def test_verify_before_done():
    tmp, bus, gw, store, (channel, memory, connector, browser) = make_env()
    channel.script("send_email", SUCCESS_NO_PROOF)  # 'success' but no proof, forever
    orch = Orchestrator(bus, gw, store, approver=AutoApprover(True), max_retries=1)
    await bus.start()
    try:
        goal = await orch.start_goal(Goal(intent="x", description="email Sarah the deck"))
    finally:
        await bus.stop()
    # no step may be 'done' without proof; the goal must NOT be done
    assert goal.state != GoalState.done
    assert all(not (s.state == StepState.done and not (s.result and s.result.proof)) for s in goal.steps)
    se = next(s for s in goal.steps if s.intent == "send_email")
    assert se.state != StepState.done
    print("  verify-before-done: send_email NOT marked done (no proof); goal state =", goal.state.value)


async def test_approval_denied():
    tmp, bus, gw, store, _ = make_env()
    orch = Orchestrator(bus, gw, store, approver=AutoApprover(False))  # deny everything risky
    await bus.start()
    try:
        goal = await orch.start_goal(Goal(intent="x", description="send Sarah an email with the deck"))
    finally:
        await bus.stop()
    se = next(s for s in goal.steps if s.intent == "send_email")
    assert se.state == StepState.needs_human and se.attempts == 0  # denied before any dispatch
    assert goal.state == GoalState.waiting
    print("  approval denied: send_email needs_human, never dispatched; goal waiting")


async def test_persist_and_resume():
    tmp, bus, gw, store, _ = make_env()
    # A goal that 'ran' step 0 (done, with proof) and is parked waiting on step 1.
    step0 = Step(intent="send_email", risk=Risk.low, state=StepState.done,
                 result=Result(job_id="prev", status=JobStatus.success, proof={"message_id": "prev"}))
    step1 = Step(intent="create_event", risk=Risk.low)
    parked = Goal(intent="resume", description="resume me", state=GoalState.waiting, steps=[step0, step1])
    store.save(parked)

    # "Restart": a brand-new orchestrator + bus reading the SAME store from disk.
    bus2 = Bus()
    for w in (ChannelStub(), MemoryStub(), ConnectorStub(), BrowserStub()):
        bus2.register_worker(w)
    gw2 = ModelGateway()
    orch2 = Orchestrator(bus2, gw2, GoalStore(data_dir=tmp))
    await bus2.start()
    try:
        resumed = await orch2.resume_waiting()
    finally:
        await bus2.stop()

    assert len(resumed) == 1
    reloaded = GoalStore(data_dir=tmp).load(parked.id)
    assert reloaded.state == GoalState.done
    assert all(s.state == StepState.done and s.result and s.result.proof for s in reloaded.steps)
    assert len(gw2.smart_calls) == 0  # resume does NOT re-plan
    print("  persist+resume: parked goal reloaded from disk and resumed to done; no re-plan")


async def main():
    await test_happy_path_with_retry()
    await test_verify_before_done()
    await test_approval_denied()
    await test_persist_and_resume()
    print("PASS piece 4: orchestrator (plan/dispatch/verify/retry/reroute/persist/resume)")


if __name__ == "__main__":
    asyncio.run(main())
