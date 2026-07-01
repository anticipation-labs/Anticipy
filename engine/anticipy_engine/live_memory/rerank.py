"""RERANK — the cheap cross-check-the-moment seam (M6), with a built-in contradictor.

The base ranker (inject.py) scores candidates by semantic + keyword + recency + importance and
takes the top-k. Rerank is a SECOND, moment-aware pass over a WIDER candidate window that pulls
the item that best matches THIS moment (exact structured/people/phrase overlap) to the front, so
the most on-point memory survives the char budget and leads the prompt.

The danger with any reranker is that it demotes a genuinely-needed item out of the top-k (recall
loss). So rerank ships with its CONTRADICTOR wired in: the reordered top-k is accepted ONLY if it
still contains every item the base ranker had in ITS top-k (recall@k held vs the base). If the
rerank would drop a base-top-k item, it is REJECTED and we fall back to the base order — recall is
safe by construction, and the contradictor is a real gate that can fire.

Deterministic in stub (a heuristic moment-match); a cheap cross-encoder can supply the bonus in
live mode behind the flag. Zero model calls on the default path.
"""
from __future__ import annotations

import re
from typing import List, Optional, Set, Tuple

from ..shared.schema import MemoryItem

_TOK = re.compile(r"[a-z0-9]+")


def _toks(s: str) -> Set[str]:
    return set(_TOK.findall((s or "").lower()))


def moment_bonus(qtok: Set[str], item: MemoryItem) -> float:
    """A small, moment-specific boost on TOP of the base score. Rewards structured overlap the
    bag-of-words base ranker under-weights: a query token naming a PERSON or hitting a structured
    FIELD value is a stronger 'this is the one' signal than a plain text token match."""
    if not qtok:
        return 0.0
    text_hits = len(qtok & _toks(item.text))
    people_hits = len(qtok & _toks(" ".join(item.people)))
    field_hits = len(qtok & _toks(" ".join(str(v) for v in (item.fields or {}).values())))
    # people/field matches weigh more than plain text; scaled small so it reorders, not dominates.
    return 0.02 * text_hits + 0.08 * people_hits + 0.06 * field_hits


def recall_held(base_ids: Set[str], post: List[MemoryItem]) -> bool:
    """CONTRADICTOR: True iff the reranked top-k still contains every base-top-k item id."""
    return base_ids <= {it.id for it in post}


def rerank(qtok: Set[str], scored: List[Tuple[float, MemoryItem]], k: int,
           bonus_fn=None) -> List[MemoryItem]:
    """Reorder a wider candidate window by (base_score + moment_bonus) and return the top-k —
    but ONLY if recall@k holds vs the base ranker; otherwise fall back to the base top-k.

    `scored` is the base ranker's (score, item) list, best-first. `bonus_fn(qtok, item)` overrides
    the default heuristic (the live-model seam plugs a cheap cross-encoder here)."""
    if k <= 0 or not scored:
        return [it for _, it in scored[:k]]
    fn = bonus_fn or moment_bonus
    base_topk = [it for _, it in scored[:k]]
    window = scored[: max(k * 3, k)]
    reranked = sorted(window, key=lambda si: -(si[0] + fn(qtok, si[1])))
    post = [it for _, it in reranked[:k]]
    if not recall_held({b.id for b in base_topk}, post):
        return base_topk            # reject: rerank would drop a needed item -> safe fallback
    return post


def rerank_ids(qtok: Set[str], scored: List[Tuple[float, MemoryItem]], k: int,
               bonus_fn=None) -> Optional[List[str]]:
    """Convenience for tests/telemetry: the reranked top-k ids (or None if nothing to do)."""
    out = rerank(qtok, scored, k, bonus_fn=bonus_fn)
    return [it.id for it in out] if out else None
