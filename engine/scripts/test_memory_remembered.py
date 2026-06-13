"""Inert REMEMBER-list — the SAFE, decision-independent half of the inference core.

The architectural answer to the reverted INTERRUPT-catch attempts is to DECOUPLE
"remember" (generous) from "interrupt" (conservative). This test proves the SAFE
remember half in isolation, WITHOUT changing the existing act/ask/trigger path:

  (a) GENEROUS CAPTURE: every commitment — INCLUDING the 5 prior misses the conservative
      act/ask side kept dropping — lands in the pull-only remember-list when fed through
      the ONE capture chokepoint (Capturer.capture), and is returned by the explicit
      pull accessor (recent/all). Pure filler does NOT pollute it.

  (b) STRUCTURAL INERTNESS (the load-bearing claim): the remember-list is a SEPARATE
      table, NOT the open_loops ledger and NOT a memory drawer. To prove it can never
      reach the trigger/act path even when GENEROUSLY over-capturing vents, we build a
      RememberList on a FRESH memory, write VENT/sarcasm lines straight into it, and show:
        - rows carry NO due_ts / remind_ts / trigger / status / fired_at (the only fields
          TriggerWatcher._due + list_open_loops ever read);
        - it created ZERO open_loops (distinct table — the existing ledger is empty);
        - inject() (the harm-line/decider context read) never surfaces a remembered line;
        - list_open_loops (the trigger's ONLY source) cannot enumerate it;
        - trigger_tick at now AND +10 years fires ZERO triggers and produces ZERO asks.
      That last point is the delayed-cardinal-sin tripwire: a wrongly-remembered vent can
      never become a delayed action, because nothing in any firing path reads this store.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_memory_remembered.py
"""
import asyncio
import sqlite3
import tempfile
from pathlib import Path

from anticipy_engine.core.bus import Bus
from anticipy_engine.core.envelopes import Job
from anticipy_engine.core.gateway import ModelGateway
from anticipy_engine.core.orchestrator import AutoApprover, Orchestrator
from anticipy_engine.core.proactive import ProactiveEngine
from anticipy_engine.core.store import GoalStore
from anticipy_engine.core.workers import BrowserStub, ChannelStub, ConnectorStub
from anticipy_engine.core.workers.memory import MemoryWorker
from anticipy_engine.live_memory.brain import LiveMemoryBrain
from anticipy_engine.live_memory.remember import RememberList
from anticipy_engine.memory import Memory
from anticipy_engine.shared.schema import now_ts

# The 5 prior misses (real commitments the conservative act/ask side dropped) PLUS some
# ordinary commitments. Every one of these must be remembered (generous, high-recall).
FIVE_PRIOR_MISSES = [
    "I told Sam I'd send the deck",
    "I'll get this over to you by 4",
    "I need to call the dentist back about rescheduling",
    "Make sure I follow up with the landlord on the lease",
    "Don't forget to renew the domain before it lapses",
]
MORE_COMMITMENTS = [
    "I'll email Priya the contract tomorrow morning",
    "Remind me to pick up the prescription",
]
# Vents / sarcasm — NOT tasks. Acting OR asking on these (even via a DELAYED reminder) is
# the cardinal sin. Generously remembering them is safe ONLY because the list is inert.
VENTS = [
    "ugh I should just quit my job and move to a beach",
    "oh great, another all-hands, can't wait to waste two hours",
    "I'm gonna scream if Bob reschedules this meeting one more time",
]

# Fields the TriggerWatcher._due / list_open_loops ever read. NONE may exist on a row.
FORBIDDEN_FIELDS = {"due_ts", "remind_ts", "fired_at", "status", "trigger", "remind", "due"}


class FakeGlass:
    def __init__(self): self.entries = []
    def log(self, kind, data): self.entries.append((kind, data))


class FakeScore:
    def record_decision(self, *a): pass
    def record_goal(self, *a): pass


def check_generous_capture(fails):
    """(a) every commitment + the 5 prior misses + vents are remembered via the chokepoint."""
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-remember-cap-"))
    lm = LiveMemoryBrain(Memory(data_dir=tmp))
    cap = lm.capturer

    for text in FIVE_PRIOR_MISSES + MORE_COMMITMENTS + VENTS:
        cap.capture(text, source="transcript")   # the ONE chokepoint (feed + owner_ingest)
    cap.capture("um", source="transcript")        # pure filler must not pollute the list
    cap.capture("ok thanks", source="transcript")

    remembered = cap.remember.all()
    texts = {r["text"] for r in remembered}
    for miss in FIVE_PRIOR_MISSES:
        if miss not in texts:
            fails.append(f"PRIOR MISS not remembered: {miss!r}")
    for c in MORE_COMMITMENTS:
        if c not in texts:
            fails.append(f"commitment not remembered: {c!r}")
    for v in VENTS:
        if v not in texts:
            fails.append(f"vent not generously remembered: {v!r}")
    if "um" in texts:
        fails.append("pure filler 'um' leaked into the remember-list")
    # explicit pull accessor returns newest-first
    recent = cap.remember.recent(3)
    if [r["text"] for r in recent] != [r["text"] for r in remembered[:3]]:
        fails.append("recent() pull accessor is not newest-first / inconsistent with all()")
    return len(remembered)


