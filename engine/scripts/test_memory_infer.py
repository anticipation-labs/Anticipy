"""Piece 5 (unit): INFER + confidence — derived facts, never promoted.

Repeated episodes about the gym become a DERIVED routine with a confidence score
< 1.0 and provenance='inferred'; it is NOT promoted to a stated profile fact
(profile is untouched); re-running is idempotent. Zero model calls.

Run:  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_memory_infer.py
"""
import tempfile
from pathlib import Path

from anticipy_engine.live_memory.infer import Inferrer
from anticipy_engine.memory import Memory
from anticipy_engine.shared.schema import MemoryItem


def main():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-inf-"))
    m = Memory(data_dir=tmp)

    # a stated fact that inference must never touch/duplicate
    m.profile.write_text("My name is Jordan.")
    profile_before = [p.id for p in m.profile.all()]

    # a clear routine: the gym recurs across four episodes
    for txt in ["Went to the gym before work.", "Hit the gym this morning.",
                "Quick gym session after lunch.", "Gym again today, leg day."]:
        m.history.write(MemoryItem(kind="history", text=txt, status="active"))

    res = Inferrer(m, min_count=3).infer()
    assert res["ran"] and res["smart_calls"] == 0, res

    # the routine is inferred as a DERIVED fact, with confidence < 1.0, marked inferred
    gym = [d for d in m.derived.all() if d.fields.get("signal") == "routine:gym"]
    assert len(gym) == 1, [d.fields for d in m.derived.all()]
    assert gym[0].provenance == "inferred" and 0.0 < gym[0].confidence < 1.0
    assert gym[0].fields.get("count") == 4 and gym[0].confidence == 0.8

    # NEVER promoted: profile (stated) is unchanged; nothing inferred leaked into it
    assert [p.id for p in m.profile.all()] == profile_before
    assert all(p.provenance == "stated" and p.confidence == 1.0 for p in m.profile.all())

    # idempotent: a second pass updates the same signal, doesn't duplicate
    n = len(m.derived.all())
    Inferrer(m, min_count=3).infer()
    assert len(m.derived.all()) == n

    print("PASS piece 5: routine inferred as derived (confidence 0.8, inferred), never promoted "
          "to a stated fact, idempotent, zero model calls")


if __name__ == "__main__":
    main()
