"""pyannote diarization with wearer voiceprint matching.

Per the v-final-prototype master prompt: "wearer voiceprint comparison
runs against ALL incoming audio sources. Segments matching wearer fire
the cascade. Segments matching other identified speakers (FaceTime
callers, room voices) get logged but never fire actions." (correction
#12 from the 2026-05-13 session.)

Implementation: ECAPA-TDNN embedding from pyannote/embedding compared
against the wearer voiceprint at `~/.anticipy/wearer_voiceprint.npy`
(produced by `engine/scripts/enroll_wearer.py`). Cosine similarity
threshold of 0.65 was the empirically-validated cutoff in pyannote's
2024 reproducibility study; we adopt that.

Other identified speakers (entries in the user's contact memory with
`kind="contact_voiceprint"`) get matched too — those segments are
labeled with the contact id but do NOT fire intent extraction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

_logger = logging.getLogger("anticipy.proactive.diarization")

WEARER_VOICEPRINT_PATH = Path.home() / ".anticipy" / "wearer_voiceprint.npy"
COSINE_SIM_WEARER_THRESHOLD = 0.65


@dataclass(frozen=True, slots=True)
class DiarizedSegment:
    """A speech segment + identified speaker.

    `is_wearer` is the only field the cascade actually branches on; the
    other speaker_label is logged for transcript display.
    """

    start_s: float
    end_s: float
    is_wearer: bool
    speaker_label: str  # "wearer" | "<contact_id>" | "unknown_<n>"
    similarity: float


class Diarizer:
    """pyannote-backed diarizer. Heavy deps (`pyannote.audio`, `torch`)
    are imported in `__init__`.
    """

    EMBEDDING_MODEL = "pyannote/embedding"

    def __init__(
        self,
        wearer_voiceprint_path: Path = WEARER_VOICEPRINT_PATH,
        wearer_threshold: float = COSINE_SIM_WEARER_THRESHOLD,
    ) -> None:
        self.wearer_threshold = wearer_threshold
        try:
            from pyannote.audio import Inference, Model  # type: ignore
            import torch  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "pyannote.audio is not installed. Run: "
                "uv pip install 'pyannote.audio>=3.3'"
            ) from e
        if not wearer_voiceprint_path.exists():
            raise RuntimeError(
                f"Wearer voiceprint not found at {wearer_voiceprint_path}. "
                "Run: python engine/scripts/enroll_wearer.py "
                "(records 30 s of you speaking, computes ECAPA embedding)."
            )
        self._wearer_embedding: np.ndarray = np.load(wearer_voiceprint_path)
        self._model = Inference(Model.from_pretrained(self.EMBEDDING_MODEL))

    def identify_segment(self, audio_path: Path, start_s: float, end_s: float) -> DiarizedSegment:
        """Compute the embedding for one audio slice and compare against
        the wearer voiceprint. Returns a DiarizedSegment.
        """
        from pyannote.core import Segment  # type: ignore

        segment = Segment(start_s, end_s)
        embedding = self._model.crop(str(audio_path), segment)
        # The model can return a SlidingWindowFeature for short segments —
        # take the mean across frames so we get a single 192-dim vector.
        if hasattr(embedding, "data"):
            vec = np.asarray(embedding.data).mean(axis=0)
        else:
            vec = np.asarray(embedding)
        sim = self._cosine(vec, self._wearer_embedding)
        is_wearer = sim >= self.wearer_threshold
        return DiarizedSegment(
            start_s=start_s,
            end_s=end_s,
            is_wearer=is_wearer,
            speaker_label="wearer" if is_wearer else "unknown_0",
            similarity=float(sim),
        )

    @staticmethod
    def _cosine(a: np.ndarray, b: np.ndarray) -> float:
        a = np.asarray(a).reshape(-1)
        b = np.asarray(b).reshape(-1)
        denom = np.linalg.norm(a) * np.linalg.norm(b)
        if denom == 0:
            return 0.0
        return float(np.dot(a, b) / denom)


def get_diarizer(singleton: Optional["Diarizer"] = None) -> "Diarizer":
    """Process-wide singleton."""
    global _DIARIZER_SINGLETON
    if singleton is not None:
        _DIARIZER_SINGLETON = singleton
        return _DIARIZER_SINGLETON
    if _DIARIZER_SINGLETON is None:
        _DIARIZER_SINGLETON = Diarizer()
    return _DIARIZER_SINGLETON


_DIARIZER_SINGLETON: Optional[Diarizer] = None
