"""LIFE_LOG: the demotion sink (Layer 4).

Everything the stack does NOT trust as an actionable wearer
instruction lands here: strangers, TV, about-you-not-to-you,
low-confidence spans, degraded-mode transcription. It is searchable
so the wearer can recall "what was said near me" and is never
blindsided, but it is explicitly NON-PROMOTABLE: nothing here can
become a durable fact or an action. Rows carry a decaying weight so
old low-confidence context fades instead of compounding (context
rot is the failure this layer exists to kill).

SQLite under data_dir so it is device-local and identical at scale.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_HALF_LIFE_S = 7 * 24 * 3600.0  # weight halves each week; tunable, fixed here


def _db_path() -> Path:
    from app.anticipy import platform_adapter

    return platform_adapter.data_dir() / "life_log.db"


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(_db_path()))
    c.execute(
        """CREATE TABLE IF NOT EXISTS life_log (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               ts REAL NOT NULL,
               speaker_id TEXT NOT NULL,
               text TEXT NOT NULL,
               reason TEXT NOT NULL,
               confidence REAL NOT NULL,
               category TEXT,
               promotable INTEGER NOT NULL DEFAULT 0,
               meta TEXT
           )"""
    )
    c.execute("CREATE INDEX IF NOT EXISTS ix_ll_text ON life_log(text)")
    c.execute("CREATE INDEX IF NOT EXISTS ix_ll_ts ON life_log(ts)")
    return c


@dataclass
class LifeLogRow:
    ts: float
    speaker_id: str
    text: str
    reason: str
    confidence: float
    category: Optional[str] = None
    meta: Optional[dict] = None


def demote(row: LifeLogRow) -> int:
    """Write a non-promotable low-trust row. promotable is HARD 0: this
    store has no API that can ever flip it, by construction.
    """
    c = _conn()
    try:
        cur = c.execute(
            "INSERT INTO life_log(ts,speaker_id,text,reason,confidence,"
            "category,promotable,meta) VALUES (?,?,?,?,?,?,0,?)",
            (row.ts or time.time(), row.speaker_id, row.text, row.reason,
             float(row.confidence), row.category,
             json.dumps(row.meta or {})),
        )
        c.commit()
        return int(cur.lastrowid)
    finally:
        c.close()


def _decayed(conf: float, age_s: float) -> float:
    return float(conf * (0.5 ** (max(0.0, age_s) / _HALF_LIFE_S)))


def search(query: str, limit: int = 50, now: Optional[float] = None) -> list[dict]:
    """Recall by substring. Returns rows with a current decayed_weight
    so stale low-confidence context is visibly faded, never promoted.
    """
    now = now if now is not None else time.time()
    c = _conn()
    try:
        rows = c.execute(
            "SELECT ts,speaker_id,text,reason,confidence,category,meta "
            "FROM life_log WHERE text LIKE ? ORDER BY ts DESC LIMIT ?",
            (f"%{query}%", int(limit)),
        ).fetchall()
    finally:
        c.close()
    out = []
    for ts, spk, text, reason, conf, cat, meta in rows:
        out.append({
            "ts": ts, "speaker_id": spk, "text": text, "reason": reason,
            "confidence": conf, "category": cat,
            "decayed_weight": _decayed(conf, now - ts),
            "promotable": False,
            "meta": json.loads(meta) if meta else {},
        })
    return out


def count(category: Optional[str] = None) -> int:
    c = _conn()
    try:
        if category is None:
            r = c.execute("SELECT COUNT(*) FROM life_log").fetchone()
        else:
            r = c.execute("SELECT COUNT(*) FROM life_log WHERE category=?",
                          (category,)).fetchone()
        return int(r[0]) if r else 0
    finally:
        c.close()


def promotable_invariant_holds() -> bool:
    """Behavioral guarantee, not a fragile source scan: this module
    exposes NO callable that could flip a row to promotable, and a
    freshly demoted row reads back promotable=0. The gate also
    independently reads the raw column to confirm.
    """
    import sys as _sys

    mod = _sys.modules[__name__]
    for nm in dir(mod):
        if nm.startswith("_"):
            continue
        obj = getattr(mod, nm)
        if callable(obj) and any(
            tok in nm.lower() for tok in ("promote", "set_promotable",
                                          "make_fact", "flip", "upgrade")
        ):
            return False  # an API that could promote exists -> invariant broken
    # behavioral: a demoted row is non-promotable at the storage layer
    import tempfile
    rid = demote(LifeLogRow(ts=1.0, speaker_id="S?", text="__invariant_probe__",
                            reason="probe", confidence=0.0, category=None))
    c = _conn()
    try:
        row = c.execute("SELECT promotable FROM life_log WHERE id=?", (rid,)).fetchone()
        c.execute("DELETE FROM life_log WHERE id=?", (rid,))
        c.commit()
    finally:
        c.close()
    return bool(row) and int(row[0]) == 0
