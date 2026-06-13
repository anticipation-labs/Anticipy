"""REMEMBER — the inert, pull-only commitment list (the SAFE half of the core).

This is deliberately NOT the open_loops ledger and NOT a memory drawer. It is a
SEPARATE sqlite table (``remembered_lines``) that the decision pipeline can never
reach:

  - it is NOT a ``MemoryKind`` (the shared schema's runtime-enforced Literal stays
    untouched), so no kind-scan in inject/infer/maintain/selfcheck can enumerate it;
  - it is NOT registered in ``Memory.drawer()`` and is NOT in inject's ``_FUZZY``;
  - it carries NO due_ts / remind_ts / trigger / status / fired_at — the only fields
    the TriggerWatcher (``trigger.py``) and ``list_open_loops`` ever read — so it can
    NEVER fire a reminder or an action;
  - it is read ONLY by the explicit PULL accessor here (``recent`` / ``all``), which is
    wired to a read-only GET endpoint and is on NO background loop.

Because a wrongly-remembered sarcastic/vent line just sits in a list the owner skims,
capture into this store is allowed to be GENEROUS (high recall) — over-capture is
harmless precisely because the store is provably inert. The cardinal sin (acting OR
asking on a vent, even via a DELAYED reminder) is impossible here: there is nothing in
this store that any firing path reads.

The table lives in the SAME sqlite file as the four drawers (one db, one place to
back up) but is a DISTINCT table — it shares no rows with ``items`` and is never wiped
by ``items``-level clear() or re-embedded by reindex().
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Dict, List, Optional

from ..memory.store import MemoryDB

# The EXACT columns. Note what is ABSENT and must stay absent: there is no due_ts,
# remind_ts, trigger, status, fired_at, or any time-to-fire field. Adding any of those
# is what would make this list actionable — so it is structurally impossible here.
_REMEMBER_COLS = ("id", "text", "ts", "source", "people")


class RememberList:
    """An inert, append-only, pull-only list of remembered commitment candidates.

    Owns its OWN table in the shared :class:`MemoryDB`. Exposes exactly two surfaces:
    ``remember(...)`` (generous fire-and-forget write) and ``recent``/``all`` (the pull).
    It deliberately has no method that schedules, fires, notifies, or marks-due anything.
    """

    def __init__(self, db: MemoryDB) -> None:
        self.db = db
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        # Reuse the MemoryDB connection + lock; a DISTINCT table so no items-level
        # scan, drawer(), reindex(), or clear() can ever touch these rows.
        with self.db._lock:
            self.db.conn.execute(
                "CREATE TABLE IF NOT EXISTS remembered_lines("
                "id TEXT PRIMARY KEY, text TEXT, ts REAL, source TEXT, people TEXT)"
            )
            self.db.conn.commit()

    def remember(self, text: str, source: str = "",
                 meta: Optional[Dict[str, object]] = None,
                 people: Optional[List[str]] = None) -> Optional[Dict[str, object]]:
        """Append a remembered line. GENEROUS + append-only; NO trigger fields ever.

        Returns the stored row dict (handy for tests) or None if the text was empty.
        This is intended to be called fire-and-forget from the capture hot path; it
        never returns into the capture decision dict and never raises that path.
        """
        t = (text or "").strip()
        if not t:
            return None
        row = {
            "id": uuid.uuid4().hex,
            "text": t,
            "ts": time.time(),
            "source": source or "",
            "people": list(people or []),
        }
        with self.db._lock:
            self.db.conn.execute(
                f"INSERT INTO remembered_lines({','.join(_REMEMBER_COLS)}) "
                f"VALUES ({','.join('?' * len(_REMEMBER_COLS))})",
                (row["id"], row["text"], row["ts"], row["source"], json.dumps(row["people"])),
            )
            self.db.conn.commit()
        return row

    @staticmethod
    def _row_to_dict(r) -> Dict[str, object]:
        return {
            "id": r["id"],
            "text": r["text"],
            "ts": r["ts"],
            "source": r["source"],
            "people": json.loads(r["people"] or "[]"),
        }

    def all(self) -> List[Dict[str, object]]:
        """The full remembered list, newest first. PULL-ONLY (no side effects)."""
        with self.db._lock:
            rows = self.db.conn.execute(
                "SELECT id, text, ts, source, people FROM remembered_lines ORDER BY ts DESC"
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def recent(self, limit: int = 50) -> List[Dict[str, object]]:
        """The most recent remembered lines, newest first. PULL-ONLY (no side effects)."""
        lim = max(0, int(limit))
        with self.db._lock:
            rows = self.db.conn.execute(
                "SELECT id, text, ts, source, people FROM remembered_lines "
                "ORDER BY ts DESC LIMIT ?",
                (lim,),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def count(self) -> int:
        with self.db._lock:
            r = self.db.conn.execute("SELECT COUNT(*) AS n FROM remembered_lines").fetchone()
        return int(r["n"] if r else 0)
