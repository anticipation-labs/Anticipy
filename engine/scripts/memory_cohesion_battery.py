"""Piece 8 — THE COHESION BATTERY (the hard done-test).

Mock onboarding (bulk profile import) + mock proactive engine (injects context for
a moment, decides act-vs-ask) poke the REAL memory agent exactly as the real ones
will. Replays a simulated WEEK (conversations, commitments, people, a mid-week job
change, a repeated routine, noise), then a cold sweep, then asserts:

  RECALL          — right item surfaces by meaning / name / date (records a score)
  COMMITMENTS     — every promise tracked, NONE dropped (deterministic, 100%)
  FRESHNESS       — job change supersedes the old fact; a stale episode decays
  INJECT-COHESION — right context lands; low-confidence (inferred) flagged -> ASK
  COST            — capture/inject/sweep cost is within budget (zero model calls)

Deterministic + free (stub embedder/model). Prints a scorecard; exits 0 on PASS.
GLUE/REGRESSION (full suite still green) is the separate scripts/run_suite.sh gate.

Run:  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/memory_cohesion_battery.py
"""
import sys
import tempfile
from pathlib import Path

from anticipy_engine.core.scorecard import Scorecard
from anticipy_engine.live_memory.brain import LiveMemoryBrain
from anticipy_engine.memory import Memory
from anticipy_engine.shared.schema import CaptureEvent, MemoryItem, now_ts

DAY = 86400.0


class MockOnboarding:
    """Opening sweep: bulk-fill the profile (as real onboarding will)."""
    def __init__(self, lm):
        self.lm = lm

    def bulk_import(self, facts):
        for text in facts:
            self.lm.capturer.capture(text, source="onboarding", force=True)


class MockProactive:
    """Pokes memory like the real gate: inject context, then decide act-vs-ask.
    Acting on a LOW-confidence (inferred) fact must become an ASK, not an act."""
    def __init__(self, lm, conf_floor=0.9):
        self.lm = lm
        self.conf_floor = conf_floor

    def gate(self, moment):
        inj = self.lm.inject_checked(moment)
        low = [i for i in inj["items"] if i.kind == "derived" and i.confidence < self.conf_floor]
        return {"items": inj["items"], "low_confidence": low, "would_ask": bool(low),
                "self_check": inj["self_check"]}


