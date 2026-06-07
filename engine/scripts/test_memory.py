"""Piece 1 (unit): the four REAL drawers (supersedes the chunk-1 room-6 stub test).

SQLite persistence, drawer isolation, the exact/deterministic open_loops ledger,
restart durability, deterministic embedder + local vector recall.

Run:  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_memory.py
"""
import tempfile
from pathlib import Path

from anticipy_engine.memory import Memory
from anticipy_engine.memory.embed import embed


def main():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-mem-"))
    m = Memory(data_dir=tmp)

    # write one item into each of the four drawers
    pf = m.profile.write_text("User's name is Jordan; they are a founder.", people=["Jordan"])
    ol = m.open_loops.write_text("Call mom on Friday", people=["Mom"],
                                 fields={"due": "Friday", "task": "call"}, status="open")
    hi = m.history.write_text("Talked about gaming chairs.")
    dv = m.derived.write_text("User usually works late evenings.",
                              provenance="inferred", confidence=0.6)

    # drawer ISOLATION — each drawer holds only its own kind; no cross-reads
    assert [i.id for i in m.profile.all()] == [pf.id]
    assert [i.id for i in m.open_loops.all()] == [ol.id]
    assert [i.id for i in m.history.all()] == [hi.id]
    assert [i.id for i in m.derived.all()] == [dv.id]
    assert m.profile.get(ol.id) is None and m.history.get(pf.id) is None
    assert pf.kind == "profile_fact" and ol.kind == "open_loop" and dv.kind == "derived"

    # open_loops is EXACT + deterministic (the never-drop-a-ball ledger): structured
    # fields preserved verbatim; state transitions explicit + retrievable by id
    got = m.open_loops.get(ol.id)
    assert got.fields == {"due": "Friday", "task": "call"} and got.status == "open"
    got.status = "waiting"; m.open_loops.update(got)
    got.status = "done";    m.open_loops.update(got)
    assert m.open_loops.get(ol.id).status == "done"

    # stated vs inferred: provenance + confidence separate guesses from facts
    assert m.profile.get(pf.id).provenance == "stated" and m.profile.get(pf.id).confidence == 1.0
    assert m.derived.get(dv.id).provenance == "inferred" and m.derived.get(dv.id).confidence == 0.6

    # deterministic embedder (free + reproducible)
    assert embed("call mom friday") == embed("call mom friday")

    # SURVIVE RESTART: reopen the db; everything is still there incl. ledger state
    m2 = Memory(data_dir=tmp)
    assert m2.open_loops.get(ol.id).status == "done"
    assert len(m2.profile.all()) == 1 and len(m2.history.all()) == 1 and len(m2.derived.all()) == 1

    # local vector recall: the semantic leg surfaces the right history item
    a = m2.history.write_text("Talked about gaming chairs.")
    b = m2.history.write_text("Researched ergonomic office chairs for the desk.")
    c = m2.history.write_text("Planned a weekend hiking trip.")
    top2 = m2.search_vec("ergonomic office desk chairs", ["history"], k=1)
    assert top2 and top2[0].id == b.id, (top2 and top2[0].text)
    assert c.id not in [i.id for i in m2.search_vec("ergonomic office desk chairs", ["history"], k=2)]

    print("PASS piece 1: 4 SQLite drawers, isolation, open_loops exact+stateful, "
          "restart-durable, deterministic embed + vector recall")
    print("  data dir:", tmp)


if __name__ == "__main__":
    main()
