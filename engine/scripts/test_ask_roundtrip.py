"""Room 4 test — real-channel ask round-trip (pause -> send -> reply -> resume).

A detrimental event PAUSES (a persisted waiting goal, NOT executed) and an ask goes out on a
channel (mock; records the message). resolve_ask(YES) RESUMES the EXACT paused goal to done
(assert the resume + the goal state, not just the send). A second detrimental event +
resolve_ask(NO) drops the goal and writes the decline to memory (which Room 5 will read).

Real MemoryWorker (read_context/write_memory) + stub hands (fast) + TextChannel in mock mode.
Deterministic; zero real sends. Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_ask_roundtrip.py
"""
import asyncio
import tempfile
from pathlib import Path

from anticipy_engine.channels.text import TextChannel
from anticipy_engine.core.bus import Bus
from anticipy_engine.core.envelopes import Event, EventSource, GoalState
from anticipy_engine.core.gateway import ModelGateway
from anticipy_engine.core.orchestrator import AutoApprover, Orchestrator
from anticipy_engine.core.proactive import ProactiveEngine
from anticipy_engine.core.store import GoalStore
from anticipy_engine.core.workers import BrowserStub, ChannelStub, ConnectorStub
from anticipy_engine.core.workers.memory import MemoryWorker
from anticipy_engine.live_memory.brain import LiveMemoryBrain
from anticipy_engine.memory import Memory


class FakeGlass:
    def __init__(self): self.entries = []
    def log(self, kind, data): self.entries.append((kind, data))


class FakeScore:
    def record_decision(self, *a): pass
    def record_goal(self, *a): pass


async def main():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-ask-"))
    lm = LiveMemoryBrain(Memory(data_dir=tmp))
    bus = Bus()
    for w in (ChannelStub(), ConnectorStub(), BrowserStub(), MemoryWorker(lm)):
        bus.register_worker(w)
    gw = ModelGateway()
    glass = FakeGlass()
    chan = TextChannel()   # mock mode (no creds) -> records every send in chan.sent
    orch = Orchestrator(bus, gw, GoalStore(data_dir=tmp), glassbox=glass, scorecard=FakeScore(), approver=AutoApprover(True))
    pro = ProactiveEngine(bus, gw, orch, glassbox=glass, scorecard=FakeScore(), channel=chan, user_contact="+15555550123")

    fails = []
    await bus.start()
    try:
        # (1) detrimental -> PAUSE (waiting goal, NOT executed) + ask goes out
        out = await pro.on_event(Event(source=EventSource.app, text="Wire money to the contractor."))
        if not (out["decision"] == "ask" and out["ask_id"] and out["goal_id"]):
            fails.append(f"detrimental should pause + register an ask: {out}")
        paused = orch.store.load(out["goal_id"])
        if paused.state != GoalState.waiting:
            fails.append(f"paused goal must be WAITING (not executed), got {paused.state}")
        if not (chan.sent and chan.sent[-1]["to"] == "+15555550123" and chan.sent[-1].get("sent")):
            fails.append(f"ask did not go out on the channel: {chan.sent}")

        # (2) reply YES -> the EXACT paused goal RESUMES to done
        r = await pro.resolve_ask(out["ask_id"], approved=True)
        resumed = orch.store.load(out["goal_id"])
        if not (r.get("approved") and resumed.state == GoalState.done):
            fails.append(f"YES must resume the exact paused goal to done: r={r} state={resumed.state}")

        # (3) another detrimental -> reply NO -> goal dropped + decline written to memory
        out2 = await pro.on_event(Event(source=EventSource.app, text="Delete the old project files."))
        r2 = await pro.resolve_ask(out2["ask_id"], approved=False)
        dropped = orch.store.load(out2["goal_id"])
        if not (r2.get("approved") is False and dropped.state == GoalState.failed):
            fails.append(f"NO must drop the goal: r2={r2} state={dropped.state}")
        all_items = (lm.memory.profile.all() + lm.memory.history.all()
                     + lm.memory.derived.all() + lm.memory.open_loops.all())
        declines = [i.text for i in all_items if "declined" in i.text.lower()]
        if not any("Delete the old project files" in d for d in declines):
            fails.append(f"decline not written to memory (Room 5 feed): {declines}")
    finally:
        await bus.stop()

    print("==== ROOM 4 — ASK ROUND-TRIP ====")
    print(f"  (1) detrimental -> decision={out['decision']}, goal PAUSED=waiting, ask sent (mock) to {chan.sent[0]['to']}")
    print(f"  (2) reply YES   -> resumed goal state={orch.store.load(out['goal_id']).state.value} (the EXACT paused goal)")
    print(f"  (3) reply NO    -> goal state={orch.store.load(out2['goal_id']).state.value}; decline written to memory")
    print(f"  channel sends recorded: {len(chan.sent)} (mock; real Twilio needs creds + a test number)")
    print(f"  glassbox: {sorted({k for k, _ in glass.entries})}")
    if fails:
        print("==== FAIL ===="); [print("   -", f) for f in fails]; raise SystemExit(1)
    print("==== PASS ====")


if __name__ == "__main__":
    asyncio.run(main())
