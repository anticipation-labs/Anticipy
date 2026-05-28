"""
Cross-session memory — the "second brain" that persists who Sarah is, where
the wearer lives, what they like, what's already promised, what's an ongoing
project. Queryable by exact key, by recency, by kind, or **semantically**
(via Gemini text-embedding-004 + the anticipy_memory_topk RPC).

Two backends, identical contract:

  - InProcessMemoryBackend: dict-based; for tests + dev cycles. The
    `search()` method here uses naive token-overlap so unit tests don't
    need an embeddings provider.
  - SupabaseMemoryBackend:   talks to public.anticipy_memory via
    supabase_client. `search()` calls the anticipy_memory_topk RPC over
    the embedding column for real semantic recall.

Schema (already applied — see Supabase migrations):

  CREATE TABLE public.anticipy_memory (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    session_id uuid,
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,                 -- JSON-encoded dict (see _encode_value)
    evidence_quote TEXT,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.7,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    embedding vector(768),               -- HNSW index built; Gemini 768-d
    UNIQUE (user_id, kind, key)
  );

VALUE-COLUMN NOTE: the production table stores `value` as TEXT (not
JSONB). We JSON-encode dicts on write and JSON-decode on read so the
in-memory contract (Memory.value: dict) is preserved. If a row was
written by a non-Python caller as plain text, it round-trips as
{"text": "<raw>"} so callers don't crash on a string-vs-dict mismatch.

Cop-out #25-aware: nothing here ever names a brand or site. Memory is
generic; the cascade decides what to remember and the wearer's data only
flows out through their own user_id.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger("engine.memory")


# ─────────────────────────────────────────────────────────────────
# Memory record
# ─────────────────────────────────────────────────────────────────


@dataclass
class Memory:
    """One stored memory entry."""

    id: str
    user_id: str
    kind: str
    key: str
    value: dict
    importance: int = 3
    source_chunks: list = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


# ─────────────────────────────────────────────────────────────────
# Backend protocol
# ─────────────────────────────────────────────────────────────────


@runtime_checkable
class MemoryBackend(Protocol):
    async def upsert(self, mem: Memory) -> Memory: ...
    async def get_by_key(self, user_id: str, kind: str, key: str) -> Memory | None: ...
    async def recent(self, user_id: str, k: int = 10) -> list[Memory]: ...
    async def by_kind(self, user_id: str, kind: str, k: int = 50) -> list[Memory]: ...
    async def search(self, user_id: str, query: str, k: int = 5) -> list[Memory]: ...
    async def delete(self, user_id: str, kind: str, key: str) -> bool: ...


# ─────────────────────────────────────────────────────────────────
# In-process backend (tests / dev)
# ─────────────────────────────────────────────────────────────────


class InProcessMemoryBackend:
    """Dict-backed memory store; for unit tests and small local dev runs."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str, str], Memory] = {}
        self._lock = asyncio.Lock()

    async def upsert(self, mem: Memory) -> Memory:
        async with self._lock:
            primary = (mem.user_id, mem.kind, mem.key)
            existing = self._store.get(primary)
            if existing is None:
                new = Memory(
                    id=mem.id or uuid.uuid4().hex,
                    user_id=mem.user_id,
                    kind=mem.kind,
                    key=mem.key,
                    value=dict(mem.value or {}),
                    importance=int(mem.importance),
                    source_chunks=list(mem.source_chunks or []),
                    created_at=mem.created_at,
                    updated_at=mem.updated_at,
                )
                self._store[primary] = new
                return new
            # Merge — value dict union (empty new values don't overwrite),
            # source_chunks deduped, importance max
            merged_value = _merge_values(existing.value, mem.value or {})
            merged_chunks = list(existing.source_chunks)
            seen = {repr(c) for c in merged_chunks}
            for c in (mem.source_chunks or []):
                rc = repr(c)
                if rc not in seen:
                    seen.add(rc)
                    merged_chunks.append(c)
            updated = Memory(
                id=existing.id,
                user_id=mem.user_id,
                kind=mem.kind,
                key=mem.key,
                value=merged_value,
                importance=max(existing.importance, int(mem.importance)),
                source_chunks=merged_chunks,
                created_at=existing.created_at,
                updated_at=time.time(),
            )
            self._store[primary] = updated
            return updated

    async def get_by_key(self, user_id: str, kind: str, key: str) -> Memory | None:
        async with self._lock:
            return self._store.get((user_id, kind, key))

    async def recent(self, user_id: str, k: int = 10) -> list[Memory]:
        async with self._lock:
            mems = [m for (uid, _, _), m in self._store.items() if uid == user_id]
        mems.sort(key=lambda m: m.updated_at, reverse=True)
        return mems[: max(0, int(k))]

    async def by_kind(self, user_id: str, kind: str, k: int = 50) -> list[Memory]:
        async with self._lock:
            mems = [
                m for (uid, knd, _), m in self._store.items()
                if uid == user_id and knd == kind
            ]
        mems.sort(key=lambda m: m.updated_at, reverse=True)
        return mems[: max(0, int(k))]

    async def search(self, user_id: str, query: str, k: int = 5) -> list[Memory]:
        """Naive token-overlap ranking. The Supabase backend will use pgvector."""
        tokens = [t for t in (query or "").lower().split() if t]
        if not tokens:
            return []
        async with self._lock:
            scored: list[tuple[int, Memory]] = []
            for (uid, _, _), m in self._store.items():
                if uid != user_id:
                    continue
                blob = f"{m.key} {m.value}".lower()
                score = sum(1 for tok in tokens if tok in blob)
                if score > 0:
                    scored.append((score, m))
        scored.sort(key=lambda s: (s[0], s[1].importance, s[1].updated_at), reverse=True)
        return [m for _, m in scored[: max(0, int(k))]]

    async def delete(self, user_id: str, kind: str, key: str) -> bool:
        async with self._lock:
            return self._store.pop((user_id, kind, key), None) is not None


