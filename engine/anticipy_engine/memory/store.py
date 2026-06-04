"""Local-first memory: four drawers in one SQLite db + a small local vector index.

Drawers (isolated by `kind`, never merged):
  - profile   (profile_fact) : slow-changing facts about the user + their people.
  - open_loops (open_loop)   : the DETERMINISTIC ledger of commitments. Exact
                               structured records with state (open|waiting|done);
                               retrievable without embeddings — never silently lost.
  - history   (history)      : timestamped episodic append-log, embedded for recall.
  - derived   (derived)      : inferred facts WITH confidence; kept separate from
                               stated facts, never promoted.

Storage is boring + swappable: structured records (incl. the ledger) live in
SQLite; each row carries its embedding (JSON) and the vector "index" is a cosine
scan over the relevant kinds (fine at single-user scale; swap for sqlite-vec later).
Default data dir is ``.anticipy-data/`` (gitignored), override ANTICIPY_DATA_DIR.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import List, Optional

from ..shared.schema import MemoryItem, MemoryKind, now_ts
from .embed import cosine, embed

_COLS = ("id", "kind", "text", "fields", "people", "timestamp", "updated_at",
         "provenance", "confidence", "importance", "status", "embedding")


def _default_data_dir() -> Path:
    return Path(os.environ.get("ANTICIPY_DATA_DIR", ".anticipy-data")).expanduser()


class MemoryDB:
    """One SQLite db holding every drawer's rows + their embeddings."""

    def __init__(self, data_dir: Path) -> None:
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = data_dir / "memory.db"
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS items("
            "id TEXT PRIMARY KEY, kind TEXT, text TEXT, fields TEXT, people TEXT, "
            "timestamp REAL, updated_at REAL, provenance TEXT, confidence REAL, "
            "importance REAL, status TEXT, embedding TEXT)"
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_kind ON items(kind)")
        self.conn.commit()

    @staticmethod
    def _row_to_item(r: sqlite3.Row) -> MemoryItem:
        return MemoryItem(
            id=r["id"], kind=r["kind"], text=r["text"], fields=json.loads(r["fields"] or "{}"),
            people=json.loads(r["people"] or "[]"), timestamp=r["timestamp"], updated_at=r["updated_at"],
            provenance=r["provenance"], confidence=r["confidence"], importance=r["importance"],
            status=r["status"],
        )

    def upsert(self, item: MemoryItem, embedding: List[float]) -> None:
        self.conn.execute(
            f"INSERT OR REPLACE INTO items({','.join(_COLS)}) VALUES ({','.join('?' * len(_COLS))})",
            (item.id, item.kind, item.text, json.dumps(item.fields), json.dumps(item.people),
             item.timestamp, item.updated_at, item.provenance, item.confidence, item.importance,
             item.status, json.dumps(embedding)),
        )
        self.conn.commit()

    def get(self, item_id: str) -> Optional[MemoryItem]:
        r = self.conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
        return self._row_to_item(r) if r else None

    def by_kind(self, kind: MemoryKind) -> List[MemoryItem]:
        rows = self.conn.execute("SELECT * FROM items WHERE kind=? ORDER BY timestamp", (kind,))
        return [self._row_to_item(r) for r in rows]

    def clear(self, kind: Optional[MemoryKind] = None) -> None:
        if kind is None:
            self.conn.execute("DELETE FROM items")
        else:
            self.conn.execute("DELETE FROM items WHERE kind=?", (kind,))
        self.conn.commit()

    def scored(self, query_vec: List[float], kinds: List[str]):
        """(id, cosine) for every embedded item in the given kinds, best first."""
        if not kinds:
            return []
        q = "SELECT id, embedding FROM items WHERE kind IN (%s)" % ",".join("?" * len(kinds))
        out = []
        for r in self.conn.execute(q, tuple(kinds)):
            emb = json.loads(r["embedding"] or "[]")
            if emb:
                out.append((r["id"], cosine(query_vec, emb)))
        out.sort(key=lambda x: -x[1])
        return out

    def vector_rank(self, query_vec: List[float], kinds: List[str], k: int) -> List[MemoryItem]:
        return [self.get(i) for i, _ in self.scored(query_vec, kinds)[:k]]

    def reindex(self) -> int:
        """One-shot: re-embed every stored row under the CURRENT embed() (e.g. after
        flipping ANTICIPY_MEMORY_MODE stub->live, or swapping models). Returns row count."""
        rows = self.conn.execute("SELECT id, text FROM items").fetchall()
        for r in rows:
            self.conn.execute("UPDATE items SET embedding=? WHERE id=?",
                              (json.dumps(embed(r["text"])), r["id"]))
        self.conn.commit()
        return len(rows)


class MemoryStore:
    """A single drawer. Reads/writes only items of its ``kind`` (isolation)."""

    def __init__(self, name: str, kind: MemoryKind, db: MemoryDB) -> None:
        self.name = name
        self.kind = kind
        self.db = db

    def all(self) -> List[MemoryItem]:
        return self.db.by_kind(self.kind)

    def get(self, item_id: str) -> Optional[MemoryItem]:
        item = self.db.get(item_id)
        return item if item and item.kind == self.kind else None  # never cross drawers

    def write(self, item: MemoryItem) -> MemoryItem:
        item.kind = self.kind  # stores stamp their own kind; never cross-contaminate
        self.db.upsert(item, embed(item.text))
        return item

    def write_text(self, text: str, people: Optional[List[str]] = None, **fields) -> MemoryItem:
        return self.write(MemoryItem(kind=self.kind, text=text, people=people or [], **fields))

    def update(self, item: MemoryItem) -> MemoryItem:
        """Re-persist an existing item (e.g. an open_loop state change). Stamps updated_at."""
        item.updated_at = now_ts()
        self.db.upsert(item, embed(item.text))
        return item

    def clear(self) -> None:
        self.db.clear(self.kind)


class Memory:
    """Facade over the four separate drawers + the shared vector index."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        base = Path(data_dir) if data_dir else _default_data_dir()
        self.db = MemoryDB(base)
        self.profile = MemoryStore("profile", "profile_fact", self.db)
        self.open_loops = MemoryStore("open_loops", "open_loop", self.db)
        self.history = MemoryStore("history", "history", self.db)
        self.derived = MemoryStore("derived", "derived", self.db)
        self.data_dir = base

    def drawer(self, kind: MemoryKind) -> MemoryStore:
        return {"profile_fact": self.profile, "open_loop": self.open_loops,
                "history": self.history, "derived": self.derived}[kind]

    def search_vec(self, query: str, kinds: List[str], k: int = 8) -> List[MemoryItem]:
        """Semantic leg of retrieval: cosine over the local index for the given kinds."""
        return self.db.vector_rank(embed(query), kinds, k)

    def reindex(self) -> int:
        """One-shot re-embed of every drawer under the current embed() (stub<->live)."""
        return self.db.reindex()
