"""Piece 3 (unit): INJECT — hybrid retrieval + assembly + budget + open-loops-always.

Seeds a small memory and asserts the right item surfaces by MEANING, by NAME, and
by DATE; that ALL open/waiting loops are always surfaced (done ones never); and
that the assembled context respects a char budget. Zero model calls in stub mode.

Run:  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_memory_inject.py
"""
import tempfile
from pathlib import Path

from anticipy_engine.live_memory.inject import Injector
from anticipy_engine.memory import Memory
from anticipy_engine.shared.schema import MemoryItem


def ids(items):
    return [i.id for i in items]


def main():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-inj-"))
    m = Memory(data_dir=tmp)

    # open_loops ledger: one open (always surfaced), one done (never surfaced)
    L1 = m.open_loops.write(MemoryItem(kind="open_loop", text="Call Sarah about the overdue invoice",
                                       people=["Sarah"], status="open"))
    L2 = m.open_loops.write(MemoryItem(kind="open_loop", text="Submit the tax forms", status="done"))

    m.profile.write_text("User's name is Jordan; they are a founder.", people=["Jordan"])
    H1 = m.history.write_text("Discussed ergonomic office chair options for the standing desk.")
    H2 = m.history.write_text("Sarah said she is moving apartments next month.", people=["Sarah"])
    H3 = m.history.write_text("Booked a dentist appointment for Monday morning.")
    m.history.write_text("Talked about a weekend hiking trip in the mountains.")
    for n in range(6):
        m.history.write_text(f"Casual chit chat number {n} about nothing in particular.")

    inj = Injector(m)

    # by MEANING: semantic+keyword surfaces the office-chair episode
    r = inj.inject("comfortable office chair for the standing desk")
    assert H1.id in ids(r["items"]) and H1.id in ids(r["history"]), r["text"][:200]

    # by NAME: the Sarah history episode surfaces (people/keyword leg)
    r = inj.inject("Sarah")
    assert H2.id in ids(r["items"]), r["text"][:200]

    # by DATE: the Monday dentist episode surfaces
    r = inj.inject("Monday dentist appointment")
    assert H3.id in ids(r["items"]), r["text"][:200]

    # OPEN-LOOPS ALWAYS: even an unrelated query surfaces the open loop, never the done one
    r = inj.inject("quantum chromodynamics totally unrelated")
    assert ids(r["open_loops"]) == [L1.id], ids(r["open_loops"])
    assert L2.id not in ids(r["items"])

    # SIZE-BUDGETED: a tight budget bounds the assembled context
    tight = Injector(m, char_budget=100)
    r = tight.inject("office chair")
    assert len(r["text"]) <= 100, len(r["text"])
    assert len(ids(r["items"])) == len(set(ids(r["items"])))  # deduped
    assert r["smart_calls"] == 0 and r["stub"] is False

    print("PASS piece 3: inject recall by meaning/name/date, open-loops always (done excluded), "
          "char-budgeted, deduped, zero model calls")


if __name__ == "__main__":
    main()