async def check_inertness(fails):
    """(b) a remember-store full of VENTS, built on a FRESH memory, fires NOTHING and
    is invisible to every decision-path reader. Isolated from the existing open_loop path."""
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-remember-inert-"))
    lm = LiveMemoryBrain(Memory(data_dir=tmp))
    rl = RememberList(lm.memory.db)            # same db file, DISTINCT table

    for v in VENTS:
        rl.remember(v, source="transcript")

    # rows carry no trigger/fire fields
    for r in rl.all():
        leaked = FORBIDDEN_FIELDS & set(r.keys())
        if leaked:
            fails.append(f"remembered row carries trigger/fire field(s) {leaked}: {r}")

    # the remember table is DISTINCT from items: no remember row ever lands in `items`
    conn = sqlite3.connect(str(lm.memory.db.path))
    items_n = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    remembered_n = conn.execute("SELECT COUNT(*) FROM remembered_lines").fetchone()[0]
    conn.close()
    if items_n != 0:
        fails.append(f"remember-write leaked into the shared items table: {items_n} rows")
    if remembered_n != len(VENTS):
        fails.append(f"remembered_lines table count wrong: {remembered_n} != {len(VENTS)}")

    # zero open_loops created — distinct table, never a drawer write
    if lm.memory.open_loops.all():
        fails.append(f"remember-write created open_loops: {[l.text for l in lm.memory.open_loops.all()]}")

    # inject() (harm-line/decider context) never surfaces a remembered line
    for v in VENTS:
        inj = lm.inject(v)
        surfaced = {i.text for i in inj["items"]} | {i.text for i in inj["open_loops"]}
        if v in surfaced:
            fails.append(f"inject() surfaced a remembered vent: {v!r}")

    # list_open_loops (the trigger's ONLY source) cannot see the remember store; and a
    # full trigger_tick now AND +10y fires nothing and raises no ask.
    bus = Bus()
    for w in (ChannelStub(), ConnectorStub(), BrowserStub(), MemoryWorker(lm)):
        bus.register_worker(w)
    gw = ModelGateway()
    glass = FakeGlass()
    orch = Orchestrator(bus, gw, GoalStore(data_dir=tmp), glassbox=glass,
                        scorecard=FakeScore(), approver=AutoApprover(True))
    pro = ProactiveEngine(bus, gw, orch, glassbox=glass, scorecard=FakeScore())

    loops_out = []
    await bus.start()
    try:
        res = await bus.submit_job(Job(intent="list_open_loops"))
        loops_out = (res.output or {}).get("loops", [])
        now = now_ts()
        fired_now = await pro.trigger_tick(now=now)
        fired_future = await pro.trigger_tick(now=now + 3650 * 86400.0)   # +10 years
    finally:
        await bus.stop()

    if loops_out:
        fails.append(f"list_open_loops enumerated remember rows: {loops_out}")
    if fired_now or fired_future:
        fails.append(f"trigger fired from the remember-list: now={fired_now} future={fired_future}")
    asks = [k for k, _ in glass.entries if k in ("ask", "ask_created", "interrupt")]
    if asks:
        fails.append(f"a remembered vent produced ask/interrupt entries: {asks}")
    return loops_out, items_n, remembered_n


async def main():
    fails = []
    n_remembered = check_generous_capture(fails)
    loops_out, items_n, remembered_n = await check_inertness(fails)

    print("==== INERT REMEMBER-LIST ====")
    print(f"  (a) generous capture: remembered {n_remembered} lines "
          f"(incl. {len(FIVE_PRIOR_MISSES)} prior misses, {len(VENTS)} vents); filler dropped")
    print(f"  (b) inert store of {remembered_n} vents -> items table rows={items_n} (must be 0), "
          f"open_loops scan={len(loops_out)} (must be 0)")
    print("      no due_ts/remind_ts/fired_at on any row; inject never surfaces it; "
          "trigger_tick now+10y fired 0; zero asks")

    if fails:
        print("==== FAIL ===="); [print("   -", f) for f in fails]; raise SystemExit(1)
    print("==== PASS: commitments+misses remembered; remember-list is provably inert "
          "(no fire, no ask, no leak) ====")


if __name__ == "__main__":
    asyncio.run(main())
