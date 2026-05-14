"""Silero VAD — acoustic voice-activity gate.

Pre-filters silence and non-speech BEFORE we burn ASR cycles on it. The
on-device cost of Parakeet is non-trivial (~50 ms/100 ms chunk on the
Neural Engine); keeping it gated by VAD cuts that to near-zero on idle
audio.

Silero VAD is a tiny LSTM that runs on CPU at >100x real-time and reports
per-chunk speech probability. We threshold at 0.5 by default (per the
Silero model card).
"""

from __future__ import annotations

import logging
from typing import Iterable, Optional

import numpy as np

_logger = logging.getLogger("anticipy.proactive.vad")


class VAD:
    """Silero VAD wrapper. Processes 16 kHz int16 audio in chunks of
    512 samples (32 ms) — the Silero default frame size.
    """

    SAMPLE_RATE_HZ = 16_000
    FRAME_SAMPLES = 512  # ~32 ms at 16 kHz
    DEFAULT_THRESHOLD = 0.5

    def __init__(self, threshold: float = DEFAULT_THRESHOLD) -> None:
        self.threshold = threshold
        try:
            import torch  # noqa: F401  (silero-vad needs torch in scope)
            from silero_vad import load_silero_vad  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "silero-vad is not installed. Run: "
                "uv pip install silero-vad torch"
            ) from e
        self._model = load_silero_vad()

    def is_speech(self, audio_chunk: bytes) -> bool:
        """Convenience: True if the chunk contains speech above threshold.
        Caller must pass int16 PCM at 16 kHz.
        """
        prob = self.speech_prob(audio_chunk)
        return prob >= self.threshold

    def speech_prob(self, audio_chunk: bytes) -> float:
        """Returns the model's speech probability for one frame."""
        import torch
        # int16 -> float32 normalized to [-1, 1]
        samples = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0
        if samples.size != self.FRAME_SAMPLES:
            # Pad or truncate to the model's expected frame size. In
            # production the streamer feeds exact-size frames; this is
            # the test/fixture path.
            if samples.size < self.FRAME_SAMPLES:
                samples = np.pad(samples, (0, self.FRAME_SAMPLES - samples.size))
            else:
                samples = samples[: self.FRAME_SAMPLES]
        tensor = torch.from_numpy(samples)
        with torch.no_grad():
            prob = self._model(tensor, self.SAMPLE_RATE_HZ).item()
        return float(prob)

    def filter(
        self,
        audio_chunks: Iterable[bytes],
    ) -> Iterable[bytes]:
        """Pass-through generator that yields ONLY chunks containing
        speech. Use as a gate before piping into ASR:

            speech_chunks = VAD().filter(mic_chunks)
            for seg in ASR().stream(speech_chunks):
                ...
        """
        for chunk in audio_chunks:
            if self.is_speech(chunk):
                yield chunk


def get_vad(singleton: Optional["VAD"] = None) -> "VAD":
    """Process-wide singleton accessor."""
    global _VAD_SINGLETON
    if singleton is not None:
        _VAD_SINGLETON = singleton
        return _VAD_SINGLETON
    if _VAD_SINGLETON is None:
        _VAD_SINGLETON = VAD()
    return _VAD_SINGLETON


_VAD_SINGLETON: Optional[VAD] = None
