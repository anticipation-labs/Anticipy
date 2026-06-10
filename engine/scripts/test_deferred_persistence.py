"""Outage-queue persistence test (ledger F7 residual / D16 family) — an engine
restart during a quota window must not eat the lines the decider never read.

Pins (zero model calls; deciders are scripted):
  - restart mid-outage: a deferred line survives into a fresh live engine and
    re-enters the FULL pipeline at its due tick (late catch, honest glass-box).
  - the DECIDER_MAX_RETRIES bound holds ACROSS restarts: attempt counts persist,
    so restarting cannot grant an event extra retries; exhaustion stays honest.
  - a restored money line still ends at the harm-line's ASK — restore never
    weakens the one-way rule.
  - stub boots neither restore nor touch the file (no decider = an unread line
    must never re-enter the pipeline without one); the next live boot still gets it.
  - a corrupt file fails toward silence: empty queue, honest log, file set aside.
  - no deferred_path (the default, every other test) = no IO at all.
  - drain persists BEFORE re-entry: a crash mid-retry LOSES the event (fail
    toward silence) — it can never restore-and-replay a line that already acted.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_deferred_persistence.py
"""
import asyncio
import json
import os
import tempfile
from pathlib import Path

os.environ["ANTICIPY_MODEL_PROVIDER"] = "stub"
os.environ.pop("ANTICIPY_MODEL_API_KEY", None)
os.environ.pop("OPENROUTER_API_KEY", None)
os.environ.pop("ANTICIPY_OPENAI_BASE_URL", None)

from anticipy_engine.core.bus import Bus
from anticipy_engine.core.envelopes import Event, EventSource, GoalState
from anticipy_engine.core.gateway import ModelGateway
from anticipy_engine.core.orchestrator import AutoApprover, Orchestrator
from anticipy_engine.core.proactive import DECIDER_RETRY_SECONDS, ProactiveEngine
from anticipy_engine.core.store import GoalStore
from anticipy_engine.core.workers import BrowserStub, ChannelStub, ConnectorStub
from anticipy_engine.core.workers.memory import MemoryWorker
from anticipy_engine.live_memory.brain import LiveMemoryBrain
from anticipy_engine.memory import Memory
from anticipy_engine.proactive.decider import ACT, UNAVAILABLE


class FakeGlass:
    def __init__(self): self.entries = []
    def log(self, kind, data): self.entries.append((kind, data))
    def kinds(self): return [k for k, _ in self.entries]


class FakeScore:
    def record_decision(self, *a): pass
    def record_goal(self, *a): pass


class FakeDecider:
    def __init__(self, word): self.word = word; self.lines = []
    async def decide(self, line): self.lines.append(line); return self.word


class CrashingDecider:
    """Stands in for the PROCESS dying mid-retry (the real Decider never raises)."""
    async def decide(self, line): raise RuntimeError("process died mid-retry")


_BUSES = []


async def fresh_engine(decider=None, deferred_path=None):
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-defper-"))
    lm = LiveMemoryBrain(Memory(data_dir=tmp))
    bus = Bus()
    for w in (ChannelStub(), ConnectorStub(), BrowserStub(), MemoryWorker(lm)):
        bus.register_worker(w)
    await bus.start()
    _BUSES.append(bus)
    glass = FakeGlass()
    gw = ModelGateway()
    store = GoalStore(data_dir=tmp)
    orch = Orchestrator(bus, gw, store, glassbox=glass, scorecard=FakeScore(),
                        approver=AutoApprover(True))
    pro = ProactiveEngine(bus, gw, orch, glassbox=glass, scorecard=FakeScore(),
                          decider=decider, deferred_path=deferred_path)
    return pro, store, glass


def ev(text):
    return Event(source=EventSource.mac_mic, text=text)


SAFE_LINE = "Remind me to stretch at six tomorrow"   # triage True, harm-safe (act)
MONEY_LINE = "Pay the contractor invoice tonight"    # triage True, harm money (ask)
T0 = 1_000_000.0


async def defer_one(path, line=SAFE_LINE):
    """One live engine takes one UNAVAILABLE deferral and 'dies' (goes out of scope)."""
    pro, store, glass = await fresh_engine(decider=FakeDecider(UNAVAILABLE),
                                           deferred_path=path)
    res = await pro.on_event(ev(line), now=T0)
    assert res["decision"] == "deferred" and not store.all() and not pro.pending
    return res


