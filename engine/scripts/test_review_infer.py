"""REVIEW-INFER — the DISPLAY-ONLY task inference for the daily review.

The product is the INFERENCE: turn a messy remembered line into the unspoken task
({task, people, due_phrase, confidence}) and show it ABOVE the raw line. This test proves:

  (a) EXTRACTION on a test set — the 5 prior misses (real commitments) infer a sensible
      task; ordinary commitments too; and VENTS/sarcasm/retractions get an EMPTY task at
      LOW confidence (no over-claim) while the raw line is still shown.

  (b) ECONOMICS — enrichment is cached per line id; a second pull does ZERO new inference
      (the cache table count does not grow), and a brand-new line is the only thing
      enriched on the next pull.

  (c) STRICT DISPLAY-ONLY INERTNESS (the cardinal-sin-adjacent guard): the enrichment
      writes a DISTINCT cache table carrying NO due_ts/remind_ts/trigger/status/fired_at;
      it creates ZERO open_loops; inject() never surfaces it; list_open_loops cannot see
      it; and trigger_tick now AND +10y fires NOTHING and raises NO ask. A wrongly-inferred
      vent can never become a delayed action, because nothing in any firing path reads it.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_review_infer.py
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
from anticipy_engine.live_memory.press_go import map_inferred_to_step
from anticipy_engine.live_memory.review_infer import (
    ReviewEnricher, infer_line, is_vent, is_vent_shape)
from anticipy_engine.memory import Memory
from anticipy_engine.shared.schema import now_ts

# The 5 prior misses (the SAME set as test_memory_remembered.py) + ordinary commitments.
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
# Vents / sarcasm — NOT tasks. The review must NOT invent a task here.
VENTS = [
    "ugh I should just quit my job and move to a beach",
    "oh great, another all-hands, can't wait to waste two hours",
    "I'm gonna scream if Bob reschedules this meeting one more time",
]

# Fields the TriggerWatcher._due / list_open_loops ever read. NONE may exist on a cache row.
FORBIDDEN_FIELDS = {"due_ts", "remind_ts", "fired_at", "status", "trigger", "remind", "due"}


class FakeGlass:
    def __init__(self): self.entries = []
    def log(self, kind, data): self.entries.append((kind, data))


class FakeScore:
    def record_decision(self, *a): pass
    def record_goal(self, *a): pass


def check_extraction(fails):
    """(a) the 5 misses + commitments infer a task; vents get empty/low. Print examples."""
    examples = []
    # commitments must yield a non-empty task at med/high confidence
    for text in FIVE_PRIOR_MISSES + MORE_COMMITMENTS:
        inf = infer_line(text)
        examples.append((text, inf))
        if not inf["task"]:
            fails.append(f"commitment got EMPTY task: {text!r} -> {inf}")
        if inf["confidence"] not in ("med", "high"):
            fails.append(f"commitment under-confident: {text!r} -> {inf}")
    # vents must yield an EMPTY task at LOW confidence (no over-claim)
    for v in VENTS:
        inf = infer_line(v)
        examples.append((v, inf))
        if inf["task"]:
            fails.append(f"VENT got a task (over-claim): {v!r} -> {inf}")
        if inf["confidence"] != "low":
            fails.append(f"VENT not flagged low-confidence: {v!r} -> {inf}")
    # a few targeted field checks (people + due_phrase actually surface)
    deck = infer_line("I told Sam I'd send the deck")
    if "Sam" not in deck["people"]:
        fails.append(f"person not extracted: {deck}")
    domain = infer_line("Don't forget to renew the domain before it lapses")
    if not domain["due_phrase"]:
        fails.append(f"due_phrase not extracted from 'before it lapses': {domain}")
    priya = infer_line("I'll email Priya the contract tomorrow morning")
    if "Priya" not in priya["people"] or not priya["due_phrase"]:
        fails.append(f"email/priya/tomorrow not extracted: {priya}")
    return examples


# ---- Apollo wave 2 regression set: the inference-layer vent + recall holes ----
# Laugh-hedged jokes, "forever"/destructive hyperbole, and sarcasm retorts that the SEPARATE
# narrower review guard used to miss (while triage dropped them). is_vent() is now the single
# source of truth and infer_line() short-circuits on it -> EMPTY task -> press-go hands back.
LAUGH_HYPERBOLE_SARCASM_VENTS = [
    "remind me to never agree to a 7am meeting again, lol",   # laugh-hedge (the breach line)
    "remind me to quit this job haha",
    "note that I should email the whole team jk",
    "schedule a vacation for me forever",                     # "forever" hyperbole
    "delete my whole calendar",                               # destructive whole-scope hyperbole
    "wipe my entire inbox",
    "yeah right I will call the dentist back at 3pm",         # sarcasm retort (was HIGH-conf task)
    "as if I will finish the report by friday",
]
# Recall: an optional adverb between the first-person subject and the commit verb must NOT
# lose the commitment; and the plain (no-adverb) commitment is unchanged.
RECALL_COMMITMENTS = [
    "I really need to email the landlord",
    "I just have to call the dentist back",
    "I actually need to renew the domain before it lapses",
    "I definitely should follow up with the landlord on the lease",
]


def check_vent_recall_holes(fails):
    """Apollo wave 2: laugh/hyperbole/sarcasm vents infer EMPTY (and press-go hands back,
    executing nothing); 'I <adverb> need to X' recalls a task; no new false-action on a vent."""
    for v in LAUGH_HYPERBOLE_SARCASM_VENTS:
        if not is_vent(v):
            fails.append(f"is_vent() (single source of truth) missed a vent: {v!r}")
        inf = infer_line(v)
        if inf["task"]:
            fails.append(f"VENT over-claimed a task: {v!r} -> {inf}")
        if inf["confidence"] != "low":
            fails.append(f"VENT not low-confidence: {v!r} -> {inf}")
        # the cardinal-sin proof: press-go can build NO executable step from a vent
        step = map_inferred_to_step(inf, v)["step"]
        if step is not None:
            fails.append(f"press-go built an executable step from a VENT: {v!r} -> {step}")
    # the joke/hyperbole/sarcasm family is also caught by the durable-card guard
    for v in ("remind me to never agree to a 7am meeting again, lol",
              "schedule a vacation for me forever", "delete my whole calendar"):
        if not is_vent_shape(v):
            fails.append(f"is_vent_shape() (durable-card guard) missed a joke/hyperbole: {v!r}")
    # recall: the adverb-gapped commitment infers a task; a press-go note step CAN form
    for c in RECALL_COMMITMENTS:
        inf = infer_line(c)
        if not inf["task"]:
            fails.append(f"RECALL miss — adverb-gapped commitment lost: {c!r} -> {inf}")
    # a REAL self-directed reminder still maps to a write_memory note (recall preserved)
    real = infer_line("Remind me to renew the domain before friday")
    if map_inferred_to_step(real, "Remind me to renew the domain before friday")["step"] is None:
        fails.append("a REAL reminder no longer maps to a note step (recall regressed)")
    # a clause-final laugh self-cancels, but a NON-final 'lol' is not a vent (recall guard)
    if is_vent("lol I really need to email the landlord by friday"):
        fails.append("mid-line 'lol' wrongly treated as a self-cancel (over-zealous guard)")


def check_cache_economics(fails):
    """(b) enrichment is cached per id; a 2nd pull does NO new inference; only NEW lines
    are enriched on the next pull."""
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-review-cache-"))
    lm = LiveMemoryBrain(Memory(data_dir=tmp))
    cap = lm.capturer
    for text in FIVE_PRIOR_MISSES + VENTS:
        cap.capture(text, source="transcript")

    enr = cap.review_enricher
    rows1 = enr.enrich_rows(cap.remember.recent(50))
    n_after_first = enr.enrichment_count()
    if n_after_first != len(FIVE_PRIOR_MISSES) + len(VENTS):
        fails.append(f"first enrich cached {n_after_first}, expected "
                     f"{len(FIVE_PRIOR_MISSES) + len(VENTS)}")
    if not all("inferred" in r for r in rows1):
        fails.append("first enrich left some rows without an inferred field")

    # second pull: cache is reused, count must NOT grow (no re-inference)
    enr.enrich_rows(cap.remember.recent(50))
    if enr.enrichment_count() != n_after_first:
        fails.append(f"second pull re-inferred: count grew to {enr.enrichment_count()}")

    # a NEW line is the only thing enriched on the next pull
    cap.capture("I'll send Dana the invoice by Friday", source="transcript")
    enr.enrich_rows(cap.remember.recent(50))
    if enr.enrichment_count() != n_after_first + 1:
        fails.append(f"new line not (or over-) enriched: {enr.enrichment_count()} "
                     f"!= {n_after_first + 1}")
    return n_after_first


async def check_display_only_inertness(fails):
    """(c) the enrichment cache fires NOTHING and is invisible to every decision-path
    reader, even when the remembered lines are all VENTS.

    We write the vents STRAIGHT into the inert RememberList (the same isolation
    test_memory_remembered.py uses) so this asserts the ENRICHMENT path's inertness, not
    the unrelated drawer-writes the full capture chokepoint makes for real commitments."""
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-review-inert-"))
    lm = LiveMemoryBrain(Memory(data_dir=tmp))
    rl = RememberList(lm.memory.db)            # same db file, DISTINCT inert table
    for v in VENTS:
        rl.remember(v, source="transcript")
    enr = ReviewEnricher(lm.memory.db)
    rows = enr.enrich_rows(rl.recent(50))

    # the cache table carries NO trigger/fire field on any column
    conn = sqlite3.connect(str(lm.memory.db.path))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(remembered_enrichment)").fetchall()}
    leaked = FORBIDDEN_FIELDS & cols
    if leaked:
        fails.append(f"enrichment cache table has trigger/fire column(s): {leaked}")
    # the cache is DISTINCT from items + open_loops: zero rows landed there
    items_n = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    conn.close()
    if items_n != 0:
        fails.append(f"enrichment leaked into items table: {items_n} rows")
    if lm.memory.open_loops.all():
        fails.append(f"enrichment created open_loops: {[l.text for l in lm.memory.open_loops.all()]}")

    # the returned inferred dicts themselves carry NO time-to-fire field
    for r in rows:
        inf = r.get("inferred") or {}
        bad = FORBIDDEN_FIELDS & set(inf.keys())
        if bad:
            fails.append(f"inferred dict carries trigger/fire field(s) {bad}: {inf}")

    # inject() (harm-line/decider context) never surfaces a remembered/enriched line
    for v in VENTS:
        inj = lm.inject(v)
        surfaced = {i.text for i in inj["items"]} | {i.text for i in inj["open_loops"]}
        if v in surfaced:
            fails.append(f"inject() surfaced a remembered vent: {v!r}")

    # list_open_loops can't see it; trigger_tick now AND +10y fires nothing, raises no ask
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
        fired_future = await pro.trigger_tick(now=now + 3650 * 86400.0)
    finally:
        await bus.stop()
    if loops_out:
        fails.append(f"list_open_loops enumerated enriched rows: {loops_out}")
    if fired_now or fired_future:
        fails.append(f"trigger fired from the review path: now={fired_now} future={fired_future}")
    asks = [k for k, _ in glass.entries if k in ("ask", "ask_created", "interrupt")]
    if asks:
        fails.append(f"the review path produced ask/interrupt entries: {asks}")
    return items_n, len(loops_out)


async def main():
    fails = []
    examples = check_extraction(fails)
    check_vent_recall_holes(fails)
    n_cached = check_cache_economics(fails)
    items_n, loops_n = await check_display_only_inertness(fails)

    print("==== REVIEW TASK-INFERENCE (display-only) ====")
    print("  (a) extraction examples (line -> inferred {task, people, due_phrase, confidence}):")
    for text, inf in examples:
        print(f"      {text!r}")
        print(f"          -> task={inf['task']!r} people={inf['people']} "
              f"due_phrase={inf['due_phrase']!r} confidence={inf['confidence']}")
    print("  (a2) Apollo wave 2: laugh/hyperbole/sarcasm vents infer EMPTY (press-go builds "
          "NO step); adverb-gapped 'I really need to X' recalls a task; is_vent single source")
    print(f"  (b) economics: cached {n_cached} enrichments once; 2nd pull re-inferred 0; "
          f"only new lines enriched")
    print(f"  (c) inert: cache table has no due/remind/trigger column; items rows={items_n} "
          f"(must be 0); open_loops scan={loops_n} (must be 0); inject hides it; "
          f"trigger_tick now+10y fired 0; zero asks")

    if fails:
        print("==== FAIL ===="); [print("   -", f) for f in fails]; raise SystemExit(1)
    print("==== PASS: tasks inferred for display; vents not over-claimed; cached "
          "(no re-infer); review path is provably inert (no fire, no ask, no leak) ====")


if __name__ == "__main__":
    asyncio.run(main())
