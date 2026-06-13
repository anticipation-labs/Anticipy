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


async def test_empty_plan_never_done():
    tmp, bus, gw, store, _ = make_env()
    gw = ModelGateway(stub=lambda task, tier, caller: "")
    orch = Orchestrator(bus, gw, store, approver=AutoApprover(True), max_retries=0)
    await bus.start()
    try:
        goal = await orch.start_goal(Goal(intent="x", description="Do the vague thing somehow"))
    finally:
        await bus.stop()
    assert goal.state == GoalState.failed, goal.state
    assert goal.steps == []
    assert store.load(goal.id).state == GoalState.failed
    print("  empty plan: failed loudly, not marked done")


async def test_deterministic_calendar_plan():
    tmp, bus, gw, store, _ = make_env()
    # Even if the model would return nothing, an explicit concrete Calendar event
    # should become a real create_event step with the proven API arg shape.
    gw = ModelGateway(stub=lambda task, tier, caller: "")
    orch = Orchestrator(bus, gw, store, approver=AutoApprover(True))
    await bus.start()
    try:
        goal = await orch.start_goal(Goal(
            intent="calendar",
            description=(
                "Create a calendar event titled [Anticipy test] Dentist "
                "on June 18, 2026 from 9:40 AM to 10:10 AM America/Los_Angeles."
            ),
        ))
    finally:
        await bus.stop()

    assert goal.state == GoalState.done, goal.state
    assert [s.intent for s in goal.steps] == ["create_event"], goal.steps
    args = goal.steps[0].args
    assert args["summary"] == "[Anticipy test] Dentist", args
    assert args["start_datetime"].startswith("2026-06-18T09:40:00"), args
    assert args["end_datetime"].startswith("2026-06-18T10:10:00"), args
    assert args["timezone"] == "America/Los_Angeles", args
    assert goal.steps[0].result and goal.steps[0].result.proof
    assert len(gw.smart_calls) == 0
    print("  deterministic calendar: create_event step done with concrete args")


async def test_stub_plan_ignores_memory_inject():
    tmp, bus, gw, store, _ = make_env()
    from anticipy_engine.core.gateway import default_stub
    seen = []

    def recording_stub(task, tier, caller):
        seen.append(task)
        return default_stub(task, tier, caller)

    gw = ModelGateway(stub=recording_stub)
    # memory full of planner-keyword noise; none of it is part of THIS goal
    noisy = {"open_loops": ["check the hardware site for the posted hours"],
             "notes": "open the returns page later"}
    orch = Orchestrator(bus, gw, store, approver=AutoApprover(True),
                        memory_context=lambda about: noisy)
    await bus.start()
    try:
        goal = await orch.start_goal(Goal(
            intent="x",
            description="Get the quarterly vendor sync on my calendar for Tuesday morning."))
    finally:
        await bus.stop()
    # the deterministic tier plans from the GOAL alone: memory keyword noise must
    # not grow junk browse/post steps that park the goal at needs_human
    assert "RELEVANT MEMORY" not in seen[0], seen[0]
    assert [s.intent for s in goal.steps] == ["create_event"], goal.steps
    assert goal.state == GoalState.done, goal.state
    # a REAL model still receives the memory: the inject seam is live-path intact
    live_orch = Orchestrator(bus, ModelGateway(provider="openrouter"), store)
    prompt = live_orch._plan_prompt(Goal(intent="x", description="anything"), noisy)
    assert "RELEVANT MEMORY" in prompt, prompt
    print("  stub plan ignores memory inject: create_event only, done; live prompt keeps memory")


