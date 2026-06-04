"""Room 3 test — the trigger model (time + open-loop watching, fire-once).

Plants open-loop commitments with controlled due_ts / created_ts, then ticks the engine's
trigger with NO new input event. Asserts: due (time) + elapsed loops fire proactive goals/
asks; not-due + fresh loops don't; a second tick at the same clock fires NOTHING (fire-once);
a fired send-commitment -> ASK, a fired research/draft commitment -> ACT (same harm-line path).

Real MemoryWorker (for list_open_loops over the real ledger) + stub hands (fast). Deterministic.
Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_trigger.py
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

DAY = 86400.0


class FakeGlass:
    def __init__(self): self.entries = []
    def log(self, kind, data): self.entries.append((kind, data))


class FakeScore:
    def record_decision(self, *a): pass
    def record_goal(self, *a): pass


def loop(text, status="open", **fields_and_ts):
    ts = fields_and_ts.pop("timestamp", None)
    item = MemoryItem(kind="open_loop", text=text, status=status, fields=fields_and_ts)
    if ts is not None:
        item.timestamp = ts
    return item


async def main():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-trig-"))
    lm = LiveMemoryBrain(Memory(data_dir=tmp))
    bus = Bus()
    for w in (ChannelStub(), ConnectorStub(), BrowserStub(), MemoryWorker(lm)):
        bus.register_worker(w)
    gw = ModelGateway()
    glass = FakeGlass()
    orch = Orchestrator(bus, gw, GoalStore(data_dir=tmp), glassbox=glass, scorecard=FakeScore(), approver=AutoApprover(True))
    pro = ProactiveEngine(bus, gw, orch, glassbox=glass, scorecard=FakeScore())

    now = now_ts()
    # plant the ledger (controlled clock fields). write() preserves the timestamp we set.
    due_send = lm.memory.open_loops.write(loop("Send Sarah the Q3 deck", task="Send Sarah the Q3 deck", due="Friday", due_ts=now - 3600))
    due_safe = lm.memory.open_loops.write(loop("Look into flight prices to Lisbon", task="Look into flight prices to Lisbon", due_ts=now - 3600))
    future   = lm.memory.open_loops.write(loop("Renew the car insurance", task="Renew the car insurance", due_ts=now + 7 * DAY))
    elapsed  = lm.memory.open_loops.write(loop("Draft the board update", task="Draft the board update", timestamp=now - 5 * DAY))
    fresh    = lm.memory.open_loops.write(loop("Draft the team email", task="Draft the team email", timestamp=now - 3600))

    await bus.start()
    try:
        fired = await pro.trigger_tick(now=now)               # NO new input event — purely the ledger + clock
        again = await pro.trigger_tick(now=now)               # same clock -> fire-once must hold
    finally:
        await bus.stop()

    ids = {f["loop_id"] for f in fired}
    by_id = {f["loop_id"]: f for f in fired}
    fails = []

    # which fired
    should_fire = {due_send.id, due_safe.id, elapsed.id}
    should_not = {future.id, fresh.id}
    if not should_fire <= ids:
        fails.append(f"due/elapsed loops did not all fire: fired={ids} expected superset of {should_fire}")
    if ids & should_not:
        fails.append(f"not-due/fresh loops wrongly fired: {ids & should_not}")

    # harm-line routing of fired triggers
    if due_send.id in by_id and not (by_id[due_send.id]["decision"] == "ask" and by_id[due_send.id]["detrimental"]):
        fails.append(f"due send-commitment should ASK: {by_id.get(due_send.id)}")
    if due_safe.id in by_id and by_id[due_safe.id]["decision"] != "act":
        fails.append(f"due research-commitment should ACT: {by_id.get(due_safe.id)}")
    if elapsed.id in by_id and by_id[elapsed.id]["decision"] != "act":
        fails.append(f"elapsed draft-commitment should ACT: {by_id.get(elapsed.id)}")

    # fire-once
    if again != []:
        fails.append(f"fire-once violated: second tick fired {[f['loop_id'] for f in again]}")

    print("==== ROOM 3 — TRIGGER MODEL ====")
    print(f"  planted 5 loops; fired {len(fired)} on tick-1 (due_send, due_safe, elapsed expected)")
    print(f"  routing: due_send -> {by_id.get(due_send.id, {}).get('decision')}, "
          f"due_safe -> {by_id.get(due_safe.id, {}).get('decision')}, "
          f"elapsed -> {by_id.get(elapsed.id, {}).get('decision')}")
    print(f"  not-fired: future={future.id not in ids}, fresh={fresh.id not in ids}")
    print(f"  tick-2 (same clock) fired {len(again)} (fire-once -> must be 0)")
    print(f"  trigger_fired glassbox entries: {sum(1 for k, _ in glass.entries if k == 'trigger_fired')}")

    if fails:
        print("==== FAIL ===="); [print("   -", f) for f in fails]; raise SystemExit(1)
    print("==== PASS ====")


if __name__ == "__main__":
    asyncio.run(main())
