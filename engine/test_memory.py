"""Unit tests for app.memory — the cross-session "second brain"."""

from __future__ import annotations

import asyncio

import pytest

from app.memory import (
    InProcessMemoryBackend,
    Memory,
    MemoryStore,
    SupabaseMemoryBackend,
    _parse_iso_ts,
    _row_to_memory,
)


# ─── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def store():
    return MemoryStore(backend=InProcessMemoryBackend())


# ─── remember/recall persons ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_remember_and_recall_person(store):
    await store.remember_person(
        user_id="u1", name="Sarah", relation="friend", notes="loves carbone",
    )
    m = await store.recall_person("u1", "Sarah")
    assert m is not None
    assert m.value["name"] == "Sarah"
    assert m.value["relation"] == "friend"
    assert m.value["notes"] == "loves carbone"


@pytest.mark.asyncio
async def test_recall_person_case_insensitive(store):
    await store.remember_person("u1", "Sarah", relation="friend")
    m_lower = await store.recall_person("u1", "sarah")
    m_upper = await store.recall_person("u1", "SARAH")
    assert m_lower is not None
    assert m_upper is not None
    assert m_lower.id == m_upper.id


@pytest.mark.asyncio
async def test_user_isolation(store):
    await store.remember_person("u1", "Sarah")
    assert await store.recall_person("u1", "Sarah") is not None
    assert await store.recall_person("u2", "Sarah") is None


@pytest.mark.asyncio
async def test_upsert_merges_value_dict(store):
    await store.remember_person("u1", "Sarah", relation="friend")
    await store.remember_person("u1", "Sarah", notes="loves italian")
    m = await store.recall_person("u1", "Sarah")
    assert m.value["relation"] == "friend"
    assert m.value["notes"] == "loves italian"


@pytest.mark.asyncio
async def test_upsert_keeps_max_importance(store):
    backend = store.backend
    await backend.upsert(Memory(id="", user_id="u", kind="x", key="k",
                                  value={}, importance=3))
    await backend.upsert(Memory(id="", user_id="u", kind="x", key="k",
                                  value={}, importance=5))
    m = await backend.get_by_key("u", "x", "k")
    assert m.importance == 5
    # Going down doesn't lower it:
    await backend.upsert(Memory(id="", user_id="u", kind="x", key="k",
                                  value={}, importance=1))
    m = await backend.get_by_key("u", "x", "k")
    assert m.importance == 5


@pytest.mark.asyncio
async def test_upsert_preserves_id_across_updates(store):
    m1 = await store.remember_person("u1", "Sarah")
    m2 = await store.remember_person("u1", "Sarah", notes="updated")
    assert m1.id == m2.id


@pytest.mark.asyncio
async def test_source_chunks_dedup_on_merge(store):
    backend = store.backend
    await backend.upsert(Memory(id="", user_id="u", kind="x", key="k",
                                  value={}, source_chunks=[1, 2, 3]))
    await backend.upsert(Memory(id="", user_id="u", kind="x", key="k",
                                  value={}, source_chunks=[3, 4, 5]))
    m = await backend.get_by_key("u", "x", "k")
    assert sorted(m.source_chunks) == [1, 2, 3, 4, 5]


# ─── named-kind helpers ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_remember_preference(store):
    await store.remember_preference("u1", "preferred_cuisine", "italian")
    m = await store.recall_preference("u1", "preferred_cuisine")
    assert m is not None
    assert m.value["value"] == "italian"


@pytest.mark.asyncio
async def test_remember_commitment_keys_on_what_and_with_whom(store):
    await store.remember_commitment(
        user_id="u1", what="dinner", with_whom="Sarah", when="Friday 7pm",
    )
    items = await store.recall_kind("u1", "commitment")
    assert len(items) == 1
    assert items[0].value["with_whom"] == "Sarah"
    # Different person → different key → different memory
    await store.remember_commitment(user_id="u1", what="dinner", with_whom="Mark")
    items = await store.recall_kind("u1", "commitment")
    assert len(items) == 2


