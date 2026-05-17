"""Wearer enrollment: the anchor the whole stack hangs on.

A clean ~30s wearer sample becomes an encrypted, device-local
speaker anchor. The anchor is the one constant the device is
attached to; Layer 1 membership is meaningless without it, so a
WEAK anchor fails CLOSED: the stack refuses to run membership
permissively and surfaces that enrollment must be redone, rather
than letting everything through.

Stored Fernet-encrypted under data_dir()/anchors/<user>.enc. The
key is the existing PROFILE_ENCRYPTION_KEY if set, else a device
-local derived key (never a new credential).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from app.audiostack import audio as A

MIN_SPEECH_S = 18.0          # below this the sample is too short to anchor
STRONG_CONSISTENCY = 0.62    # mean intra-sample window cosine for a usable anchor


def _key() -> bytes:
    raw = os.environ.get("PROFILE_ENCRYPTION_KEY", "")
    if raw:
        try:
            base64.urlsafe_b64decode(raw)
            return raw.encode() if isinstance(raw, str) else raw
        except Exception:
            pass
    from app.anticipy import platform_adapter

    seed = ("anticipy-anchor-v1:" + str(platform_adapter.data_dir())).encode()
    return base64.urlsafe_b64encode(hashlib.sha256(seed).digest())


def _anchors_dir() -> Path:
    from app.anticipy import platform_adapter

    d = platform_adapter.data_dir() / "anchors"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class Anchor:
    user_id: str
    vector: np.ndarray
    consistency: float           # mean intra-sample window cosine, 0..1
    speech_seconds: float
    strong: bool                 # False -> membership must fail closed


def _windows(wav: np.ndarray, win_s: float = 3.0, hop_s: float = 1.5):
    w, h = int(win_s * A.SR), int(hop_s * A.SR)
    for s in range(0, max(1, len(wav) - w + 1), h):
        seg = wav[s:s + w]
        if len(seg) >= int(1.0 * A.SR):
            yield seg


def enroll(wav_path: str, user_id: str = "wearer") -> Anchor:
    """Build and persist the encrypted anchor. Fails CLOSED (strong=
    False) on a too-short or inconsistent sample rather than minting
    a permissive anchor.
    """
    wav = A.load_wav(wav_path)
    spans = A.vad_segments(wav)
    speech_s = float(sum(e - s for s, e in spans))
    speech = (np.concatenate([wav[int(s * A.SR):int(e * A.SR)] for s, e in spans])
              if spans else wav)

    embs = [A.speaker_embed(seg) for seg in _windows(speech)]
    embs = [e for e in embs if np.linalg.norm(e) > 0]
    if not embs:
        anchor = Anchor(user_id, np.zeros(1536, np.float32), 0.0, speech_s, False)
        _save(anchor)
        return anchor

    mat = np.stack(embs)
    centroid = mat.mean(axis=0)
    n = np.linalg.norm(centroid)
    centroid = centroid / n if n > 0 else centroid
    sims = [A.cosine(e, centroid) for e in embs]
    consistency = float(np.mean(sims)) if sims else 0.0
    strong = (speech_s >= MIN_SPEECH_S) and (consistency >= STRONG_CONSISTENCY)

    anchor = Anchor(user_id, centroid.astype(np.float32), consistency,
                    speech_s, strong)
    _save(anchor)
    return anchor


def _save(a: Anchor) -> None:
    from cryptography.fernet import Fernet

    blob = json.dumps({
        "user_id": a.user_id,
        "vector": a.vector.tolist(),
        "consistency": a.consistency,
        "speech_seconds": a.speech_seconds,
        "strong": a.strong,
    }).encode()
    enc = Fernet(_key()).encrypt(blob)
    (_anchors_dir() / f"{a.user_id}.enc").write_bytes(enc)


def load_anchor(user_id: str = "wearer") -> Optional[Anchor]:
    p = _anchors_dir() / f"{user_id}.enc"
    if not p.exists():
        return None
    from cryptography.fernet import Fernet

    try:
        d = json.loads(Fernet(_key()).decrypt(p.read_bytes()))
    except Exception:
        return None
    return Anchor(
        user_id=d["user_id"],
        vector=np.asarray(d["vector"], dtype=np.float32),
        consistency=float(d["consistency"]),
        speech_seconds=float(d["speech_seconds"]),
        strong=bool(d["strong"]),
    )


def is_wearer(emb: np.ndarray, anchor: Anchor, threshold: float = 0.55) -> bool:
    """Anchor match test. If the anchor is WEAK this still answers, but
    Layer 1 is required to treat a weak anchor as fail-closed (it must
    NOT pass membership permissively); that policy lives in the stack,
    enforced and tested from P1.
    """
    if anchor is None or np.linalg.norm(anchor.vector) == 0:
        return False
    return A.cosine(emb, anchor.vector) >= threshold
