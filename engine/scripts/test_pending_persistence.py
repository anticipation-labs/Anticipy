"""Pending-ask persistence test (the D16 sibling) — an engine restart between the
ask SMS and the owner's reply must not strand the ask. The paused goal was always
durable in the goal store; the map that lets a YES/NO match it was not.

Pins (zero model calls; mock channels; no Twilio transport ever constructed):
  - restart-survival: a pending ask persists to <data>/pending_asks.json, restores
    into a fresh engine, and the owner's YES resumes the EXACT paused goal to done.
  - NO after a restart declines: goal failed, decline recorded, nothing executes.
  - restore validates against the durable store: entries whose goal is missing or
    no longer waiting are DROPPED toward silence (an ask that cannot safely resume
    its exact goal must not be resumable) and the file is pruned.
  - the resolve pop persists BEFORE the goal resumes: a crash mid-resolve LOSES
    the ask (fail toward silence) — it can never restore-and-replay an approval
    after the goal may already have acted (same law as the deferred-queue drain).
  - a corrupt file fails toward silence: empty map, honest log, file set aside.
  - no pending_path (the default, every other engine-level test) = no IO at all.
  - end-to-end (the gate_P3 inbound leg): ControlCore restart with BOTH in-memory
    maps gone -> the restored pending ask + the F18 durable card linkage resolve
    an inbound "YES <code>" to a done goal with the owner card written back.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_pending_persistence.py
"""
import asyncio
import json
import os
import tempfile
from pathlib import Path

os.environ["ANTICIPY_MODEL_PROVIDER"] = "stub"
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")
os.environ.pop("ANTICIPY_OWNER_INGEST", None)
os.environ.pop("ANTICIPY_CHANNELS_MODE", None)   # mock everywhere; no transports
os.environ.pop("ANTICIPY_MODEL_API_KEY", None)
os.environ.pop("OPENROUTER_API_KEY", None)
OWNER = "+15550009999"
os.environ["OWNER_PHONE"] = OWNER

from anticipy_engine.channels.inbound import InboundPoller  # noqa: E402
from anticipy_engine.core.bus import Bus  # noqa: E402
from anticipy_engine.core.control_core import ControlCore  # noqa: E402
from anticipy_engine.core.envelopes import Event, EventSource, GoalState  # noqa: E402
from anticipy_engine.core.gateway import ModelGateway  # noqa: E402
from anticipy_engine.core.orchestrator import AutoApprover, Orchestrator  # noqa: E402
from anticipy_engine.core.proactive import ProactiveEngine  # noqa: E402
from anticipy_engine.core.store import GoalStore  # noqa: E402
from anticipy_engine.core.workers import BrowserStub, ChannelStub, ConnectorStub  # noqa: E402
from anticipy_engine.core.workers.memory import MemoryWorker  # noqa: E402
from anticipy_engine.live_memory.brain import LiveMemoryBrain  # noqa: E402
from anticipy_engine.memory import Memory  # noqa: E402


class FakeGlass:
    def __init__(self): self.entries = []
    def log(self, kind, data): self.entries.append((kind, data))
    def kinds(self): return [k for k, _ in self.entries]


class FakeScore:
    def record_decision(self, *a): pass
    def record_goal(self, *a): pass


_BUSES = []

# money lines: triage actionable + harm-line detrimental -> the ask path
MONEY = "Pay the contractor invoice tonight"
MONEY2 = "Wire the deposit to the venue tomorrow"
MONEY3 = "Pay the caterer the remaining balance"
SEND_SAM = "okay just send Sam the revised decking file before Friday."


async def engine_in(tmp: Path):
    """One engine over a SHARED data dir (store + pending file) — boots = restarts."""
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
                          pending_path=tmp / "pending_asks.json")
    return pro, store, glass


def ev(text):
    return Event(source=EventSource.mac_mic, text=text)


async def ask_one(tmp: Path, line=MONEY):
    """One engine takes one money ask and 'dies' (goes out of scope)."""
    pro, store, glass = await engine_in(tmp)
    res = await pro.on_event(ev(line))
    assert res["decision"] == "ask" and res["ask_id"], res
    assert store.load(res["goal_id"]).state == GoalState.waiting
    return res