@pytest.mark.asyncio
async def test_remember_place(store):
    await store.remember_place("u1", "home", kind_of_place="residence",
                                address="123 Main")
    m = await store.recall_place("u1", "Home")  # case-insensitive lookup
    assert m is not None
    assert m.value["address"] == "123 Main"


@pytest.mark.asyncio
async def test_remember_project(store):
    await store.remember_project("u1", "Kitchen Renovation", status="active")
    items = await store.recall_kind("u1", "project")
    assert len(items) == 1
    assert items[0].value["name"] == "Kitchen Renovation"


@pytest.mark.asyncio
async def test_remember_fact(store):
    await store.remember_fact("u1", "favorite_color", "blue")
    items = await store.recall_kind("u1", "fact")
    assert len(items) == 1


# ─── recall_recent ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recall_recent_orders_by_updated_at(store):
    await store.remember_person("u1", "Alice")
    await asyncio.sleep(0.005)
    await store.remember_person("u1", "Bob")
    await asyncio.sleep(0.005)
    await store.remember_person("u1", "Alice", notes="updated")  # bumps Alice
    recent = await store.recall_recent("u1", k=2)
    assert recent[0].key == "alice"


@pytest.mark.asyncio
async def test_recall_recent_respects_k(store):
    for name in ["A", "B", "C", "D", "E"]:
        await store.remember_person("u1", name)
    out = await store.recall_recent("u1", k=3)
    assert len(out) == 3


@pytest.mark.asyncio
async def test_recall_recent_isolated_by_user(store):
    await store.remember_person("u1", "Alice")
    await store.remember_person("u2", "Bob")
    out = await store.recall_recent("u1", k=10)
    assert {m.value["name"] for m in out} == {"Alice"}


# ─── recall_kind ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recall_kind_filters_by_kind(store):
    await store.remember_person("u1", "Alice")
    await store.remember_preference("u1", "color", "blue")
    persons = await store.recall_kind("u1", "person")
    prefs = await store.recall_kind("u1", "preference")
    assert {m.value.get("name") for m in persons} == {"Alice"}
    assert {m.value.get("value") for m in prefs} == {"blue"}


# ─── search ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_naive_token_overlap(store):
    await store.remember_person("u1", "Sarah", notes="loves italian food")
    await store.remember_person("u1", "Bob", notes="loves sushi")
    out = await store.search("u1", "italian", k=5)
    assert len(out) == 1
    assert out[0].key == "sarah"


@pytest.mark.asyncio
async def test_search_returns_empty_on_empty_query(store):
    await store.remember_person("u1", "Sarah")
    out = await store.search("u1", "", k=5)
    assert out == []


@pytest.mark.asyncio
async def test_search_isolated_by_user(store):
    await store.remember_person("u1", "Sarah", notes="italian food")
    await store.remember_person("u2", "Sarah", notes="italian food")
    out = await store.search("u1", "italian", k=5)
    assert len(out) == 1
    assert out[0].user_id == "u1"


@pytest.mark.asyncio
async def test_search_ranks_by_score_then_importance(store):
    backend = store.backend
    await backend.upsert(Memory(id="a", user_id="u", kind="x", key="alice",
                                  value={"notes": "italian food"}, importance=2))
    await backend.upsert(Memory(id="b", user_id="u", kind="x", key="bob",
                                  value={"notes": "italian food"}, importance=5))
    out = await store.search("u", "italian", k=5)
    # Both match equally; importance breaks the tie
    assert out[0].id == "b"


# ─── delete ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_removes_entry(store):
    await store.remember_person("u1", "Sarah")
    deleted = await store.backend.delete("u1", "person", "sarah")
    assert deleted is True
    assert await store.recall_person("u1", "Sarah") is None


@pytest.mark.asyncio
async def test_delete_returns_false_when_missing(store):
    deleted = await store.backend.delete("u1", "person", "nobody")
    assert deleted is False


