"""
SQLite-backed prompt cache for the LLM router.

Per B477 lesson (jsonl files grow unbounded), the cache uses SQLite at
``~/.anticipy/v7/llm_cache.db``. Cache key is the SHA256 hash of
(task_type, model, prompt-canonical-json). TTL is 24h for grounded
lookups (Perplexity Sonar) and 1h for everything else.

Cache also doubles as the per-user budget tracker (see budget.py for the
user-facing API). Both tables live in the same DB to avoid two file handles.

Public API:

    cache_get(task_type, model, messages) -> dict or None
    cache_put(task_type, model, messages, response_dict, ttl_seconds=None)
    cache_stats() -> dict with hit / miss / size totals
    cache_reset()  # for tests

NOT thread-safe across processes. Multi-engine launches MUST point each
instance at a separate db file via ``ANTICIPY_LLM_CACHE_DB`` env var.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional


logger = logging.getLogger("engine.llm_router.cache")


DEFAULT_DB_PATH: Path = (
    Path(os.environ.get("ANTICIPY_LLM_CACHE_DB", "")).expanduser()
    if os.environ.get("ANTICIPY_LLM_CACHE_DB")
    else Path.home() / ".anticipy" / "v7" / "llm_cache.db"
)


# Default TTLs in seconds.
TTL_GROUNDED = 24 * 60 * 60  # 24h for trivia_lookup / perplexity-sonar
TTL_DEFAULT = 60 * 60        # 1h for everything else


_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_cache (
    key TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,
    model TEXT NOT NULL,
    response_json TEXT NOT NULL,
    expires_at REAL NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_llm_cache_expires ON llm_cache(expires_at);

CREATE TABLE IF NOT EXISTS llm_cache_stats (
    name TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO llm_cache_stats(name, value) VALUES ('hit', 0), ('miss', 0);

CREATE TABLE IF NOT EXISTS llm_budget_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at REAL NOT NULL,
    user_id TEXT NOT NULL,
    task_type TEXT NOT NULL,
    model TEXT NOT NULL,
    cost_usd REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_budget_log_user_time
    ON llm_budget_log(user_id, occurred_at);
"""


# Per-process lock; sqlite3 is fine across threads in this module because
# we hold the lock while talking to the DB.
_LOCK = threading.RLock()
_DB_PATH_OVERRIDE: Optional[Path] = None


def _db_path() -> Path:
    if _DB_PATH_OVERRIDE is not None:
        return _DB_PATH_OVERRIDE
    return DEFAULT_DB_PATH


def set_db_path(path: Path | str | None) -> None:
    """Override the DB path. Used by tests; pass None to revert."""
    global _DB_PATH_OVERRIDE
    if path is None:
        _DB_PATH_OVERRIDE = None
    else:
        _DB_PATH_OVERRIDE = Path(path).expanduser()


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(_SCHEMA)
    return conn


def _canonical_key(task_type: str, model: str, messages: list[dict]) -> str:
    """SHA256-hash the canonical JSON of (task_type, model, messages)."""
    payload = {
        "task_type": task_type,
        "model": model,
        "messages": messages,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def cache_get(task_type: str, model: str, messages: list[dict]) -> dict | None:
    """Return the cached response dict or None if miss / expired.

    On hit, bumps the ``hit`` stat. On miss, bumps the ``miss`` stat. Expired
    rows are deleted in-line (lazy expiry, no separate sweeper).
    """
    key = _canonical_key(task_type, model, messages)
    now = time.time()
    with _LOCK:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT response_json, expires_at FROM llm_cache WHERE key = ?",
                (key,),
            ).fetchone()
            if not row:
                conn.execute(
                    "UPDATE llm_cache_stats SET value = value + 1 WHERE name = 'miss'"
                )
                conn.commit()
                return None
            response_json, expires_at = row
            if expires_at < now:
                # Expired; delete and treat as miss.
                conn.execute("DELETE FROM llm_cache WHERE key = ?", (key,))
                conn.execute(
                    "UPDATE llm_cache_stats SET value = value + 1 WHERE name = 'miss'"
                )
                conn.commit()
                return None
            conn.execute(
                "UPDATE llm_cache_stats SET value = value + 1 WHERE name = 'hit'"
            )
            conn.commit()
            return json.loads(response_json)
        finally:
            conn.close()


def cache_put(
    task_type: str,
    model: str,
    messages: list[dict],
    response: dict,
    ttl_seconds: int | None = None,
) -> None:
    """Insert a response into the cache. TTL defaults by task type."""
    if ttl_seconds is None:
        ttl_seconds = TTL_GROUNDED if task_type == "trivia_lookup" else TTL_DEFAULT
    key = _canonical_key(task_type, model, messages)
    now = time.time()
    expires = now + ttl_seconds
    payload = json.dumps(response, ensure_ascii=False, default=str)
    with _LOCK:
        conn = _connect()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO llm_cache "
                "(key, task_type, model, response_json, expires_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (key, task_type, model, payload, expires, now),
            )
            conn.commit()
        finally:
            conn.close()


def cache_stats() -> dict:
    """Return current hit, miss, and row count stats."""
    with _LOCK:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT name, value FROM llm_cache_stats"
            ).fetchall()
            stats = {name: int(value) for name, value in rows}
            (rowcount,) = conn.execute(
                "SELECT COUNT(*) FROM llm_cache"
            ).fetchone()
            stats["rows"] = int(rowcount)
            return stats
        finally:
            conn.close()


def cache_reset() -> None:
    """Wipe the cache + stats. Used by tests."""
    with _LOCK:
        conn = _connect()
        try:
            conn.execute("DELETE FROM llm_cache")
            conn.execute("UPDATE llm_cache_stats SET value = 0")
            conn.execute("DELETE FROM llm_budget_log")
            conn.commit()
        finally:
            conn.close()


# --- Budget log helpers (shared DB) -----------------------------------------
#
# Living in cache.py keeps the file handle count low. budget.py imports these.


def budget_log_insert(user_id: str, task_type: str, model: str, cost_usd: float) -> None:
    """Append a row to llm_budget_log."""
    now = time.time()
    with _LOCK:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO llm_budget_log "
                "(occurred_at, user_id, task_type, model, cost_usd) "
                "VALUES (?, ?, ?, ?, ?)",
                (now, str(user_id or "_anon"), task_type, model, float(cost_usd)),
            )
            conn.commit()
        finally:
            conn.close()


def budget_log_sum(user_id: str, since_seconds_ago: float) -> float:
    """Sum cost_usd for ``user_id`` over the last ``since_seconds_ago`` seconds."""
    cutoff = time.time() - since_seconds_ago
    with _LOCK:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_budget_log "
                "WHERE user_id = ? AND occurred_at >= ?",
                (str(user_id or "_anon"), cutoff),
            ).fetchone()
            return float(row[0] or 0.0)
        finally:
            conn.close()


__all__ = [
    "cache_get",
    "cache_put",
    "cache_stats",
    "cache_reset",
    "set_db_path",
    "budget_log_insert",
    "budget_log_sum",
    "TTL_GROUNDED",
    "TTL_DEFAULT",
    "DEFAULT_DB_PATH",
]
