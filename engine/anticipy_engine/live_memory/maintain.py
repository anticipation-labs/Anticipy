"""MAINTAIN — the COLD batched sweep (idle / end-of-day, NOT per event).

Rare + amortized, so a bigger model is fine here later; the stub is deterministic
rules (zero model calls). Three jobs:
  - SUPERSEDE: when a newer profile fact updates the same subject (employer/name/
    location), mark the older one `superseded` (timestamped) — contradictions
    resolve toward the newest stated fact.
  - CONSOLIDATE: collapse near-duplicate episodes into one durable item (keep the
    newest, archive the rest, bump its importance) — re-dedupe across sources.
  - DECAY: archive old, low-importance history so stale clutter falls away.
The open_loops ledger is never touched here (commitments are deterministic and
close via explicit state changes, not decay).
"""
from __future__ import annotations

import os
import re
from typing import Dict, Optional

from ..memory.store import Memory
from ..shared.schema import now_ts

_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _WS.sub(" ", (s or "").strip().lower())


def _subject(text: str) -> Optional[str]:
    """Precise subject key for supersede — only facts that genuinely replace each
    other (employer/name/location). Preferences/roles return None (they coexist)."""
    t = text.lower()
    if re.search(r"work (at|for)", t):
        return "employer"
    if "name is" in t:
        return "name"
    if "live in" in t or "lives in" in t:
        return "location"
    return None


class Maintainer:
    def __init__(self, memory: Memory, gateway=None, mode: Optional[str] = None,
                 stale_days: float = 30.0) -> None:
        self.memory = memory
        self.gateway = gateway
        self.mode = mode or os.environ.get("ANTICIPY_MEMORY_MODE", "stub")
        self.stale_days = stale_days

    def _supersede(self) -> int:
        facts = [f for f in self.memory.profile.all() if f.status not in ("superseded", "archived")]
        groups: Dict[str, list] = {}
        for f in facts:
            s = _subject(f.text)
            if s:
                groups.setdefault(s, []).append(f)
        n = 0
        for group in groups.values():
            if len(group) <= 1:
                continue
            group.sort(key=lambda f: f.timestamp)
            for old in group[:-1]:                       # keep the newest active
                old.status = "superseded"
                self.memory.profile.update(old)          # stamps updated_at
                n += 1
        return n

    def _consolidate(self) -> int:
        items = [h for h in self.memory.history.all() if h.status not in ("archived", "superseded")]
        seen: Dict[str, object] = {}
        n = 0
        for h in sorted(items, key=lambda x: x.timestamp):
            key = _norm(h.text)
            if key in seen:
                older = seen[key]
                older.status = "archived"
                self.memory.history.update(older)
                h.importance = min(1.0, h.importance + 0.1)   # repetition => more durable
                self.memory.history.update(h)
                n += 1
            seen[key] = h
        return n

    def _decay(self) -> int:
        now = now_ts()
        cutoff = self.stale_days * 86400.0
        n = 0
        for h in self.memory.history.all():
            if h.status not in ("archived", "superseded") and (now - h.timestamp) > cutoff and h.importance < 0.5:
                h.status = "archived"
                self.memory.history.update(h)
                n += 1
        return n

    def _expire_raw(self, at: Optional[float] = None) -> int:
        """TIERED MEMORY (M4): prune the raw buffer. A low-salience episodic line was written
        with tier="raw" and a short validity window (M3 valid_to); once it is no longer valid it
        is archived, so the firehose can never bloat the durable store. Retrieval already hides
        it (is_valid_at) the instant it expires; this physically clears it in the cold sweep."""
        moment = now_ts() if at is None else at
        n = 0
        for h in self.memory.history.all():
            if h.status in ("archived", "superseded"):
                continue
            if (h.fields or {}).get("tier") == "raw" and not h.is_valid_at(moment):
                h.status = "archived"
                self.memory.history.update(h)
                n += 1
        return n

    def sweep(self, at: Optional[float] = None) -> Dict[str, object]:
        if self.mode == "live":
            pass  # TODO(live): a bigger model can do richer reflection here; rare + amortized.
        superseded = self._supersede()
        consolidated = self._consolidate()
        archived = self._decay()
        expired_raw = self._expire_raw(at=at)
        return {"ran": True, "superseded": superseded, "consolidated": consolidated,
                "archived": archived, "expired_raw": expired_raw, "smart_calls": 0}
