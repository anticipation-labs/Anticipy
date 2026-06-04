"""Piece 6 (unit): SELF-CHECK + Scorecard — recall is MEASURED, bad injections caught.

A good injection logs a recall HIT; a deliberately-bad one (expected item missing)
and a completeness failure (an open loop dropped) are both caught and logged as
MISSES. The Scorecard's recall readout reflects the hit rate. Zero model calls.

Run:  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_memory_selfcheck.py
"""
import tempfile
from pathlib import Path

from anticipy_engine.core.scorecard import Scorecard
from anticipy_engine.live_memory.brain import LiveMemoryBrain
from anticipy_engine.live_memory.inject import Injector
from anticipy_engine.live_memory.selfcheck import SelfCheck
from anticipy_engine.memory import Memory
from anticipy_engine.shared.schema import MemoryItem


def main():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-sc-"))
    m = Memory(data_dir=tmp)
    m.open_loops.write(MemoryItem(kind="open_loop", text="Call the accountant about taxes", status="open"))
    h = m.history.write_text("The invoice for the Q3 project is overdue.")

    inj = Injector(m)
    good = inj.inject("overdue invoice Q3 project")
    assert h.id in [i.id for i in good["items"]]                # sanity: it really surfaced

    sc = Scorecard(tmp / "scorecard.jsonl")
    chk = SelfCheck(m, scorecard=sc)

    # 1) good injection -> HIT (expected item present + open loop surfaced)
    a1 = chk.audit("overdue invoice Q3 project", good, expected_ids=[h.id])
    assert a1["hit"] is True and a1["complete"] is True and a1["smart_calls"] == 0

    # 2) deliberately-bad: expected item missing -> MISS, caught
    bad_relevance = {"items": [], "open_loops": good["open_loops"]}
    a2 = chk.audit("overdue invoice Q3 project", bad_relevance, expected_ids=[h.id])
    assert a2["hit"] is False and a2["relevant"] is False

    # 3) deliberately-bad: an open loop dropped -> MISS on completeness, caught
    bad_complete = {"items": good["items"], "open_loops": []}
    a3 = chk.audit("overdue invoice Q3 project", bad_complete)
    assert a3["hit"] is False and a3["complete"] is False and "open loops" in a3["reason"]

    # recall is MEASURED on the scorecard
    ro = sc.recall_readout()
    assert ro == {"recall_checked": 3, "recall_hits": 1, "recall_misses": 2, "recall_hit_rate": 0.333}, ro

    # the seam method wires inject + self-check in one hop
    lmb = LiveMemoryBrain(m, scorecard=Scorecard(tmp / "sc2.jsonl"))
    r = lmb.inject_checked("overdue invoice Q3 project")
    assert r["self_check"]["complete"] is True

    print("PASS piece 6: self-check logs recall hits/misses to the scorecard "
          "(hit_rate 0.333), catches a missing item AND a dropped open loop, zero model calls")


if __name__ == "__main__":
    main()
