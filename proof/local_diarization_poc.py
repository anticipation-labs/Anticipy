"""PROVEN 2026-08-05 on Omar's Mac: speaker recognition runs fully LOCALLY.

Two questions, both answered with zero cloud calls, CPU only:

1. WHO SPOKE WHEN (diarization) — a 22.7s two-voice conversation was
   separated in 5.95s (3.8x realtime): 2 speakers found, boundaries within
   ~0.4s of truth, and the same voice RE-IDENTIFIED after the other spoke:
       0.05- 8.77  speaker_1     (owner voice)
       9.24-17.46  speaker_0     (other person)
      17.92-22.14  speaker_1     (owner voice again)
2. IS THIS EVEN OMAR (voice profile) — enroll on ~9s of speech, then:
       owner profile vs owner, new sentence : 0.923
       owner profile vs a different person  : 0.236
   Decided in <1s. A 0.6 threshold has an ocean on each side.

Models (~46MB total, both run on iPhone via sherpa-onnx's iOS support):
  segmentation: pyannote-segmentation-3.0 (sherpa-onnx release)
  embedding:    3dspeaker eres2net (sherpa-onnx release; swap candidates
                are benchmarked the same way — this script IS the bench)

Setup (models are not committed; ~46MB):
  pip install sherpa-onnx numpy
  curl -sL -o seg.tar.bz2 https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2
  curl -sL -o emb.onnx https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx
  tar xf seg.tar.bz2

Run:  python3 proof/local_diarization_poc.py <wav 16k mono> [enroll.wav probe.wav]
"""
from __future__ import annotations

import sys
import time
import wave

import numpy as np
import sherpa_onnx

SEG = "sherpa-onnx-pyannote-segmentation-3-0/model.onnx"
EMB = "emb.onnx"


def load(path: str) -> np.ndarray:
    w = wave.open(path, "rb")
    assert w.getframerate() == 16000 and w.getnchannels() == 1, \
        f"{path}: need 16k mono (got {w.getframerate()}Hz/{w.getnchannels()}ch)"
    return (np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
            .astype(np.float32) / 32768.0)


def diarize(path: str) -> None:
    sd = sherpa_onnx.OfflineSpeakerDiarization(
        sherpa_onnx.OfflineSpeakerDiarizationConfig(
            segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
                pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                    model=SEG)),
            embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=EMB),
            clustering=sherpa_onnx.FastClusteringConfig(num_clusters=-1,
                                                        threshold=0.5),
            min_duration_on=0.3, min_duration_off=0.5))
    samples = load(path)
    dur = len(samples) / 16000
    t0 = time.time()
    result = sd.process(samples).sort_by_start_time()
    dt = time.time() - t0
    print(f"{path}: {dur:.1f}s audio, diarized in {dt:.2f}s "
          f"({dur / dt:.1f}x realtime, CPU, local)")
    for r in result:
        print(f"  {r.start:6.2f}-{r.end:6.2f}  speaker_{r.speaker}")


def profile_gate(enroll_path: str, probe_path: str) -> None:
    ex = sherpa_onnx.SpeakerEmbeddingExtractor(
        sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=EMB))

    def emb(p):
        st = ex.create_stream()
        st.accept_waveform(16000, load(p))
        st.input_finished()
        return np.array(ex.compute(st))

    a, b = emb(enroll_path), emb(probe_path)
    score = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    print(f"voice-profile match {enroll_path} vs {probe_path}: {score:.3f} "
          f"({'same person' if score >= 0.6 else 'different person'} @0.6)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    diarize(sys.argv[1])
    if len(sys.argv) >= 4:
        profile_gate(sys.argv[2], sys.argv[3])
