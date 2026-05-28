"""Unit tests for app.embeddings — Gemini embedding client (768-d)."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app import embeddings


# ---------------------------------------------------------------------------
# Helpers — fake httpx.Response and httpx.AsyncClient
# ---------------------------------------------------------------------------


def _fake_response(status_code: int, json_body: Any = None, text: str = "") -> Any:
    """Build a stand-in for httpx.Response that exposes status_code, .json(), .text."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text or (str(json_body) if json_body is not None else "")
    if json_body is None:
        resp.json.side_effect = ValueError("no body")
    else:
        resp.json.return_value = json_body
    return resp


class _FakeClient:
    """Replaces httpx.AsyncClient as a context manager that returns canned posts."""

    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a, **_kw):
        return None

    async def post(self, url: str, json: dict | None = None, timeout: float | None = None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if not self.responses:
            raise AssertionError("FakeClient ran out of canned responses")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _good_embedding_response(dim: int = 768) -> Any:
    return _fake_response(
        200,
        json_body={"embedding": {"values": [0.01] * dim}},
    )


def _good_batch_response(n: int, dim: int = 768) -> Any:
    return _fake_response(
        200,
        json_body={"embeddings": [{"values": [0.02] * dim} for _ in range(n)]},
    )


# ---------------------------------------------------------------------------
# embed_one
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_one_returns_768_floats():
    fake = _FakeClient([_good_embedding_response()])
    with patch("app.embeddings.GOOGLE_API_KEY", "fake-key"), \
            patch("app.embeddings.httpx.AsyncClient", return_value=fake):
        vec = await embeddings.embed_one("hello")
    assert vec is not None
    assert len(vec) == 768
    assert all(isinstance(x, float) for x in vec)


@pytest.mark.asyncio
async def test_embed_one_returns_none_without_key():
    with patch("app.embeddings.GOOGLE_API_KEY", ""):
        vec = await embeddings.embed_one("hello")
    assert vec is None


@pytest.mark.asyncio
async def test_embed_one_returns_none_on_empty_input():
    with patch("app.embeddings.GOOGLE_API_KEY", "fake-key"):
        assert await embeddings.embed_one("") is None
        assert await embeddings.embed_one("   ") is None


@pytest.mark.asyncio
async def test_embed_one_retries_on_429_then_succeeds():
    fake = _FakeClient([
        _fake_response(429, text="quota"),
        _fake_response(429, text="quota"),
        _good_embedding_response(),
    ])
    with patch("app.embeddings.GOOGLE_API_KEY", "fake-key"), \
            patch("app.embeddings.httpx.AsyncClient", return_value=fake), \
            patch("app.embeddings.asyncio.sleep", new=AsyncMock()):
        vec = await embeddings.embed_one("hello")
    assert vec is not None
    assert len(fake.calls) == 3


@pytest.mark.asyncio
async def test_embed_one_returns_none_after_three_429s():
    fake = _FakeClient([
        _fake_response(429),
        _fake_response(429),
        _fake_response(429),
    ])
    with patch("app.embeddings.GOOGLE_API_KEY", "fake-key"), \
            patch("app.embeddings.httpx.AsyncClient", return_value=fake), \
            patch("app.embeddings.asyncio.sleep", new=AsyncMock()):
        vec = await embeddings.embed_one("hello")
    assert vec is None
    assert len(fake.calls) == 3


@pytest.mark.asyncio
async def test_embed_one_returns_none_on_4xx():
    fake = _FakeClient([_fake_response(400, text="bad")])
    with patch("app.embeddings.GOOGLE_API_KEY", "fake-key"), \
            patch("app.embeddings.httpx.AsyncClient", return_value=fake):
        vec = await embeddings.embed_one("hello")
    assert vec is None


@pytest.mark.asyncio
async def test_embed_one_returns_none_on_network_error():
    fake = _FakeClient([
        httpx.NetworkError("conn refused"),
        httpx.NetworkError("conn refused"),
        httpx.NetworkError("conn refused"),
    ])
    with patch("app.embeddings.GOOGLE_API_KEY", "fake-key"), \
            patch("app.embeddings.httpx.AsyncClient", return_value=fake), \
            patch("app.embeddings.asyncio.sleep", new=AsyncMock()):
        vec = await embeddings.embed_one("hello")
    assert vec is None


@pytest.mark.asyncio
async def test_embed_one_rejects_wrong_dim_response():
    fake = _FakeClient([
        _fake_response(200, json_body={"embedding": {"values": [0.0] * 512}}),
    ])
    with patch("app.embeddings.GOOGLE_API_KEY", "fake-key"), \
            patch("app.embeddings.httpx.AsyncClient", return_value=fake):
        vec = await embeddings.embed_one("hello")
    assert vec is None


@pytest.mark.asyncio
async def test_embed_query_uses_query_task_type():
    fake = _FakeClient([_good_embedding_response()])
    with patch("app.embeddings.GOOGLE_API_KEY", "fake-key"), \
            patch("app.embeddings.httpx.AsyncClient", return_value=fake):
        vec = await embeddings.embed_query("hello")
    assert vec is not None
    payload = fake.calls[0]["json"]
    assert payload["taskType"] == "RETRIEVAL_QUERY"


# ---------------------------------------------------------------------------
# embed_batch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_batch_uses_batch_endpoint():
    fake = _FakeClient([_good_batch_response(3)])
    with patch("app.embeddings.GOOGLE_API_KEY", "fake-key"), \
            patch("app.embeddings.httpx.AsyncClient", return_value=fake):
        out = await embeddings.embed_batch(["a", "b", "c"])
    assert len(out) == 3
    assert all(v is not None and len(v) == 768 for v in out)
    # Should hit the batch URL exactly once
    assert len(fake.calls) == 1
    assert "batchEmbedContents" in fake.calls[0]["url"]


@pytest.mark.asyncio
async def test_embed_batch_handles_empty_input():
    out = await embeddings.embed_batch([])
    assert out == []


@pytest.mark.asyncio
async def test_embed_batch_skips_empty_strings():
    fake = _FakeClient([_good_batch_response(2)])
    with patch("app.embeddings.GOOGLE_API_KEY", "fake-key"), \
            patch("app.embeddings.httpx.AsyncClient", return_value=fake):
        out = await embeddings.embed_batch(["a", "", "  ", "b"])
    assert len(out) == 4
    assert out[0] is not None
    assert out[1] is None
    assert out[2] is None
    assert out[3] is not None
    # Only 2 actual texts in the batch payload
    payload = fake.calls[0]["json"]
    assert len(payload["requests"]) == 2


@pytest.mark.asyncio
async def test_embed_batch_falls_back_to_per_item_on_batch_failure():
    # First call (batch) fails with 500, then 3 per-item calls succeed.
    fake = _FakeClient([
        _fake_response(500, text="oops"),
        _good_embedding_response(),
        _good_embedding_response(),
        _good_embedding_response(),
    ])
    with patch("app.embeddings.GOOGLE_API_KEY", "fake-key"), \
            patch("app.embeddings.httpx.AsyncClient", return_value=fake), \
            patch("app.embeddings.asyncio.sleep", new=AsyncMock()):
        out = await embeddings.embed_batch(["a", "b", "c"])
    assert all(v is not None for v in out)


@pytest.mark.asyncio
async def test_embed_batch_returns_all_none_without_key():
    with patch("app.embeddings.GOOGLE_API_KEY", ""):
        out = await embeddings.embed_batch(["a", "b"])
    assert out == [None, None]


# ---------------------------------------------------------------------------
# vector_to_pg_literal
# ---------------------------------------------------------------------------


def test_vector_to_pg_literal_format():
    out = embeddings.vector_to_pg_literal([0.1, 0.2, 0.3])
    assert out.startswith("[")
    assert out.endswith("]")
    parts = out[1:-1].split(",")
    assert len(parts) == 3
    # Six decimals
    assert "." in parts[0]
    assert len(parts[0].split(".")[1]) == 6


def test_vector_to_pg_literal_handles_negatives():
    out = embeddings.vector_to_pg_literal([-0.5, 0.0, 1.5])
    assert "-0.500000" in out
    assert "1.500000" in out


# ---------------------------------------------------------------------------
# embeddings_available
# ---------------------------------------------------------------------------


def test_embeddings_available_false_without_key():
    with patch("app.embeddings.GOOGLE_API_KEY", ""):
        assert embeddings.embeddings_available() is False


def test_embeddings_available_true_with_key():
    with patch("app.embeddings.GOOGLE_API_KEY", "fake-key"):
        assert embeddings.embeddings_available() is True


# ---------------------------------------------------------------------------
# Real-network test (gated)
# ---------------------------------------------------------------------------


@pytest.mark.real_network
@pytest.mark.asyncio
async def test_embed_one_real_network():
    """One actual call to Gemini gemini-embedding-001. Skipped by default.

    Run with: `pytest -m real_network test_embeddings.py` and ensure
    GOOGLE_API_KEY is set in the env.
    """
    if not os.environ.get("GOOGLE_API_KEY"):
        pytest.skip("GOOGLE_API_KEY not set")
    # Reload module-level key from env
    with patch("app.embeddings.GOOGLE_API_KEY", os.environ["GOOGLE_API_KEY"]):
        vec = await embeddings.embed_one(
            "Sarah is a friend who likes Italian food."
        )
    assert vec is not None
    assert len(vec) == 768
    assert all(isinstance(x, float) for x in vec)


@pytest.mark.real_network
@pytest.mark.asyncio
async def test_paraphrase_similarity_real_network():
    """Real-network sanity check: paraphrases land closer than unrelated.

    Asserts cosine(paraphrase, query) > cosine(unrelated, query) by a
    meaningful margin so we know the embedding really preserves
    semantic similarity (and the wiring isn't returning constants).
    """
    import math
    if not os.environ.get("GOOGLE_API_KEY"):
        pytest.skip("GOOGLE_API_KEY not set")
    with patch("app.embeddings.GOOGLE_API_KEY", os.environ["GOOGLE_API_KEY"]):
        q = await embeddings.embed_query("What does Sarah eat?")
        para = await embeddings.embed_one(
            "Sarah is a friend who likes Italian food."
        )
        unrelated = await embeddings.embed_one(
            "The capital of France is Paris."
        )

    def _cos(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a)) or 1.0
        nb = math.sqrt(sum(x * x for x in b)) or 1.0
        return dot / (na * nb)

    s_para = _cos(q, para)
    s_unr = _cos(q, unrelated)
    assert s_para > s_unr + 0.05, (
        f"paraphrase similarity ({s_para:.3f}) must beat unrelated ({s_unr:.3f})"
    )
