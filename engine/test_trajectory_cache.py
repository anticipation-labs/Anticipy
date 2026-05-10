"""Unit tests for app.trajectory_cache.

The cache lookup layer combines the embeddings client + the
engine_trajectories_topk RPC. Tests use deterministic mocked embeddings
and a stub RPC so behaviour is repeatable without the network.

Includes one end-to-end shape test (store-then-query paraphrase) that
mocks the embeddings to return cosine-aligned vectors so the threshold
logic can be exercised without a real provider.
"""

from __future__ import annotations

import math
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app import trajectory_cache


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _vec_from_score(score: float, dim: int = 768) -> list[float]:
    """Build a deterministic vector with a known dot-product against
    the canonical query vector (all-1/sqrt(dim)). Caller controls the
    cosine similarity by passing the desired score.

    Used by the in-memory RPC stub to produce a known similarity ordering
    without doing actual embedding math.
    """
    # Not used directly in these tests — kept here as a marker for what
    # the deterministic mock represents. The stub_rpc returns rows with a
    # `similarity` field directly.
    base = 1.0 / math.sqrt(dim)
    return [base * score] * dim


class _StubRpc:
    """Replaces app.supabase_client.call_rpc.

    Stores pre-canned rows; returns them on any call (the test sets up
    the rows it wants the RPC to return).
    """

    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = rows or []
        self.calls: list[tuple[str, dict]] = []

    async def __call__(self, name: str, args: dict) -> list[dict]:
        self.calls.append((name, args))
        return list(self.rows)


@pytest.fixture
def fake_embed_query():
    """Provides a deterministic embed_query that returns a fixed vector."""
    async def _embed(text: str):
        # 768-vector — content doesn't matter; the RPC stub doesn't use it.
        return [0.001] * 768
    return _embed


# ---------------------------------------------------------------------------
# find_similar_trajectories
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_similar_returns_high_similarity_rows(fake_embed_query):
    rows = [
        {
            "id": "t-1",
            "user_id": "u1",
            "task_summary": "Get python release year on wikipedia",
            "domain": "en.wikipedia.org",
            "steps": [{"action": "navigate"}],
            "outcome": "success",
            "outcome_message": "1991",
            "total_steps": 4,
            "similarity": 0.95,
        },
        {
            "id": "t-2",
            "user_id": "u1",
            "task_summary": "Capital of France",
            "domain": "en.wikipedia.org",
            "steps": [{"action": "navigate"}],
            "outcome": "success",
            "outcome_message": "Paris",
            "total_steps": 3,
            "similarity": 0.85,
        },
    ]
    stub = _StubRpc(rows)
    with patch("app.trajectory_cache.embeddings.embed_query", new=fake_embed_query), \
            patch("app.trajectory_cache.supabase_client.call_rpc", new=stub):
        out = await trajectory_cache.find_similar_trajectories(
            "u1", "When was Python first released?", k=5,
        )
    assert len(out) == 2
    assert out[0]["id"] == "t-1"
    assert out[0]["similarity"] == 0.95
    assert out[1]["similarity"] == 0.85


@pytest.mark.asyncio
async def test_find_similar_filters_below_threshold(fake_embed_query):
    rows = [
        {
            "id": "t-good",
            "task_summary": "good match",
            "domain": "x.com",
            "steps": [],
            "outcome": "success",
            "outcome_message": "ok",
            "total_steps": 1,
            "similarity": 0.85,
        },
        {
            "id": "t-bad",
            "task_summary": "weak match",
            "domain": "x.com",
            "steps": [],
            "outcome": "success",
            "outcome_message": "ok",
            "total_steps": 1,
            "similarity": 0.50,
        },
    ]
    stub = _StubRpc(rows)
    with patch("app.trajectory_cache.embeddings.embed_query", new=fake_embed_query), \
            patch("app.trajectory_cache.supabase_client.call_rpc", new=stub):
        out = await trajectory_cache.find_similar_trajectories(
            "u1", "task", k=5, similarity_threshold=0.78,
        )
    assert len(out) == 1
    assert out[0]["id"] == "t-good"