async def test_memory_resolved_store_name_plan():
    # F29: memory names stores the way people speak ("at Walmart"), never as
    # hostnames. The resolver derives the site (deny-bounded; shared/storesite),
    # records the provenance honestly, and a storeless vague request still plans
    # NO browse step (no instruction dumping). Non-bank sentences on purpose.
    from anticipy_engine.core.orchestrator import _browser_action_step, _memory_resolved_browser_step

    spoken = "Grab that ring light thing I was looking at, just stick it in the cart."
    resolving = {"history": ["Was comparing ring lights at Walmart last week - liked the Neewer kit best."]}
    step = _memory_resolved_browser_step(spoken, resolving)
    assert step is not None and step.intent == "browse_task", step
    assert step.args["url"] == "https://www.walmart.com", step.args
    assert step.args["resolved_from_memory"] is True
    assert step.args["memory_resolution"]["site_derived_from_store_name"] is True, step.args
    assert "Do not checkout" in step.args["task"], step.args
    assert "ring lights" in step.args["item"] if "item" in step.args else True

    # a memory line with a SPOKEN hostname keeps provenance False (heard, not derived)
    heard = {"history": ["Was looking at the Neewer ring light kit on bhphotovideo.com last week."]}
    step2 = _memory_resolved_browser_step(spoken, heard)
    assert step2 is not None and step2.args["url"].startswith("https://bhphotovideo.com"), step2.args
    assert step2.args["memory_resolution"]["site_derived_from_store_name"] is False, step2.args

    # storeless memory: vague action line plans NOTHING at the deterministic tier
    storeless = {"history": ["Was comparing ring lights last week - liked the Neewer kit best."]}
    assert _memory_resolved_browser_step(spoken, storeless) is None
    assert _browser_action_step(spoken, storeless) is None  # never a whole-line dump

    cart_only = "That notebook size I liked at Staples, cart one pack so I can check shipping later, no buying."
    cart_ctx = {"history": ["Was comparing spiral notebooks at Staples; liked the 5x8 recycled notebook pack."]}
    step3 = _memory_resolved_browser_step(cart_only, cart_ctx)
    assert step3 is not None and step3.intent == "browse_task", step3
    assert step3.args["url"] == "https://www.staples.com", step3.args
    assert step3.args["memory_resolution"]["item"] == "5x8 recycled notebook pack", step3.args
    assert "Do not checkout" in step3.args["task"], step3.args

    product_page_ctx = {
        "history": [
            "I was looking at the Computing and Internet book at "
            "https://demowebshop.tricentis.com/computing-and-internet and liked Computing and Internet."
        ]
    }
    product_page_step = _memory_resolved_browser_step(
        "That Computing and Internet book thing, put it in the cart so I can check it later.",
        product_page_ctx,
    )
    assert product_page_step is not None and product_page_step.intent == "browse_task", product_page_step
    assert product_page_step.args["url"] == "https://demowebshop.tricentis.com/computing-and-internet", \
        product_page_step.args
    assert product_page_step.args["memory_resolution"]["item"] == "Computing and Internet", product_page_step.args

    lowes_cart = (
        "That grab bar I was looking at for Dad's shower, put it in the cart at Lowe's, no checkout."
    )
    lowes_ctx = {
        "history": [
            lowes_cart,
            "Was comparing shower grab bars at Lowe's for Dad's bathroom; preferred the Moen 24-inch bar."
        ]
    }
    step4 = _memory_resolved_browser_step(lowes_cart, lowes_ctx)
    assert step4 is not None and step4.intent == "browse_task", step4
    assert step4.args["url"] == "https://www.lowes.com", step4.args
    assert step4.args["memory_resolution"]["item"] == "Moen 24-inch bar", step4.args
    assert step4.args["memory_resolution"]["site_derived_from_store_name"] is True, step4.args

    mixed_brand = {
        "history": ["Was comparing portable projector stands at B&H Photo; liked the folding stand best."]
    }
    step5 = _memory_resolved_browser_step(
        "That projector stand thing, put it in the cart if the same one is still at B&H, don't buy it.",
        mixed_brand,
    )
    assert step5 is not None and step5.intent == "browse_task", step5
    assert step5.args["url"] == "https://www.bhphotovideo.com", step5.args
    assert step5.args["memory_resolution"]["item"] == "folding stand", step5.args
    assert step5.args["memory_resolution"]["site_derived_from_store_name"] is True, step5.args

    unseeded_ampersand = {
        "history": ["Was comparing portable tripod stands at A&B Photo; liked the folding stand best."]
    }
    assert _memory_resolved_browser_step(
        "That tripod stand thing, put it in the cart if the same one is still at A&B Photo, don't buy it.",
        unseeded_ampersand,
    ) is None

    # end-to-end: the resolved plan drives the goal to done with proof, zero model calls
    tmp, bus, gw, store, _ = make_env()
    orch = Orchestrator(bus, gw, store, approver=AutoApprover(True),
                        memory_context=lambda about: resolving)
    await bus.start()
    try:
        goal = await orch.start_goal(Goal(intent="cart", description=spoken))
    finally:
        await bus.stop()
    assert [s.intent for s in goal.steps] == ["browse_task"], goal.steps
    assert goal.state == GoalState.done and goal.steps[0].result.proof, goal.state
    assert len(gw.smart_calls) == 0

    tmp2, bus2, gw2, store2, _ = make_env()
    orch2 = Orchestrator(bus2, gw2, store2, approver=AutoApprover(True),
                         memory_context=lambda about: cart_ctx)
    await bus2.start()
    try:
        goal2 = await orch2.start_goal(Goal(intent="cart", description=cart_only))
    finally:
        await bus2.stop()
    assert [s.intent for s in goal2.steps] == ["browse_task"], goal2.steps
    assert goal2.steps[0].args["url"] == "https://www.staples.com", goal2.steps[0].args
    assert goal2.state == GoalState.done and goal2.steps[0].result.proof, goal2.state
    assert len(gw2.smart_calls) == 0
    print("  memory-resolved store name: derived-site browse plan, honest provenance, "
          "storeless stays unplanned, goal done with proof")


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
    await test_empty_plan_never_done()
    await test_deterministic_calendar_plan()
    await test_stub_plan_ignores_memory_inject()
    await test_memory_resolved_store_name_plan()
    await test_approval_denied()
    await test_persist_and_resume()
    print("PASS piece 4: orchestrator (plan/dispatch/verify/retry/reroute/persist/resume)")


if __name__ == "__main__":
    asyncio.run(main())
