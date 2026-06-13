"""Trigger fired-state persistence test (ledger D16 proper) — an engine restart must
never re-fire an already-fired trigger. The open-loop ledger was always durable; the
fire-once guard (TriggerWatcher._fired) was not, so every restart re-fired all still-
listed due loops: duplicate reminder sends, duplicate full-pipeline re-entry.

Pins (zero model calls; mock channels; no Twilio transport ever constructed):
  - reminder restart: a fired notify-reminder stamps fields['fired_at'] on the durable
    loop record BEFORE the send; a fresh engine over the same ledger fires NOTHING.
  - follow-up restart: a fired due/act loop never re-enters the pipeline after a
    restart — no second goal is ever created from the same firing.
  - crash ordering: a crash AFTER the stamp, BEFORE the send, LOSES that firing
    toward silence — the restarted engine does not send a late duplicate and does
    not recover the firing (honest loss, the seen-sid law).
  - failed stamp skips the firing the same direction (never fire unstamped) with an
    honest trigger_stamp_failed log; the unstamped loop fires on the next healthy
    boot (the skip is a retry, not a loss).
  - mark_loop contract: fired_at-only stamps leave status alone; the legacy
    no-status default ('waiting') is preserved; both args together both apply.
  - end-to-end: ControlCore restart on one data dir — the gate_P3 trigger leg
    cannot double-interrupt across a restart.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_trigger_persistence.py
"""
import asyncio
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

from anticipy_engine.core.bus import Bus  # noqa: E402
from anticipy_engine.core.control_core import ControlCore  # noqa: E402
from anticipy_engine.core.envelopes import Job, JobStatus  # noqa: E402
from anticipy_engine.core.gateway import ModelGateway  # noqa: E402
from anticipy_engine.core.orchestrator import AutoApprover, Orchestrator  # noqa: E402
from anticipy_engine.core.proactive import ProactiveEngine  # noqa: E402
from anticipy_engine.core.store import GoalStore  # noqa: E402
from anticipy_engine.core.workers import BrowserStub, ChannelStub, ConnectorStub  # noqa: E402
from anticipy_engine.core.workers.memory import MemoryWorker  # noqa: E402
from anticipy_engine.live_memory.brain import LiveMemoryBrain  # noqa: E402
from anticipy_engine.memory import Memory  # noqa: E402
from anticipy_engine.shared.schema import MemoryItem, now_ts  # noqa: E402


class FakeGlass:
    def __init__(self): self.entries = []
    def log(self, kind, data): self.entries.append((kind, data))
    def kinds(self): return [k for k, _ in self.entries]


class FakeScore:
    def record_decision(self, *a): pass
    def record_goal(self, *a): pass


class DyingChannel:
    """The process dies mid-send (after the stamp, before delivery)."""
    name = "dying"
    def __init__(self): self.sent = []
    def send(self, to, message):
        raise RuntimeError("process died mid-send")


class StampRefusingMemoryWorker(MemoryWorker):
    """The fired stamp cannot be written (disk full, db locked, ...)."""
    async def handle(self, job):
        if job.intent == "mark_loop" and job.args.get("fired_at") is not None:
            from anticipy_engine.core.envelopes import Result
            return Result(job_id=job.id, status=JobStatus.failed,
                          error="stamp refused (test)", proof=None)
        return await super().handle(job)


_BUSES = []


def loop_item(text, **fields_and_ts):
    ts = fields_and_ts.pop("timestamp", None)
    item = MemoryItem(kind="open_loop", text=text, status="open",
                      fields={"task": text, **fields_and_ts})
    if ts is not None:
        item.timestamp = ts
    return item


