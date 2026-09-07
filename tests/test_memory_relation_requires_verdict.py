"""A word score cannot merge identities, corrections, or replayed history."""
import json
import time

import pytest

from brain.memory import Memory
from tests.llm_fakes import FakeLLM


@pytest.mark.parametrize("first,second", [
    ("Amira manages the Vancouver office and approves the weekly supplier invoices for the local manufacturing and distribution teams",
     "Simone manages the Vancouver office and approves the weekly supplier invoices for the local manufacturing and distribution teams"),
    ("Alex introduced Morgan to Casey", "Morgan introduced Alex to Casey"),
    ("My access code is AbCd", "My access code is abcd"),
    ("The two weekly project check-ins are Monday at 6", "The two weekly project check-ins are Monday at 8"),
])
def test_nonidentical_facts_cannot_merge_without_the_models_verdict(first, second):
    model = FakeLLM(relations=["different"])
    memory = Memory(":memory:", llm=model)
    memory.remember_fact(first, source="consolidation")
    memory.remember_fact(second, source="consolidation")
    assert len(model.relation_calls()) == 1
    assert {f["fact"] for f in memory.profile_facts()} == {first, second}


def test_identical_transport_replay_does_not_need_a_model():
    memory = Memory(":memory:", llm=None)
    first = memory.remember_fact("Case-sensitive code AbCd", source="consolidation")
    assert memory.remember_fact("Case-sensitive code AbCd", source="consolidation") == first


def test_unanswered_relation_is_distinct_from_different_and_preserves_both():
    memory = Memory(":memory:", llm=None)
    memory.remember_fact("Morgan introduced Alex to Casey", source="consolidation")
    assert memory._relate_fact("Alex introduced Morgan to Casey") == (None, "unknown")
    memory.remember_fact("Alex introduced Morgan to Casey", source="consolidation")
    assert len(memory.profile_facts()) == 2


def test_replayed_paraphrase_is_judged_with_its_retirement_and_stays_retired():
    now = time.time()
    model = FakeLLM(relations=["same"])
    memory = Memory(":memory:", llm=model)
    rid = memory.remember_fact("Amira is my manager", ts=now - 100)
    memory.db.execute("UPDATE profile_facts SET retired_ts=? WHERE id=?", (now - 50, rid))
    assert memory.remember_fact("My manager is Amira", ts=now - 90) == rid
    assert memory.profile_facts() == []
    payload = json.loads(model.relation_calls()[0])
    assert payload["stored_notes"][0]["retired_days_ago"] is not None


def test_unanswered_historical_comparison_cannot_resurrect_retired_knowledge():
    now = time.time()
    memory = Memory(":memory:")
    rid = memory.remember_fact("Amira is my manager", ts=now - 100)
    memory.db.execute("UPDATE profile_facts SET retired_ts=? WHERE id=?", (now - 50, rid))
    with pytest.raises(RuntimeError, match="historical comparison unanswered"):
        memory.remember_fact("My manager is Amira", ts=now - 90)
    assert memory.profile_facts() == []


def test_memory_uses_stronger_judgment_and_current_identity(monkeypatch):
    from types import SimpleNamespace
    import brain.anticipy_core as core
    primary = SimpleNamespace(owner_name="New name", owner_email="new@example.invalid", owner_zone="UTC")
    class Strong(FakeLLM):
        def chat(self, system, user, **kwargs):
            assert kwargs["aux"] is False
            return super().chat(system, user, **kwargs)
    strong = Strong(relations=["different"])
    monkeypatch.setattr(core, "Brain", lambda **kwargs: SimpleNamespace(strong=strong))
    memory = Memory(":memory:", llm=primary)
    core.Anticipy(memory=memory, llm=primary)
    memory.remember_fact("Alex introduced Morgan to Casey")
    memory.remember_fact("Morgan introduced Alex to Casey")
    assert len(strong.relation_calls()) == 1
    assert strong.owner_name == "New name"
    assert strong.owner_email == "new@example.invalid"
