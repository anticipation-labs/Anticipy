"""Silero VAD smoke against the gold-standard WAV fixtures.

Each fixture is a TTS rendering of a real wearer utterance — pure
speech, no silence. VAD should classify >= 80% of frames as speech.

Per Rule 13: this is the gate for vad.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.proactive.vad import VAD  # noqa: E402

WAV_DIR = ROOT / "tests" / "fixtures" / "gold_standard"
SPEECH_FRAME_TARGET = 0.80  # 80% of frames in a speech-only clip should be speech


def main() -> int:
    vad = VAD()
    cases = []
    for wav in sorted(WAV_DIR.glob("*.wav")):
        samples, sr = sf.read(str(wav), dtype="int16")
        # Mono-convert if needed
        if samples.ndim > 1:
            samples = samples[:, 0]
        # Resample if needed (fixtures are 16kHz so this is a no-op)
        if sr != VAD.SAMPLE_RATE_HZ:
            print(f"[skip] {wav.name} unexpected sr={sr}", file=sys.stderr)
            continue
        # Frame into 512-sample windows
        n_frames = len(samples) // VAD.FRAME_SAMPLES
        speech_frames = 0
        for i in range(n_frames):
            chunk = samples[i * VAD.FRAME_SAMPLES : (i + 1) * VAD.FRAME_SAMPLES].tobytes()
            if vad.is_speech(chunk):
                speech_frames += 1
        rate = speech_frames / n_frames if n_frames else 0.0
        ok = rate >= SPEECH_FRAME_TARGET
        cases.append({"name": wav.name, "ok": ok, "speech_rate": rate, "n_frames": n_frames})
        print(f"[{'PASS' if ok else 'FAIL'}] {wav.name}  speech={speech_frames}/{n_frames} ({rate*100:.0f}%)")

    n = len(cases)
    hits = sum(1 for c in cases if c["ok"])
    print(f"\n== SUMMARY: {hits}/{n} (target ≥{int(SPEECH_FRAME_TARGET*100)}% speech-frame rate) ==")
    return 0 if hits == n else 1


if __name__ == "__main__":
    sys.exit(main())
