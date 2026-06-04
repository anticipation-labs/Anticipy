"""Local embedder behind a flag.

TEST/default (ANTICIPY_MEMORY_MODE=stub): a DETERMINISTIC, dependency-free local
embedder — a hashed bag-of-tokens vector, L2-normalized. Same text -> same vector,
so the suite is free + reproducible, and shared vocabulary -> higher cosine (enough
for the hybrid retriever's semantic leg; keyword/structured legs do the rest).

LIVE (ANTICIPY_MEMORY_MODE=live): swap in a real cheap embedder here (local
sentence model or a cheap embeddings API). Kept behind the flag so it never costs
anything in tests. The seam is stable; only this function's live branch changes.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
from typing import List

DIM = 256
_TOKEN = re.compile(r"[a-z0-9]+")


def _stub_embed(text: str, dim: int = DIM) -> List[float]:
    v = [0.0] * dim
    for tok in _TOKEN.findall((text or "").lower()):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        v[h % dim] += 1.0
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else v


def embed(text: str) -> List[float]:
    if os.environ.get("ANTICIPY_MEMORY_MODE", "stub") == "live":
        # TODO(live): real cheap embedder behind the flag; never hit in tests.
        return _stub_embed(text)
    return _stub_embed(text)


def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))  # both are L2-normalized -> dot == cosine