async def main():
    # ---- 1) restart mid-outage: the deferred line survives and late-catches ----
    path = Path(tempfile.mkdtemp(prefix="anticipy-defper-")) / "decider_deferred.json"
    await defer_one(path)
    entries = json.loads(path.read_text())
    assert len(entries) == 1
    assert entries[0]["event"]["text"] == SAFE_LINE
    assert entries[0]["due"] == T0 + DECIDER_RETRY_SECONDS
    assert entries[0]["attempt"] == 1
    pro2, store2, glass2 = await fresh_engine(decider=FakeDecider(ACT), deferred_path=path)
    assert len(pro2.decider_deferred) == 1, "restart must restore the outage queue"
    assert pro2.decider_deferred[0]["event"].text == SAFE_LINE
    assert pro2._decider_attempts[pro2.decider_deferred[0]["event"].id] == 1
    assert "decider_deferred_restored" in glass2.kinds()
    await pro2.trigger_tick(now=T0 + 10)                          # window not elapsed
    assert pro2.decider_deferred and not store2.all()
    await pro2.trigger_tick(now=T0 + DECIDER_RETRY_SECONDS + 5)   # elapsed -> retry
    assert not pro2.decider_deferred
    goals = store2.all()
    assert len(goals) == 1, "the restored line must run the normal act path"
    assert json.loads(path.read_text()) == [], "a drained queue must persist as empty"
    print("PASS restart: deferred line survives, re-enters the pipeline, late-catches")

    # ---- 2) the retry bound holds ACROSS restarts: no extra lives from rebooting ----
    path = Path(tempfile.mkdtemp(prefix="anticipy-defper-")) / "decider_deferred.json"
    await defer_one(path)                                          # attempt 1, then 'death'
    pro_b, store_b, _ = await fresh_engine(decider=FakeDecider(UNAVAILABLE), deferred_path=path)
    await pro_b.trigger_tick(now=T0 + DECIDER_RETRY_SECONDS + 5)   # retry 1 -> defers again
    assert json.loads(path.read_text())[0]["attempt"] == 2
    pro_c, store_c, glass_c = await fresh_engine(decider=FakeDecider(UNAVAILABLE), deferred_path=path)
    assert pro_c._decider_attempts and len(pro_c.decider_deferred) == 1
    await pro_c.trigger_tick(now=T0 + 2 * DECIDER_RETRY_SECONDS + 10)  # retry 2 -> exhausted
    assert not pro_c.decider_deferred and not pro_c._decider_attempts
    assert not store_c.all() and not pro_c.pending, "an unread line must never act or ask"
    reasons = [d.get("reason", "") for k, d in glass_c.entries if k == "decision"]
    assert any("after retries" in r for r in reasons), "exhaustion must be stated honestly"
    assert json.loads(path.read_text()) == []
    print("PASS bound: attempt counts persist — restarts grant no extra retries")

    # ---- 3) a restored money line still ends at the harm-line's ASK ----
    path = Path(tempfile.mkdtemp(prefix="anticipy-defper-")) / "decider_deferred.json"
    await defer_one(path, line=MONEY_LINE)
    pro_m, store_m, glass_m = await fresh_engine(decider=FakeDecider(ACT), deferred_path=path)
    await pro_m.trigger_tick(now=T0 + DECIDER_RETRY_SECONDS + 5)
    goals = store_m.all()
    assert len(goals) == 1 and goals[0].state == GoalState.waiting, \
        "restore must not weaken the harm-line: money waits for a YES"
    assert pro_m.pending, "the restored money line must reach the ask path"
    print("PASS one-way: restored money line -> harm-line ASK is still FINAL")

    # ---- 4) stub boots neither restore nor touch the file; the next live boot gets it ----
    path = Path(tempfile.mkdtemp(prefix="anticipy-defper-")) / "decider_deferred.json"
    await defer_one(path)
    before = path.read_bytes()
    pro_s, store_s, _ = await fresh_engine(deferred_path=path)     # stub: decider is None
    assert pro_s.decider is None and pro_s.decider_deferred == [], \
        "a stub engine must never restore unread lines (no decider to read them)"
    await pro_s.on_event(ev(SAFE_LINE))                            # normal stub traffic
    await pro_s.trigger_tick(now=T0 + DECIDER_RETRY_SECONDS + 5)
    assert path.read_bytes() == before, "a stub boot must leave the file untouched"
    pro_l, _, _ = await fresh_engine(decider=FakeDecider(ACT), deferred_path=path)
    assert len(pro_l.decider_deferred) == 1, "the line must outlive the stub interlude"
    print("PASS stub: no restore, file untouched; the next live boot still restores")

    # ---- 5) a corrupt file fails toward silence, honestly, and is set aside ----
    path = Path(tempfile.mkdtemp(prefix="anticipy-defper-")) / "decider_deferred.json"
    path.write_text("{not json at all")
    pro_x, _, glass_x = await fresh_engine(decider=FakeDecider(ACT), deferred_path=path)
    assert pro_x.decider_deferred == [] and not pro_x._decider_attempts
    assert "decider_deferred_restore_failed" in glass_x.kinds()
    assert not path.exists() and path.with_suffix(".json.corrupt").exists(), \
        "the unreadable file must be set aside, never silently deleted"
    print("PASS corrupt: empty queue, honest log, file set aside as .corrupt")

    # ---- 6) no deferred_path (the default) -> no IO at all ----
    pro_n, _, _ = await fresh_engine(decider=FakeDecider(UNAVAILABLE))
    res = await pro_n.on_event(ev(SAFE_LINE), now=T0)
    assert res["decision"] == "deferred" and pro_n._deferred_path is None
    print("PASS default: no path configured -> in-memory behavior unchanged, no files")

    # ---- 7) crash mid-retry LOSES the event — it never restores-and-replays ----
    path = Path(tempfile.mkdtemp(prefix="anticipy-defper-")) / "decider_deferred.json"
    await defer_one(path)
    pro_k, _, _ = await fresh_engine(decider=CrashingDecider(), deferred_path=path)
    died = False
    try:
        await pro_k.trigger_tick(now=T0 + DECIDER_RETRY_SECONDS + 5)
    except RuntimeError:
        died = True
    assert died, "the crash stand-in must fire inside the retry"
    assert json.loads(path.read_text()) == [], \
        "the drain must persist BEFORE re-entry: a crash loses the event (silence), " \
        "it must never leave it on disk to be replayed after it may have acted"
    pro_r, store_r, _ = await fresh_engine(decider=FakeDecider(ACT), deferred_path=path)
    assert pro_r.decider_deferred == []
    await pro_r.trigger_tick(now=T0 + 2 * DECIDER_RETRY_SECONDS + 10)
    assert not store_r.all(), "nothing may replay after a mid-retry crash"
    print("PASS crash ordering: mid-retry death fails toward silence, never replay")

    for b in _BUSES:
        await b.stop()
    print("ALL DEFERRED-PERSISTENCE TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
