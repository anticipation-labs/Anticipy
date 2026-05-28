"""Measure the real wearer-vs-nonwearer embedding separation so the
Layer-1 anchor threshold is DATA-DRIVEN, not guessed. Safe direction:
prefer missing a wearer turn over accepting a stranger as the wearer,
so pick the threshold at/above the max non-wearer cosine (incl. the
hardest near-wearer voices) and report the resulting wearer recall
honestly.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ENGINE = Path(__file__).resolve().parent.parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from app.audiostack import audio as A
from app.audiostack import corpus as C
from app.audiostack import enrollment as E

LINES = [
    "send the quarterly deck to dana by friday",
    "book a table for two at the usual place tonight",
    "remind me to email priya about the schedule",
    "move the standup to next week and tell the team",
    "wire the budget to operations before noon",
    "what time is the review tomorrow",
]
NEAR = C._NEAR_WEARER_VOICES                       # hardest: same male register
FAR = [v for v in C._NONWEARER_VOICES if v not in NEAR][:6]


def main() -> int:
    a = E.enroll_synthetic_wearer("wearer")  # rebuild with current embedding
    print(f"anchor: speech={a.speech_seconds:.1f}s consistency={a.consistency:.3f} "
          f"strong={a.strong}")
    if a is None or not a.strong:
        print("anchor weak after re-enroll")
        return 1

    def cos_of(text, voice, pitch=0.0):
        w = C._tts(text, voice, pitch=pitch)
        return A.cosine(A.speaker_embed(w), a.vector)

    wearer = [cos_of(t, C.WEARER_VOICE) for t in LINES]
    near = [cos_of(LINES[i % len(LINES)], v, pitch=-1.5)
            for i, v in enumerate(NEAR)]
    far = [cos_of(LINES[i % len(LINES)], v) for i, v in enumerate(FAR)]

    wmin, wmax = min(wearer), max(wearer)
    nmax = max(near) if near else 0.0
    fmax = max(far) if far else 0.0
    nonwearer_max = max(nmax, fmax)
    # safe-direction threshold: strictly above the worst non-wearer
    thr = round(nonwearer_max + 0.02, 3)
    recall = sum(1 for c in wearer if c >= thr) / len(wearer)

    print(f"wearer  cos: min={wmin:.3f} max={wmax:.3f} mean={np.mean(wearer):.3f}")
    print(f"near-wearer cos: max={nmax:.3f} vals={[round(x,3) for x in near]}")
    print(f"far     cos: max={fmax:.3f} vals={[round(x,3) for x in far]}")
    print(f"nonwearer_max={nonwearer_max:.3f}")
    print(f"SAFE_THRESHOLD={thr}  wearer_recall_at_safe={recall:.3f}")
    # a usable threshold must keep some wearer recall AND zero
    # non-wearer accept; report honestly either way.
    print("SEPARABLE" if wmin > nonwearer_max else "OVERLAP")
    print(f"RECOMMEND_THRESHOLD={thr}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