def main():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-cohesion-"))
    m = Memory(data_dir=tmp)
    sc = Scorecard(tmp / "scorecard.jsonl")
    lm = LiveMemoryBrain(m, scorecard=sc)
    onb, prox = MockOnboarding(lm), MockProactive(lm)
    smart_calls = 0  # the whole week must cost zero model calls in stub mode

    # ---- onboarding: bulk profile import ----
    onb.bulk_import([
        "My name is Jordan and I'm a founder.",
        "I work at OldCo Inc.",            # employer (changes mid-week)
        "My wife is Mia.",
        "My boss is Dana.",
        "I prefer tea over coffee.",
        "I use Gmail and Notion.",
    ])

    # ---- the week: (day, text, expected_kind) ----
    WEEK = [
        (1, "I'll call the dentist tomorrow.", "open_loop"),
        (1, "um", "noise"), (1, "ok thanks", "noise"),
        (1, "Chatted with Mia about weekend plans.", "history"),
        (2, "Remind me to pay rent on Friday.", "open_loop"),
        (2, "Went to the gym before work.", "history"),
        (3, "I need to email the accountant about taxes by Thursday.", "open_loop"),
        (3, "Hit the gym this morning.", "history"),
        (3, "yeah", "noise"),
        (4, "I work at NewCo Labs now.", "profile_fact"),   # the JOB CHANGE
        (4, "I should follow up with Dana about the contract.", "open_loop"),
        (4, "Quick gym session after lunch.", "history"),
        (5, "I'll book the flights for the trip next week.", "open_loop"),
        (5, "Gym again, leg day.", "history"),
        (6, "Reviewed the Q3 budget spreadsheet.", "history"),
        (6, "hey", "noise"),
    ]
    commitments_made, kept, dropped = [], 0, 0
    for _day, text, expect in WEEK:
        r = lm.capture(CaptureEvent(source="mac_mic", text=text))
        smart_calls += r.get("smart_calls", 0)
        if expect == "noise":
            dropped += 1
        else:
            kept += 1
            if r.get("kept") and r.get("kind") == "open_loop":
                commitments_made.append(text)

    # a stale episode from weeks ago (for the decay check) + one completed commitment
    m.history.write(MemoryItem(kind="history", text="Idle small talk from last month.",
                               status="active", importance=0.2, timestamp=now_ts() - 40 * DAY))
    dentist = next(l for l in m.open_loops.all() if "dentist" in l.text)
    dentist.status = "done"; m.open_loops.update(dentist)   # commitment completed (still tracked)

    # ---- end-of-week cold sweep (maintain + infer) ----
    sweep = lm.maintain(); smart_calls += sweep.get("smart_calls", 0)
    inferred = lm.infer(); smart_calls += inferred.get("smart_calls", 0)

    # ============ ASSERT THE BAR ============
    fails = []

    # COMMITMENTS — every promise tracked, none dropped (100%); completed one still tracked
    loop_texts = {l.text for l in m.open_loops.all()}
    tracked = sum(1 for c in commitments_made if c in loop_texts)
    commit_rate = tracked / len(commitments_made) if commitments_made else 0.0
    if commit_rate != 1.0 or len(commitments_made) != 5:
        fails.append(f"COMMITMENTS {tracked}/{len(commitments_made)} (expected 5/5)")
    if m.open_loops.get(dentist.id).status != "done":
        fails.append("completed commitment not tracked as done")

    # FRESHNESS — job change superseded OldCo (active=NewCo); stale episode decayed
    employers = [p for p in m.profile.all() if "work at" in p.text.lower()]
    old = next((p for p in employers if "OldCo" in p.text), None)
    new = next((p for p in employers if "NewCo" in p.text), None)
    if not (old and old.status == "superseded" and new and new.status != "superseded"):
        fails.append(f"FRESHNESS supersede failed: old={old and old.status} new={new and new.status}")
    stale = next((h for h in m.history.all() if "last month" in h.text), None)
    if not (stale and stale.status == "archived"):
        fails.append(f"FRESHNESS decay failed: stale={stale and stale.status}")

    # RECALL — right item surfaces by meaning / name / date (record the score)
    new_id = new.id if new else "?"
    boss = next((p for p in m.profile.all() if "Dana" in p.text), None)
    tea = next((p for p in m.profile.all() if "tea" in p.text), None)
    rent = next((l for l in m.open_loops.all() if "rent" in l.text), None)
    probes = [
        ("where do I work these days", new_id),                 # meaning (+ freshness: NewCo not OldCo)
        ("what is my boss Dana about", boss.id if boss else "?"),  # name
        ("rent payment due Friday", rent.id if rent else "?"),  # date
        ("do I like tea or coffee", tea.id if tea else "?"),    # meaning
    ]
    hits = 0
    for q, eid in probes:
        inj = lm.inject(q)
        audit = lm.recall_check(q, inj, expected_ids=[eid])   # logs hit/miss to the scorecard
        smart_calls += audit.get("smart_calls", 0)
        if audit["hit"]:
            hits += 1
    recall = hits / len(probes)
    # the old employer fact must NOT resurface for the "where do I work" probe
    work_items = [i.text for i in lm.inject("where do I work these days")["items"]]
    if any("OldCo" in t for t in work_items):
        fails.append("RECALL freshness: superseded OldCo resurfaced")
    if recall < 0.8:
        fails.append(f"RECALL {recall:.2f} below 0.80 bar")

    # INJECT-COHESION — right context lands; low-confidence (inferred) flagged -> ASK
    gym_gate = prox.gate("should I go to the gym today")
    if not gym_gate["would_ask"]:
        fails.append("INJECT-COHESION: low-confidence routine not flagged for ASK")
    work_gate = prox.gate("where do I work these days")
    if work_gate["would_ask"]:
        fails.append("INJECT-COHESION: acted-ASK on a high-confidence stated fact")
    routine = [i for i in lm.inject("gym routine")["items"] if i.kind == "derived"]
    if not (routine and routine[0].confidence < 1.0):
        fails.append("INFER: gym routine not present as a sub-1.0 derived fact")

    # COST — zero model calls all week (stub); scorecard cost within budget
    cost = sc.readout().get("total_model_cost", 0.0)
    if smart_calls != 0 or cost > 0.0:
        fails.append(f"COST not free: smart_calls={smart_calls} cost={cost}")

    # ============ SCORECARD ============
    print("==== MEMORY COHESION BATTERY — simulated week ====")
    print(f"  RECALL          : {hits}/{len(probes)} probes ({recall:.2f})        [bar >= 0.80]")
    print(f"  COMMITMENTS     : {tracked}/{len(commitments_made)} tracked, 0 dropped ({commit_rate:.2f})   [bar 1.00]")
    print(f"  FRESHNESS       : OldCo->superseded, NewCo active; stale episode decayed")
    print(f"  INJECT-COHESION : gym(inferred,conf<1) -> would_ask={gym_gate['would_ask']}; "
          f"employer(stated) -> would_ask={work_gate['would_ask']}")
    print(f"  COST            : smart_calls={smart_calls}, model_cost={cost}   [free]")
    print(f"  scorecard.recall: {sc.recall_readout()}")
    print(f"  open_loops={len(m.open_loops.all())} profile_active="
          f"{len([p for p in m.profile.all() if p.status not in ('superseded','archived')])} "
          f"history={len(m.history.all())} derived={len(m.derived.all())}")
    if fails:
        print("==== FAIL ====")
        for f in fails:
            print("   -", f)
        sys.exit(1)
    print("==== PASS ====")


if __name__ == "__main__":
    main()