async def engine_in(tmp: Path, channel=None, worker_cls=MemoryWorker):
    """One engine over a SHARED data dir (ledger + goal store) — boots = restarts.
    Fresh Memory/Bus/TriggerWatcher every call: only the SQLite ledger carries over."""
    lm = LiveMemoryBrain(Memory(data_dir=tmp))
    bus = Bus()
    for w in (ChannelStub(), ConnectorStub(), BrowserStub(), worker_cls(lm)):
        bus.register_worker(w)
    await bus.start()
    _BUSES.append(bus)
    glass = FakeGlass()
    gw = ModelGateway()
    store = GoalStore(data_dir=tmp)
    orch = Orchestrator(bus, gw, store, glassbox=glass, scorecard=FakeScore(),
                        approver=AutoApprover(True))
    pro = ProactiveEngine(bus, gw, orch, glassbox=glass, scorecard=FakeScore(),
                          channel=channel)
    return pro, lm, store, glass


async def main():
    now = now_ts()

    # ---- 1) reminder restart: fired once, stamped, NEVER again ----
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-trigper-"))
    pro, lm, _, _ = await engine_in(tmp)
    safe = lm.memory.open_loops.write(
        loop_item("remind me to stretch", due_ts=now + 120, remind_ts=now - 10,
                  timestamp=now - 600))
    fired = await pro.trigger_tick(now=now)
    assert [f["loop_id"] for f in fired] == [safe.id] and fired[0]["decision"] == "notify", fired
    assert len(pro.channel.sent) == 1, pro.channel.sent
    stamped = lm.memory.open_loops.get(safe.id)
    assert stamped.fields.get("fired_at") == now, \
        "the fire must stamp fired_at on the DURABLE loop record"
    assert stamped.status == "waiting", "a notified reminder should stay visible as waiting"
    pro2, lm2, _, _ = await engine_in(tmp)   # restart: fresh _fired set, same ledger
    again = await pro2.trigger_tick(now=now + 60)
    assert again == [], f"restart re-fired an already-fired reminder: {again}"
    assert pro2.channel.sent == [], "a restart must never send a duplicate reminder"
    print("PASS reminder: one fire, durable stamp, zero re-fires across restart")

    # ---- 2) follow-up (act) restart: no duplicate pipeline re-entry ----
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-trigper-"))
    pro_a, lm_a, store_a, _ = await engine_in(tmp)
    due = lm_a.memory.open_loops.write(
        loop_item("Look into flight prices to Lisbon", due_ts=now - 3600,
                  timestamp=now - 7200))
    fired = await pro_a.trigger_tick(now=now)
    assert [f["loop_id"] for f in fired] == [due.id] and fired[0]["decision"] == "act", fired
    goals_after_fire = len(store_a.all())
    assert goals_after_fire >= 1, "the act path must have created a goal"
    assert lm_a.memory.open_loops.get(due.id).status == "done", \
        "an acted fired loop should leave the active backlog"
    pro_b, _, store_b, glass_b = await engine_in(tmp)
    again = await pro_b.trigger_tick(now=now + 60)
    assert again == [], f"restart re-fired a due follow-up loop: {again}"
    assert len(store_b.all()) == goals_after_fire, \
        "a restart must never re-enter the pipeline and create a second goal"
    assert "trigger_fired" not in glass_b.kinds()
    print("PASS follow-up: fired act loop never re-enters the pipeline after restart")

    # ---- 3) crash AFTER stamp BEFORE send: lost toward silence, never duplicated ----
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-trigper-"))
    pro_c, lm_c, _, _ = await engine_in(tmp, channel=DyingChannel())
    rem = lm_c.memory.open_loops.write(
        loop_item("remind me to water the plants", due_ts=now + 120, remind_ts=now - 10,
                  timestamp=now - 300))
    died = False
    try:
        await pro_c.trigger_tick(now=now)
    except RuntimeError:
        died = True
    assert died, "the crash stand-in must fire inside the send"
    assert lm_c.memory.open_loops.get(rem.id).fields.get("fired_at") == now, \
        "the stamp must land BEFORE the send (mark-before-act)"
    assert lm_c.memory.open_loops.get(rem.id).status == "open", \
        "crash after stamp but before decision keeps raw status; active surfaces hide fired-open loops"
    pro_d, _, _, _ = await engine_in(tmp)
    assert await pro_d.trigger_tick(now=now + 60) == [], \
        "a firing lost to a crash must stay lost (silence), never replay as a late send"
    assert pro_d.channel.sent == []
    print("PASS crash ordering: stamp-then-die loses the firing toward silence")

    # ---- 4) failed stamp: skip the firing (never fire unstamped), retry next boot ----
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-trigper-"))
    pro_e, lm_e, _, glass_e = await engine_in(tmp, worker_cls=StampRefusingMemoryWorker)
    rem = lm_e.memory.open_loops.write(
        loop_item("remind me to stretch", due_ts=now + 120, remind_ts=now - 10,
                  timestamp=now - 600))
    fired = await pro_e.trigger_tick(now=now)
    assert fired == [], f"an unstamped loop must not fire: {fired}"
    assert pro_e.channel.sent == [], "no stamp -> no send, ever"
    assert "trigger_stamp_failed" in glass_e.kinds(), "the skip must be logged honestly"
    assert lm_e.memory.open_loops.get(rem.id).fields.get("fired_at") is None
    pro_f, _, _, _ = await engine_in(tmp)   # healthy boot: the skip was a retry, not a loss
    fired = await pro_f.trigger_tick(now=now + 60)
    assert [f["loop_id"] for f in fired] == [rem.id] and fired[0]["decision"] == "notify"
    assert len(pro_f.channel.sent) == 1
    print("PASS failed stamp: firing skipped unstamped, honest log, fires next boot")

    # ---- 5) mark_loop contract: stamp-only, legacy default, both ----
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-trigper-"))
    pro_g, lm_g, _, _ = await engine_in(tmp)
    a = lm_g.memory.open_loops.write(loop_item("loop A"))
    b = lm_g.memory.open_loops.write(loop_item("loop B"))
    c = lm_g.memory.open_loops.write(loop_item("loop C"))
    r = await pro_g.bus.submit_job(Job(intent="mark_loop", args={"id": a.id, "fired_at": now}))
    assert r.status == JobStatus.success and r.output["fired_at"] == now
    got = lm_g.memory.open_loops.get(a.id)
    assert got.fields["fired_at"] == now and got.status == "open", \
        "a pure fired stamp must not change ledger status"
    r = await pro_g.bus.submit_job(Job(intent="mark_loop", args={"id": b.id}))
    assert r.status == JobStatus.success
    assert lm_g.memory.open_loops.get(b.id).status == "waiting", \
        "legacy no-arg mark_loop default must stay 'waiting'"
    r = await pro_g.bus.submit_job(Job(intent="mark_loop",
                                       args={"id": c.id, "status": "done", "fired_at": now}))
    assert r.status == JobStatus.success
    got = lm_g.memory.open_loops.get(c.id)
    assert got.status == "done" and got.fields["fired_at"] == now
    print("PASS mark_loop: stamp-only keeps status; legacy default holds; both apply")

    # ---- 6) end-to-end: ControlCore restart on one data dir (the gate_P3 trigger leg) ----
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-trigper-e2e-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    try:
        core.memory.open_loops.write(
            loop_item("remind me to leave for the dentist", due_ts=now + 120,
                      remind_ts=now - 10, timestamp=now - 600))
        fired = await core.proactive.trigger_tick(now=now)
        assert len(fired) == 1 and fired[0]["decision"] == "notify", fired
        assert len(core.text_channel.sent) == 1
    finally:
        await core.stop()   # the engine restarts after the reminder went out
    core2 = ControlCore(data_dir=tmp)
    await core2.start()
    try:
        again = await core2.proactive.trigger_tick(now=now + 60)
        assert again == [], f"restarted ControlCore re-fired the reminder: {again}"
        assert core2.text_channel.sent == [], \
            "the owner must never get a duplicate reminder because the engine restarted"
    finally:
        await core2.stop()
    print("PASS e2e: ControlCore restart cannot double-interrupt (gate_P3 trigger leg)")

    for b in _BUSES:
        await b.stop()
    print("ALL TRIGGER-PERSISTENCE TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
