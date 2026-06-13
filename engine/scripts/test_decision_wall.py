"""Room 1.5 test — the decision wall (J2: the action-brain degrades, never freezes).

The brain is a rate-limited free tier; a single decider model call can hang 60s+. An
always-listening loop must NEVER freeze on a slow brain — a timed-out decision is deafness,
routed to the SAME bounded defer-then-fail-silent path (an unread line NEVER acts). This pins:
  - a decider that stalls (10s) is bounded by ANTICIPY_DECISION_WALL_S and the event DEFERS
    fast (well under the stall), instead of blocking the loop;
  - a normal fast decider is unaffected.
Stub brain forced; fake slow decider; controlled clock; deterministic; 0 real model calls.
Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_decision_wall.py
"""
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")   # never call the live (starved) brain
os.environ.setdefault("ANTICIPY_MEMORY_MODE", "stub")

import asyncio  # noqa: E402

from anticipy_engine.channels.text import TextChannel  # noqa: E402
from anticipy_engine.core.bus import Bus  # noqa: E402
from anticipy_engine.core.envelopes import Event, EventSource  # noqa: E402
from anticipy_engine.core.gateway import ModelGateway  # noqa: E402
from anticipy_engine.core.orchestrator import AutoApprover, Orchestrator  # noqa: E402
from anticipy_engine.core.proactive import ProactiveEngine  # noqa: E402
from anticipy_engine.core.store import GoalStore  # noqa: E402
from anticipy_engine.core.workers import BrowserStub, ChannelStub, ConnectorStub  # noqa: E402
from anticipy_engine.core.workers.memory import MemoryWorker  # noqa: E402
from anticipy_engine.live_memory.brain import LiveMemoryBrain  # noqa: E402
from anticipy_engine.memory import Memory  # noqa: E402
from anticipy_engine.proactive.decider import ACT as DECIDER_ACT  # noqa: E402
from anticipy_engine.shared.schema import now_ts  # noqa: E402


class FakeGlass:
    def __init__(self): self.entries = []
    def log(self, kind, data): self.entries.append((kind, data))


class FakeScore:
    def record_decision(self, *a): pass
    def record_goal(self, *a): pass


class StallDecider:
    """A decider that hangs (a starved brain) — the wall must bound it."""
    def __init__(self, delay): self.delay = delay
    async def decide(self, line):
        await asyncio.sleep(self.delay)
        return DECIDER_ACT


class FastDecider:
    async def decide(self, line):
        return DECIDER_ACT


def make():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-wall-"))
    lm = LiveMemoryBrain(Memory(data_dir=tmp))
    bus = Bus()
    for w in (ChannelStub(), ConnectorStub(), BrowserStub(), MemoryWorker(lm)):
        bus.register_worker(w)
    gw = ModelGateway()
    orch = Orchestrator(bus, gw, GoalStore(data_dir=tmp), glassbox=FakeGlass(),
                        scorecard=FakeScore(), approver=AutoApprover(True))
    pro = ProactiveEngine(bus, gw, orch, glassbox=FakeGlass(), scorecard=FakeScore(),
                          channel=TextChannel())
    return bus, pro


async def main():
    bus, pro = make()
    now = now_ts()
    fails = []
    await bus.start()
    try:
        # A stalled brain must be BOUNDED, not freeze the loop.
        pro.decider = StallDecider(delay=10.0)
        os.environ["ANTICIPY_DECISION_WALL_S"] = "0.3"
        t0 = time.time()
        o = await pro.on_event(Event(source=EventSource.system,
                                     text="follow up on the signed contract"), now=now)
        dt = time.time() - t0
        os.environ.pop("ANTICIPY_DECISION_WALL_S", None)
        if dt > 3.0:
            fails.append(f"decider stall not bounded: on_event took {dt:.1f}s (must fail fast under the wall)")
        if o["decision"] != "deferred":
            fails.append(f"a timed-out decision must route to the deaf/defer path, got {o['decision']}")

        # A fast decider is unaffected.
        pro.decider = FastDecider()
        o2 = await pro.on_event(Event(source=EventSource.system,
                                      text="send the signed contract to the vendor"), now=now)
        if o2["decision"] == "deferred":
            fails.append(f"a fast decider must NOT be treated as deaf, got {o2['decision']}")
    finally:
        await bus.stop()

    print("==== ROOM 1.5 — DECISION WALL (J2) ====")
    if fails:
        print("==== FAIL ===="); [print("   -", f) for f in fails]; sys.exit(1)
    print("  a stalled brain is bounded -> deaf/defer (no freeze); a fast brain is unaffected")
    print("==== PASS ====")


if __name__ == "__main__":
    asyncio.run(main())
