"""M6 gate — the live seams, each proven with its CONTRADICTOR (a check that can FAIL).

Two seams, two contradictors:

  RERANK (rerank.py):
    * it does real work — a moment-relevant memory that the base ranker buried is pulled to the
      FRONT so it survives a tight char budget (without rerank the wrong memory would win).
    * its CONTRADICTOR holds — recall@k vs the base ranker never regresses: when a boost would
      evict a base-top-k item, the rerank is REJECTED and we fall back to base order. Proven by
      forcing that exact conflict and asserting the base set is preserved.

  REFLECTION (infer.py):
    * a genuine routine (recurs across DISTINCT episodes) IS derived (confidence < 1.0, never
      promoted to a stated fact).
    * its CONTRADICTOR holds — a single line RE-INGESTED many times does NOT become a routine
      (evidence is one distinct episode), and a VENT never hardens into an inferred fact.

Deterministic, no model. Run:
  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_memctx_rerank.py
"""
import tempfile
from pathlib import Path

from anticipy_engine.live_memory.brain import LiveMemoryBrain
from anticipy_engine.live_memory.rerank import rerank, recall_held, moment_bonus
from anticipy_engine.memory import Memory
from anticipy_engine.shared.schema import MemoryItem


def _mk(id_, text, people=None, fields=None):
    it = MemoryItem(kind="history", text=text, people=people or [], fields=fields or {},
                    provenance="stated", status="active")
    it.id = id_
    return it


def test_rerank_pulls_moment_item_to_front():
    # base order buries the on-point item (id=B, names the person 'Priya') at rank 2, behind a
    # higher-base but off-moment item A. The query is about Priya. Rerank must surface B first.
    A = _mk("A", "generic note about the office move logistics")
    B = _mk("B", "send the contract", people=["Priya"])
    C = _mk("C", "unrelated grocery list")
    scored = [(0.80, A), (0.78, B), (0.40, C)]
    qtok = {"priya", "contract"}
    out = rerank(qtok, scored, k=3)
    assert out[0].id == "B", ("rerank did not pull the moment item to the front", [i.id for i in out])
    # and recall is trivially held (same set, reordered)
    assert recall_held({"A", "B", "C"}, out)


def test_rerank_contradictor_rejects_recall_loss():
    # k=2: base top-k is {A, B}. A window item D (rank 3) gets a big moment boost that WOULD evict
    # B from the top-2. The contradictor must REJECT the rerank and fall back to base order {A,B}.
    A = _mk("A", "alpha")
    B = _mk("B", "bravo")
    D = _mk("D", "delta", people=["Zoe"], fields={"tag": "zoe"})
    scored = [(0.90, A), (0.62, B), (0.60, D)]
    qtok = {"zoe"}
    # sanity: D really would outrank B under the boost (so the guard is doing real work).
    assert 0.60 + moment_bonus(qtok, D) > 0.62, "test premise broke: D would not evict B"
    out = rerank(qtok, scored, k=2)
    ids = {i.id for i in out}
    assert ids == {"A", "B"}, ("recall@k regressed — contradictor did not fire", ids)


def test_reflection_real_routine_derived_but_fakes_rejected():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-reflect-"))
    lm = LiveMemoryBrain(Memory(data_dir=tmp))
    mem = lm.memory

    # GENUINE routine: yoga recurs across 3 DISTINCT episodes -> should be derived.
    for t in ["went to yoga after work", "yoga class this morning was great",
              "signed up for another yoga session"]:
        mem.history.write(MemoryItem(kind="history", text=t, provenance="stated", status="active"))
    # FAKE routine 1: the SAME line re-ingested 4x -> ONE distinct episode -> must NOT derive.
    for _ in range(4):
        mem.history.write(MemoryItem(kind="history", text="pistachio delivery arrived",
                                     provenance="stated", status="active"))
    # FAKE routine 2: a vent repeated 3x -> must NEVER harden into an inferred fact.
    for _ in range(3):
        mem.history.write(MemoryItem(kind="history", text="ugh everything is such a disaster today",
                                     provenance="stated", status="active"))

    lm.inferrer.min_count = 3
    lm.inferrer.infer()
    derived = [d.text.lower() for d in mem.derived.all() if d.status == "active"]
    blob = " ".join(derived)

    assert any("yoga" in d for d in derived), ("genuine routine was not derived", derived)
    assert "pistachio" not in blob, ("a re-ingested single line became a fake routine", derived)
    assert "disaster" not in blob and "everything" not in blob, \
        ("a vent hardened into an inferred fact", derived)
    # derived facts are never promoted to certainty.
    for d in mem.derived.all():
        assert d.confidence < 1.0, ("derived fact was promoted to a stated certainty", d)


def main():
    test_rerank_pulls_moment_item_to_front()
    test_rerank_contradictor_rejects_recall_loss()
    test_reflection_real_routine_derived_but_fakes_rejected()
    print("OK  M6 seams: rerank surfaces the moment item + recall-guard fires on conflict; "
          "reflection derives real routines, rejects re-ingest fakes & vents")


if __name__ == "__main__":
    main()
