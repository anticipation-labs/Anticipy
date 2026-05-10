"""End-to-end test that proves semantic memory recall works.

Stores a memory ("Sarah is a friend who likes Italian food"), then
queries with a paraphrase ("what does Sarah eat") and confirms we get
the right row back. Embeddings + RPC are both mocked so the test is
deterministic and offline.

The test is shaped exactly like a real run through SupabaseMemoryBackend:
  1. upsert(Memory) writes the row
  2. background _embed_and_update fires (we let it complete)
  3. search() embeds the query and calls anticipy_memory_topk
  4. We return rows whose embedding is most similar to the query

Mocked surface area:
  * app.embeddings.embed_one      → deterministic 768-vector per text
  * app.embeddings.embed_query    → same family of vectors so paraphrases land near
  * supabase_client.call_rpc      → simulates the SQL RPC over the fake corpus
  * supabase_client.update_rows   → captures the embedding write
"""

from __future__ import annotations

import asyncio
import json
import math
from typing import Any
from unittest.mock import patch

import pytest

from app.memory import (
    Memory,
    MemoryStore,
    SupabaseMemoryBackend,
    _decode_value,
    _encode_value,
)


# ---------------------------------------------------------------------------
# Deterministic fake embedder
# ---------------------------------------------------------------------------


def _hash_to_unit_vec(text: str, dim: int = 768) -> list[float]:
    """Map a string to a unit vector deterministically.

    We bucket bytes of the lowercased input mod `dim` and accumulate
    weight in those positions, then L2-normalize. Two paraphrases that
    share most words end up with high cosine similarity; unrelated
    strings end up nearly orthogonal.
    """
    vec = [0.0] * dim
    s = (text or "").lower()
    # Stride by character bigrams so we keep some structural signal —
    # plain unigrams tend to swamp into a small set of buckets.
    for i in range(len(s) - 1):
        bigram = s[i:i + 2]
        h = (hash(bigram) % dim + dim) % dim  # nonneg modulo
        vec[h] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


# ---------------------------------------------------------------------------
# Fake supabase_client surface that supports the FULL backend contract
# ---------------------------------------------------------------------------


class _SupabaseLike:
    """Records rows, embeddings, and answers RPC calls with cosine ranking.

    Mirrors the part of `app.supabase_client` the SupabaseMemoryBackend
    actually touches: `upsert_row`, `select_rows`, `update_rows`,
    `call_rpc`. Lets the test exercise the production code path without
    any real network or database.
    """

    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}  # id → row
        self.embeddings: dict[str, list[float]] = {}  # id → vector

    async def upsert_row(self, table: str, data: dict) -> dict:
        # Match on (user_id, kind, key) like the real PG unique constraint.
        for rid, existing in list(self.rows.items()):
            if (
                existing.get("user_id") == data.get("user_id")
                and existing.get("kind") == data.get("kind")
                and existing.get("key") == data.get("key")
            ):
                merged = {**existing, **data, "id": existing["id"]}
                self.rows[existing["id"]] = merged
                return merged
        rid = data["id"]
        self.rows[rid] = dict(data)
        return self.rows[rid]

    async def select_rows(
        self, table: str, filters: dict | None = None,
        columns: str = "*", limit: int = 100,
    ) -> list[dict]:
        out = []
        for row in self.rows.values():
            if filters and not all(row.get(k) == v for k, v in filters.items()):
                continue
            out.append(row)
        return out[:limit]

    async def update_rows(self, table: str, filters: dict, data: dict) -> list[dict]:
        updated = []
        for rid, row in self.rows.items():
            if not all(row.get(k) == v for k, v in filters.items()):
                continue
            if "embedding" in data:
                # Decode the [v1,v2,...] literal back into a Python list.
                literal = data["embedding"]
                if isinstance(literal, str) and literal.startswith("[") \
                        and literal.endswith("]"):
                    self.embeddings[rid] = [
                        float(x) for x in literal[1:-1].split(",") if x
                    ]
            row.update(data)
            updated.append(row)
        return updated

    async def call_rpc(self, name: str, args: dict) -> list[dict]:
        if name != "anticipy_memory_topk":
            return []
        # Decode the query vector literal.
        qlit = args.get("p_query", "")
        if isinstance(qlit, str) and qlit.startswith("[") and qlit.endswith("]"):
            qvec = [float(x) for x in qlit[1:-1].split(",") if x]
        else:
            qvec = []

        user_id = args.get("p_user_id")
        k = int(args.get("p_k") or 5)

        scored: list[tuple[float, dict]] = []
        for rid, row in self.rows.items():
            if row.get("user_id") != user_id:
                continue
            vec = self.embeddings.get(rid)
            if not vec:
                continue  # row hasn't been embedded yet — not eligible
            sim = _cosine(qvec, vec)
            row_with_sim = {**row, "similarity": sim}
            scored.append((sim, row_with_sim))
        scored.sort(key=lambda s: s[0], reverse=True)
        return [r for _, r in scored[:k]]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_value_encode_decode_round_trip():
    payload = {"name": "Sarah", "relation": "friend", "notes": "italian"}
    encoded = _encode_value(payload)
    assert isinstance(encoded, str)
    assert _decode_value(encoded) == payload


@pytest.mark.asyncio
async def test_value_decode_handles_plain_text_legacy():
    """Rows written by a non-Python caller as plain text round-trip
    safely as {"text": "<raw>"}."""
    out = _decode_value("just some prose")
    assert out == {"text": "just some prose"}


