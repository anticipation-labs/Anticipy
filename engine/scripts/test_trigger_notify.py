"""Room 3 reminder routing test — a fired TIME-GROUNDED reminder NOTIFIES, never asks.

Plants open loops with remind_ts (what due-time grounding writes at capture):
  - a safe reminder past its remind_ts -> direct channel notify, NO pending ask,
    NO new goal, loop marked waiting, counted against the annoyance budget.
  - a detrimental reminder (money text) -> falls back to the ask round-trip.
  - over-budget reminders -> suppressed (no notify, no ask).
  - fire-once still holds; non-reminder loops (no remind_ts) keep the act path.

Real MemoryWorker + stub hands. Deterministic, zero model calls.
Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_trigger_notify.py
"""
import asyncio
import tempfile
from pathlib import Path

from anticipy_engine.core.bus import Bus
from anticipy_engine.core.gateway import ModelGateway
from anticipy_engine.core.orchestrator import AutoApprover, Orchestrator
from anticipy_engine.core.proactive import ProactiveEngine
from anticipy_engine.core.store import GoalStore
from anticipy_engine.core.workers import BrowserStub, ChannelStub, ConnectorStub
from anticipy_engine.core.workers.memory import MemoryWorker
from anticipy_engine.live_memory.brain import LiveMemoryBrain
from anticipy_engine.memory import Memory
from anticipy_engine.shared.schema import MemoryItem, now_ts


class FakeGlass:
    def __init__(self): self.entries = []
    def log(self, kind, data): self.entries.append((kind, data))


class FakeScore:
    def record_decision(self, *a): pass
    def record_goal(self, *a): pass


def loop(text, **fields_and_ts):
    ts = fields_and_ts.pop("timestamp", None)
    item = MemoryItem(kind="open_loop", text=text, status="open",
                      fields={"task": text, **fields_and_ts})
    if ts is not None:
        item.timestamp = ts
    return item


async def main():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-trignotify-"))
    lm = LiveMemoryBrain(Memory(data_dir=tmp))
    bus = Bus()
    for w in (ChannelStub(), ConnectorStub(), BrowserStub(), MemoryWorker(lm)):
        bus.register_worker(w)
    glass = FakeGlass()
    orch = Orchestrator(bus, ModelGateway(), GoalStore(data_dir=tmp), glassbox=glass,
                        scorecard=FakeScore(), approver=AutoApprover(True))
    pro = ProactiveEngine(bus, ModelGateway(), orch, glassbox=glass, scorecard=FakeScore())

    now = now_ts()
    # a grounded reminder whose 15-min lead has arrived (due still 2 min out — the gate-S2 shape)
    safe = lm.memory.open_loops.write(
        loop("remind me to stretch", due_ts=now + 120, remind_ts=now - 10, timestamp=now - 600))
    # a grounded reminder whose TEXT is money — must re-gate to ASK, never notify silently
    money = lm.memory.open_loops.write(
        loop("remind me to wire the settlement money to the vendor",
             due_ts=now + 120, remind_ts=now - 10, timestamp=now - 500))
    # an ungrounded due loop — the EXISTING act path must be untouched by the notify route
    plain = lm.memory.open_loops.write(
        loop("Look into flight prices to Lisbon", due_ts=now - 3600, timestamp=now - 400))

    await bus.start()
    try:
        fired = await pro.trigger_tick(now=now)
        again = await pro.trigger_tick(now=now)

        by_id = {f["loop_id"]: f for f in fired}
        fails = []

        # safe grounded reminder -> notify
        f = by_id.get(safe.id)
        if not f or f["decision"] != "notify":
            fails.append(f"safe reminder should NOTIFY: {f}")
        notifies = [m for m in pro.channel.sent if "stretch" in m.get("message", "")]
        if not notifies:
            fails.append(f"no channel send for the safe reminder: {pro.channel.sent}")
        if any(p["action"] == "remind me to stretch" for p in pro.pending.values()):
            fails.append("safe reminder must not open a YES/NO ask")
        if lm.memory.open_loops.get(safe.id).status != "waiting":
            fails.append(f"notified loop should be waiting: {lm.memory.open_loops.get(safe.id).status}")
        if pro.budget.count(now) < 1:
            fails.append("a notify must count against the annoyance budget")

        # detrimental grounded reminder -> ask path, not notify
        f = by_id.get(money.id)
        if not f or f["decision"] != "ask":
            fails.append(f"money reminder should fall back to ASK: {f}")
        if any("wire the settlement" in m.get("message", "") and m["message"].startswith("Reminder:")
               for m in pro.channel.sent):
            fails.append("money reminder must never go out as a bare notify")

        # ungrounded due loop keeps the existing act path
        f = by_id.get(plain.id)
        if not f or f["decision"] != "act":
            fails.append(f"ungrounded due research loop should still ACT: {f}")

        # fire-once
        if again != []:
            fails.append(f"fire-once violated: {[f['loop_id'] for f in again]}")

        # budget cap: a fresh engine with budget already spent suppresses the next reminder
        pro2 = ProactiveEngine(bus, ModelGateway(), orch, glassbox=glass, scorecard=FakeScore())
        for _ in range(pro2.budget.max_per_day):
            pro2.budget.record_interruption(now)
        capped = lm.memory.open_loops.write(
            loop("remind me to water the plants", due_ts=now + 120, remind_ts=now - 10,
                 timestamp=now - 300))
        fired2 = await pro2.trigger_tick(now=now)
        f = next((x for x in fired2 if x["loop_id"] == capped.id), None)
        if not f or f["decision"] != "suppressed":
            fails.append(f"over-budget reminder should be suppressed: {f}")
        if any("water the plants" in m.get("message", "") for m in pro2.channel.sent):
            fails.append("a suppressed reminder must not send")
    finally:
        await bus.stop()

    print("==== ROOM 3 — REMINDER NOTIFY ROUTING ====")
    print(f"  fired {len(fired)} loops: safe->notify, money->ask, ungrounded->act; "
          f"tick-2 fired {len(again)}; over-budget->suppressed")
    if fails:
        print("==== FAIL ====")
        for x in fails:
            print("   -", x)
        raise SystemExit(1)
    print("==== PASS ====")


if __name__ == "__main__":
    asyncio.run(main())
