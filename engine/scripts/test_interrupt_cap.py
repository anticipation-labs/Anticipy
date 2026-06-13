"""Room 5 test — the HARD global interrupt cap (J5: cold-boot flood guard).

The AnnoyanceBudget is a soft per-type learner; the InterruptGuard is a blunt HARD ceiling
so a cold boot against a backlog of due loops can NEVER become a text storm (it once fired
6 real reminder SMS in ~36s). This pins:
  PART 1 (boot cap): with the budget wide open, proactive interrupts beyond the per-boot cap
          are SUPPRESSED (not sent); exactly cap real sends leave the channel.
  PART 2 (window cap): the rolling-window ceiling fires independently of the boot cap.
  PART 3 (user bypass): a USER-initiated event is NEVER capped (even at cap 0) — the user asked.
  PART 4 (money invariant): at cap, a money/hard-stop is NEVER demoted to "suppressed" and
          NEVER executes — it still routes to its hard stop with the goal left WAITING.

Real MemoryWorker + stub hands + mock channel; controlled clock; deterministic; 0 model calls.
Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_interrupt_cap.py
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

# Deterministic + safe: force the STUB brain so this test never calls the live (rate-limited)
# model. Set before the anticipy_engine imports trigger .env.local load (load_dotenv override=False).
os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_MEMORY_MODE", "stub")

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
from anticipy_engine.proactive.budget import AnnoyanceBudget, InterruptGuard
from anticipy_engine.shared.schema import now_ts


class FakeGlass:
    def __init__(self): self.entries = []
    def log(self, kind, data): self.entries.append((kind, data))


class FakeScore:
    def record_decision(self, *a): pass
    def record_goal(self, *a): pass


def make():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-guard-"))
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
        # PART 1 — per-BOOT cap (budget wide open so ONLY the guard can suppress)
        pro.budget = AnnoyanceBudget(max_per_day=999)
        pro.guard = InterruptGuard(max_boot=2, max_window=999, window_s=3600.0)
        outs = [await pro.on_event(Event(source=EventSource.system,
                                         text=f"Send the signed contract to vendor {i}."), now=now)
                for i in range(5)]
        asks = [o for o in outs if o["decision"] == "ask"]
        supp = [o for o in outs if o["decision"] == "suppressed"]
        sent = sum(1 for s in pro.channel.sent if s.get("sent"))
        if len(asks) != 2:
            fails.append(f"boot cap: expected 2 asks, got {len(asks)}")
        if len(supp) != 3:
            fails.append(f"boot cap: expected 3 suppressed, got {len(supp)} (decisions={[o['decision'] for o in outs]})")
        if sent != 2:
            fails.append(f"boot cap: expected 2 REAL channel sends, got {sent}")
        if pro.guard.boot_count != 2:
            fails.append(f"boot cap: guard.boot_count should be 2, got {pro.guard.boot_count}")

        # PART 2 — rolling WINDOW cap fires independently of the boot cap (reuse the STARTED engine;
        # a fresh budget + guard reset the counters). A second make() whose bus is never started would
        # hang forever on the first read_context job — reuse, don't re-create.
        pro.budget = AnnoyanceBudget(max_per_day=999)
        pro.guard = InterruptGuard(max_boot=999, max_window=2, window_s=3600.0)
        outs2 = [await pro.on_event(Event(source=EventSource.system,
                                          text=f"Send the signed contract to vendor {i}."), now=now)
                 for i in range(5)]
        if sum(1 for o in outs2 if o["decision"] == "ask") != 2:
            fails.append(f"window cap: expected 2 asks, got {[o['decision'] for o in outs2]}")

        # PART 3 — USER-initiated events are NEVER capped (even at cap 0)
        pro.guard = InterruptGuard(max_boot=0, max_window=0, window_s=3600.0)
        u = await pro.on_event(Event(source=EventSource.app,
                                     text="Send the signed contract to the vendor."), now=now)
        if u["decision"] not in ("ask", "act"):
            fails.append(f"user-initiated event must bypass the cap, got {u['decision']}")

        # PART 4 — at cap, a money/hard-stop is NEVER demoted to suppressed and NEVER executes
        pro.guard = InterruptGuard(max_boot=0, max_window=0, window_s=3600.0)
        m = await pro.on_event(Event(source=EventSource.system,
                                     text="Wire $5,000 to the contractor's account now."), now=now)
        if m["decision"] in ("act", "suppressed"):
            fails.append(f"money at cap must NOT act or be demoted to suppressed, got {m['decision']}")
        if m.get("goal_id"):
            g = pro.orchestrator.store.load(m["goal_id"])
            if g is not None and g.state in (GoalState.done, GoalState.running):
                fails.append(f"money goal must NEVER execute (done/running) at cap, got {g.state}")
    finally:
        await bus.stop()

    print("==== ROOM 5 — HARD INTERRUPT CAP (J5) ====")
    if fails:
        print("==== FAIL ===="); [print("   -", f) for f in fails]; sys.exit(1)
    print("  boot cap + window cap suppress excess proactive interrupts; user events bypass; money never demoted/executed")
    print("==== PASS ====")


if __name__ == "__main__":
    asyncio.run(main())
