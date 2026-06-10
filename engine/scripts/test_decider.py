"""Room 1.5 decider test — the cheap-model commitment gate is live-only and one-way safe.

Pins the safety contract (zero model calls; the decider is faked or keyless):
  - parse: word-boundary only, safest verdict wins on rambles, unparseable -> SILENT.
  - fail-SILENT: a raising gateway and a keyless live gateway both return SILENT.
  - live-only: stub gateway -> engine has NO decider; openrouter gateway -> it has one.
  - pipeline one-way: SILENT drops a triage-surviving event (no goal, no ask);
    ASK forces the ask path on a harm-safe line (goal paused, ask pending);
    ACT defers to the harm-line and can NEVER turn its ASK into an act.
  - triage still runs first: a non-actionable line never reaches the decider.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_decider.py
"""
import asyncio
import os
import tempfile
from pathlib import Path

# the suite forces stub, but pin it here too so this file is safe standalone —
# and make sure no live key leaks into the keyless fail-SILENT check below
os.environ["ANTICIPY_MODEL_PROVIDER"] = "stub"
os.environ.pop("ANTICIPY_MODEL_API_KEY", None)
os.environ.pop("OPENROUTER_API_KEY", None)
os.environ.pop("ANTICIPY_OPENAI_BASE_URL", None)

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
from anticipy_engine.proactive.decider import ACT, ASK, SILENT, Decider, _PROMPT, parse_verdict


class FakeGlass:
    def __init__(self): self.entries = []
    def log(self, kind, data): self.entries.append((kind, data))
    def kinds(self): return [k for k, _ in self.entries]


class FakeScore:
    def record_decision(self, *a): pass
    def record_goal(self, *a): pass


class FakeDecider:
    """Scripted decider — pipeline tests never touch a model."""
    def __init__(self, word): self.word = word; self.lines = []
    async def decide(self, line): self.lines.append(line); return self.word


class RaisingGateway:
    async def think(self, *a, **kw): raise RuntimeError("provider down")


class CannedGateway:
    def __init__(self, raw): self.raw = raw; self.calls = []
    async def think(self, task, tier, caller, **kw):
        self.calls.append({"tier": tier, "caller": caller, **kw})
        return self.raw


_BUSES = []


async def fresh_engine(decider=None, gateway=None):
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-decider-"))
    lm = LiveMemoryBrain(Memory(data_dir=tmp))
    bus = Bus()
    for w in (ChannelStub(), ConnectorStub(), BrowserStub(), MemoryWorker(lm)):
        bus.register_worker(w)
    await bus.start()
    _BUSES.append(bus)
    glass = FakeGlass()
    gw = gateway or ModelGateway()
    store = GoalStore(data_dir=tmp)
    orch = Orchestrator(bus, gw, store, glassbox=glass, scorecard=FakeScore(),
                        approver=AutoApprover(True))
    pro = ProactiveEngine(bus, gw, orch, glassbox=glass, scorecard=FakeScore(),
                          decider=decider)
    return pro, store, glass


def ev(text):
    return Event(source=EventSource.mac_mic, text=text)


SAFE_LINE = "Remind me to stretch at six tomorrow"          # triage True, harm calendar_hold (act)
MONEY_LINE = "Pay the contractor invoice tonight"           # triage True, harm money (ask)
VENT_LINE = "Ugh, what a day."                              # triage False