async def main():
    # ---- 1) restart-survival: the ask outlives the engine; YES resumes the goal ----
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-penper-"))
    path = tmp / "pending_asks.json"
    res = await ask_one(tmp)
    on_disk = json.loads(path.read_text())
    assert set(on_disk) == {res["ask_id"]}, on_disk
    assert on_disk[res["ask_id"]]["goal_id"] == res["goal_id"]
    assert on_disk[res["ask_id"]]["action"] == MONEY
    pro2, store2, glass2 = await engine_in(tmp)
    assert "pending_restored" in glass2.kinds()
    assert set(pro2.pending) == {res["ask_id"]}, "restart must restore the pending map"
    assert pro2.pending[res["ask_id"]]["action"] == MONEY
    out = await pro2.resolve_ask(res["ask_id"], True)
    assert out["approved"] is True and out["goal_id"] == res["goal_id"], out
    assert store2.load(res["goal_id"]).state == GoalState.done, \
        "YES after a restart must resume the EXACT paused goal"
    assert json.loads(path.read_text()) == {}, "a resolved ask must persist as gone"
    assert not pro2.pending
    print("PASS restart: pending ask survives, YES resumes the exact goal to done")

    # ---- 2) NO after a restart declines without executing ----
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-penper-"))
    res = await ask_one(tmp)
    pro_n, store_n, glass_n = await engine_in(tmp)
    out = await pro_n.resolve_ask(res["ask_id"], False)
    assert out["approved"] is False and out["declined_action"] == MONEY, out
    assert store_n.load(res["goal_id"]).state == GoalState.failed
    assert "ask_declined" in glass_n.kinds()
    assert json.loads((tmp / "pending_asks.json").read_text()) == {}
    print("PASS decline: NO after a restart fails the goal, never executes")

    # ---- 3) restore validates against the store: stale entries drop, valid stay ----
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-penper-"))
    path = tmp / "pending_asks.json"
    pro_a, store_a, _ = await engine_in(tmp)
    r1 = await pro_a.on_event(ev(MONEY))
    r2 = await pro_a.on_event(ev(MONEY2))
    r3 = await pro_a.on_event(ev(MONEY3))
    assert all(r["decision"] == "ask" for r in (r1, r2, r3))
    # stale by deletion (the goal file is gone) and stale by state (already ran):
    # defense-in-depth — the live mutation order never writes these shapes itself
    (tmp / "goals" / f"{r1['goal_id']}.json").unlink()
    g2 = store_a.load(r2["goal_id"]); g2.state = GoalState.done; store_a.save(g2)
    pro_b, _, glass_b = await engine_in(tmp)
    assert set(pro_b.pending) == {r3["ask_id"]}, \
        "only the ask whose goal is still waiting may restore"
    restored = [d for k, d in glass_b.entries if k == "pending_restored"]
    assert restored and restored[0]["count"] == 1 and restored[0]["dropped"] == 2
    assert set(json.loads(path.read_text())) == {r3["ask_id"]}, \
        "dropped entries must be pruned from the file, not linger"
    print("PASS validate: missing/non-waiting goals drop toward silence; file pruned")

    # ---- 4) crash mid-resolve LOSES the ask — an approval never replays ----
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-penper-"))
    res = await ask_one(tmp)
    pro_k, store_k, _ = await engine_in(tmp)

    async def die(goal):
        raise RuntimeError("process died mid-resolve")
    pro_k.orchestrator.start_goal = die
    died = False
    try:
        await pro_k.resolve_ask(res["ask_id"], True)
    except RuntimeError:
        died = True
    assert died, "the crash stand-in must fire inside the resume"
    assert json.loads((tmp / "pending_asks.json").read_text()) == {}, \
        "the pop must persist BEFORE the resume: a crash loses the ask (silence), " \
        "it must never leave it on disk to replay an approval that may have acted"
    pro_r, store_r, _ = await engine_in(tmp)
    assert pro_r.pending == {}
    assert store_r.load(res["goal_id"]).state == GoalState.waiting, \
        "the goal stays honestly paused — nothing may execute from a lost approval"
    print("PASS crash ordering: mid-resolve death fails toward silence, never replay")

    # ---- 5) a corrupt file fails toward silence, honestly, and is set aside ----
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-penper-"))
    path = tmp / "pending_asks.json"
    path.write_text("{not json at all")
    pro_x, _, glass_x = await engine_in(tmp)
    assert pro_x.pending == {}
    assert "pending_restore_failed" in glass_x.kinds()
    assert not path.exists() and path.with_suffix(".json.corrupt").exists(), \
        "the unreadable file must be set aside, never silently deleted"
    print("PASS corrupt: empty map, honest log, file set aside as .corrupt")

    # ---- 6) no pending_path (the default) -> no IO at all ----
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-penper-"))
    lm = LiveMemoryBrain(Memory(data_dir=tmp))
    bus = Bus()
    for w in (ChannelStub(), ConnectorStub(), BrowserStub(), MemoryWorker(lm)):
        bus.register_worker(w)
    await bus.start()
    _BUSES.append(bus)
    store_d = GoalStore(data_dir=tmp)
    orch_d = Orchestrator(bus, ModelGateway(), store_d, glassbox=FakeGlass(),
                          scorecard=FakeScore(), approver=AutoApprover(True))
    pro_d = ProactiveEngine(bus, ModelGateway(), orch_d, glassbox=FakeGlass(),
                            scorecard=FakeScore())
    res = await pro_d.on_event(ev(MONEY))
    assert res["decision"] == "ask" and pro_d._pending_path is None
    assert not (tmp / "pending_asks.json").exists(), "no path configured -> no files"
    print("PASS default: no path configured -> in-memory behavior unchanged, no files")

    # ---- 7) end-to-end: ControlCore restart + inbound YES (the gate_P3 leg) ----
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-penper-e2e-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    os.environ["ANTICIPY_OWNER_INGEST"] = "1"
    try:
        ask = await core.feed("app", SEND_SAM, {})
    finally:
        os.environ.pop("ANTICIPY_OWNER_INGEST", None)
    assert ask["decision"] == "ask" and ask["ask_id"], ask
    record_path = tmp / "owner_cards" / f"{ask['goal_id']}.json"
    assert json.loads(record_path.read_text())["state"] == "waiting"
    assert set(json.loads((tmp / "pending_asks.json").read_text())) == {ask["ask_id"]}
    await core.stop()   # the engine restarts between the ask SMS and the reply

    core2 = ControlCore(data_dir=tmp)   # BOTH in-memory maps start empty here
    await core2.start()
    try:
        assert [p["ask_id"] for p in core2.pending_asks()] == [ask["ask_id"]], \
            "the restarted engine must list the restored ask on /pending"
        poller = InboundPoller(core2, fetch=lambda: [
            {"sid": "SM40", "body": f"yes {ask['ask_id'][:6]}", "from": OWNER,
             "to": "+15550000000", "direction": "inbound", "date_sent": None}])
        out = await poller.poll_once()
        assert [r["ask_id"] for r in out["resolved"]] == [ask["ask_id"]], out
        # owner-lane ids: ask["goal_id"] is the card RECORD id; the real goal id is
        # the ask id itself (_send_ask sets ask_id = goal.id)
        assert core2.store.load(ask["ask_id"]).state == GoalState.done, \
            "the inbound YES must resume the pre-restart goal to done"
        record = json.loads(record_path.read_text())
        assert record["state"] == "done", record
        assert record["resolution"] == {"ask_id": ask["ask_id"], "approved": True}, \
            "the F18 durable linkage must carry the card write-back across the restart"
        assert not core2.pending_asks()
        assert json.loads((tmp / "pending_asks.json").read_text()) == {}
    finally:
        await core2.stop()
    print("PASS e2e: restart between ask and reply; inbound YES still resolves, "
          "goal done, owner card written back (gate_P3 inbound leg holds)")

    for b in _BUSES:
        await b.stop()
    print("ALL PENDING-PERSISTENCE TESTS PASSED")


if __name__ == "__main__":
    # this test must never construct a Twilio transport
    assert not InboundPoller.live_ready()
    asyncio.run(main())
