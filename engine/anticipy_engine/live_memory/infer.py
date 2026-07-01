"""INFER — derive routines / recurring people as DERIVED facts (mostly COLD).

Patterns across the episodic log become DERIVED facts WITH a confidence score and
provenance='inferred'. They live ONLY in the derived drawer and are NEVER promoted
to stated profile facts (confidence stays < 1.0). Idempotent: re-running updates
the same signal rather than duplicating. Deterministic in stub (zero model calls);
a model can enrich this later behind the flag.
"""
from __future__ import annotations

import os
import re
from collections import Counter
from typing import Dict, List, Optional

from ..memory.store import Memory
from ..shared.schema import MemoryItem

_STOP = {"the", "a", "an", "to", "and", "of", "in", "on", "for", "with", "at", "this",
         "that", "my", "is", "are", "was", "were", "be", "about", "after", "before",
         "again", "today", "then", "so", "but", "or", "as", "by", "from", "we", "they",
         "you", "me", "him", "her", "them", "up", "out", "over", "had", "has", "have",
         "did", "got", "get", "went", "going", "just", "some", "any", "all", "now"}


def _content(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z]+", (text or "").lower()) if len(t) >= 3 and t not in _STOP]


class Inferrer:
    def __init__(self, memory: Memory, gateway=None, mode: Optional[str] = None,
                 min_count: int = 3, max_conf: float = 0.9) -> None:
        self.memory = memory
        self.gateway = gateway
        self.mode = mode or os.environ.get("ANTICIPY_MEMORY_MODE", "stub")
        self.min_count = min_count
        self.max_conf = max_conf

    def _conf(self, count: int) -> float:
        return round(min(self.max_conf, count / (count + 1)), 2)   # always < 1.0; grows with evidence

    def _upsert(self, signal: str, text: str, count: int) -> MemoryItem:
        conf = self._conf(count)
        for d in self.memory.derived.all():
            if d.fields.get("signal") == signal:            # idempotent: update, don't duplicate
                d.text = text
                d.fields = {"signal": signal, "count": count}
                d.confidence = conf
                self.memory.derived.update(d)
                return d
        item = MemoryItem(kind="derived", text=text, fields={"signal": signal, "count": count},
                          provenance="inferred", confidence=conf, status="active")
        self.memory.derived.write(item)
        return item

    def infer(self) -> Dict[str, object]:
        if self.mode == "live":
            pass  # TODO(live): a model can derive richer routines/relationships; mostly cold.
        episodes = [h for h in self.memory.history.all() if h.status not in ("archived", "superseded")]

        # REFLECTION CONTRADICTOR (M6): a routine is only real if it recurs across DISTINCT
        # episodes. The raw episodic log can hold the SAME line many times (re-ingest / echo), which
        # would inflate a single mention into a fake "routine". So we count support over episodes
        # DEDUPED by normalized text, and we EXCLUDE vent-shaped lines entirely (a vent must never
        # harden into an inferred fact — the cardinal-sin guard on the reflection path). This is a
        # different-family check than the min_count threshold: it attacks the evidence, not the tally.
        from .review_infer import is_vent_shape as _is_vent_shape

        def _norm(t: str) -> str:
            return " ".join((t or "").lower().split())

        seen_norm = set()
        distinct: List[MemoryItem] = []
        for h in episodes:
            try:
                if _is_vent_shape(h.text):
                    continue
            except Exception:
                pass
            key = _norm(h.text)
            if key in seen_norm:
                continue
            seen_norm.add(key)
            distinct.append(h)

        topic_df: Counter = Counter()       # DISTINCT-episode frequency of content tokens
        for h in distinct:
            for tok in set(_content(h.text)):
                topic_df[tok] += 1
        people_c: Counter = Counter()
        for h in distinct:
            for p in h.people:
                people_c[p] += 1

        created = 0
        for tok, c in topic_df.items():
            if c >= self.min_count:
                self._upsert(f"routine:{tok}", f"Recurring topic/routine: {tok} (seen {c}x).", c)
                created += 1
        for p, c in people_c.items():
            if c >= self.min_count:
                self._upsert(f"person:{p.lower()}", f"{p} recurs in the user's life (seen {c}x).", c)
                created += 1

        return {"ran": True, "created": created, "smart_calls": 0}
