"""Local embedder behind a flag.

TEST/default (ANTICIPY_MEMORY_MODE=stub): a DETERMINISTIC, dependency-free local
embedder — a hashed bag-of-tokens vector, L2-normalized. Same text -> same vector,
so the suite is free + reproducible, and shared vocabulary -> higher cosine (enough
for the hybrid retriever's semantic leg; keyword/structured legs do the rest).

LIVE (ANTICIPY_MEMORY_MODE=live): a REAL local sentence-embedding model loaded via
sentence-transformers, L2-normalized so dot == cosine (matches cosine() below).
Fully on-device — no embeddings API. The model is a lazy singleton, so stub mode
NEVER imports torch/sentence-transformers and the free CI suite stays dependency-light.

Default live model: BAAI/bge-small-en-v1.5 — 384-d, 33M params, MIT (ungated), fast
on Apple-Silicon CPU. Chosen over the higher-MTEB EmbeddingGemma-300m because that
one is GATED (license/HF-auth), f32-only, and ~10x slower per call on CPU (no EdgeTPU,
no batching in our capture path). Swap any sentence-transformers model in via
ANTICIPY_EMBED_MODEL; device via ANTICIPY_EMBED_DEVICE (default cpu). Only this
function's live branch changes — the store, cosine, and hybrid retriever are untouched.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
from typing import List

DIM = 256  # stub embedding width (live width is the model's, e.g. 384 for bge-small)
LIVE_MODEL_ID = os.environ.get("ANTICIPY_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
_TOKEN = re.compile(r"[a-z0-9]+")

_model = None  # lazy singleton; only constructed when live mode is first used


def _is_live() -> bool:
    return os.environ.get("ANTICIPY_MEMORY_MODE", "stub") == "live"


def _stub_embed(text: str, dim: int = DIM) -> List[float]:
    v = [0.0] * dim
    for tok in _TOKEN.findall((text or "").lower()):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        v[h % dim] += 1.0
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else v


def _live_model():
    """Load the real model once (lazy). Import is local so stub-mode never needs torch."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:  # stub mode (default) never reaches here -> CI stays dep-light
            raise ImportError(
                "ANTICIPY_MEMORY_MODE=live needs sentence-transformers: "
                "`engine/.venv/bin/pip install sentence-transformers`."
            ) from e
        device = os.environ.get("ANTICIPY_EMBED_DEVICE", "cpu")
        _model = SentenceTransformer(LIVE_MODEL_ID, device=device)
    return _model


def _live_embed(text: str) -> List[float]:
    # normalize_embeddings=True -> unit vectors, so dot product == cosine (cosine() contract).
    vec = _live_model().encode(text or "", normalize_embeddings=True, convert_to_numpy=True)
    return vec.astype("float32").tolist()


def embed(text: str) -> List[float]:
    return _live_embed(text) if _is_live() else _stub_embed(text)


def embedding_dim() -> int:
    """Active embedding width — for manifests + reindex sanity. Triggers a live load."""
    if not _is_live():
        return DIM
    m = _live_model()
    fn = getattr(m, "get_embedding_dimension", None) or m.get_sentence_embedding_dimension
    return fn()


def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))  # both are L2-normalized -> dot == cosine
