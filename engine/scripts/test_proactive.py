"""Proactive engine test — ACT-FIRST (Room 1 triage + Room 2 harm-line).

The engine acts by default and stops to ask ONLY before something detrimental:
  A) clearly-safe/reversible actionable event -> ACT (goal created + run to done)
  B) ambient noise                            -> triaged out -> ignore (zero smart calls)
  C) detrimental event (spend money)          -> ASK (no goal; raised to human) [hard sub-gate]
The harm-line is deterministic (no smart call); only the orchestrator's plan uses smart.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_proactive.py
"""
import asyncio
import tempfile
from pathlib import Path

from anticipy_engine.core.bus import Bus
from anticipy_engine.core.envelopes import Event, EventSource, GoalState
from anticipy_engine.core.gateway import ModelGateway
from anticipy_engine.core.orchestrator import AutoApprover, Orchestrator
from anticipy_engine.core.proactive import ProactiveEngine
from anticipy_engine.core.store import GoalStore
from anticipy_engine.core.workers import BrowserStub, ChannelStub, ConnectorStub, MemoryStub


class FakeGlass:
    def __init__(self):
        self.entries = []

    def log(self, kind, data):
        self.entries.append((kind, data))


class FakeScore:
    def __init__(self):
        self.decisions = []
        self.goals = []

    def record_decision(self, decision, event_id, reason):
        self.decisions.append(decision)

    def record_goal(self, goal_id, outcome, cost):
        self.goals.append((goal_id, outcome, cost))


def make():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-pro-"))
    bus = Bus()
    for w in (ChannelStub(), MemoryStub(), ConnectorStub(), BrowserStub()):
        bus.register_worker(w)
    gw = ModelGateway()
    glass, score = FakeGlass(), FakeScore()
    orch = Orchestrator(bus, gw, GoalStore(data_dir=tmp), glassbox=glass, scorecard=score, approver=AutoApprover(True))
    pro = ProactiveEngine(bus, gw, orch, glassbox=glass, scorecard=score)
    return tmp, bus, gw, glass, score, orch, pro


async def main():
    # A) clearly-safe/reversible actionable event -> ACT -> goal created and run to done
    tmp, bus, gw, glass, score, orch, pro = make()
    await bus.start()
    try:
        out = await pro.on_event(Event(source=EventSource.mac_mic,
                                       text="Look up flight options to Lisbon and put together a trip outline."))
    finally:
        await bus.stop()
    assert out["decision"] == "act" and out["goal_id"], f"expected act+goal, got {out}"
    assert not out["detrimental"]
    assert orch.store.load(out["goal_id"]).state == GoalState.done
    assert len(gw.smart_calls) == 1, f"harm-line is deterministic; only plan is smart, got {len(gw.smart_calls)}"
    assert "act" in score.decisions
    print(f"  A safe: decision=act ({out['category']}), goal done, smart calls = {len(gw.smart_calls)}")

    # A2) clean typed calendar event -> ACT, not ask. This is the M0 floor shape; the
    # live judge proves the real app artifact, this only protects the route.
    tmp, bus, gw, glass, score, orch, pro = make()
    await bus.start()
    try:
        out = await pro.on_event(Event(
            source=EventSource.app,
            text="Create a calendar event titled Dentist on June 18, 2026 from 9:40 AM to 10:10 AM.",
        ))
    finally:
        await bus.stop()
    assert out["decision"] == "act" and out["category"] == "calendar_event", f"expected calendar act, got {out}"
    assert orch.store.load(out["goal_id"]).state == GoalState.done
    print(f"  A2 clean calendar: decision=act ({out['category']}), goal done")

    # B) ambient noise -> triaged out -> ignore, no goal, no smart call
    tmp, bus, gw, glass, score, orch, pro = make()
    await bus.start()
    try:
        out = await pro.on_event(Event(source=EventSource.mac_mic, text="The weather is nice today."))
    finally:
        await bus.stop()
    assert out["decision"] == "ignore" and out["goal_id"] is None
    assert len(gw.smart_calls) == 0  # triage is free; no smart model touched
    print("  B noise: triaged out -> ignore; smart calls =", len(gw.smart_calls))

    # C) detrimental (spend money) -> ASK -> raised to human, NO goal (hard sub-gate: no silent harm)
    tmp, bus, gw, glass, score, orch, pro = make()
    await bus.start()
    try:
        out = await pro.on_event(Event(source=EventSource.mac_mic, text="Wire money to the contractor."))
    finally:
        await bus.stop()
    assert out["decision"] == "ask" and out["detrimental"] and out["category"] == "money"
    assert out["goal_id"] and out["ask_id"], f"ask must pause a goal + register the ask, got {out}"
    assert orch.store.load(out["goal_id"]).state == GoalState.waiting  # PAUSED, not executed (no silent harm)
    assert any(k == "ask_human" for k, _ in glass.entries) and any(k == "ask_sent" for k, _ in glass.entries)
    assert len(gw.smart_calls) == 0  # waiting goal not run -> no plan; harm-line deterministic
    print(f"  C detrimental: decision=ask ({out['category']}), goal PAUSED (waiting), ask sent")

    print("PASS proactive: act-first engine (triage / harm-line / act-or-ask / record)")


if __name__ == "__main__":
    asyncio.run(main())