async def main():
    # ---- 1) tolerant parse: word-boundary, safety-ordered, fail-SILENT ----
    assert parse_verdict("ACT") == ACT
    assert parse_verdict("ask.") == ASK
    assert parse_verdict("Verdict: SILENT (it is a vent)") == SILENT
    assert parse_verdict("I would ASK here, not ACT.") == ASK          # safest mentioned wins
    assert parse_verdict("ACT or SILENT? hard to say") == SILENT      # safest mentioned wins
    assert parse_verdict("Multitasking is fun") == SILENT             # no word-boundary ASK
    assert parse_verdict("") == SILENT
    assert parse_verdict("the model rambled with no verdict") == SILENT
    print("PASS parse_verdict: boundaries, safety order, unparseable -> SILENT")

    # ---- 1.5) prompt pins the HANDOFF framing (ledger F5: the first live run showed the
    #      cheap model false-acting on narration; the lap-20260610T072358Z revision draws
    #      the delegated-task vs self-narration boundary — these clauses are load-bearing) ----
    for clause in ("HANDED OFF", "someone should", "past tense", "their own social act",
                   '"-ing" openings', "{line}"):
        assert clause in _PROMPT, f"decider prompt lost its F5 clause: {clause!r}"
    print("PASS prompt: F5 handoff/narration clauses present")

    # ---- 2) Decider unit: canned reply parsed; failures and keyless live fail SILENT ----
    glass = FakeGlass()
    canned = CannedGateway("  ask\n")
    d = Decider(canned, glassbox=glass)
    assert await d.decide(SAFE_LINE) == ASK
    assert canned.calls[0]["caller"] == "decider" and canned.calls[0]["tier"] == "cheap"
    assert canned.calls[0].get("temperature") == 0
    assert "decider" in glass.kinds()

    glass = FakeGlass()
    d = Decider(RaisingGateway(), glassbox=glass)
    assert await d.decide(SAFE_LINE) == SILENT                        # provider error -> SILENT
    assert "decider_error" in glass.kinds()

    d = Decider(ModelGateway(provider="openrouter"))                  # live provider, NO key
    assert await d.decide(SAFE_LINE) == SILENT                        # keyless -> SILENT, no raise
    print("PASS decider unit: temp-0 cheap call, error and keyless both fail SILENT")

    # ---- 3) live-only construction: stub gateway -> no decider; openrouter -> decider ----
    pro, _, _ = await fresh_engine()
    assert pro.decider is None, "stub gateway must not get a decider"
    pro_live, _, _ = await fresh_engine(gateway=ModelGateway(provider="openrouter"))
    assert isinstance(pro_live.decider, Decider), "live gateway must get a decider"
    print("PASS live-only: stub bypasses the decider, openrouter constructs it")

    # ---- 4) pipeline: decider SILENT drops a triage-surviving line ----
    fake = FakeDecider(SILENT)
    pro, store, _ = await fresh_engine(decider=fake)
    res = await pro.on_event(ev(SAFE_LINE))
    assert res["decision"] == "ignore" and res["decider"] == SILENT
    assert res["goal_id"] is None and not pro.pending
    assert fake.lines == [SAFE_LINE]
    assert not store.all(), "SILENT must not create or pause any goal"
    print("PASS pipeline: decider SILENT -> dropped, no goal, no ask")

    # ---- 5) pipeline: decider ASK forces the ask path on a harm-safe line ----
    fake = FakeDecider(ASK)
    pro, store, _ = await fresh_engine(decider=fake)
    res = await pro.on_event(ev(SAFE_LINE))
    assert res["decision"] == "ask" and res["decider"] == ASK
    assert res["detrimental"] is False, "harm-line still reads safe; the decider forced the ask"
    assert "decider" in res["reason"]
    assert res["ask_id"] in pro.pending
    assert store.load(res["goal_id"]).state == GoalState.waiting
    print("PASS pipeline: decider ASK on harm-safe line -> paused goal + pending ask")

    # ---- 6) pipeline: decider ACT defers to the harm-line on a safe line ----
    fake = FakeDecider(ACT)
    pro, store, _ = await fresh_engine(decider=fake)
    res = await pro.on_event(ev(SAFE_LINE))
    assert res["decision"] == "act" and res["goal_id"] is not None
    print("PASS pipeline: decider ACT + harm-safe -> acts")

    # ---- 7) one-way: decider ACT can NEVER override the harm-line's ASK ----
    fake = FakeDecider(ACT)
    pro, store, _ = await fresh_engine(decider=fake)
    res = await pro.on_event(ev(MONEY_LINE))
    assert res["decision"] == "ask" and res["detrimental"] is True
    assert store.load(res["goal_id"]).state == GoalState.waiting
    print("PASS pipeline: decider ACT on money line -> harm-line ASK is FINAL")

    # ---- 8) triage still runs first: non-actionable lines never reach the decider ----
    fake = FakeDecider(ACT)
    pro, _, _ = await fresh_engine(decider=fake)
    res = await pro.on_event(ev(VENT_LINE))
    assert res["decision"] == "ignore" and fake.lines == []
    print("PASS pipeline: triaged-out vent never reaches the decider")

    # ---- 9) no decider (stub) -> behavior unchanged, result carries decider=None ----
    pro, _, _ = await fresh_engine()
    res = await pro.on_event(ev(SAFE_LINE))
    assert res["decision"] == "act" and res["decider"] is None
    print("PASS pipeline: stub mode unchanged (act path, no decider)")

    for b in _BUSES:
        await b.stop()
    print("ALL DECIDER TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