# ─── Supabase backend with stub ────────────────────────────────────────


class _StubSupabase:
    """Minimal stub of the supabase_client module surface used by SupabaseMemoryBackend."""

    def __init__(self) -> None:
        self.rows: list[dict] = []

    async def upsert_row(self, table: str, data: dict):
        # Mimic upsert by primary-key (user_id, kind, key)
        for i, existing in enumerate(self.rows):
            if (
                existing.get("user_id") == data.get("user_id")
                and existing.get("kind") == data.get("kind")
                and existing.get("key") == data.get("key")
            ):
                self.rows[i] = {**existing, **data}
                return self.rows[i]
        self.rows.append(dict(data))
        return self.rows[-1]

    async def select_rows(self, table: str, filters=None, columns="*", limit=100):
        out = []
        for row in self.rows:
            if filters and not all(row.get(k) == v for k, v in filters.items()):
                continue
            out.append(row)
        return out[:limit]


@pytest.mark.asyncio
async def test_supabase_backend_upsert_writes_row():
    stub = _StubSupabase()
    backend = SupabaseMemoryBackend(supabase_client_module=stub)
    mem = Memory(id="", user_id="u1", kind="person", key="sarah",
                  value={"name": "Sarah"})
    out = await backend.upsert(mem)
    assert len(stub.rows) == 1
    assert out.user_id == "u1"
    assert out.value.get("name") == "Sarah"


@pytest.mark.asyncio
async def test_supabase_backend_get_by_key():
    stub = _StubSupabase()
    backend = SupabaseMemoryBackend(supabase_client_module=stub)
    await backend.upsert(Memory(id="", user_id="u1", kind="person", key="sarah",
                                  value={"name": "Sarah"}))
    found = await backend.get_by_key("u1", "person", "sarah")
    assert found is not None
    assert found.value["name"] == "Sarah"
    missing = await backend.get_by_key("u1", "person", "bob")
    assert missing is None


@pytest.mark.asyncio
async def test_supabase_backend_returns_memory_object_on_storage_failure():
    """If upsert returns None (transient failure), we still get back a coherent Memory."""

    class _FailingStub:
        async def upsert_row(self, *_a, **_kw):
            return None
        async def select_rows(self, *_a, **_kw):
            return []

    backend = SupabaseMemoryBackend(supabase_client_module=_FailingStub())
    mem = Memory(id="", user_id="u1", kind="person", key="sarah", value={})
    out = await backend.upsert(mem)
    assert out.user_id == "u1"
    assert out.kind == "person"
    assert out.key == "sarah"


# ─── _parse_iso_ts and _row_to_memory ───────────────────────────────────


def test_parse_iso_ts_handles_supabase_format():
    ts = _parse_iso_ts("2026-05-09T01:23:45.000Z")
    assert ts > 1_000_000_000  # sane epoch range
    # 2026-05 is well after 2025
    from datetime import datetime, timezone
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    assert dt.year == 2026
    assert dt.month == 5


def test_parse_iso_ts_handles_int():
    ts = _parse_iso_ts(1234567890)
    assert ts == 1234567890.0


def test_parse_iso_ts_handles_unparseable():
    import time
    before = time.time()
    out = _parse_iso_ts("not a date")
    after = time.time()
    # Falls back to "now"
    assert before <= out <= after + 1.0


def test_row_to_memory_full_round_trip():
    row = {
        "id": "x123",
        "user_id": "u1",
        "kind": "person",
        "key": "sarah",
        "value": {"name": "Sarah"},
        "importance": 4,
        "source_chunks": [1, 2, 3],
        "created_at": "2026-05-09T01:00:00.000Z",
        "updated_at": "2026-05-09T02:00:00.000Z",
    }
    m = _row_to_memory(row)
    assert m.id == "x123"
    assert m.value == {"name": "Sarah"}
    assert m.importance == 4
    assert m.source_chunks == [1, 2, 3]
    assert m.created_at < m.updated_at
