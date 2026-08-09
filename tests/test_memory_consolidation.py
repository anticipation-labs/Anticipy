"""Memory consolidation + profile layer (roadmap §1, brief 05).

Everything here runs offline with a scripted LLM (tests/llm_fakes.py):
extraction into profile rows with provenance, LLM-judged dedup of
restatements, salience-aware recall, the llm=None no-op, the seed API, and
the additive migration that must leave an old memory file working.
"""
import sqlite3
import time

from brain.memory import Memory
from llm_fakes import FakeLLM


# ------------------------------------------------- extraction + provenance

def test_consolidation_extracts_profile_rows_with_provenance():
    t0 = time.time() - 3600
    fake = FakeLLM(consolidations=[
        {"facts": [{"fact": "partner is Sarah", "importance": 4,
                    "episode_ids": [1, 2]}]},
    ])
    m = Memory(llm=fake)
    m.ingest("Sarah and I are looking at rings.", ts=t0)
    m.ingest("dinner with Sarah tonight, like always", ts=t0 + 60)

    out = m.consolidate(now=t0 + 3600)
    assert out["ran"] and out["new"] == 1 and out["merged"] == 0
    assert out["episodes"] == 2 and out["remaining"] == 0

    facts = m.profile_facts()
    assert len(facts) == 1
    f = facts[0]
    assert f["fact"] == "partner is Sarah"
    assert f["importance"] == 4
    assert f["provenance"] == [1, 2], "provenance must be the episode ids"
    assert f["source"] == "consolidation"
    assert f["first_seen_ts"] == f["last_seen_ts"] == t0 + 60

    # The batch listing carried the episode ids and the raw lines.
    listing = fake.consolidation_calls()[0]
    assert "[1]" in listing and "rings" in listing


def test_consolidation_is_incremental():
    t0 = time.time() - 3600
    fake = FakeLLM(consolidations=[
        {"facts": []},
        {"facts": []},
    ])
    m = Memory(llm=fake)
    m.ingest("morning mumble", ts=t0)
    assert m.consolidate(now=t0 + 10)["episodes"] == 1

    # Nothing new: the cursor advanced, so the pass reads zero episodes and
    # never even asks the model.
    out = m.consolidate(now=t0 + 20)
    assert out["ran"] and out["episodes"] == 0
    assert len(fake.consolidation_calls()) == 1

    # A new episode after the cursor is the only thing the next pass sees.
    m.ingest("an afternoon line", ts=t0 + 30)
    m.consolidate(now=t0 + 40)
    assert len(fake.consolidation_calls()) == 2
    assert "afternoon" in fake.consolidation_calls()[1]
    assert "mumble" not in fake.consolidation_calls()[1]


def test_facts_without_real_provenance_are_dropped():
    t0 = time.time() - 3600
    fake = FakeLLM(consolidations=[
        {"facts": [{"fact": "invented thing", "importance": 5,
                    "episode_ids": [99]},           # id not in the batch
                   {"fact": "unmoored thing", "importance": 5}]},
    ])
    m = Memory(llm=fake)
    m.ingest("one real line", ts=t0)
    out = m.consolidate(now=t0 + 10)
    assert out["ran"] and out["new"] == 0
    assert m.profile_facts() == []


# --------------------------------------------------------------- dedup

def test_dedup_merges_restatements():
    t0 = time.time() - 3600
    fake = FakeLLM(
        consolidations=[
            {"facts": [{"fact": "partner is Sarah", "importance": 4,
                        "episode_ids": [1]}]},
            {"facts": [{"fact": "his partner's name is Sarah",
                        "importance": 3, "episode_ids": [2]}]},
        ],
        same_verdicts=[True],
    )
    m = Memory(llm=fake)
    m.ingest("Sarah and I are looking at rings.", ts=t0)
    m.consolidate(now=t0 + 10)
    m.ingest("my partner Sarah says hi", ts=t0 + 100)
    out = m.consolidate(now=t0 + 200)

    assert out["merged"] == 1 and out["new"] == 0
    facts = m.profile_facts()
    assert len(facts) == 1, "a restatement must merge, not duplicate"
    f = facts[0]
    assert f["fact"] == "partner is Sarah"      # original wording kept
    assert f["provenance"] == [1, 2]            # evidence accumulates
    assert f["last_seen_ts"] == t0 + 100
    assert f["confidence"] > 0.6                # re-observation raises it
    assert f["importance"] == 4                 # max of the two wins


def test_judge_says_different_keeps_both():
    t0 = time.time() - 3600
    fake = FakeLLM(
        consolidations=[
            {"facts": [{"fact": "prefers 7pm dinners", "importance": 3,
                        "episode_ids": [1]}]},
            {"facts": [{"fact": "prefers Italian dinners", "importance": 3,
                        "episode_ids": [2]}]},
        ],
        same_verdicts=[False],
    )
    m = Memory(llm=fake)
    m.ingest("seven again for dinner, perfect", ts=t0)
    m.consolidate(now=t0 + 10)
    m.ingest("Italian for dinner, obviously", ts=t0 + 100)
    m.consolidate(now=t0 + 200)
    assert len(m.profile_facts()) == 2


# ------------------------------------------------------ salience recall

