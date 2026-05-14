"""Parakeet TDT 0.6B v3 streaming ASR via parakeet-mlx (CoreML on the
Mac's Neural Engine).

Latency target: <100ms per 16 kHz audio chunk. Accuracy target: comparable
to Whisper-large-v3 on conversational English (per nvidia/parakeet-tdt-0.6b-v3
model card 2025).

Heavy deps (`parakeet_mlx`, `mlx`) are imported inside `ASR.__init__`. Top-
level import of this module is cheap — useful when only the dataclass
shapes are needed (e.g. tests, contract checks).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

_logger = logging.getLogger("anticipy.proactive.asr")


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    """One segment of transcribed speech with byte-exact timing.

    Mirrors the wire-format `TranscriptSegment` in
    `src/lib/contracts-v2.ts` (start_ts/end_ts in seconds-since-epoch
    when published, in seconds-since-stream-start when in-process).
    """

    text: str
    start_s: float
    end_s: float
    confidence: float


class ASR:
    """Parakeet TDT 0.6B v3 streaming wrapper.

    Usage:
        asr = ASR()                              # loads model (~600 MB on first call)
        for seg in asr.stream(audio_iter):       # yields segments as they finalize
            print(seg.text)

    Or for offline single-file:
        for seg in asr.transcribe_file(Path("clip.wav")):
            print(seg.text)
    """

    DEFAULT_MODEL = "mlx-community/parakeet-tdt-0.6b-v3"
    DEFAULT_SAMPLE_RATE_HZ = 16_000

    def __init__(self, model_id: str = DEFAULT_MODEL) -> None:
        self.model_id = model_id
        try:
            from parakeet_mlx import from_pretrained  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "parakeet-mlx is not installed. Run: "
                "uv pip install parakeet-mlx"
            ) from e
        _logger.info("loading Parakeet model %s — first call downloads ~600MB", model_id)
        self._model = from_pretrained(model_id)
        _logger.info("Parakeet ready")

    def transcribe_file(self, path: Path) -> Iterable[TranscriptSegment]:
        """Transcribe a 16 kHz mono WAV file end-to-end. Used by the
        gold-standard test harness against `engine/tests/fixtures/gold_standard/*.wav`.
        """
        result = self._model.transcribe(str(path))
        for s in getattr(result, "sentences", []) or []:
            yield TranscriptSegment(
                text=s.text.strip(),
                start_s=float(getattr(s, "start", 0.0)),
                end_s=float(getattr(s, "end", 0.0)),
                confidence=float(getattr(s, "confidence", 1.0)),
            )

    def stream(
        self,
        audio_chunks: Iterable[bytes],
        sample_rate_hz: int = DEFAULT_SAMPLE_RATE_HZ,
    ) -> Iterable[TranscriptSegment]:
        """Stream 16 kHz int16 PCM chunks. Yields each segment as it
        finalizes. Caller is responsible for chunk timing — typical: 100ms
        chunks of 1600 int16 samples each.
        """
        # parakeet-mlx exposes a streaming context that maintains its
        # decoder state across chunks. We thread the chunks in and yield
        # finalized sentences as they come out.
        with self._model.transcribe_stream(samplerate=sample_rate_hz) as stream:
            buffered_count = 0
            for chunk in audio_chunks:
                stream.add_audio(chunk)
                # Drain whatever finalized sentences are ready right now.
                for s in getattr(stream, "result", None).sentences[buffered_count:]:
                    yield TranscriptSegment(
                        text=s.text.strip(),
                        start_s=float(getattr(s, "start", 0.0)),
                        end_s=float(getattr(s, "end", 0.0)),
                        confidence=float(getattr(s, "confidence", 1.0)),
                    )
                    buffered_count += 1


def get_asr(singleton: Optional["ASR"] = None) -> "ASR":
    """Process-wide singleton accessor. The Parakeet model takes ~600MB
    of RAM and ~3s to load; we never want to instantiate it twice.
    """
    global _ASR_SINGLETON
    if singleton is not None:
        _ASR_SINGLETON = singleton
        return _ASR_SINGLETON
    if _ASR_SINGLETON is None:
        _ASR_SINGLETON = ASR()
    return _ASR_SINGLETON


_ASR_SINGLETON: Optional[ASR] = None
