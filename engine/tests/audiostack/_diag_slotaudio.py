"""ASR confidence is useless here (parakeet ~1.0 on destroyed audio,
measured). The real trust signal: is the AUDIO under the load-bearing
word actually clean? The corpus now genuinely corrupts ONLY the slot
region (heavy real noise + a literal dropout). Measure, per
instruction utterance, the slot-token time region's: dropout fraction
(samples below a tiny energy floor) and local RMS vs whole-utterance
RMS. Find the band that separates a corrupted LOADBEARING slot from a
clean WEARER_DIRECT / BOSS slot.
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
from app.audiostack import layer3


def _slot_region_stats(seg: np.ndarray, asr) -> list:
    """For each load-bearing slot word, return (type, dropout_frac,
    local_rms_ratio) over the slot's token time span."""
    wc = layer3.words_with_conf(asr.text, asr.tokens)
    # rebuild per-word time spans from tokens in order (same walk)
    import re
    words = re.findall(r"[A-Za-z0-9$']+", asr.text or "")
    ti = 0
    spans = []
    for w in words:
        tgt = layer3._norm(w)
        if not tgt:
            continue
        buf = ""
        st = en = None
        while ti < len(asr.tokens) and len(buf) < len(tgt):
            tk = asr.tokens[ti]
            ti += 1
            p = layer3._norm(getattr(tk, "text", "") or "")
            if not p:
                continue
            if st is None:
                st = float(getattr(tk, "start", 0.0) or 0.0)
            en = float(getattr(tk, "end", 0.0) or 0.0)
            buf += p
        spans.append((w, st, en))
    whole_rms = float(np.sqrt(np.mean(seg ** 2) + 1e-9))
    out = []
    sset = layer3.extract_slots(asr.text, asr.tokens)
    slot_words = {layer3._norm(t) for items in sset.values()
                  for t, _c in items}
    for w, st, en in spans:
        if layer3._norm(w) not in slot_words or st is None or en is None:
            continue
        i0, i1 = int(st * A.SR), int(max(en, st + 0.05) * A.SR)
        reg = seg[i0:i1]
        if len(reg) < 80:
            continue
        floor = 0.01 * (np.max(np.abs(seg)) + 1e-9)
        drop = float(np.mean(np.abs(reg) < floor))
        rms = float(np.sqrt(np.mean(reg ** 2) + 1e-9))
        out.append((w, round(drop, 3), round(rms / (whole_rms + 1e-9), 3)))
    return out


def main() -> int:
    for cat in ("LOADBEARING_WORD_STRESS", "WEARER_DIRECT_COMMAND",
                "BOSS_INSTRUCTION_IN_CONVERSATION"):
        spec = C.SPEC_BY_NAME[cat]
        rep = []
        for i in range(6):
            wav_arr, it = C._assemble_item(spec, i, 20260516 + i)
            spans = A.vad_segments(wav_arr)
            if not spans:
                continue
            s, e = max(spans, key=lambda se: se[1] - se[0])
            seg = wav_arr[int(s * A.SR):int(e * A.SR)]
            asr = A.asr_tokens(seg)
            rep += _slot_region_stats(seg, asr)
        if rep:
            drops = [d for _w, d, _r in rep]
            ratios = [r for _w, _d, r in rep]
            print(f"{cat}: n_slots={len(rep)} "
                  f"dropout mean={np.mean(drops):.3f} max={max(drops):.3f} | "
                  f"rms_ratio mean={np.mean(ratios):.3f} "
                  f"min={min(ratios):.3f}")
            print("  samples:", rep[:6])
        else:
            print(f"{cat}: NO slot regions extracted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
