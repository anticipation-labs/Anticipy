"""INJECT — the hot read path: hybrid retrieval -> rank -> dedupe -> budget.

For a moment's context query, combine four signals over the fuzzy drawers
(profile/history/derived): semantic (embeddings) + structured/keyword (incl.
people + fields) + recency + importance. Rank, dedupe, fit a char budget. The
open_loops ledger is NOT retrieval-dependent — ALL open/waiting loops are ALWAYS
surfaced (never drop a ball). Escalate to a smart model only when genuinely
ambiguous (seam; never fires in stub mode -> free).
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional

from ..memory.embed import embed
from ..memory.store import Memory, is_active_open_loop
from ..shared.schema import MemoryItem, now_ts

_TOK = re.compile(r"[a-z0-9]+")


def _toks(s: str) -> set:
    return set(_TOK.findall((s or "").lower()))

_FUZZY = ["profile_fact", "history", "derived"]

# Memory Fix 2 — semantic-confidence abstention. Abstain ("i don't know") when the best
# ACTIVE memory's cosine to the query falls below a calibrated floor. The signal is DERIVED
# from the real embedder's distance, NOT a number the model reports about itself. Mode-aware:
# bge-small (live) embeddings sit in a high-baseline cone (~0.5 even for unrelated text); the
# hash stub is sparse (~0). The live floor is fit on a HELD-OUT slice (disjoint from the eval)
# by Youden's J — never tuned to the eval set. Override per-run with ANTICIPY_ABSTAIN_FLOOR.
# live=0.66 fit on a held-out 20 _abs + 20 answerable slice (seed 999): J=0.60, TPR=0.75,
# FPR=0.15. stub=0.22 is a CI sanity value (deterministic test embedder), not calibrated.
ABSTAIN_FLOOR = {"live": 0.66, "stub": 0.22}


def abstain_floor(mode: str) -> float:
    return float(os.environ.get("ANTICIPY_ABSTAIN_FLOOR", ABSTAIN_FLOOR.get(mode, ABSTAIN_FLOOR["stub"])))


class Injector:
    def __init__(self, memory: Memory, gateway=None, char_budget: int = 2000,
                 k: int = 12, mode: Optional[str] = None) -> None:
        self.memory = memory
        self.gateway = gateway
        self.char_budget = char_budget
        self.k = k
        self.mode = mode or os.environ.get("ANTICIPY_MEMORY_MODE", "stub")

    def _kw(self, qtok: set, item: MemoryItem) -> float:
        if not qtok:
            return 0.0
        hay = _toks(item.text) | _toks(" ".join(item.people)) | _toks(" ".join(str(v) for v in item.fields.values()))
        return len(qtok & hay) / len(qtok)

    def inject(self, context: str = "", k: Optional[int] = None) -> Dict[str, object]:
        k = k or self.k
        qv = embed(context)
        qtok = _toks(context)

        # the deterministic ledger: ALL open/waiting loops, always (importance, recent first)
        loops = [i for i in self.memory.open_loops.all() if is_active_open_loop(i)]
        loops.sort(key=lambda i: (-i.importance, -i.timestamp))
        # DEDUP + VENT-GATE what the BRAIN actually sees (audit fix). The durable store can hold the
        # same loop many times (re-ingest) — the read endpoint collapsed them but inject did NOT, so the
        # brain saw "send sarah the deck" up to 11x and even vents leaked into its context. Collapse to
        # one per content key (sorted first, so the best copy wins) and never surface a vent-shaped loop.
        from .review_infer import is_vent_shape as _is_vent_shape
        def _loop_key(i):
            ck = (getattr(i, "fields", None) or {}).get("capture_key")
            return ck or " ".join((i.text or "").lower().split())
        _seen_keys, _deduped = set(), []
        for _i in loops:
            try:
                if _is_vent_shape(_i.text):
                    continue
            except Exception:
                pass
            _kk = _loop_key(_i)
            if _kk in _seen_keys:
                continue
            _seen_keys.add(_kk)
            _deduped.append(_i)
        loops = _deduped

        cos = dict(self.memory.db.scored(qv, _FUZZY))   # id -> cosine (stored embeddings)
        # never surface superseded/archived items (a changed fact's old version)
        cands = [i for i in (self.memory.profile.all() + self.memory.history.all() + self.memory.derived.all())
                 if i.status not in ("superseded", "archived")]
        now = now_ts()
        scored = []
        for it in cands:
            sem = cos.get(it.id, 0.0)
            kw = self._kw(qtok, it)
            if kw <= 0.0 and sem < 0.2:
                continue  # require genuine relevance (keyword or strong semantic), not importance/recency alone
            rec = 1.0 / (1.0 + max(0.0, (now - it.timestamp)) / 86400.0)
            score = 0.55 * sem + 0.30 * kw + 0.10 * rec + 0.05 * it.importance
            scored.append((score, it))
        scored.sort(key=lambda x: -x[0])
        ranked = [it for _, it in scored[:k]]

        # semantic confidence (Memory Fix 2): how well the BEST active memory matches the
        # query. Below the calibrated floor -> abstain instead of fabricating an answer.
        top_relevance = max((cos.get(it.id, 0.0) for it in cands), default=0.0)
        floor = abstain_floor(self.mode)
        abstain = top_relevance < floor

        ambiguous = len(scored) >= 2 and abs(scored[0][0] - scored[1][0]) < 0.05 and scored[0][0] < 0.4
        if self.mode == "live" and ambiguous and self.gateway:
            pass  # TODO(live): escalate to a smart model to disambiguate; never in tests

        # assemble within the char budget: loops first (the spine), then ranked items
        items: List[MemoryItem] = []
        parts: List[str] = []
        used = 0
        for it in loops + ranked:
            line = f"[{it.kind}] {it.text}"
            if used + len(line) + 1 <= self.char_budget:
                items.append(it)
                parts.append(line)
                used += len(line) + 1

        return {
            "context": context,
            "open_loops": loops,                                       # ALWAYS all open/waiting
            "profile": [i for i in ranked if i.kind == "profile_fact"],
            "history": [i for i in ranked if i.kind == "history"],
            "derived": [i for i in ranked if i.kind == "derived"],
            "items": items,
            "text": "\n".join(parts),
            "ambiguous": ambiguous,
            "top_relevance": top_relevance,   # derived semantic confidence (Memory Fix 2)
            "abstain": abstain,               # True -> "i don't know" (don't fabricate)
            "abstain_floor": floor,
            "smart_calls": 0,
            "stub": False,
        }
