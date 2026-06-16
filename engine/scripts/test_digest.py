"""NF10 — the ONE daily digest (anti-spam: N non-urgent items become ONE report, not N pings).

Proves: a non-urgent proactive item suppressed by the interrupt BUDGET is not dropped and not
spammed — it lands in the daily digest, which delivers as ONE message drawing ZERO budget; a
DECLINED action-type never lands in the digest (the user said no); a quiet day sends nothing.

Real MemoryWorker + stub hands + mock channel; controlled clock; deterministic (zero model calls).
Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_digest.py
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
from anticipy_engine.proactive.digest import DigestQueue
from anticipy_engine.shared.schema import now_ts


class FakeGlass:
    def __init__(self): self.entries = []
    def log(self, kind, data): self.entries.append((kind, data))


class FakeScore:
    def record_decision(self, *a): pass
    def record_goal(self, *a): pass


def make():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-digest-"))
    lm = LiveMemoryBrain(Memory(data_dir=tmp))
    bus = Bus()
    for w in (ChannelStub(), ConnectorStub(), BrowserStub(), MemoryWorker(lm)):
        bus.register_worker(w)
    gw = ModelGateway()
    orch = Orchestrator(bus, gw, GoalStore(data_dir=tmp), glassbox=FakeGlass(),
                        scorecard=FakeScore(), approver=AutoApprover(True))
    pro = ProactiveEngine(bus, gw, orch, glassbox=FakeGlass(), scorecard=FakeScore(), channel=TextChannel())
    return bus, pro


def unit_checks(fails):
    dq = DigestQueue()
    assert dq.build() is None and dq.deliver() is None, "an empty digest is silent (a quiet day says nothing)"
    dq.defer("remind me to call the dentist")
    dq.defer("book a dinner table Friday")
    dq.defer("remind me to call the dentist")  # identical -> deduped, never stacks
    if dq.count() != 2:
        fails.append(f"digest should dedupe identical items: count={dq.count()}")
    msg = dq.build() or ""
    if not msg.startswith("Here's what I caught today."):
        fails.append(f"digest header wrong: {msg!r}")
    if "Call the dentist" not in msg or "Book a dinner table Friday" not in msg:
        fails.append(f"digest must list each item, humanized: {msg!r}")
    if "remind me to" in msg.lower():
        fails.append("digest must be humanized (strip 'remind me to'), not raw engine text")
    if dq.deliver() != msg or dq.count() != 0:
        fails.append("deliver() returns the message AND clears (deliver-once)")
    # persistence across a restart
    p = Path(tempfile.mkdtemp(prefix="anticipy-digest-p-")) / "d.json"
    DigestQueue(p).defer("email Sarah the budget")
    if DigestQueue(p).count() != 1:
        fails.append("digest must persist across an engine restart")


async def main():
    fails = []
    unit_checks(fails)

    bus, pro = make()
    now = now_ts()
    await bus.start()
    try:
        # N over-budget non-urgent asks -> ONE digest, not N pings
        pro.budget = AnnoyanceBudget(max_per_day=2)
        outs = [await pro.on_event(Event(source=EventSource.system,
                                         text=f"Send the signed contract to vendor {i}."), now=now)
                for i in range(5)]
        asks = [o for o in outs if o["decision"] == "ask"]
        if len(asks) != 2:
            fails.append(f"budget cap=2 -> 2 real-time asks, got {len(asks)}")
        if pro.digest.count() != 3:
            fails.append(f"the 3 over-budget items must DEFER to the digest (not drop), got {pro.digest.count()}")
        if len(pro.channel.sent) != 2:
            fails.append(f"only the 2 real-time asks send; NO spam for the overflow, got {len(pro.channel.sent)} sends")
        if pro.budget.count(now) != 2:
            fails.append(f"deferring to the digest must draw ZERO budget; budget={pro.budget.count(now)}")

        # deliver the digest: ONE message for all 3, drawing ZERO budget
        res = pro.deliver_digest(now)
        if not (res.get("sent") and res.get("count") == 3):
            fails.append(f"digest deliver should send ONE message for 3 items: {res}")
        if len(pro.channel.sent) != 3:
            fails.append(f"after the digest: 3 total sends (2 asks + 1 digest), got {len(pro.channel.sent)}")
        if pro.budget.count(now) != 2:
            fails.append("the digest delivery itself must NOT draw interrupt budget")
        if pro.digest.count() != 0:
            fails.append("the digest clears after delivery")
        # a quiet day sends nothing
        res2 = pro.deliver_digest(now)
        if res2.get("sent") or len(pro.channel.sent) != 3:
            fails.append(f"a quiet day must send nothing (no filler digest): {res2}")

        # a DECLINED action-type is dropped, NEVER deferred to the digest
        pro.budget = AnnoyanceBudget(max_per_day=99)
        pro.digest = DigestQueue()
        o = await pro.on_event(Event(source=EventSource.system, text="Email the investor the deck."), now=now)
        await pro.resolve_ask(o["ask_id"], approved=False)   # the user said no to this type
        o2 = await pro.on_event(Event(source=EventSource.system, text="Email the investor the deck."), now=now)
        if o2["decision"] != "suppressed":
            fails.append(f"a declined type should suppress on its next occurrence: {o2}")
        if pro.digest.count() != 0:
            fails.append("a DECLINED type must NEVER land in the digest (the user said no)")
    finally:
        await bus.stop()

    if fails:
        print("==== FAIL ===="); [print("   -", f) for f in fails]; raise SystemExit(1)
    print("PASS digest (NF10): N over-budget non-urgent items -> ONE daily digest, not N pings; "
          "the digest draws zero interrupt budget; declined types never land in it; a quiet day stays quiet")


if __name__ == "__main__":
    asyncio.run(main())
