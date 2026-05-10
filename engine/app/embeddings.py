"""
Gemini embeddings client.

Single-purpose module that turns text into a 768-dim embedding vector.
Used by `app.memory` and `app.trajectory_cache` for semantic recall.

Design notes:
  * Uses `gemini-embedding-001` with `outputDimensionality=768` so the
    output drops cleanly into the 768-d vector columns we already have
    (engine_trajectories.task_embedding, anticipy_memory.embedding).
    The older alias `text-embedding-004` is not available on the
    project's current API endpoints — stick with the explicit model.
  * Free-tier Gemini embeddings have a separate quota from the chat models.
    Calls here do NOT count against the action-engine's chat budget.
  * The Gemini REST API supports a `batchEmbedContents` endpoint that takes
    up to 100 requests in one round-trip — we use it from `embed_batch`.
  * On 429 we back off (0.5s, 1s, 2s) and retry up to three times. After
    that we return None and the caller decides whether to skip the row,
    fall back to token-overlap search, or surface the failure.
  * The embedding endpoint is documented at:
      https://ai.google.dev/api/embeddings
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from app.config import GOOGLE_API_KEY


logger = logging.getLogger("engine.embeddings")


_MODEL = "gemini-embedding-001"
_EMBED_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{_MODEL}:embedContent"
)
_BATCH_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{_MODEL}:batchEmbedContents"
)
_DIM = 768
_TIMEOUT_S = 8.0
_MAX_RETRIES = 3
_MAX_INPUT_CHARS = 8000  # Gemini truncates internally; this caps payload size
_MAX_BATCH = 100  # API hard limit
_CONCURRENCY = 5  # Cap concurrent calls when we have to fall back to per-item


# Module-level semaphore for asyncio.gather fan-out so we don't spam the API.
_SEMAPHORE = asyncio.Semaphore(_CONCURRENCY)


def embeddings_available() -> bool:
    """Whether an API key is configured. Used by callers to decide if they
    should even try to embed (so they can skip cleanly in tests / dev)."""
    return bool(GOOGLE_API_KEY)


async def _post_json(
    client: httpx.AsyncClient,
    url: str,
    payload: dict,
) -> Optional[dict]:
    """One HTTP POST with retry/backoff on transient failures.

    Returns the parsed JSON response on success. Returns None on:
      * Persistent rate-limit (after _MAX_RETRIES backoffs)
      * 4xx that isn't 429 (programming error or quota — caller decides)
      * Network errors after _MAX_RETRIES
    """
    delay = 0.5
    for attempt in range(_MAX_RETRIES):
        try:
            resp = await client.post(url, json=payload, timeout=_TIMEOUT_S)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            logger.debug(
                "embedding call network error attempt %d: %s", attempt + 1, exc
            )
            if attempt == _MAX_RETRIES - 1:
                return None
            await asyncio.sleep(delay)
            delay *= 2
            continue
        except Exception:
            logger.exception("embedding call raised unexpectedly")
            return None

        if resp.status_code == 200:
            try:
                return resp.json()
            except Exception:
                logger.exception("embedding response was not JSON")
                return None

        if resp.status_code == 429:
            logger.info(
                "embedding rate-limited (attempt %d/%d), backing off %.1fs",
                attempt + 1, _MAX_RETRIES, delay,
            )
            if attempt == _MAX_RETRIES - 1:
                return None
            await asyncio.sleep(delay)
            delay *= 2
            continue

        # Non-retryable: log a snippet and bail
        body = (resp.text or "")[:240]
        logger.warning(
            "embedding call failed status=%d body=%s", resp.status_code, body
        )
        return None

    return None


async def embed_one(text: str) -> Optional[list[float]]:
    """Embed a single piece of text. Returns None on any failure.

    `text` is truncated to _MAX_INPUT_CHARS before sending. Empty/whitespace
    input returns None without making a network call.
    """
    if not GOOGLE_API_KEY:
        logger.debug("embed_one called without GOOGLE_API_KEY; returning None")
        return None
    if not text or not text.strip():
        return None

    payload = {
        "model": f"models/{_MODEL}",
        "content": {"parts": [{"text": text[:_MAX_INPUT_CHARS]}]},
        # taskType improves retrieval quality with asymmetric embeddings.
        # We use RETRIEVAL_DOCUMENT for stored items; embed_query() flips it.
        "taskType": "RETRIEVAL_DOCUMENT",
        # gemini-embedding-001 returns 3072-d by default; truncate to 768
        # so it drops into the existing pgvector columns.
        "outputDimensionality": _DIM,
    }
    url = f"{_EMBED_URL}?key={GOOGLE_API_KEY}"

    async with _SEMAPHORE:
        async with httpx.AsyncClient() as client:
            data = await _post_json(client, url, payload)

    if not data:
        return None
    vec = (data.get("embedding") or {}).get("values")
    if not isinstance(vec, list) or len(vec) != _DIM:
        logger.warning(
            "embed_one got unexpected vector shape: %s",
            type(vec).__name__ if vec is not None else "None",
        )
        return None
    return [float(x) for x in vec]


async def embed_query(text: str) -> Optional[list[float]]:
    """Embed text as a search QUERY (asymmetric). Slightly higher recall on
    retrieval than treating the query as a document. Same failure semantics
    as embed_one."""
    if not GOOGLE_API_KEY:
        return None
    if not text or not text.strip():
        return None

    payload = {
        "model": f"models/{_MODEL}",
        "content": {"parts": [{"text": text[:_MAX_INPUT_CHARS]}]},
        "taskType": "RETRIEVAL_QUERY",
        "outputDimensionality": _DIM,
    }
    url = f"{_EMBED_URL}?key={GOOGLE_API_KEY}"

    async with _SEMAPHORE:
        async with httpx.AsyncClient() as client:
            data = await _post_json(client, url, payload)

    if not data:
        return None
    vec = (data.get("embedding") or {}).get("values")
    if not isinstance(vec, list) or len(vec) != _DIM:
        return None
    return [float(x) for x in vec]


async def embed_batch(texts: list[str]) -> list[Optional[list[float]]]:
    """Embed a list of texts. Returns a list aligned with the input (same
    length, same order). Each entry is the 768-vector or None on failure.

    Implementation:
      * Up to _MAX_BATCH per HTTP call via Gemini's batchEmbedContents.
      * Empty/whitespace items short-circuit to None without a request.
      * On batch-call failure we fall back to per-item embed_one with a
        bounded asyncio.gather so quotas don't get blown.
    """
    if not texts:
        return []
    if not GOOGLE_API_KEY:
        return [None] * len(texts)

    out: list[Optional[list[float]]] = [None] * len(texts)

    # Index pairs we still need to fetch (skip empty inputs upfront).
    pending: list[tuple[int, str]] = [
        (i, t[:_MAX_INPUT_CHARS])
        for i, t in enumerate(texts)
        if t and t.strip()
    ]
    if not pending:
        return out

    # Slice into batches of _MAX_BATCH
    async with httpx.AsyncClient() as client:
        for chunk_start in range(0, len(pending), _MAX_BATCH):
            chunk = pending[chunk_start:chunk_start + _MAX_BATCH]
            payload = {
                "requests": [
                    {
                        "model": f"models/{_MODEL}",
                        "content": {"parts": [{"text": txt}]},
                        "taskType": "RETRIEVAL_DOCUMENT",
                        "outputDimensionality": _DIM,
                    }
                    for _, txt in chunk
                ],
            }
            url = f"{_BATCH_URL}?key={GOOGLE_API_KEY}"
            data = await _post_json(client, url, payload)

            if data and isinstance(data.get("embeddings"), list) and \
                    len(data["embeddings"]) == len(chunk):
                for (idx, _txt), emb in zip(chunk, data["embeddings"]):
                    vec = (emb or {}).get("values")
                    if isinstance(vec, list) and len(vec) == _DIM:
                        out[idx] = [float(x) for x in vec]
                continue

            # Batch failed — fall back to per-item with concurrency guard.
            logger.info(
                "embed_batch fell back to per-item for chunk of %d (batch path failed)",
                len(chunk),
            )

            async def _one(i: int, t: str) -> tuple[int, Optional[list[float]]]:
                return i, await embed_one(t)

            results = await asyncio.gather(
                *(_one(i, t) for i, t in chunk),
                return_exceptions=True,
            )
            for r in results:
                if isinstance(r, Exception):
                    logger.debug("per-item embed in fallback raised: %s", r)
                    continue
                idx, vec = r  # type: ignore[misc]
                if vec is not None:
                    out[idx] = vec

    return out


def vector_to_pg_literal(vec: list[float]) -> str:
    """Format a vector as a Postgres `vector` literal: '[0.1,0.2,...]'.

    pgvector accepts this form via PostgREST as a JSON string (the column
    type is `vector`). Six decimals is sufficient — Gemini returns ~7
    significant digits and the dot-product loss at 6 decimals is < 1e-7.
    """
    return "[" + ",".join(f"{float(v):.6f}" for v in vec) + "]"