def test_salience_ranking_beats_raw_term_hits():
    m = Memory()
    now = time.time()
    for i in range(30):
        m.ingest(f"uh grocery list dinner stuff number {i}", ts=now - 600 + i)
    m.remember_fact("prefers 7pm dinners", importance=5, ts=now - 5 * 86400)

    out = m.recall("dinner")
    assert out, "recall found nothing"
    assert out[0]["src_type"] == "profile", \
        "the profile fact must outrank thirty raw term-hits"
    assert "7pm dinners" in out[0]["fact"]
    assert any(f["src_type"] == "episode" for f in out[1:]), \
        "raw episode search still fills the rest of the window"


def test_importance_outranks_recency_within_profile():
    m = Memory()
    now = time.time()
    m.remember_fact("loves the farmers market on Saturdays",
                    importance=5, ts=now - 10 * 86400)
    m.remember_fact("stopped by the market for milk",
                    importance=1, ts=now)
    out = m.recall("market")
    profile = [f for f in out if f["src_type"] == "profile"]
    assert len(profile) == 2
    assert "farmers market" in profile[0]["fact"], \
        "importance x recency: an old core fact beats fresh color"


def test_recall_without_profile_is_unchanged():
    m = Memory()
    t0 = time.time() - 3600
    m.ingest("I'll send Sarah the pitch deck tomorrow.", ts=t0)
    out = m.recall("what did I promise Sarah?")
    assert out and all(f["src_type"] != "profile" for f in out)


# ------------------------------------------------------------ llm=None

def test_llm_none_consolidation_is_noop():
    m = Memory()
    m.ingest("I'll send Sarah the pitch deck.")
    out = m.consolidate()
    assert out["ran"] is False and out["reason"] == "no llm"
    assert out["new"] == 0 and out["merged"] == 0
    assert m.profile_facts() == []
    assert m.last_consolidation_ts() == 0.0
    assert m._state_get("last_episode_id", "") == "", "cursor untouched"


# ----------------------------------------------------------- crash-safety

def test_crash_mid_pass_loses_nothing():
    t0 = time.time() - 3600
    fake = FakeLLM(consolidations=[
        RuntimeError("model fell over"),
        {"facts": [{"fact": "building Anticipy", "importance": 3,
                    "episode_ids": [1]}]},
    ])
    m = Memory(llm=fake)
    m.ingest("Anticipy all day again", ts=t0)

    out = m.consolidate(now=t0 + 10)
    assert out["ran"] is False
    assert out["remaining"] == 1, "the episode is still waiting"
    assert m.profile_facts() == []
    assert m.last_consolidation_ts() == 0.0

    out2 = m.consolidate(now=t0 + 20)
    assert out2["ran"] and out2["new"] == 1 and out2["episodes"] == 1


# ------------------------------------------------------------- seed API

def test_remember_fact_seeds_and_never_dupes():
    m = Memory()
    fid = m.remember_fact("never touch the joint account",
                          importance=5, source="interview")
    fid2 = m.remember_fact("never touch the joint account",
                           importance=5, source="interview")
    assert fid == fid2, "re-seeding the same fact must merge, not dupe"
    facts = m.profile_facts()
    assert len(facts) == 1
    assert facts[0]["source"] == "interview"
    assert facts[0]["importance"] == 5
    assert facts[0]["confidence"] >= 0.9


def test_remember_fact_clamps_importance():
    m = Memory()
    m.remember_fact("drinks his coffee black", importance=9)
    assert m.profile_facts()[0]["importance"] == 5


# ------------------------------------------------------------- briefing

def test_briefing_facts_prefer_profile():
    m = Memory()
    start = time.time() - 10
    m.ingest("I'll book the Italian place for Saturday.")
    m.remember_fact("partner is Sarah", importance=5)
    facts = m.briefing_facts(start)
    assert list(facts)[0] == "profile", "the profile leads the briefing"
    assert facts["profile"][0]["fact"] == "partner is Sarah"
    # The old shape is intact for every existing consumer.
    assert len(facts["heard"]) == 1
    assert len(facts["open_loops"]) == 1


# ------------------------------------------------------------- migration

_PRE_PROFILE_SCHEMA = """
CREATE TABLE episodes (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    text TEXT NOT NULL
);
CREATE TABLE nodes (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    attrs TEXT NOT NULL DEFAULT '{}',
    status TEXT,
    created_ts REAL NOT NULL,
    last_seen_ts REAL NOT NULL,
    UNIQUE(type, name)
);
CREATE TABLE edges (
    id INTEGER PRIMARY KEY,
    src INTEGER NOT NULL REFERENCES nodes(id),
    rel TEXT NOT NULL,
    dst INTEGER NOT NULL REFERENCES nodes(id),
    episode_id INTEGER REFERENCES episodes(id),
    ts REAL NOT NULL
);
"""


def test_existing_memory_file_opens_unchanged(tmp_path):
    db = tmp_path / "mem.db"
    conn = sqlite3.connect(db)
    conn.executescript(_PRE_PROFILE_SCHEMA)
    conn.execute("INSERT INTO episodes(ts, text) VALUES (1.0, 'an old line')")
    conn.commit()
    conn.close()

    m = Memory(path=db)
    assert m.db.execute("SELECT COUNT(*) FROM episodes").fetchone()[0] == 1
    assert m.profile_facts() == []
    m.remember_fact("prefers 7pm dinners", importance=3)
    assert len(m.profile_facts()) == 1
