"""WHERE A RESEARCHED PROCEDURE LIVES ON THE SERVER, settled.

HANDS 1 spec §4.3 left one question open: is the procedure store owner-scoped?
The recommendation was "owner-scoped first, shared later or never", and §4.4
priced the two backings — a PocketBase collection costs a migration plus three
registration points (`guard.pb.js`, `account_delete.pb.js` OWNER_TABLES, and a
retention sweep), while a per-owner SQLite TABLE has always been free.

It is the SQLite. These are the properties that choice has to keep true:
one store per owner, deleted by the delete that deletes the owner's directory,
bounded, and speaking exactly the `get`/`set` map interface `brain.research`
already expects — the same interface `chrome.storage.local` gives the browser
half, so the two sides of the port cannot drift.
"""
import json
import time

import pytest

import brain.research as research
from brain.memory import PROCEDURE_TABLE, Memory


def procedure(learned_at=None, steps=("open the portal", "file the form")):
    return {"startUrl": "https://bchydro.com/help", "needs": ["an account number"],
            "steps": list(steps), "caveats": ["takes 10 business days"],
            "sources": ["https://bchydro.com/help"],
            "learnedAt": learned_at if learned_at is not None
            else int(time.time() * 1000),
            "question": "how do you dispute a hydro bill"}


def test_a_procedure_round_trips_through_the_owners_own_sqlite():
    store = Memory().procedures()
    research.remember_procedure("dispute hydro bill", procedure(), store)
    hit = research.recall_procedure("dispute hydro bill", store)
    assert hit and hit["steps"] == ["open the portal", "file the form"]


def test_two_owners_do_not_share_a_store(tmp_path):
    """The scoping is the FILE. Two owners are two databases, so a procedure
    one owner's research paid for is invisible to the other — which is §4.3's
    recommendation ("owner-scoped first") made structural rather than
    remembered."""
    a = Memory(tmp_path / "a.db").procedures()
    b = Memory(tmp_path / "b.db").procedures()
    research.remember_procedure("shape", procedure(), a)
    assert research.recall_procedure("shape", a)
    assert research.recall_procedure("shape", b) is None


def test_the_store_survives_a_reopen_of_the_same_database(tmp_path):
    """A procedure that died with the process would be a cache that never
    compounds — the whole point of moving it off the browser is that it
    outlives one run."""
    research.remember_procedure("shape", procedure(),
                                Memory(tmp_path / "own.db").procedures())
    assert research.recall_procedure(
        "shape", Memory(tmp_path / "own.db").procedures())


def test_an_existing_database_gains_the_table_with_no_migration(tmp_path):
    """`CREATE TABLE IF NOT EXISTS` reaches an old database with a new TABLE —
    that is how `vetoed_facts` shipped, and it is the whole reason this is
    free where a PocketBase collection is not (§4.4)."""
    import sqlite3
    db = sqlite3.connect(str(tmp_path / "old.db"))
    db.execute("CREATE TABLE episodes (id INTEGER PRIMARY KEY, ts REAL, text TEXT)")
    db.commit()
    db.close()
    store = Memory(tmp_path / "old.db").procedures()
    research.remember_procedure("shape", procedure(), store)
    assert research.recall_procedure("shape", store)


def test_the_store_is_bounded_the_way_the_browser_half_is(tmp_path):
    store = Memory(tmp_path / "own.db").procedures()
    for i in range(5):
        research.remember_procedure(f"shape{i}", procedure(learned_at=1000 + i),
                                    store, limit=3)
    kept = set(store.get(research.PROCEDURE_KEY))
    assert len(kept) == 3
    assert "shape0" not in kept and "shape4" in kept


def test_the_table_is_one_row_per_shape_and_not_one_opaque_blob(tmp_path):
    """Inspectable on purpose. `sources` is retained so provenance stays
    checkable (§4.3), and provenance nobody can query is provenance in name
    only."""
    memory = Memory(tmp_path / "own.db")
    research.remember_procedure("shape", procedure(), memory.procedures())
    rows = memory.db.execute(
        f"SELECT shape, record FROM {PROCEDURE_TABLE}").fetchall()
    assert [r[0] for r in rows] == ["shape"]
    assert json.loads(rows[0][1])["sources"] == ["https://bchydro.com/help"]


def test_a_key_this_store_does_not_hold_is_a_miss_not_a_silent_share(tmp_path):
    """One table, one meaning. A second caller reaching for another key must
    not quietly get the procedures — that is how two unrelated things end up
    sharing a row and neither owner notices."""
    store = Memory(tmp_path / "own.db").procedures()
    research.remember_procedure("shape", procedure(), store)
    assert store.get("something_else") == {}
    store.set("something_else", {"shape": procedure()})
    assert research.recall_procedure("shape", store)["steps"]


def test_the_key_is_spelled_the_same_on_both_sides():
    """memory.py cannot import research.py (research imports orchestrator and
    memory is imported BY anticipy_core, so the constant would build a cycle),
    so the two spellings are held together HERE. A store answering a key
    nothing writes is a cache that is always empty and never says so."""
    from brain import memory as memory_module
    assert memory_module._PROCEDURE_MAP_KEY == research.PROCEDURE_KEY


def test_a_broken_database_is_a_miss_and_never_a_crash(tmp_path):
    """`recall_procedure`'s contract: breaking an errand over a storage
    failure is worse than paying for the research again."""
    memory = Memory(tmp_path / "own.db")
    store = memory.procedures()
    memory.db.close()
    assert research.recall_procedure("shape", store) is None
    research.remember_procedure("shape", procedure(), store)   # must not raise
