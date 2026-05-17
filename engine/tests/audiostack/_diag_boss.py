"""Why is BOSS_INSTRUCTION Layer-1 true_pass 0? Measure, do not guess.
For 3 real BOSS items: list every VAD utterance with duration, ASR
text, speaker cosine-to-anchor, is_wearer. Pinpoint whether the
wearer cue is ASR-dropped, too-short-to-embed, or adjacency-too-strict.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from app.audiostack import audio as A
from app.audiostack import corpus as C
from app.audiostack import enrollment as E
from app.audiostack.stack import ANCHOR_THRESHOLD


def main() -> int:
    a = E.enroll_synthetic_wearer("wearer")
    out = tempfile.mkdtemp(prefix="diag_boss_")
    spec = C.SPEC_BY_NAME["BOSS_INSTRUCTION_IN_CONVERSATION"]
    for i in range(3):
        wav_arr, it = C._assemble_item(spec, i, 20260516 + i)
        wp = Path(out) / f"{it.item_id}.wav"
        A.write_wav(wp, wav_arr)
        wav = A.load_wav(wp)
        spans = A.vad_segments(wav)
        print(f"\n[{it.item_id}] expected={it.expected_text!r} "
              f"timeline={it.timeline} dur={len(wav)/A.SR:.1f}s "
              f"n_vad={len(spans)}")
        for s, e in spans:
            seg = wav[int(s * A.SR):int(e * A.SR)]
            d = (e - s)
            asr = A.asr_tokens(seg)
            emb = A.speaker_embed(seg)
            cz = A.cosine(emb, a.vector)
            isw = cz >= ANCHOR_THRESHOLD
            print(f"  span {s:6.2f}-{e:6.2f} dur={d:4.2f}s "
                  f"cos={cz:5.3f} wearer={isw} asr={asr.text[:48]!r}")
    print(f"\nthreshold={ANCHOR_THRESHOLD} embed_min_s=0.40 "
          f"resemblyzer_min_s=0.50")
    return 0


if __name__ == "__main__":
    sys.exit(main())
