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


def _clamp01(x) -> float:
    try:
        return float(max(0.0, min(1.0, float(x))))
    except (TypeError, ValueError):
        return 0.5


def asr_tokens(wav: np.ndarray) -> AsrResult:
    """Transcribe with per-token timing and parakeet's NATIVE per-token
    confidence (the Layer 3 substrate). parakeet-mlx.transcribe takes
    a path, so the segment is written to a temp wav. Never raises on
    empty/garbled audio; returns an empty result so callers fail
    closed (safe direction).
    """
    if wav is None or len(wav) < int(0.1 * SR):
        return AsrResult(text="", tokens=[])
    import tempfile

    model = _get_asr()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tf:
        write_wav(tf.name, np.asarray(wav, dtype=np.float32))
        try:
            res = model.transcribe(tf.name)
        except Exception:
            return AsrResult(text="", tokens=[])
    toks: list[AsrToken] = []
    parts: list[str] = []
    for sent in getattr(res, "sentences", []) or []:
        for tk in getattr(sent, "tokens", []) or []:
            txt = (getattr(tk, "text", "") or "").strip()
            if not txt:
                continue
            start = float(getattr(tk, "start", 0.0) or 0.0)
            end = float(getattr(tk, "end", None)
                        if getattr(tk, "end", None) is not None
                        else start + (getattr(tk, "duration", 0.0) or 0.0))
            toks.append(AsrToken(
                text=txt, start=start, end=end,
                confidence=_clamp01(getattr(tk, "confidence", 0.5)),
            ))
            parts.append(txt)
    text = (getattr(res, "text", "") or " ".join(parts)).strip()
    return AsrResult(text=text, tokens=toks)


# --------------------------------------------------------------------------
# speaker embedding  -> the wearer anchor (Layer 1)
# --------------------------------------------------------------------------

EMB_DIM = 256
_spk = None


def _get_spk():
    """Resemblyzer GE2E voice encoder: a real speaker-verification
    embedding (purpose-built for 'same speaker?'), not an ASR feature.
    Weights ship inside the wheel, so there is no download and no
    credential. wav2vec2 was tried first and measured: it barely
    separated speakers (0.003 cosine margin) because it encodes
    phonetic content, not identity. This is the correct tool.
    """
    global _spk
    if _spk is None:
        from resemblyzer import VoiceEncoder

        _spk = VoiceEncoder(verbose=False)
    return _spk


def denoise(wav: np.ndarray) -> np.ndarray:
    """Light spectral-gate denoise. Estimates the noise magnitude from
    the quietest frames and subtracts it with a floor. Conservative
    (keeps speaker structure, does not over-suppress). Applied before
    speaker embedding so enrollment and inference see the SAME front
    end, which is what lets a noised short wearer turn still land near
    the anchor without lowering any decision threshold.
    """
    from scipy.signal import istft, stft

    if wav is None or len(wav) < int(0.2 * SR):
        return np.asarray(wav, dtype=np.float32)
    f, t, Z = stft(np.asarray(wav, dtype=np.float32), fs=SR, nperseg=512,
                    noverlap=384)
    mag, phase = np.abs(Z), np.angle(Z)
    frame_e = mag.sum(axis=0)
    floor = np.quantile(mag[:, frame_e <= np.quantile(frame_e, 0.20)]
                        if (frame_e <= np.quantile(frame_e, 0.20)).any()
                        else mag, 0.5, axis=1, keepdims=True)
    clean = np.maximum(mag - 1.5 * floor, 0.05 * mag)
    _, y = istft(clean * np.exp(1j * phase), fs=SR, nperseg=512, noverlap=384)
    y = np.asarray(y, dtype=np.float32)
    m = np.max(np.abs(y))
    return (y / m * 0.97).astype(np.float32) if m > 1.0 else y


def speaker_embed(wav: np.ndarray) -> np.ndarray:
    """L2-normalized 256-d GE2E speaker vector, on denoised audio.
    Offline, deterministic. Returns a zero vector on too-short/empty
    audio so callers fail closed (cosine 0 to any anchor -> not wearer).
    """
    from resemblyzer import preprocess_wav

    if wav is None or len(wav) < int(0.4 * SR):
        return np.zeros(EMB_DIM, dtype=np.float32)
    try:
        dn = denoise(np.asarray(wav, dtype=np.float32))
        proc = preprocess_wav(dn, source_sr=SR)
        if proc is None or len(proc) < SR // 2:
            return np.zeros(EMB_DIM, dtype=np.float32)
        v = _get_spk().embed_utterance(proc).astype(np.float32)
    except Exception:
        return np.zeros(EMB_DIM, dtype=np.float32)
    n = np.linalg.norm(v)
    return (v / n).astype(np.float32) if n > 0 else v


def is_bandlimited(wav: np.ndarray) -> bool:
    """True if energy is concentrated in the 300-3400 Hz telephone
    band with little outside it: the deterministic, ASR-INDEPENDENT
    signature of phone / compressed-broadcast / TV audio. A person
    physically co-present giving the wearer a drive-by is full-band,
    so this can only REJECT (strengthen precision), never loosen.
    """
    if wav is None or len(wav) < int(0.2 * SR):
        return False
    x = np.asarray(wav, dtype=np.float32)
    sp = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    fr = np.fft.rfftfreq(len(x), 1.0 / SR)
    total = float(np.sum(sp) + 1e-9)
    out_of_band = float(np.sum(sp[(fr < 250) | (fr > 3600)]))
    # phone/broadcast: <8% of spectral energy outside the phone band
    return (out_of_band / total) < 0.08


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))
