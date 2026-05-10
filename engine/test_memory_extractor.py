"""Unit tests for app.proactive.memory_extractor."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from app.memory import InProcessMemoryBackend, MemoryStore
from app.proactive.memory_extractor import MemoryExtractor


def _llm(response: Any):
    async def call(system: str, user: str) -> str:
        if isinstance(response, Exception):
            raise response
        if isinstance(response, dict):
            return json.dumps(response)
        return response
    return call


@pytest.fixture
def store():
    return MemoryStore(backend=InProcessMemoryBackend())


@pytest.mark.asyncio
async def test_extracts_person(store):
    e = MemoryExtractor(
        llm_call=_llm({
            "memories": [
                {"kind": "person", "key": "Sarah",
                 "value": {"name": "Sarah", "relation": "friend"},
                 "importance": 4}
            ]
        }),
        store=store,
    )
    out = await e.extract_and_write("u1", "yeah I'm grabbing dinner with Sarah Friday")
    assert len(out) == 1
    assert out[0].kind == "person"
    assert out[0].importance == 4
    found = await store.recall_person("u1", "Sarah")
    assert found is not None
    assert found.value["relation"] == "friend"


@pytest.mark.asyncio
async def test_extracts_multiple_kinds(store):
    e = MemoryExtractor(
        llm_call=_llm({
            "memories": [
                {"kind": "person", "key": "Sarah",
                 "value": {"name": "Sarah"}, "importance": 4},
                {"kind": "preference", "key": "preferred_cuisine",
                 "value": {"value": "italian"}, "importance": 3},
                {"kind": "commitment", "key": "dinner:sarah",
                 "value": {"what": "dinner", "with_whom": "Sarah", "when": "Friday"},
                 "importance": 5},
            ]
        }),
        store=store,
    )
    out = await e.extract_and_write("u1", "...")
    assert len(out) == 3
    kinds = {m.kind for m in out}
    assert kinds == {"person", "preference", "commitment"}


@pytest.mark.asyncio
async def test_no_memories_on_chitchat(store):
    e = MemoryExtractor(llm_call=_llm({"memories": []}), store=store)
    out = await e.extract_and_write("u1", "yeah it's a nice day out")
    assert out == []


@pytest.mark.asyncio
async def test_handles_empty_text(store):
    e = MemoryExtractor(llm_call=_llm({"memories": [{"kind": "person", "key": "x", "value": {}}]}), store=store)
    out = await e.extract_and_write("u1", "")
    assert out == []
    out2 = await e.extract_and_write("u1", "   ")
    assert out2 == []


@pytest.mark.asyncio
async def test_handles_llm_timeout(store):
    async def slow_llm(s, u):
        await asyncio.sleep(10.0)
        return ""
    e = MemoryExtractor(llm_call=slow_llm, store=store, timeout_s=0.1)
    out = await e.extract_and_write("u1", "blah")
    assert out == []


@pytest.mark.asyncio
async def test_handles_llm_error(store):
    e = MemoryExtractor(llm_call=_llm(RuntimeError("provider down")), store=store)
    out = await e.extract_and_write("u1", "blah")
    assert out == []


@pytest.mark.asyncio
async def test_handles_empty_llm_response(store):
    e = MemoryExtractor(llm_call=_llm(""), store=store)
    out = await e.extract_and_write("u1", "blah")
    assert out == []


@pytest.mark.asyncio
async def test_handles_malformed_json(store):
    e = MemoryExtractor(llm_call=_llm("not valid {"), store=store)
    out = await e.extract_and_write("u1", "blah")
    assert out == []


@pytest.mark.asyncio
async def test_handles_non_dict_response(store):
    e = MemoryExtractor(llm_call=_llm("[1,2,3]"), store=store)
    out = await e.extract_and_write("u1", "blah")
    assert out == []


@pytest.mark.asyncio
async def test_skips_invalid_kind(store):
    e = MemoryExtractor(
        llm_call=_llm({
            "memories": [
                {"kind": "bogus_category", "key": "x", "value": {"a": 1}},
                {"kind": "person", "key": "Alice", "value": {"name": "Alice"}, "importance": 3},
            ]
        }),
        store=store,
    )
    out = await e.extract_and_write("u1", "blah")
    assert len(out) == 1
    assert out[0].kind == "person"


@pytest.mark.asyncio
async def test_skips_empty_key(store):
    e = MemoryExtractor(
        llm_call=_llm({
            "memories": [
                {"kind": "person", "key": "", "value": {"name": "x"}},
                {"kind": "person", "key": "  ", "value": {"name": "y"}},
            ]
        }),
        store=store,
    )
    out = await e.extract_and_write("u1", "blah")
    assert out == []


@pytest.mark.asyncio
async def test_skips_non_dict_value(store):
    e = MemoryExtractor(
        llm_call=_llm({
            "memories": [
                {"kind": "person", "key": "x", "value": "not a dict"},
                {"kind": "person", "key": "Alice", "value": {"name": "Alice"}},
            ]
        }),
        store=store,
    )
    out = await e.extract_and_write("u1", "blah")
    assert len(out) == 1


@pytest.mark.asyncio
async def test_clamps_importance_above_five(store):
    e = MemoryExtractor(
        llm_call=_llm({
            "memories": [{"kind": "person", "key": "x", "value": {"name": "x"}, "importance": 99}]
        }),
        store=store,
    )
    out = await e.extract_and_write("u1", "x")
    assert out[0].importance == 5


@pytest.mark.asyncio
async def test_clamps_importance_below_one(store):
    e = MemoryExtractor(
        llm_call=_llm({
            "memories": [{"kind": "person", "key": "x", "value": {"name": "x"}, "importance": 0}]
        }),
        store=store,
    )
    out = await e.extract_and_write("u1", "x")
    assert out[0].importance == 1


@pytest.mark.asyncio
async def test_default_importance_when_missing(store):
    e = MemoryExtractor(
        llm_call=_llm({
            "memories": [{"kind": "person", "key": "x", "value": {"name": "x"}}]
        }),
        store=store,
    )
    out = await e.extract_and_write("u1", "x")
    assert out[0].importance == 3


@pytest.mark.asyncio
async def test_records_chunk_id_in_source(store):
    e = MemoryExtractor(
        llm_call=_llm({
            "memories": [{"kind": "person", "key": "x", "value": {"name": "x"}, "importance": 3}]
        }),
        store=store,
    )
    out = await e.extract_and_write("u1", "x", chunk_id=42)
    assert out[0].source_chunks == [42]


@pytest.mark.asyncio
async def test_user_isolation(store):
    e = MemoryExtractor(
        llm_call=_llm({
            "memories": [{"kind": "person", "key": "Sarah", "value": {"name": "Sarah"}, "importance": 3}]
        }),
        store=store,
    )
    await e.extract_and_write("alice_id", "...")
    found_alice = await store.recall_person("alice_id", "Sarah")
    found_bob = await store.recall_person("bob_id", "Sarah")
    assert found_alice is not None
    assert found_bob is None


@pytest.mark.asyncio
async def test_subsequent_extracts_merge_value(store):
    """Two chunks both mention Sarah; second adds detail to first."""
    e1 = MemoryExtractor(
        llm_call=_llm({
            "memories": [{"kind": "person", "key": "Sarah",
                          "value": {"name": "Sarah", "relation": "friend"},
                          "importance": 4}]
        }),
        store=store,
    )
    e2 = MemoryExtractor(
        llm_call=_llm({
            "memories": [{"kind": "person", "key": "Sarah",
                          "value": {"name": "Sarah", "notes": "loves italian"},
                          "importance": 3}]
        }),
        store=store,
    )
    await e1.extract_and_write("u1", "chunk 1")
    await e2.extract_and_write("u1", "chunk 2")
    found = await store.recall_person("u1", "Sarah")
    assert found.value["relation"] == "friend"
    assert found.value["notes"] == "loves italian"
    # Importance is max of the two
    assert found.importance == 4