# ─────────────────────────────────────────────────────────────────
# Supabase backend (production)
# ─────────────────────────────────────────────────────────────────


def _merge_values(existing: dict, new: dict) -> dict:
    """Union of two value dicts. Empty values in `new` (None, "", [], {}) do
    NOT overwrite existing entries — that way calling
    `remember_person(name='Sarah', notes='likes italian')` after
    `remember_person(name='Sarah', relation='friend')` keeps relation='friend'
    instead of clobbering it with the default `relation=""`."""
    out = dict(existing)
    for k, v in (new or {}).items():
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        if isinstance(v, (list, dict)) and not v:
            continue
        out[k] = v
    return out


def _parse_iso_ts(value: Any) -> float:
    """Parse an ISO-8601 string from Supabase into a unix timestamp.
    Returns time.time() on any parse failure (memory still works, just
    with a slightly off updated_at)."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value:
        s = value.rstrip("Z")
        if value.endswith("Z"):
            s = s + "+00:00"
        try:
            return datetime.fromisoformat(s).timestamp()
        except (ValueError, TypeError):
            return time.time()
    return time.time()


def _decode_value(raw: Any) -> dict:
    """Turn a TEXT-stored value back into the dict the rest of the engine expects.

    The anticipy_memory.value column is TEXT. We always write JSON on the
    way in (`_encode_value`). On the way out we tolerate three shapes:
      - a real dict (legacy / direct REST insert): pass through
      - a JSON-encoded dict-string: parse it
      - any other string (free-text from a non-Python caller): wrap it as
        {"text": "<raw>"} so callers can still introspect with .get()
    """
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return {}
        if s.startswith("{") and s.endswith("}"):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
        # Plain text fallback — keeps the dict contract intact.
        return {"text": raw}
    return {}


def _encode_value(value: dict | None) -> str:
    """JSON-encode a value dict for the TEXT column. Empty dict → '{}'."""
    if not value:
        return "{}"
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        # Fall back to repr — guarantees the row writes; consumers will
        # see {"text": "<repr>"} on read.
        return json.dumps({"text": repr(value)})


def _row_to_memory(row: dict) -> Memory:
    """Hydrate a DB row into a Memory.

    Tolerates both the new anticipy_memory schema (TEXT value, confidence,
    no source_chunks/importance/updated_at) and the legacy in-process
    shape used by tests. Missing columns default sanely.
    """
    raw_value = row.get("value")
    value = _decode_value(raw_value) if raw_value is not None else {}

    # Map confidence (0..1 float) → importance (1..5 int) so the existing
    # public Memory dataclass field stays meaningful even when the row
    # only carries `confidence`. Round to nearest int, clamp to [1,5].
    if "importance" in row:
        importance = int(row.get("importance") or 3)
    elif "confidence" in row and row.get("confidence") is not None:
        try:
            c = float(row.get("confidence") or 0.5)
            importance = max(1, min(5, int(round(c * 5))))
        except (TypeError, ValueError):
            importance = 3
    else:
        importance = 3

    created_at = _parse_iso_ts(row.get("created_at"))
    updated_at = _parse_iso_ts(row.get("updated_at")) \
        if row.get("updated_at") is not None else created_at

    return Memory(
        id=str(row.get("id") or ""),
        user_id=str(row.get("user_id") or ""),
        kind=str(row.get("kind") or ""),
        key=str(row.get("key") or ""),
        value=value,
        importance=importance,
        source_chunks=row.get("source_chunks") or [],
        created_at=created_at,
        updated_at=updated_at,
    )


class SupabaseMemoryBackend:
    """Production backend. Uses the anticipy_memory table via supabase_client.

    Reads & writes are JSON-encoded for the TEXT value column. Search
    delegates to the anticipy_memory_topk RPC for real semantic recall;
    if no embeddings provider is configured (e.g. unit tests against this
    backend with no GOOGLE_API_KEY) it degrades to token-overlap on a
    recent-items window.

    On every successful upsert we fire-and-forget an embedding update so
    the row participates in future semantic searches. The user-facing
    write completes synchronously without waiting for the embedding.
    """

    TABLE = "anticipy_memory"
    SEARCH_RPC = "anticipy_memory_topk"

    def __init__(self, supabase_client_module: Any = None) -> None:
        if supabase_client_module is None:
            from app import supabase_client as _sc
            supabase_client_module = _sc
        self._sc = supabase_client_module

    def _row_for_write(self, mem: Memory) -> dict:
        # Map our Memory dataclass onto the anticipy_memory schema.
        # importance (1..5) → confidence (0..1) so the column stays
        # meaningful for non-Python writers.
        confidence = max(0.0, min(1.0, float(mem.importance) / 5.0))
        return {
            "id": mem.id or uuid.uuid4().hex,
            "user_id": mem.user_id,
            "kind": mem.kind,
            "key": mem.key,
            "value": _encode_value(mem.value),
            "confidence": confidence,
        }

    async def _embed_and_update(self, row_id: str, key: str, value: dict) -> None:
        """Best-effort: embed `key + value` and patch the row's `embedding`.

        Runs as a background task. Any failure is logged at debug level
        and swallowed so it never affects the user-visible upsert.
        """
        try:
            from app import embeddings
            text = f"{key} {json.dumps(value, ensure_ascii=False, default=str)}"
            vec = await embeddings.embed_one(text)
            if vec is None:
                logger.debug(
                    "memory embed skipped (no provider or failure) for id=%s", row_id,
                )
                return
            literal = embeddings.vector_to_pg_literal(vec)
            update = getattr(self._sc, "update_rows", None)
            if not callable(update):
                logger.debug("supabase_client.update_rows missing; skip embed update")
                return
            await update(self.TABLE, {"id": row_id}, {"embedding": literal})
        except Exception:
            logger.debug("memory embedding background update failed", exc_info=True)

    async def upsert(self, mem: Memory) -> Memory:
        row = self._row_for_write(mem)
        try:
            result = await self._sc.upsert_row(self.TABLE, row)
        except Exception:
            logger.exception("memory upsert raised")
            result = None

        # Fire-and-forget the embedding update. We only schedule it when
        # the row probably landed (result is not None) AND we're inside a
        # running event loop. Tests that don't want this to fire can pass
        # a stub supabase client whose update_rows is a no-op.
        if result is not None:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._embed_and_update(
                    row_id=row["id"], key=row["key"], value=mem.value or {},
                ))
            except RuntimeError:
                # No running loop (called from sync context) — skip silently.
                pass

        if result is None:
            return Memory(
                id=row["id"], user_id=row["user_id"], kind=row["kind"], key=row["key"],
                value=mem.value or {}, importance=mem.importance,
                source_chunks=list(mem.source_chunks or []),
            )
        return _row_to_memory(result if isinstance(result, dict) else row)

    async def get_by_key(self, user_id: str, kind: str, key: str) -> Memory | None:
        rows = await self._sc.select_rows(
            self.TABLE,
            filters={"user_id": user_id, "kind": kind, "key": key},
            limit=1,
        )
        if not rows:
            return None
        return _row_to_memory(rows[0])

    async def recent(self, user_id: str, k: int = 10) -> list[Memory]:
        rows = await self._sc.select_rows(
            self.TABLE,
            filters={"user_id": user_id},
            limit=max(50, int(k)),
        )
        mems = [_row_to_memory(r) for r in rows]
        mems.sort(key=lambda m: m.updated_at, reverse=True)
        return mems[: max(0, int(k))]

    async def by_kind(self, user_id: str, kind: str, k: int = 50) -> list[Memory]:
        rows = await self._sc.select_rows(
            self.TABLE,
            filters={"user_id": user_id, "kind": kind},
            limit=max(50, int(k)),
        )
        return [_row_to_memory(r) for r in rows]

    async def search(self, user_id: str, query: str, k: int = 5) -> list[Memory]:
        """Semantic search over anticipy_memory.embedding via the
        anticipy_memory_topk RPC. Falls back to token-overlap on the
        recent window if embeddings are unavailable (no key, quota, etc.).

        Returns Memory dataclasses sorted by descending similarity.
        """
        if not query or not query.strip():
            return []

        # Try semantic first.
        try:
            from app import embeddings
            qvec = await embeddings.embed_query(query)
        except Exception:
            logger.debug("embed_query raised in memory.search", exc_info=True)
            qvec = None

        if qvec is not None:
            try:
                rpc = getattr(self._sc, "call_rpc", None)
                if callable(rpc):
                    rows = await rpc(self.SEARCH_RPC, {
                        "p_user_id": user_id,
                        "p_query": embeddings.vector_to_pg_literal(qvec),
                        "p_k": int(k),
                    })
                    if rows:
                        return [_row_to_memory(r) for r in rows[: max(0, int(k))]]
                    # Empty result is a valid answer; only fall through to
                    # token-overlap when the RPC errored.
                    return []
            except Exception:
                logger.debug("memory_topk RPC raised; falling back", exc_info=True)

        # Fallback: token-overlap on recent window. Same logic as before
        # the embeddings rewrite — preserves utility when the embedding
        # provider is missing or the column hasn't been backfilled yet.
        candidates = await self.recent(user_id, k=200)
        tokens = [t for t in query.lower().split() if t]
        if not tokens:
            return []
        scored: list[tuple[int, Memory]] = []
        for m in candidates:
            blob = f"{m.key} {m.value}".lower()
            score = sum(1 for tok in tokens if tok in blob)
            if score > 0:
                scored.append((score, m))
        scored.sort(key=lambda s: (s[0], s[1].importance, s[1].updated_at), reverse=True)
        return [m for _, m in scored[: max(0, int(k))]]

    async def delete(self, user_id: str, kind: str, key: str) -> bool:
        # supabase_client doesn't expose DELETE today; we leave this as a
        # future hook so callers can plan for it.
        logger.info("delete not implemented for SupabaseMemoryBackend")
        return False


# ─────────────────────────────────────────────────────────────────
# MemoryStore — public façade with named-kind helpers
# ─────────────────────────────────────────────────────────────────


@dataclass
class MemoryStore:
    """Public façade over a memory backend.

    Provides typed helpers for the common kinds (person, place, preference,
    commitment, project, fact) so callers don't string-key by hand. All keys
    are lowercased + stripped before storage so case variation doesn't
    duplicate entries.
    """

    backend: MemoryBackend

    @staticmethod
    def _norm_key(s: str) -> str:
        return (s or "").strip().lower()

    async def remember_person(
        self,
        user_id: str,
        name: str,
        relation: str = "",
        notes: str = "",
        **extra: Any,
    ) -> Memory:
        return await self.backend.upsert(Memory(
            id="",
            user_id=user_id,
            kind="person",
            key=self._norm_key(name),
            value={"name": name, "relation": relation, "notes": notes, **extra},
        ))

    async def remember_place(
        self,
        user_id: str,
        name: str,
        kind_of_place: str = "",
        address: str = "",
        notes: str = "",
        **extra: Any,
    ) -> Memory:
        return await self.backend.upsert(Memory(
            id="",
            user_id=user_id,
            kind="place",
            key=self._norm_key(name),
            value={"name": name, "kind_of_place": kind_of_place, "address": address,
                   "notes": notes, **extra},
        ))

    async def remember_preference(
        self,
        user_id: str,
        key: str,
        value: Any,
        notes: str = "",
    ) -> Memory:
        return await self.backend.upsert(Memory(
            id="",
            user_id=user_id,
            kind="preference",
            key=self._norm_key(key),
            value={"value": value, "notes": notes},
        ))

    async def remember_commitment(
        self,
        user_id: str,
        what: str,
        with_whom: str = "",
        when: str = "",
        status: str = "open",
        notes: str = "",
    ) -> Memory:
        key_parts = [self._norm_key(what)]
        if with_whom:
            key_parts.append(self._norm_key(with_whom))
        return await self.backend.upsert(Memory(
            id="",
            user_id=user_id,
            kind="commitment",
            key=":".join(key_parts),
            value={"what": what, "with_whom": with_whom, "when": when,
                   "status": status, "notes": notes},
        ))

    async def remember_project(
        self,
        user_id: str,
        name: str,
        status: str = "active",
        notes: str = "",
    ) -> Memory:
        return await self.backend.upsert(Memory(
            id="",
            user_id=user_id,
            kind="project",
            key=self._norm_key(name),
            value={"name": name, "status": status, "notes": notes},
        ))

    async def remember_fact(
        self,
        user_id: str,
        topic: str,
        content: str,
    ) -> Memory:
        return await self.backend.upsert(Memory(
            id="",
            user_id=user_id,
            kind="fact",
            key=self._norm_key(topic),
            value={"topic": topic, "content": content},
        ))

    # ─── Recall helpers ──────────────────────────────────────────

    async def recall_person(self, user_id: str, name: str) -> Memory | None:
        return await self.backend.get_by_key(user_id, "person", self._norm_key(name))

    async def recall_place(self, user_id: str, name: str) -> Memory | None:
        return await self.backend.get_by_key(user_id, "place", self._norm_key(name))

    async def recall_preference(self, user_id: str, key: str) -> Memory | None:
        return await self.backend.get_by_key(user_id, "preference", self._norm_key(key))

    async def recall_recent(self, user_id: str, k: int = 10) -> list[Memory]:
        return await self.backend.recent(user_id, k)

    async def recall_kind(self, user_id: str, kind: str, k: int = 50) -> list[Memory]:
        return await self.backend.by_kind(user_id, kind, k)

    async def search(self, user_id: str, query: str, k: int = 5) -> list[Memory]:
        return await self.backend.search(user_id, query, k)


def make_memory_store(prefer_supabase: bool = True) -> MemoryStore:
    """Factory. Uses the Supabase backend when SUPABASE config is present,
    falls back to in-process otherwise."""
    if prefer_supabase:
        try:
            from app.config import SUPABASE_URL, SUPABASE_ANON_KEY
            if SUPABASE_URL and SUPABASE_ANON_KEY:
                return MemoryStore(backend=SupabaseMemoryBackend())
        except Exception:
            pass
    return MemoryStore(backend=InProcessMemoryBackend())
