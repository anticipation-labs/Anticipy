"""Offline reproductions of the September 8 memory reliability audit."""
import json
import sqlite3

import pytest

from brain.memory import Memory, OVERHEARD
from llm_fakes import FakeLLM


@pytest.mark.parametrize("fillers", [299, 300, 301, 1000])
@pytest.mark.parametrize("fts", [True, False])
def test_recall_ranks_matching_history_before_limiting(fillers, fts):
    memory = Memory()
    memory.ingest("Project lighthouse gate code is 4417", ts=1)
    for index in range(fillers):
        memory.ingest(f"Project update number {index}", ts=2 + index)
    if not fts:
        memory.db.execute("DROP TABLE episodes_fts")

    facts = memory.recall("project lighthouse gate code")

    assert any("4417" in row["fact"] for row in facts)


@pytest.mark.parametrize("retired", [False, True])
def test_recall_window_is_not_filled_by_duplicates_or_retired_sources(retired):
    memory = Memory()
    memory.ingest("Lighthouse gate code is 4417", ts=1)
    for index in range(301):
        text = f"Project lighthouse gate code changed {index}" if retired else "Project lighthouse gate code changed"
        memory.ingest(text, ts=index + 2)
    if retired:
        old = memory._insert_fact("An obsolete fact", 4, 0.6, "consolidation", 400,
                                  list(range(2, 303)))
        memory.db.execute("UPDATE profile_facts SET retired_ts=401 WHERE id=?", (old,))
        memory.db.commit()

    assert any("4417" in row["fact"] for row in memory.recall("project lighthouse gate code"))


@pytest.mark.parametrize("count", [1000, 2000])
@pytest.mark.parametrize("fts", [True, False])
def test_long_recall_query_does_not_exceed_sqlite_expression_depth(count, fts):
    memory = Memory()
    memory.ingest("Unicorn sentinel code is 4417", ts=1)
    if not fts:
        memory.db.execute("DROP TABLE episodes_fts")
    query = " ".join([*(f"term{i}" for i in range(count)), "unicorn", "sentinel"])

    assert any("4417" in row["fact"] for row in memory.recall(query))


def _candidate(text, episode):
    return {"fact": text, "importance": 4, "episode_ids": [episode]}


def _pending_memory(path=":memory:"):
    memory = Memory(path)
    memory.forget_fact("The private project is called Northstar")
    memory.ingest("I work on Northstar", ts=1)
    memory.ingest("My preferred lunch is noodles", ts=2)
    memory.llm = FakeLLM(consolidations=[{"facts": [
        _candidate("I work on Northstar", 1),
        _candidate("My preferred lunch is noodles", 2),
    ]}], vetoes=["unknown", "outside"])
    return memory


def test_unanswered_veto_defers_only_its_fact_and_advances_the_batch():
    memory = _pending_memory()

    result = memory.consolidate(now=3)

    assert result["ran"] and result["new"] == 1
    assert result["episodes"] == 2 and result["remaining"] == 0
    assert result["deferred"] == 1
    assert memory._state_get("last_episode_id") == "2"
    assert [r["fact"] for r in memory.profile_facts()] == ["My preferred lunch is noodles"]


@pytest.mark.parametrize("verdict,learned", [("outside", True), ("covered", False)])
def test_deferred_fact_survives_restart_and_requires_a_verdict(tmp_path, verdict, learned):
    path = tmp_path / "memory.db"
    memory = _pending_memory(path)
    memory.consolidate(now=3)
    memory.db.close()
    model = FakeLLM(vetoes=[verdict])
    memory = Memory(path, llm=model)

    result = memory.consolidate(now=4)

    assert result["episodes"] == 0
    assert result["deferred"] == 0
    assert result["new"] == int(learned)
    assert bool([r for r in memory.profile_facts() if r["fact"] == "I work on Northstar"]) is learned
    assert model.consolidation_calls() == [], "retry the saved fact, not the already processed day"
    lunch = next(r for r in memory.profile_facts() if "noodles" in r["fact"])
    assert lunch["confidence"] == 0.6, "a retry must not reinforce already committed facts"


def test_a_still_unanswered_veto_does_not_block_next_days_facts():
    memory = _pending_memory()
    memory.consolidate(now=3)
    memory.ingest("My bike is blue", ts=4)
    memory.llm = FakeLLM(consolidations=[{"facts": [_candidate("My bike is blue", 3)]}],
                         vetoes=["unknown", "outside"])

    result = memory.consolidate(now=5)

    assert result["new"] == 1 and result["deferred"] == 1
    assert {r["fact"] for r in memory.profile_facts()} == {
        "My preferred lunch is noodles", "My bike is blue"}


