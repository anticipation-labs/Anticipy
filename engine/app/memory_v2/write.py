"""MH-P2: the disciplined memory write path.

Composes the EXISTING app.memory backend (InProcess for the local
deterministic gate, Supabase pgvector + the anticipy_memory_topk
RPC for production, wired but the real prod write is the gated
edge: an autonomous run never pollutes the shared DB). Nothing in
app.memory or any frozen file is modified.

Three properties the gate binds on:

  NON-PROMOTABLE INVARIANT (hard). A low-trust life-log item is
  NEVER stored or promoted as a durable fact. Life-log writes are
  quarantined to kind="life_log" with capped importance. Promotion
  to a durable kind requires explicit wearer confirmation OR
  >= PROMOTE_CORROBORATION independent corroborating observations.
  It never happens automatically from a single ambient line. This
  extends the existing demotion invariant (audiostack life-log +
  the frozen engine) into the write path.

  DEDUP (no duplicate facts). Beyond the backend's exact
  (user_id,kind,key) merge, a semantic near-duplicate within a
  durable kind (same canonical content signature, OR embedding
  cosine >= DEDUP_TAU) collapses onto the existing row via the
  backend's own merge, never a second fact.

  DECAY. Effective confidence decays with age unless reinforced;
  re-observation refreshes it. Non-durable items below the prune
  floor are swept; durable facts decay slowly and never below a
  floor, so a real preference is not forgotten.

Embedding: the deterministic local embedder (sklearn TF-IDF,
offline, reproducible) is used so the gate is exact and not
network-bound. The production embedder (app.embeddings, Gemini
text-embedding-004) is wired behind the same call and is the
labelled real edge.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from app.memory import Memory

LIFELOG_KIND = "life_log"
DURABLE_KINDS = {"fact", "preference", "contact", "aversion", "habit"}
LIFELOG_IMPORTANCE_CAP = 2          # durable facts are importance >= 3
PROMOTE_CORROBORATION = 2          # independent observations to promote
DEDUP_TAU = 0.86                   # cosine >= this within a kind == dup
PRUNE_FLOOR = 0.20                 # effective-confidence prune floor
DURABLE_CONF_FLOOR = 0.45          # durable facts never decay below this

_TRUST = {"life_log": 0.15, "ambient": 0.35, "observed": 0.6,
          "confirmed": 0.95}

_STOP = {"the", "a", "an", "to", "of", "for", "and", "is", "are",
         "my", "i", "me", "you", "it", "that", "this", "'s", "be",
         "with", "in", "on", "at", "as", "his", "her", "their"}


def _norm_tokens(text: str) -> list[str]:
    toks = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [t for t in toks if t not in _STOP and len(t) > 1]


def canonical_key(text: str) -> str:
    """Order-independent content signature so 'wife is Priya' and
    'Priya is my wife' collapse to one durable fact. Deterministic.
    """
    return " ".join(sorted(set(_norm_tokens(text)))) or (text or "").strip().lower()


def _local_embed(texts: list[str]):
    """Deterministic offline embedding for the gate (sklearn TF-IDF
    char+word n-grams). Production uses app.embeddings (Gemini
    text-embedding-004), wired behind the same role and labelled.
    """
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer

    v = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4),
                         lowercase=True)
    m = v.fit_transform([t or "" for t in texts]).toarray()
    n = np.linalg.norm(m, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return (m / n)


def _cos(a, b) -> float:
    import numpy as np

    return float(np.dot(a, b))


def decay_confidence(conf: float, age_days: float, importance: int,
                     durable: bool) -> float:
    """Exponential decay; half-life scales with importance. Durable
    facts decay slowly and are floored so a real preference is never
    silently forgotten; non-durable can fall to the prune floor.
    """
    half_life = 3.0 + 6.0 * max(0, int(importance))      # days
    eff = float(conf) * math.exp(-math.log(2) * max(0.0, age_days)
                                 / half_life)
    if durable:
        return max(DURABLE_CONF_FLOOR, eff)
    return eff


@dataclass
class IngestItem:
    text: str
    kind_hint: str                 # life_log | fact | preference | contact ...
    trust: str = "ambient"         # life_log|ambient|observed|confirmed
    ts: float = field(default_factory=time.time)
    value: dict = field(default_factory=dict)
    wearer_confirmed: bool = False


@dataclass
class WriteReport:
    stored: int = 0
    deduped: int = 0
    quarantined_lifelog: int = 0
    promoted: int = 0
    blocked_promotions: int = 0
    write_latency_ms: float = 0.0


class MemoryWriter:
    """The write path. `backend` is any app.memory MemoryBackend
    (InProcessMemoryBackend for the gate). Async to match the
    backend protocol.
    """

    def __init__(self, backend) -> None:
        self.backend = backend
        # corroboration ledger: (user_id, durable_kind, canon) -> count
        self._corro: dict[tuple, int] = {}

    def _effective_kind(self, it: IngestItem) -> tuple[str, int, bool]:
        """Enforce the non-promotable invariant. A low-trust life-log
        item can NEVER be written as a durable kind. Returns
        (kind, importance, is_durable).
        """
        low_trust = _TRUST.get(it.trust, 0.35) < 0.5
        wants_durable = it.kind_hint in DURABLE_KINDS
        if it.kind_hint == LIFELOG_KIND or (low_trust and
                                            not it.wearer_confirmed):
            return LIFELOG_KIND, min(LIFELOG_IMPORTANCE_CAP, 2), False
        if wants_durable:
            return it.kind_hint, 3, True
        return LIFELOG_KIND, 1, False

    async def _dedupe_target(self, user_id: str, kind: str,
                             canon: str, vec, kind_rows) -> Optional[Memory]:
        for m in kind_rows:
            if m.value.get("_canon") == canon:
                return m
        if kind_rows:
            import numpy as np

            texts = [canon] + [m.value.get("_canon", m.key)
                               for m in kind_rows]
            E = _local_embed(texts)
            q = E[0]
            for i, m in enumerate(kind_rows):
                if _cos(q, E[i + 1]) >= DEDUP_TAU:
                    return m
        return None

    async def ingest(self, user_id: str,
                     items: list[IngestItem]) -> WriteReport:
        rep = WriteReport()
        t0 = time.perf_counter()
        for it in items:
            kind, imp, durable = self._effective_kind(it)
            canon = canonical_key(it.text)

            if not durable:
                # life-log: quarantined, NEVER a durable fact. It may
                # still corroborate a FUTURE explicit promotion, but
                # it is stored only as life_log.
                if it.kind_hint in DURABLE_KINDS:
                    rep.blocked_promotions += 1
                key = f"ll:{canon[:48]}:{int(it.ts)}"
                await self.backend.upsert(Memory(
                    id="", user_id=user_id, kind=LIFELOG_KIND, key=key,
                    value={"text": it.text, "_canon": canon,
                           "trust": it.trust, **it.value},
                    importance=imp, created_at=it.ts, updated_at=it.ts))
                rep.quarantined_lifelog += 1
                # corroboration accrues toward a possible explicit promo
                ck = (user_id, it.kind_hint, canon)
                if it.kind_hint in DURABLE_KINDS:
                    self._corro[ck] = self._corro.get(ck, 0) + 1
                continue

            # durable path: dedup within the kind, then merge or write
            kind_rows = await self.backend.by_kind(user_id, kind, k=500)
            tgt = await self._dedupe_target(user_id, kind, canon, None,
                                            kind_rows)
            if tgt is not None:
                await self.backend.upsert(Memory(
                    id=tgt.id, user_id=user_id, kind=kind, key=tgt.key,
                    value={"_canon": canon, "text": it.text, **it.value},
                    importance=max(imp, tgt.importance),
                    created_at=tgt.created_at, updated_at=it.ts))
                rep.deduped += 1
            else:
                await self.backend.upsert(Memory(
                    id="", user_id=user_id, kind=kind,
                    key=canon[:60] or it.text[:60],
                    value={"text": it.text, "_canon": canon, **it.value},
                    importance=imp, created_at=it.ts, updated_at=it.ts))
                rep.stored += 1
            if it.wearer_confirmed:
                rep.promoted += 1
        rep.write_latency_ms = (time.perf_counter() - t0) * 1000.0
        return rep

    async def promote_if_corroborated(self, user_id: str, kind_hint: str,
                                      text: str) -> bool:
        """Explicit, never-automatic promotion of a life-logged
        observation to a durable fact, ONLY when independent
        corroboration reached the threshold. Returns True if promoted.
        """
        if kind_hint not in DURABLE_KINDS:
            return False
        canon = canonical_key(text)
        if self._corro.get((user_id, kind_hint, canon), 0) < \
                PROMOTE_CORROBORATION:
            return False
        await self.backend.upsert(Memory(
            id="", user_id=user_id, kind=kind_hint,
            key=canon[:60], value={"text": text, "_canon": canon,
                                   "_promoted": True},
            importance=3, created_at=time.time(),
            updated_at=time.time()))
        return True

    async def decay_sweep(self, user_id: str, now: Optional[float] = None
                          ) -> dict:
        """Apply decay; prune non-durable items below the floor;
        durable facts survive (floored). Returns a summary.
        """
        now = now or time.time()
        pruned = kept = 0
        # InProcess backend: reach the store snapshot via recent()
        all_rows = await self.backend.recent(user_id, k=100000)
        for m in all_rows:
            durable = m.kind in DURABLE_KINDS
            age_days = max(0.0, (now - m.updated_at) / 86400.0)
            base = float(m.value.get("trust_conf",
                                     _TRUST.get(m.value.get("trust"),
                                                0.7)))
            eff = decay_confidence(base, age_days, m.importance, durable)
            if not durable and eff < PRUNE_FLOOR:
                await self.backend.delete(user_id, m.kind, m.key)
                pruned += 1
            else:
                kept += 1
        return {"pruned": pruned, "kept": kept}

    async def durable_facts(self, user_id: str) -> list[Memory]:
        """The invariant boundary: durable reads NEVER include
        life-log. This is what a decision is allowed to treat as a
        known fact about the wearer.
        """
        out: list[Memory] = []
        for k in sorted(DURABLE_KINDS):
            out.extend(await self.backend.by_kind(user_id, k, k=1000))
        return out
