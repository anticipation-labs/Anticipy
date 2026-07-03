"""Embedder behind a flag — THREE providers, one interface.

The retriever calls ``embed(text)`` and ``cosine(a, b)``; everything below is
swappable without touching the store or the hybrid retriever. Provider is chosen
by ``ANTICIPY_EMBED_PROVIDER`` (default ``""`` -> the on-device behavior, so the
free/deterministic CI suite and the working on-device 8/8 are NEVER at risk):

  1. STUB (default; ANTICIPY_MEMORY_MODE=stub): a DETERMINISTIC, dependency-free
     hashed bag-of-tokens vector, L2-normalized. Same text -> same vector, so the
     suite is free + reproducible; shared vocabulary -> higher cosine (enough for
     the hybrid retriever's semantic leg; keyword/structured legs do the rest).
     Blind to paraphrase: "book a haircut" vs "schedule a trim" share no tokens,
     so cosine ~= 0 — it CANNOT recall a paraphrase.

  2. BGE (ANTICIPY_MEMORY_MODE=live): a REAL on-device sentence-embedding model
     (BAAI/bge-small-en-v1.5, 384-d) via sentence-transformers. Paraphrase-aware,
     fully local, no API. Lazy singleton so stub mode never imports torch.

  3. GEMINI (ANTICIPY_EMBED_PROVIDER=gemini): REAL cloud embeddings via the Google
     Generative Language API (model ``gemini-embedding-001`` by default, or
     ``text-embedding-004``) using GOOGLE_API_KEY/GEMINI_API_KEY. This is the
     paraphrase-robust semantic-recall path: "book a haircut" retrieves a stored
     "schedule a trim" even with zero keyword overlap (cos ~0.93 vs stub ~0.33).
     Results are L2-normalized (so dot == cosine) and CACHED in-process (same text
     -> one API call). Rate limits / 5xx are retried with exponential backoff.
     FAIL-SAFE: a missing key or an exhausted-retry error falls back to the
     on-device embedder (bge if live else stub) and logs — it never crashes ingest.

Config (all read at call time so a launch env or a test can flip them):
  ANTICIPY_EMBED_PROVIDER      "" (on-device) | "gemini"
  ANTICIPY_GEMINI_EMBED_MODEL  gemini-embedding-001 (default) | text-embedding-004
  ANTICIPY_GEMINI_EMBED_DIM    output width, MRL-truncated (default 768; 0 = model default)
  ANTICIPY_GEMINI_EMBED_TASK   SEMANTIC_SIMILARITY (default; symmetric doc<->query)
  ANTICIPY_EMBED_MODEL         bge model id (default BAAI/bge-small-en-v1.5)
  ANTICIPY_EMBED_DEVICE        bge device (default cpu)

Swapping providers on an EXISTING store requires ``Memory.reindex()`` (the stored
vectors must be re-embedded under the new provider, and dims differ). A fresh data
dir (e.g. the throwaway test engine) embeds everything under the active provider,
so no reindex is needed there.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import time
import urllib.error
import urllib.request
from typing import List, Optional

log = logging.getLogger(__name__)

DIM = 256  # stub embedding width (bge live width is the model's, e.g. 384; gemini is _gemini_dim())
LIVE_MODEL_ID = os.environ.get("ANTICIPY_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
_TOKEN = re.compile(r"[a-z0-9]+")

_model = None  # lazy bge singleton; only constructed when live (bge) mode is first used

# ── Gemini (cloud) ──────────────────────────────────────────────────────────
_GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:{method}"
_gemini_cache: dict = {}          # (model, dim, task, text) -> unit vector
_gemini_disabled = False          # set once when NO key is present -> fall back for the run


def _provider() -> str:
    return os.environ.get("ANTICIPY_EMBED_PROVIDER", "").strip().lower()


def _is_live() -> bool:
    return os.environ.get("ANTICIPY_MEMORY_MODE", "stub") == "live"


# ── 1. stub ──────────────────────────────────────────────────────────────────
def _stub_embed(text: str, dim: int = DIM) -> List[float]:
    v = [0.0] * dim
    for tok in _TOKEN.findall((text or "").lower()):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        v[h % dim] += 1.0
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else v


# ── 2. bge (on-device) ───────────────────────────────────────────────────────
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


def _ondevice_embed(text: str) -> List[float]:
    """The on-device fallback path (bge if live, else stub)."""
    return _live_embed(text) if _is_live() else _stub_embed(text)


# ── 3. gemini (cloud) ────────────────────────────────────────────────────────
def _gemini_model() -> str:
    return os.environ.get("ANTICIPY_GEMINI_EMBED_MODEL", "gemini-embedding-001")


def _gemini_dim() -> int:
    return int(os.environ.get("ANTICIPY_GEMINI_EMBED_DIM", "768"))


def _gemini_task() -> str:
    return os.environ.get("ANTICIPY_GEMINI_EMBED_TASK", "SEMANTIC_SIMILARITY")


def _gemini_key() -> Optional[str]:
    return os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")


def _l2(v: List[float]) -> List[float]:
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else v


def _gemini_content(text: str) -> dict:
    body = {
        "model": f"models/{_gemini_model()}",
        "content": {"parts": [{"text": text or " "}]},
        "taskType": _gemini_task(),
    }
    dim = _gemini_dim()
    if dim:
        body["outputDimensionality"] = dim
    return body


def _gemini_request(method: str, key: str, payload: dict, retries: int = 5, timeout: int = 30):
    """POST to the API with exponential backoff on 429/5xx. Returns parsed JSON or raises."""
    url = _GEMINI_ENDPOINT.format(model=_gemini_model(), method=method) + f"?key={key}"
    data = json.dumps(payload).encode()
    delay = 0.6
    last: Optional[Exception] = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            last = e
            transient = e.code in (429, 500, 502, 503, 504)
            if transient and attempt < retries - 1:
                # honor Retry-After when present, else exponential backoff
                ra = e.headers.get("Retry-After") if e.headers else None
                time.sleep(float(ra) if (ra and ra.isdigit()) else delay)
                delay *= 2
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
            if attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise
    if last:
        raise last
    raise RuntimeError("gemini request failed with no exception captured")


def _gemini_embed(text: str) -> Optional[List[float]]:
    """One cloud embedding, L2-normalized + cached. None => caller should fall back."""
    global _gemini_disabled
    if _gemini_disabled:
        return None
    key = _gemini_key()
    if not key:
        _gemini_disabled = True
        log.warning("ANTICIPY_EMBED_PROVIDER=gemini but no GOOGLE_API_KEY/GEMINI_API_KEY; "
                    "falling back to on-device embedder for this process.")
        return None
    text = text or ""
    ck = (_gemini_model(), _gemini_dim(), _gemini_task(), text)
    hit = _gemini_cache.get(ck)
    if hit is not None:
        return hit
    try:
        out = _gemini_request("embedContent", key, _gemini_content(text))
    except Exception as e:  # exhausted retries -> graceful fallback (never crash ingest)
        log.warning("gemini embedContent failed (%s); falling back to on-device for this call.", e)
        return None
    values = (out.get("embedding") or {}).get("values")
    if not values:
        log.warning("gemini embedContent returned no values; falling back for this call.")
        return None
    vec = _l2([float(x) for x in values])
    _gemini_cache[ck] = vec
    return vec


def embed_batch(texts: List[str]) -> List[List[float]]:
    """Embed many texts. On the gemini provider this uses the batchEmbedContents
    endpoint (one HTTP round-trip for the whole batch) with cache reuse + graceful
    per-item fallback; otherwise it maps embed() over the list. Cheap for reindex."""
    texts = list(texts)
    if _provider() != "gemini":
        return [embed(t) for t in texts]
    key = _gemini_key()
    # cache hits first; only ask the API for the misses
    out: List[Optional[List[float]]] = [None] * len(texts)
    misses = []
    for i, t in enumerate(texts):
        ck = (_gemini_model(), _gemini_dim(), _gemini_task(), t or "")
        hit = _gemini_cache.get(ck)
        if hit is not None:
            out[i] = hit
        else:
            misses.append(i)
    if misses and key and not _gemini_disabled:
        payload = {"requests": [_gemini_content(texts[i] or "") for i in misses]}
        try:
            res = _gemini_request("batchEmbedContents", key, payload)
            embs = res.get("embeddings") or []
            for j, i in enumerate(misses):
                vals = (embs[j] or {}).get("values") if j < len(embs) else None
                if vals:
                    vec = _l2([float(x) for x in vals])
                    _gemini_cache[(_gemini_model(), _gemini_dim(), _gemini_task(), texts[i] or "")] = vec
                    out[i] = vec
        except Exception as e:
            log.warning("gemini batchEmbedContents failed (%s); falling back per item.", e)
    # any remaining misses (no key, batch error, empty row) -> single/on-device path
    return [v if v is not None else embed(texts[i]) for i, v in enumerate(out)]


# ── public interface (unchanged signature) ───────────────────────────────────
def embed(text: str) -> List[float]:
    if _provider() == "gemini":
        v = _gemini_embed(text)
        if v is not None:
            return v
        # graceful fallback keeps ingest/retrieval alive (dims differ, so cosine()
        # simply scores a fallback row 0 against gemini rows — degraded, not broken).
    return _ondevice_embed(text)


def embedding_dim() -> int:
    """Active embedding width — for manifests + reindex sanity."""
    if _provider() == "gemini":
        return _gemini_dim() or 3072  # gemini-embedding-001 default width
    if not _is_live():
        return DIM
    m = _live_model()
    fn = getattr(m, "get_embedding_dimension", None) or m.get_sentence_embedding_dimension
    return fn()


def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))  # both are L2-normalized -> dot == cosine
