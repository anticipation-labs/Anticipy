"""Measure ASR-independent acoustic-stress signals so the Layer-3
slot-trust gate is data-driven, not guessed. For LOADBEARING (must
NOT fire) vs WEARER_DIRECT / BOSS_INSTRUCTION (must fire) vs NOISY:
per instruction-utterance speaking-rate (tokens/sec) and an SNR
proxy (raw RMS vs denoise-removed-noise RMS, dB). Find the band
that separates trustworthy slots from stressed ones.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

ENGINE = Path(__file__).resolve().parent.parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from app.audiostack import audio as A
from app.audiostack import corpus as C


def _snr_db(seg: np.ndarray) -> float:
    dn = A.denoise(seg)
    n = seg[: len(dn)] - dn if len(dn) <= len(seg) else seg - dn[: len(seg)]
    s = float(np.sqrt(np.mean(dn ** 2) + 1e-12))
    nz = float(np.sqrt(np.mean(n ** 2) + 1e-12))
    return float(20.0 * np.log10((s + 1e-9) / (nz + 1e-9)))


def main() -> int:
    rows = {}
    for cat in ("LOADBEARING_WORD_STRESS", "WEARER_DIRECT_COMMAND",
                "BOSS_INSTRUCTION_IN_CONVERSATION", "NOISY_REAL_ROOM"):
        spec = C.SPEC_BY_NAME[cat]
        rates, snrs = [], []
        for i in range(6):
            wav_arr, it = C._assemble_item(spec, i, 20260516 + i)
            # the instruction is the last non-wearer (S1) span; use VAD
            spans = A.vad_segments(wav_arr)
            if not spans:
                continue
            # pick the longest span (the task utterance) as the slot carrier
            s, e = max(spans, key=lambda se: se[1] - se[0])
            seg = wav_arr[int(s * A.SR):int(e * A.SR)]
            r = A.asr_tokens(seg)
            dur = max(0.3, e - s)
            rate = len(r.tokens) / dur
            rates.append(round(rate, 2))
            snrs.append(round(_snr_db(seg), 1))
        rows[cat] = (rates, snrs)
        print(f"{cat}: rate(tok/s) mean={np.mean(rates):.1f} "
              f"min={min(rates):.1f} max={max(rates):.1f} | "
              f"snr_dB mean={np.mean(snrs):.1f} min={min(snrs):.1f} "
              f"max={max(snrs):.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