def test_multiple_batches_in_one_nightly_pass_do_not_repeat_the_same_unknown_judge():
    memory = _pending_memory()
    assert memory.consolidate(now=3)["deferred"] == 1
    memory.ingest("My bike is blue", ts=4)
    model = FakeLLM(consolidations=[{"facts": [_candidate("My bike is blue", 3)]}],
                    vetoes=["outside"])
    memory.llm = model

    result = memory.consolidate(now=3)

    assert result["new"] == 1 and result["deferred"] == 1
    veto_calls = [json.loads(user) for system, user in model.calls if "stored veto_note" in system]
    assert [call["candidate_note"] for call in veto_calls] == ["My bike is blue"]
    assert memory.consolidate(now=3)["deferred"] == 1, "an unattempted pending row is still pending"


def test_unexpected_database_failure_still_rolls_back_the_whole_pass(monkeypatch):
    memory = _pending_memory()
    original = memory._insert_fact

    def failing_insert(text, *args, **kwargs):
        if text == "My preferred lunch is noodles":
            raise sqlite3.OperationalError("disk full")
        return original(text, *args, **kwargs)

    monkeypatch.setattr(memory, "_insert_fact", failing_insert)
    with pytest.raises(sqlite3.OperationalError, match="disk full"):
        memory.consolidate(now=3)

    assert memory.profile_facts() == []
    assert memory._state_get("last_episode_id", "0") == "0"
    assert memory.db.execute("SELECT COUNT(*) FROM deferred_consolidation").fetchone()[0] == 0


def test_deferred_supersession_preserves_the_old_fact_until_permission_is_answered():
    memory = Memory()
    old = memory.remember_fact("My manager is Sarah", ts=0.1)
    memory.forget_fact("Forget the private project")
    memory.ingest("My manager is Tom", ts=1)
    memory.ingest("My bike is blue", ts=2)
    memory.llm = FakeLLM(consolidations=[{"facts": [
        _candidate("My manager is Tom", 1), _candidate("My bike is blue", 2)]}],
        relations=["replaces", "different"], vetoes=["unknown", "outside"])

    result = memory.consolidate(now=3)

    assert result["retired"] == 0 and result["new"] == 1 and result["deferred"] == 1
    assert not memory._is_retired(old)
    memory.llm = FakeLLM(relations=["replaces"], vetoes=["outside"])
    result = memory.consolidate(now=4)
    assert result["new"] == 1 and result["retired"] == 1 and result["deferred"] == 0
    assert memory._is_retired(old)


def test_deferred_guest_fact_keeps_original_provenance_and_timestamp():
    memory = Memory()
    memory.forget_fact("Forget my private project")
    memory.ingest("My manager is Tom", ts=1, speaker="other")
    candidate = _candidate("My manager is Tom", 1)
    candidate["kind"] = "situation"
    memory.llm = FakeLLM(consolidations=[{"facts": [candidate]}], vetoes=["unknown"])
    assert memory.consolidate(now=2)["deferred"] == 1
    memory.llm = FakeLLM(vetoes=["outside"])

    memory.consolidate(now=1000)

    fact = memory.profile_facts()[0]
    assert fact["source"] == OVERHEARD
    assert fact["first_seen_ts"] == fact["last_seen_ts"] == 1
    assert fact["provenance"] == [1] and fact["kind"] == "situation"


def test_unanswered_historical_comparison_is_also_a_retryable_fact():
    memory = Memory()
    old = memory.remember_fact("My manager is Sarah", ts=1)
    memory.db.execute("UPDATE profile_facts SET retired_ts=2 WHERE id=?", (old,))
    memory.db.commit()
    memory.ingest("Sarah manages my team", ts=1.5)
    memory.ingest("My bike is blue", ts=3)
    memory.llm = FakeLLM(consolidations=[{"facts": [
        _candidate("Sarah manages my team", 1), _candidate("My bike is blue", 2)]}],
        relations=["unknown"])

    result = memory.consolidate(now=4)

    assert result["deferred"] == 1 and result["new"] == 1
    assert memory._is_retired(old), "an unanswered old comparison cannot resurrect a retired fact"
    assert [row["fact"] for row in memory.profile_facts()] == ["My bike is blue"]