@pytest.mark.asyncio
async def test_find_similar_empty_when_no_rows(fake_embed_query):
    stub = _StubRpc([])
    with patch("app.trajectory_cache.embeddings.embed_query", new=fake_embed_query), \
            patch("app.trajectory_cache.supabase_client.call_rpc", new=stub):
        out = await trajectory_cache.find_similar_trajectories(
            "new-user", "first task", k=3,
        )
    assert out == []


@pytest.mark.asyncio
async def test_find_similar_empty_when_no_embeddings():
    """If the embeddings provider returns None, we degrade to []."""
    async def _no_embed(text: str):
        return None

    stub = _StubRpc([{"id": "x", "similarity": 0.99, "task_summary": "x",
                      "domain": "y", "steps": [], "outcome": "success",
                      "outcome_message": None, "total_steps": 0}])
    with patch("app.trajectory_cache.embeddings.embed_query", new=_no_embed), \
            patch("app.trajectory_cache.supabase_client.call_rpc", new=stub):
        out = await trajectory_cache.find_similar_trajectories("u1", "task")
    assert out == []
    # And we never made an RPC call
    assert stub.calls == []


@pytest.mark.asyncio
async def test_find_similar_handles_rpc_failure(fake_embed_query):
    async def _explode(_n, _a):
        raise RuntimeError("network down")

    with patch("app.trajectory_cache.embeddings.embed_query", new=fake_embed_query), \
            patch("app.trajectory_cache.supabase_client.call_rpc", new=_explode):
        out = await trajectory_cache.find_similar_trajectories("u1", "task")
    assert out == []


@pytest.mark.asyncio
async def test_find_similar_validates_inputs():
    out = await trajectory_cache.find_similar_trajectories("", "task")
    assert out == []
    out = await trajectory_cache.find_similar_trajectories("u1", "")
    assert out == []
    out = await trajectory_cache.find_similar_trajectories("u1", "task", k=0)
    assert out == []


@pytest.mark.asyncio
async def test_find_similar_passes_only_success_flag(fake_embed_query):
    stub = _StubRpc([])
    with patch("app.trajectory_cache.embeddings.embed_query", new=fake_embed_query), \
            patch("app.trajectory_cache.supabase_client.call_rpc", new=stub):
        await trajectory_cache.find_similar_trajectories(
            "u1", "task", only_success=False,
        )
    assert stub.calls
    name, args = stub.calls[0]
    assert name == "engine_trajectories_topk"
    assert args["p_only_success"] is False
    assert args["p_user_id"] == "u1"


# ---------------------------------------------------------------------------
# cache_hit_for
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_hit_returns_best_match_above_threshold(fake_embed_query):
    rows = [{
        "id": "near-dup",
        "task_summary": "same task",
        "domain": "x.com",
        "steps": [],
        "outcome": "success",
        "outcome_message": "ok",
        "total_steps": 2,
        "similarity": 0.94,
    }]
    stub = _StubRpc(rows)
    with patch("app.trajectory_cache.embeddings.embed_query", new=fake_embed_query), \
            patch("app.trajectory_cache.supabase_client.call_rpc", new=stub):
        hit = await trajectory_cache.cache_hit_for("u1", "task")
    assert hit is not None
    assert hit["id"] == "near-dup"


@pytest.mark.asyncio
async def test_cache_hit_returns_none_below_threshold(fake_embed_query):
    rows = [{
        "id": "loose",
        "task_summary": "looserly related",
        "domain": "x.com",
        "steps": [],
        "outcome": "success",
        "outcome_message": "ok",
        "total_steps": 1,
        "similarity": 0.85,
    }]
    stub = _StubRpc(rows)
    with patch("app.trajectory_cache.embeddings.embed_query", new=fake_embed_query), \
            patch("app.trajectory_cache.supabase_client.call_rpc", new=stub):
        hit = await trajectory_cache.cache_hit_for("u1", "task")
    assert hit is None


