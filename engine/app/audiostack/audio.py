"""Audio primitives for the stack. All offline after first model
fetch. Models are lazy and cached so importing this module is cheap
and a machine with no weights yet can still import every other
module (the P0 gate checks structure without forcing a fetch).

Primitives, each a thin contract the layers build on:
  load_wav(path)            -> float32 mono 16k numpy
  vad_segments(wav)         -> [(start_s, end_s)] speech spans (silero)
  asr_tokens(wav)           -> AsrResult{text, tokens:[AsrToken{
                               text,start,end,confidence}]} (parakeet)
  speaker_embed(wav)        -> L2-normalized float32 vector
  cosine(a, b)              -> float in [-1, 1]

Model weights come from public hubs with NO credential (parakeet-mlx
ASR, a torchaudio self-hosted wav2vec2 for the speaker embedding).
They are fetched on first real use only, into data_dir()/models.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

SR = 16000  # the whole stack works at 16 kHz mono


def _models_dir() -> Path:
    from app.anticipy import platform_adapter
    d = platform_adapter.data_dir() / "models"
    d.mkdir(parents=True, exist_ok=True)
    # keep every hub cache device-local and out of the repo
    os.environ.setdefault("HF_HOME", str(d / "hf"))
    os.environ.setdefault("TORCH_HOME", str(d / "torch"))
    return d


# --------------------------------------------------------------------------
# load / resample
# --------------------------------------------------------------------------

def load_wav(path: str | Path) -> np.ndarray:
    import soundfile as sf

    data, sr = sf.read(str(path), dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    if sr != SR:
        import librosa

        data = librosa.resample(np.asarray(data, dtype=np.float32),
                                 orig_sr=sr, target_sr=SR)
    return np.ascontiguousarray(data, dtype=np.float32)


def write_wav(path: str | Path, wav: np.ndarray, sr: int = SR) -> None:
    import soundfile as sf

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), np.asarray(wav, dtype=np.float32), sr)


# --------------------------------------------------------------------------
# VAD (silero) -> speech spans, the turn-taking timing substrate
# --------------------------------------------------------------------------

_vad = None


def _get_vad():
    global _vad
    if _vad is None:
        from silero_vad import load_silero_vad

        _vad = load_silero_vad()
    return _vad


def vad_segments(wav: np.ndarray, min_speech_s: float = 0.20,
                 min_silence_s: float = 0.20) -> list[tuple[float, float]]:
    """Speech spans as (start_s, end_s). Empty list means silence."""
    import torch
    from silero_vad import get_speech_timestamps

    model = _get_vad()
    t = torch.from_numpy(np.asarray(wav, dtype=np.float32))
    ts = get_speech_timestamps(
        t, model, sampling_rate=SR,
        min_speech_duration_ms=int(min_speech_s * 1000),
        min_silence_duration_ms=int(min_silence_s * 1000),
    )
    return [(d["start"] / SR, d["end"] / SR) for d in ts]


# --------------------------------------------------------------------------
# ASR (parakeet-mlx) with per-token confidence  -> Layer 3 substrate
# --------------------------------------------------------------------------

@dataclass
class AsrToken:
    text: str
    start: float
    end: float
    confidence: float  # 0..1, calibrated from the model's token logprob


@dataclass
class AsrResult:
    text: str
    tokens: list[AsrToken] = field(default_factory=list)

    def mean_conf(self) -> float:
        return float(np.mean([t.confidence for t in self.tokens])) if self.tokens else 0.0


_asr = None
_ASR_MODEL = "mlx-community/parakeet-tdt-0.6b-v2"


def _get_asr():
    global _asr
    if _asr is None:
        from parakeet_mlx import from_pretrained

        _models_dir()
        _asr = from_pretrained(_ASR_MODEL)
    return _asr


def _logprob_to_conf(lp: Optional[float]) -> float:
    if lp is None:
        return 0.5
    # token logprob (natural log) -> probability, clamped. Calibrated
    # softly so a strong token is ~0.9+ and a guessed token is ~0.3.
    import math

    p = math.exp(max(min(float(lp), 0.0), -10.0))
    return float(max(0.0, min(1.0, p)))


def asr_tokens(wav: np.ndarray) -> AsrResult:
    """Transcribe with per-token timing and confidence. Never raises on
    empty audio; returns an empty result so callers fail closed.
    """
    if wav is None or len(wav) < int(0.1 * SR):
        return AsrResult(text="", tokens=[])
    model = _get_asr()
    res = model.transcribe(np.asarray(wav, dtype=np.float32))
    toks: list[AsrToken] = []
    text_parts: list[str] = []
    for sent in getattr(res, "sentences", []) or []:
        for tk in getattr(sent, "tokens", []) or []:
            txt = (getattr(tk, "text", "") or "").strip()
            if not txt:
                continue
            conf = _logprob_to_conf(getattr(tk, "logprob", None))
            toks.append(AsrToken(
                text=txt,
                start=float(getattr(tk, "start", 0.0) or 0.0),
                end=float(getattr(tk, "end", 0.0) or 0.0),
                confidence=conf,
            ))
            text_parts.append(txt)
    text = (getattr(res, "text", "") or " ".join(text_parts)).strip()
    return AsrResult(text=text, tokens=toks)


# --------------------------------------------------------------------------
# speaker embedding  -> the wearer anchor (Layer 1)
# --------------------------------------------------------------------------

_spk = None


def _get_spk():
    global _spk
    if _spk is None:
        import torchaudio

        _models_dir()
        bundle = torchaudio.pipelines.WAV2VEC2_BASE
        _spk = (bundle, bundle.get_model().eval())
    return _spk


def speaker_embed(wav: np.ndarray) -> np.ndarray:
    """A fixed-length L2-normalized speaker vector. wav2vec2-base
    features, mean+std pooled. Offline, no credential. Deterministic.
    """
    import torch

    if wav is None or len(wav) < int(0.2 * SR):
        return np.zeros(1536, dtype=np.float32)
    bundle, model = _get_spk()
    with torch.inference_mode():
        t = torch.from_numpy(np.asarray(wav, dtype=np.float32)).unsqueeze(0)
        feats, _ = model.extract_features(t)
        h = feats[-1].squeeze(0)  # (frames, 768)
        emb = torch.cat([h.mean(0), h.std(0)], dim=0)  # (1536,)
    v = emb.numpy().astype(np.float32)
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))
