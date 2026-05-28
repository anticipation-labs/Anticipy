"""
Context buffer + semantic memory for the proactive engine.

Two layers:

1. **Recent buffer**: a sliding window of the last N minutes of TranscriptChunks
   from the user's voice. Lives in memory. Used by the interpreter and decider
   to provide local conversational context.

2. **Semantic memory**: a longer-horizon embedding-keyed store of past
   conversation summaries. Used by the interpreter to pull "I've heard this
   name before" / "the user mentioned this last week" context. Backed by an
   in-memory index for the reference impl; the on-device port uses Core
   ML / Android NNAPI vector search on a SQLite-backed store.

The buffer NEVER stores raw audio. Only text. Per-user isolated.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Iterable

from .types import TranscriptChunk


# Default sliding-window length, in seconds. Two minutes is enough for
# multi-turn intent buildup; longer than ten and the LLM context becomes
# costly. The interpreter typically queries the most recent 60-120 s.
DEFAULT_WINDOW_SECONDS = 600  # 10 minutes


@dataclass
class _MemoryRow:
    """A single row in the semantic memory.

    `embedding` is the vector representation. The dimension and model are
    runtime-configurable (defaults to a 384-d local embedding model).
    `summary` is a short human-readable summary of the conversation segment;
    surfaced in the "Things I noticed" feed when this memory is recalled.
    """

    summary: str
    embedding: list[float]
    chunk_ids: list[int]
    created_at: float = field(default_factory=time.time)


class ContextBuffer:
    """The recent + long-horizon context for one user.

    Single instance per user per session. Thread-safe via an async lock so the
    transcript callback and the interpreter can both touch the buffer.
    """

    def __init__(
        self,
        user_id: str,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        embed_fn: "EmbedFn | None" = None,
    ) -> None:
        self.user_id = user_id
        self.window_seconds = window_seconds
        self._chunks: deque[TranscriptChunk] = deque()
        self._memory: list[_MemoryRow] = []
        self._lock = asyncio.Lock()
        self._embed_fn = embed_fn  # injected; can be None in tests

    # --- Recent buffer ---------------------------------------------------------

    async def append(self, chunk: TranscriptChunk) -> None:
        """Add a transcript chunk and prune anything outside the window."""
        async with self._lock:
            self._chunks.append(chunk)
            self._prune_locked()

    def _prune_locked(self) -> None:
        cutoff = time.time() - self.window_seconds
        while self._chunks and self._chunks[0].end_ts < cutoff:
            self._chunks.popleft()

    async def recent(self, seconds: float = 120.0) -> list[TranscriptChunk]:
        """Chunks within the last `seconds` window, oldest first."""
        async with self._lock:
            cutoff = time.time() - seconds
            return [c for c in self._chunks if c.end_ts >= cutoff]

    async def recent_text(self, seconds: float = 120.0) -> str:
        """Recent transcript as one block of text, oldest first."""
        chunks = await self.recent(seconds)
        return "\n".join(c.text for c in chunks if c.text)

    async def latest(self) -> TranscriptChunk | None:
        async with self._lock:
            return self._chunks[-1] if self._chunks else None

    async def chunks_in_session(self, session_id: str) -> list[TranscriptChunk]:
        async with self._lock:
            return [c for c in self._chunks if c.session_id == session_id]

    async def chunk_count(self) -> int:
        async with self._lock:
            return len(self._chunks)

    # --- Semantic memory -------------------------------------------------------

    async def remember(self, summary: str, chunk_ids: list[int]) -> None:
        """Compact a recent conversation segment into long-horizon memory.

        Called by the interpreter or by a periodic compaction job (e.g.,
        every 5 minutes when the buffer fills, or end-of-conversation).
        """
        if not summary.strip():
            return
        embedding: list[float] = []
        if self._embed_fn is not None:
            embedding = await self._embed_fn(summary)
        async with self._lock:
            self._memory.append(_MemoryRow(
                summary=summary,
                embedding=embedding,
                chunk_ids=list(chunk_ids),
            ))

    async def retrieve(self, query: str, k: int = 5) -> list[str]:
        """Semantic retrieval. Returns up to k most-relevant memory summaries.

        If no embed_fn is configured (tests, dev), falls back to most-recent.
        """
        if self._embed_fn is None or not query.strip():
            async with self._lock:
                return [m.summary for m in self._memory[-k:]]

        q_emb = await self._embed_fn(query)
        async with self._lock:
            scored = [
                (_cosine(q_emb, m.embedding), m.summary)
                for m in self._memory
                if m.embedding
            ]
        scored.sort(key=lambda t: t[0], reverse=True)
        return [s for _, s in scored[:k]]

    async def memory_size(self) -> int:
        async with self._lock:
            return len(self._memory)

    # --- Notes/recording introspection -----------------------------------------

    async def all_chunks(self) -> list[TranscriptChunk]:
        async with self._lock:
            return list(self._chunks)


def _cosine(a: Iterable[float], b: Iterable[float]) -> float:
    """Plain cosine similarity. Returns 0 on degenerate inputs."""
    a_list = list(a)
    b_list = list(b)
    if not a_list or not b_list or len(a_list) != len(b_list):
        return 0.0
    dot = sum(x * y for x, y in zip(a_list, b_list))
    norm_a = sum(x * x for x in a_list) ** 0.5
    norm_b = sum(y * y for y in b_list) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# Type alias for an injected embedding function. The reference impl can
# wrap a small local model (sentence-transformers MiniLM, ~80 MB) or a
# remote call (OpenAI text-embedding-3-small). On the phone, this is a
# Core ML / NNAPI call.
class EmbedFn:  # protocol-ish; runtime is `Callable[[str], Awaitable[list[float]]]`
    async def __call__(self, text: str) -> list[float]: ...