@pytest.mark.asyncio
async def test_cache_hit_returns_none_for_new_user(fake_embed_query):
    stub = _StubRpc([])
    with patch("app.trajectory_cache.embeddings.embed_query", new=fake_embed_query), \
            patch("app.trajectory_cache.supabase_client.call_rpc", new=stub):
        hit = await trajectory_cache.cache_hit_for("brand-new-user", "first ever task")
    assert hit is None


# ---------------------------------------------------------------------------
# get_few_shot_examples
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_few_shot_uses_loose_threshold(fake_embed_query):
    rows = [
        {"id": "fs-1", "task_summary": "loose 1", "domain": "x", "steps": [],
         "outcome": "success", "outcome_message": None, "total_steps": 0,
         "similarity": 0.70},
        {"id": "fs-2", "task_summary": "loose 2", "domain": "x", "steps": [],
         "outcome": "success", "outcome_message": None, "total_steps": 0,
         "similarity": 0.66},
        {"id": "fs-3", "task_summary": "below", "domain": "x", "steps": [],
         "outcome": "success", "outcome_message": None, "total_steps": 0,
         "similarity": 0.40},
    ]
    stub = _StubRpc(rows)
    with patch("app.trajectory_cache.embeddings.embed_query", new=fake_embed_query), \
            patch("app.trajectory_cache.supabase_client.call_rpc", new=stub):
        out = await trajectory_cache.get_few_shot_examples("u1", "task", k=3)
    ids = {r["id"] for r in out}
    assert ids == {"fs-1", "fs-2"}


# ---------------------------------------------------------------------------
# End-to-end shape: paraphrase retrieval crosses threshold
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_paraphrase_retrieval_e2e():
    """Store task A's vector in a fake corpus, then query for paraphrase A'.

    The fake `corpus` here is a tiny in-memory dict mapping id → vector.
    The fake embed_query embeds the query into a vector that is cosine-
    aligned with A's stored vector (we just return A's vector for a
    paraphrase, an orthogonal vector for an unrelated query).

    This is the same shape as a real run: cache.find_similar(user_id, A')
    pulls A back at high similarity.
    """
    # Two stored "trajectories": one for "weather in Paris", one unrelated.
    # The RPC computes 1 - cosine_distance(query, stored) on the server,
    # so we simulate by hand-picking similarity values for each row based
    # on the query text.
    def _make_rpc(query_vec: list[float]):
        async def _rpc(name: str, args: dict) -> list[dict]:
            # Compute cosine sim by hand against canned stored vectors.
            stored = {
                "weather-paris": [1.0] + [0.0] * 767,
                "buy-shoes":     [0.0] + [1.0] + [0.0] * 766,
            }
            results: list[dict] = []
            qnorm = math.sqrt(sum(v * v for v in query_vec)) or 1.0
            for row_id, vec in stored.items():
                vnorm = math.sqrt(sum(v * v for v in vec)) or 1.0
                dot = sum(a * b for a, b in zip(query_vec, vec))
                sim = dot / (qnorm * vnorm)
                results.append({
                    "id": row_id,
                    "task_summary": row_id.replace("-", " "),
                    "domain": "weather.com" if "weather" in row_id else "shoes.com",
                    "steps": [{"action": "navigate"}],
                    "outcome": "success",
                    "outcome_message": "ok",
                    "total_steps": 3,
                    "similarity": sim,
                })
            results.sort(key=lambda r: r["similarity"], reverse=True)
            return results[: args["p_k"]]
        return _rpc

    # Embedding mock: paraphrase of "weather in paris" returns a vector
    # very close to the stored weather-paris vector.
    paraphrase_vec = [0.99] + [0.001] * 767

    async def _fake_embed(text: str):
        return paraphrase_vec

    with patch("app.trajectory_cache.embeddings.embed_query", new=_fake_embed), \
            patch("app.trajectory_cache.supabase_client.call_rpc",
                  new=_make_rpc(paraphrase_vec)):
        out = await trajectory_cache.find_similar_trajectories(
            "u1", "What's the weather like in Paris today?", k=2,
        )
    # We should get the weather row at the top; similarity well above 0.78
    assert out, "expected at least one match"
    assert out[0]["id"] == "weather-paris"
    assert out[0]["similarity"] > trajectory_cache.SIMILARITY_USEFUL
