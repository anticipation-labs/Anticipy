"""The consolidation gate, driven against synthetic stores.

A gate leg nobody has watched fail is not a gate leg. Every leg below is shown
going RED for its own reason and GREEN only when the thing it claims to measure
is actually true — including the two failures that matter most and look like
success from a distance:

  * NOTHING TO MEASURE. The gate is run where no brain runs, or against stores
    that have heard nothing. Silence must be a failure; the first draft of
    overnight/consolidation_gate.py had leg 2 printing "every live store
    carries kind, retired_ts and retired_by" against a list of ZERO stores,
    which is a green light produced by an empty for-loop.
  * THE PASS RAN AND ACHIEVED NOTHING. `last_run_ts` fresh, not one fact
    labelled. That is a live worker calling a model that cannot answer, and
    half (a) of the leg on its own would call it healthy.

And one property the gate has to hold about ITSELF: it is pointed at
production, so it must not write. Opening these stores through
brain.memory.Memory would run the schema and the column retrofit, which would
silently repair the very thing leg 2 exists to find missing.
"""
from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from brain.memory import Memory  # noqa: E402
from llm_fakes import FakeLLM  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    # By path, not by package: overnight/ has no __init__.py and is a
    # directory of runnable scoreboards, not an importable module. Same shape
    # tests/test_tape_gate.py uses.
    spec = importlib.util.spec_from_file_location(
        "consolidation_gate",
        os.path.join(ROOT, "overnight", "consolidation_gate.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gate = _load()

DAY = 86400.0


@pytest.fixture(autouse=True)
def _no_inherited_store(monkeypatch, tmp_path):
    """The gate reads two environment variables to find production. A test
    inheriting the developer's own would measure their real memory."""
    monkeypatch.delenv("ANTICIPY_MEMORY_DB", raising=False)
    monkeypatch.setenv("ANTICIPY_STATE_ROOT", str(tmp_path / "empty-root"))


def _healthy_store(tmp_path, ref: str = "ownerA", now: float | None = None,
                   kind: str | None = "stable") -> str:
    """A store in the state the gate is asking about: episodes heard, a
    consolidation pass completed just now, and the model's stability verdict
    on the profile row where the ranker reads it."""
    now = now or time.time()
    owner = tmp_path / "root" / ref
    owner.mkdir(parents=True, exist_ok=True)
    path = owner / "memory.db"
    fact = {"fact": "allergic to shellfish", "importance": 5,
            "episode_ids": [1]}
    if kind:
        fact["kind"] = kind
    m = Memory(path=path, llm=FakeLLM(consolidations=[{"facts": [fact]}]))
    m.ingest("I can't have shellfish, it's a real allergy.", ts=now - 60)
    out = m.consolidate(now=now)
    assert out["ran"], out
    m.db.close()
    return str(path)


def _root(tmp_path, monkeypatch) -> list[str]:
    monkeypatch.setenv("ANTICIPY_STATE_ROOT", str(tmp_path / "root"))
    return gate.find_stores()


# ------------------------------------------------------------- all green


def test_a_brain_that_is_consolidating_passes_every_leg(tmp_path, monkeypatch):
    _healthy_store(tmp_path)
    stores = _root(tmp_path, monkeypatch)
    assert len(stores) == 1
    now = time.time()
    assert gate.leg_1_a_store_exists(stores)
    assert gate.leg_2_columns_present(stores)
    assert gate.leg_3_it_ran_recently(stores, now)
    assert gate.leg_4_it_wrote_a_kind(stores)
    # And end to end, both ways in: the scan and the explicit --db.
    assert gate.main([]) == 0
    assert gate.main(["--db", stores[0]]) == 0


# ------------------------------------------- nothing to measure is a FAILURE


def test_no_store_anywhere_fails_every_leg(tmp_path, monkeypatch):
    """Run on a laptop. The answer to "did the nightly pass run" only exists
    where the brain runs, and a gate that shrugs at that teaches the next agent
    that green means safe."""
    stores = _root(tmp_path, monkeypatch)
    assert stores == []
    for leg in (lambda: gate.leg_1_a_store_exists(stores),
                lambda: gate.leg_2_columns_present(stores),
                lambda: gate.leg_3_it_ran_recently(stores, time.time()),
                lambda: gate.leg_4_it_wrote_a_kind(stores)):
        with pytest.raises(gate.LegFailed) as e:
            leg()
        assert "cannot be tested does not pass" in str(e.value)
    assert gate.main([]) == 1


def test_stores_that_have_heard_nothing_are_not_evidence(tmp_path, monkeypatch):
    """A pass over an empty store correctly does nothing, so it proves
    nothing. Counting that as a healthy night is the silence door."""
    owner = tmp_path / "root" / "ownerA"
    owner.mkdir(parents=True)
    Memory(path=owner / "memory.db").db.close()
    stores = _root(tmp_path, monkeypatch)
    assert len(stores) == 1
    with pytest.raises(gate.LegFailed) as e:
        gate.leg_1_a_store_exists(stores)
    assert "ZERO episodes" in str(e.value)
    with pytest.raises(gate.LegFailed):
        gate.leg_4_it_wrote_a_kind(stores)


def test_one_silent_new_owner_does_not_turn_the_gate_red(tmp_path, monkeypatch):
    """The other direction, and the reason the empty-store rule is "all of
    them" rather than "any of them": somebody signing up this morning has an
    empty store and nothing to consolidate. A gate that went red the day a new
    owner arrived would be switched off inside a week."""
    _healthy_store(tmp_path, ref="ownerA")
    fresh = tmp_path / "root" / "ownerB"
    fresh.mkdir(parents=True)
    Memory(path=fresh / "memory.db").db.close()
    stores = _root(tmp_path, monkeypatch)
    assert len(stores) == 2
    assert gate.leg_1_a_store_exists(stores)
    assert gate.leg_3_it_ran_recently(stores, time.time())
    assert gate.leg_4_it_wrote_a_kind(stores)


# ------------------------------------------------------ leg 2: stale code


_PRE_FIX_SCHEMA = """
CREATE TABLE episodes (id INTEGER PRIMARY KEY, ts REAL NOT NULL,
                       text TEXT NOT NULL);
CREATE TABLE profile_facts (
    id INTEGER PRIMARY KEY, fact TEXT NOT NULL,
    importance INTEGER NOT NULL DEFAULT 3,
    confidence REAL NOT NULL DEFAULT 0.6,
    source TEXT NOT NULL DEFAULT 'consolidation',
    provenance TEXT NOT NULL DEFAULT '[]',
    first_seen_ts REAL NOT NULL, last_seen_ts REAL NOT NULL);
CREATE TABLE consolidation_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def _stale_brain_store(tmp_path, now: float) -> str:
    """A store as an OLDER worker would have left it: no kind column, no
    retirement columns, but consolidating happily."""
    owner = tmp_path / "root" / "ownerOld"
    owner.mkdir(parents=True)
    path = owner / "memory.db"
    conn = sqlite3.connect(str(path))
    conn.executescript(_PRE_FIX_SCHEMA)
    conn.execute("INSERT INTO episodes(ts, text) VALUES (?,?)",
                 (now - 60, "I can't have shellfish"))
    conn.execute("INSERT INTO profile_facts(fact, first_seen_ts, last_seen_ts) "
                 "VALUES (?,?,?)", ("allergic to shellfish", now, now))
    conn.execute("INSERT INTO consolidation_state(key, value) VALUES (?,?)",
                 ("last_run_ts", str(now)))
    conn.commit()
    conn.close()
    return str(path)


def test_a_brain_older_than_the_fix_is_caught_before_anything_else(
        tmp_path, monkeypatch):
    """Law 3's actual failure: prod serving stale code while the repo is
    green. The store is the fingerprint — the column retrofit runs on every
    Memory() open, so a missing column means the worker touching this file
    predates the fix. This brain would consolidate all night and never write a
    stability verdict, because its code has nowhere to put one."""
    now = time.time()
    _stale_brain_store(tmp_path, now)
    stores = _root(tmp_path, monkeypatch)
    with pytest.raises(gate.LegFailed) as e:
        gate.leg_2_columns_present(stores)
    msg = str(e.value)
    assert "kind" in msg and "retired_ts" in msg
    assert "not deployed" in msg
    # And leg 3 still reports honestly rather than exploding on the old shape.
    assert gate.leg_3_it_ran_recently(stores, now)


def test_the_gate_does_not_repair_what_it_is_measuring(tmp_path, monkeypatch):
    """The gate opens production. If it went through brain.memory.Memory the
    schema and the retrofit would run, the missing columns would appear, and
    leg 2 would pass on the second invocation while prod stayed stale — a gate
    that fixes what it measures measures nothing."""
    now = time.time()
    path = _stale_brain_store(tmp_path, now)
    stores = _root(tmp_path, monkeypatch)
    before = os.stat(path).st_mtime_ns
    for _ in range(2):
        with pytest.raises(gate.LegFailed):
            gate.leg_2_columns_present(stores)
    conn = sqlite3.connect(path)
    cols = {r[1] for r in conn.execute(
        "PRAGMA table_info(profile_facts)").fetchall()}
    conn.close()
    assert "kind" not in cols, "the gate wrote to the store it was measuring"
    assert os.stat(path).st_mtime_ns == before


# ------------------------------------------------------ leg 3: half (a)


def test_a_store_that_never_consolidated_is_red(tmp_path, monkeypatch):
    """Episodes heard, no pass ever finished. Every fact unlabelled, the decay
    half of the ranker inert, and no contradicted fact retirable."""
    owner = tmp_path / "root" / "ownerA"
    owner.mkdir(parents=True)
    m = Memory(path=owner / "memory.db", llm=None)
    m.ingest("I can't have shellfish", ts=time.time() - 60)
    m.db.close()
    stores = _root(tmp_path, monkeypatch)
    assert gate.leg_1_a_store_exists(stores)      # there IS something to read
    with pytest.raises(gate.LegFailed) as e:
        gate.leg_3_it_ran_recently(stores, time.time())
    assert "NEVER" in str(e.value)


def test_a_pass_that_stopped_days_ago_is_red(tmp_path, monkeypatch):
    """The nightly pass is nightly. Three days of silence is a brain that has
    stopped learning, and it looks identical to a healthy one from outside."""
    now = time.time()
    path = _healthy_store(tmp_path, now=now)
    conn = sqlite3.connect(path)
    conn.execute("UPDATE consolidation_state SET value=? WHERE key=?",
                 (str(now - 3 * DAY), "last_run_ts"))
    conn.commit()
    conn.close()
    stores = _root(tmp_path, monkeypatch)
    with pytest.raises(gate.LegFailed) as e:
        gate.leg_3_it_ran_recently(stores, now)
    assert "72 hours ago" in str(e.value)


def test_the_freshness_line_is_where_the_gate_says_it_is(tmp_path, monkeypatch):
    """One missed night plus slack. A pass 47 hours old is a redeploy; 49 is a
    night nobody consolidated."""
    now = time.time()
    path = _healthy_store(tmp_path, now=now)

    def stamp(hours):
        conn = sqlite3.connect(path)
        conn.execute("UPDATE consolidation_state SET value=? WHERE key=?",
                     (str(now - hours * 3600), "last_run_ts"))
        conn.commit()
        conn.close()

    stores = _root(tmp_path, monkeypatch)
    stamp(47)
    assert gate.leg_3_it_ran_recently(stores, now)
    stamp(49)
    with pytest.raises(gate.LegFailed):
        gate.leg_3_it_ran_recently(stores, now)


# ------------------------------------------------------ leg 4: half (b)


def test_a_pass_that_ran_and_wrote_no_verdict_is_red(tmp_path, monkeypatch):
    """THE LEG THAT MATTERS MOST. `last_run_ts` is fresh — half (a) is green —
    and not one fact carries a stability verdict. That is a live worker
    spending a night on a model that cannot answer, and the ranking fix is
    inert in production while the repository is 100% green. Half (a) alone
    would call this healthy, which is why both halves are required."""
    now = time.time()
    _healthy_store(tmp_path, now=now, kind=None)   # the model omitted `kind`
    stores = _root(tmp_path, monkeypatch)
    assert gate.leg_3_it_ran_recently(stores, now), \
        "half (a) must be GREEN here, or this leg is not testing half (b)"
    with pytest.raises(gate.LegFailed) as e:
        gate.leg_4_it_wrote_a_kind(stores)
    assert "not one consolidated fact" in str(e.value)


def test_a_verdict_nobody_modelled_does_not_count(tmp_path, monkeypatch):
    """remember_fact takes `kind` as a parameter, so a label on an interview
    or supervised_mail row proves somebody passed an argument — not that the
    nightly pass, or any model, thought about anything. The leg keys on the
    consolidation source for exactly that reason."""
    now = time.time()
    path = _healthy_store(tmp_path, now=now, kind=None)
    m = Memory(path=path, llm=None)
    m.remember_fact("prefers window seats", importance=3, source="interview",
                    kind="stable", ts=now)
    m.db.close()
    stores = _root(tmp_path, monkeypatch)
    with pytest.raises(gate.LegFailed):
        gate.leg_4_it_wrote_a_kind(stores)


def test_one_live_night_turns_the_last_leg_green(tmp_path, monkeypatch):
    now = time.time()
    _healthy_store(tmp_path, now=now, kind="stable")
    stores = _root(tmp_path, monkeypatch)
    detail = gate.leg_4_it_wrote_a_kind(stores)
    assert "1 consolidated fact(s) carry a model-written kind" in detail


# ---------------------------------------------------- the founder's store


def test_the_founders_legacy_path_is_measured_too(tmp_path, monkeypatch):
    """The founder's account keeps its original ANTICIPY_MEMORY_DB path
    through the multi-owner migration (brain/supervisor.py:87-94). It is the
    store with the longest history and the one most likely to have something
    to consolidate, so a gate that only globbed the state root would measure
    everybody except the person who has been using this longest."""
    now = time.time()
    legacy = tmp_path / "legacy.db"
    m = Memory(path=legacy, llm=FakeLLM(consolidations=[
        {"facts": [{"fact": "allergic to shellfish", "importance": 5,
                    "episode_ids": [1], "kind": "stable"}]}]))
    m.ingest("I can't have shellfish", ts=now - 60)
    m.consolidate(now=now)
    m.db.close()
    monkeypatch.setenv("ANTICIPY_MEMORY_DB", str(legacy))
    monkeypatch.setenv("ANTICIPY_STATE_ROOT", str(tmp_path / "root"))
    stores = gate.find_stores()
    assert stores == [str(legacy)]
    assert gate.leg_4_it_wrote_a_kind(stores)
