"""Piece 5 test: proactive skeleton — triage, gate, hand-off, record.

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
    # A) actionable event -> gate decides do_and_notify -> goal created and run to done
    tmp, bus, gw, glass, score, orch, pro = make()
    await bus.start()
    try:
        out = await pro.on_event(Event(source=EventSource.mac_mic,
                                       text="I'll send Sarah the Q3 deck on Friday and book us lunch."))
    finally:
        await bus.stop()
    assert out["decision"] == "do_and_notify" and out["goal_id"]
    assert orch.store.load(out["goal_id"]).state == GoalState.done
    assert len(gw.smart_calls) == 2  # gate + plan
    assert "do_and_notify" in score.decisions
    assert any(k == "decision" for k, _ in glass.entries)
    print("  A actionable: decision=do_and_notify, goal done, smart calls =", len(gw.smart_calls))

    # B) nothing event -> triaged out -> ignore, no goal, no smart call
    tmp, bus, gw, glass, score, orch, pro = make()
    await bus.start()
    try:
        out = await pro.on_event(Event(source=EventSource.mac_mic, text="The weather is nice today."))
    finally:
        await bus.stop()
    assert out["decision"] == "ignore" and out["goal_id"] is None
    assert len(gw.smart_calls) == 0  # triage is free; no smart model touched
    print("  B nothing: triaged out -> ignore; smart calls =", len(gw.smart_calls))

    # C) risky event -> gate says ask_first -> raised to human, no goal
    tmp, bus, gw, glass, score, orch, pro = make()
    await bus.start()
    try:
        out = await pro.on_event(Event(source=EventSource.mac_mic, text="Wire money to the contractor."))
    finally:
        await bus.stop()
    assert out["decision"] == "ask_first" and out["goal_id"] is None
    assert any(k == "ask_human" for k, _ in glass.entries)
    print("  C risky: decision=ask_first, raised to human, no goal")

    print("PASS piece 5: proactive engine skeleton (triage / gate / hand-off / record)")


if __name__ == "__main__":
    asyncio.run(main())
