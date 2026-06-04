"""Room 5 test — the annoyance budget (cap proactive interruptions; learn from declines).

PART 1 (budget): replay a day of PROACTIVE detrimental asks; interruptions sent stay <= the
configured cap, the rest are suppressed (over budget).
PART 2 (decline-learning): after the user DECLINES an action-type, the SAME proactive type is
suppressed on its next occurrence, while a DIFFERENT type still goes through.
PART 3 (safety): a USER-initiated ask is NEVER suppressed (even at cap 0) — the user asked.

Real MemoryWorker + stub hands + mock channel; controlled clock; deterministic.
Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_annoyance.py
"""
import asyncio
import tempfile
from pathlib import Path

from anticipy_engine.channels.text import TextChannel
from anticipy_engine.core.bus import Bus
from anticipy_engine.core.envelopes import Event, EventSource
from anticipy_engine.core.gateway import ModelGateway
from anticipy_engine.core.orchestrator import AutoApprover, Orchestrator
from anticipy_engine.core.proactive import ProactiveEngine
from anticipy_engine.core.store import GoalStore
from anticipy_engine.core.workers import BrowserStub, ChannelStub, ConnectorStub
from anticipy_engine.core.workers.memory import MemoryWorker
from anticipy_engine.live_memory.brain import LiveMemoryBrain
from anticipy_engine.memory import Memory
from anticipy_engine.proactive.budget import AnnoyanceBudget
from anticipy_engine.shared.schema import now_ts


class FakeGlass:
    def __init__(self): self.entries = []
    def log(self, kind, data): self.entries.append((kind, data))


class FakeScore:
    def record_decision(self, *a): pass
    def record_goal(self, *a): pass


def make():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-budget-"))
    lm = LiveMemoryBrain(Memory(data_dir=tmp))
    bus = Bus()
    for w in (ChannelStub(), ConnectorStub(), BrowserStub(), MemoryWorker(lm)):
        bus.register_worker(w)
    gw = ModelGateway()
    orch = Orchestrator(bus, gw, GoalStore(data_dir=tmp), glassbox=FakeGlass(), scorecard=FakeScore(), approver=AutoApprover(True))
    pro = ProactiveEngine(bus, gw, orch, glassbox=FakeGlass(), scorecard=FakeScore(), channel=TextChannel())
    return bus, pro


async def main():
    bus, pro = make()
    now = now_ts()
    fails = []
    await bus.start()
    try:
        # PART 1 — interruption budget caps proactive asks
        pro.budget = AnnoyanceBudget(max_per_day=3)   # small cap for the test (DECISIONS-ONLY-OMAR)
        outs = [await pro.on_event(Event(source=EventSource.system, text=f"Wire payment {i} to a vendor."), now=now)
                for i in range(6)]
        asks = [o for o in outs if o["decision"] == "ask"]
        supp = [o for o in outs if o["decision"] == "suppressed"]
        if not (len(asks) == 3 and len(supp) == 3):
            fails.append(f"budget cap: expected 3 ask + 3 suppressed, got asks={len(asks)} supp={len(supp)}")
        if pro.budget.count(now) != 3:
            fails.append(f"budget count should be 3, got {pro.budget.count(now)}")

        # PART 2 — decline a type -> suppress the SAME type next time; a different type still asks
        pro.budget = AnnoyanceBudget(max_per_day=99)  # high cap -> only decline-suppression can fire
        o1 = await pro.on_event(Event(source=EventSource.system, text="Email the investor about the Q3 deck."), now=now)
        if not (o1["decision"] == "ask" and o1["ask_id"]):
            fails.append(f"first proactive ask should go through: {o1}")
        await pro.resolve_ask(o1["ask_id"], approved=False)   # user declines this type
        o2 = await pro.on_event(Event(source=EventSource.system, text="Email the investor about the Q3 deck."), now=now)
        if o2["decision"] != "suppressed":
            fails.append(f"declined type should be suppressed next time: {o2}")
        o3 = await pro.on_event(Event(source=EventSource.system, text="Delete the old build logs."), now=now)
        if o3["decision"] != "ask":
            fails.append(f"a different type should still ask: {o3}")

        # PART 3 — a USER-initiated ask is never suppressed (even at cap 0)
        pro.budget = AnnoyanceBudget(max_per_day=0)
        ouser = await pro.on_event(Event(source=EventSource.app, text="Wire payment to a vendor."), now=now)
        if ouser["decision"] != "ask":
            fails.append(f"user-initiated ask must bypass the budget: {ouser}")
        oproactive = await pro.on_event(Event(source=EventSource.system, text="Wire a different payment."), now=now)
        if oproactive["decision"] != "suppressed":
            fails.append(f"proactive ask at cap 0 must be suppressed: {oproactive}")
    finally:
        await bus.stop()

    print("==== ROOM 5 — ANNOYANCE BUDGET ====")
    print(f"  PART 1 budget(cap=3): 6 proactive detrimental -> {len(asks)} asked, {len(supp)} suppressed (<= cap)")
    print(f"  PART 2 decline-learning: declined 'email investor' -> same type suppressed; different type still asks")
    print(f"  PART 3 user-initiated ask bypasses budget (cap 0); proactive ask suppressed")
    print(f"  NOTE: the cap NUMBER is DECISIONS-ONLY-OMAR (research ceiling ~3-5/day; default 5)")
    if fails:
        print("==== FAIL ===="); [print("   -", f) for f in fails]; raise SystemExit(1)
    print("==== PASS ====")


if __name__ == "__main__":
    asyncio.run(main())