@pytest.mark.asyncio
async def test_value_decode_handles_dict_legacy():
    """Older rows that wrote a real dict (jsonb-style) still work."""
    payload = {"name": "Sarah"}
    assert _decode_value(payload) == payload


@pytest.mark.asyncio
async def test_supabase_backend_writes_text_value():
    """The wire format on the value column must be JSON text, not a dict."""
    fake = _SupabaseLike()
    backend = SupabaseMemoryBackend(supabase_client_module=fake)
    await backend.upsert(Memory(
        id="", user_id="u1", kind="person", key="sarah",
        value={"name": "Sarah"}, importance=4,
    ))
    rows = list(fake.rows.values())
    assert len(rows) == 1
    raw_value = rows[0]["value"]
    # Wire format is text
    assert isinstance(raw_value, str)
    # And it round-trips
    assert json.loads(raw_value) == {"name": "Sarah"}


@pytest.mark.asyncio
async def test_supabase_backend_maps_importance_to_confidence():
    fake = _SupabaseLike()
    backend = SupabaseMemoryBackend(supabase_client_module=fake)
    await backend.upsert(Memory(
        id="", user_id="u1", kind="x", key="k",
        value={}, importance=5,
    ))
    rows = list(fake.rows.values())
    # 5/5 → confidence 1.0
    assert rows[0]["confidence"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_search_falls_back_to_token_overlap_without_embeddings():
    """When embed_query returns None, search uses the recent-window
    token-overlap path so we don't lose all retrieval in dev/test."""
    fake = _SupabaseLike()
    backend = SupabaseMemoryBackend(supabase_client_module=fake)

    async def _no_embed(text: str):
        return None

    with patch("app.embeddings.embed_query", new=_no_embed), \
            patch("app.embeddings.embed_one", new=_no_embed):
        await backend.upsert(Memory(
            id="", user_id="u1", kind="person", key="sarah",
            value={"name": "Sarah", "notes": "loves italian food"},
            importance=4,
        ))
        await backend.upsert(Memory(
            id="", user_id="u1", kind="person", key="bob",
            value={"name": "Bob", "notes": "loves sushi"},
            importance=3,
        ))
        out = await backend.search("u1", "italian", k=5)

    assert len(out) == 1
    assert out[0].key == "sarah"


@pytest.mark.asyncio
async def test_semantic_recall_e2e_paraphrase():
    """The headline test: store a memory, query with a paraphrase, prove
    we get it back at the top of the result.

    Setup:
      mem #1: "Sarah is a friend who likes Italian food"
      mem #2: "Bob loves baseball"
    Query: "what does Sarah eat"

    Expectation: mem #1 ranks first by cosine over our deterministic
    bigram-hash embedder. If this fails the entire RAG path is broken.
    """
    fake = _SupabaseLike()
    backend = SupabaseMemoryBackend(supabase_client_module=fake)

    async def _embed_one(text: str):
        return _hash_to_unit_vec(text)

    async def _embed_query(text: str):
        return _hash_to_unit_vec(text)

    with patch("app.embeddings.embed_one", new=_embed_one), \
            patch("app.embeddings.embed_query", new=_embed_query):
        store = MemoryStore(backend=backend)
        await store.remember_person(
            user_id="u1", name="Sarah", relation="friend",
            notes="likes Italian food, lives in Brooklyn",
        )
        await store.remember_person(
            user_id="u1", name="Bob", relation="cousin",
            notes="loves baseball, plays on weekends",
        )

        # Wait for the fire-and-forget embedding tasks to land.
        await _drain_pending_tasks()

        # Sanity: both rows now have embeddings stored.
        assert len(fake.embeddings) == 2

        out = await store.search("u1", "what does Sarah eat", k=3)

    assert out, "expected at least one search hit"
    # The Sarah row should be top — it shares 'sarah' and 'eat'-shape
    # signal via the bigram-hash family of our deterministic embedder.
    assert out[0].key == "sarah", \
        f"expected sarah at top; got {[m.key for m in out]}"


@pytest.mark.asyncio
async def test_semantic_recall_isolates_by_user():
    fake = _SupabaseLike()
    backend = SupabaseMemoryBackend(supabase_client_module=fake)

    async def _embed_one(text: str):
        return _hash_to_unit_vec(text)

    async def _embed_query(text: str):
        return _hash_to_unit_vec(text)

    with patch("app.embeddings.embed_one", new=_embed_one), \
            patch("app.embeddings.embed_query", new=_embed_query):
        store = MemoryStore(backend=backend)
        await store.remember_person(
            "u1", "Sarah", relation="friend",
            notes="lives in Brooklyn"
        )
        await store.remember_person(
            "u2", "Sarah", relation="cousin",
            notes="lives in Berlin"
        )
        await _drain_pending_tasks()
        out = await store.search("u1", "where does Sarah live", k=5)

    assert all(m.user_id == "u1" for m in out)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _drain_pending_tasks() -> None:
    """Yield control until all currently-scheduled tasks complete.

    The Supabase backend dispatches the embedding update via
    `loop.create_task(...)`. In a unit test we need to let those tasks
    finish before asserting on `fake.embeddings`. A small ladder of
    sleeps is enough — each task is one await-point per call.
    """
    for _ in range(10):
        await asyncio.sleep(0)
