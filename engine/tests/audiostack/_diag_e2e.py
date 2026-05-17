"""Why is end-to-end true_pass 0 everywhere? Measure, do not guess.
Run a few WEARER_DIRECT_COMMAND + BOSS_INSTRUCTION items through the
bridge and print: stack outcome, whether lines were emitted, the
RAW frozen-engine decision (or exception). Pinpoints stack-not-
emitting vs engine-not-ACTing vs bridge-exception.
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
from app.audiostack import enrollment
from app.audiostack.stack import AudioStack
from app.anticipy import action_handoff, platform_adapter
from app.audiostack.engine_bridge import _ctx


def main() -> int:
    action_handoff.use_mock()
    enrollment.enroll_synthetic_wearer("wearer")
    st = AudioStack("wearer")
    ctx = _ctx("wearer")
    out = tempfile.mkdtemp(prefix="diag_e2e_")
    for cat in ("WEARER_DIRECT_COMMAND", "BOSS_INSTRUCTION_IN_CONVERSATION"):
        spec = C.SPEC_BY_NAME[cat]
        for i in range(3):
            wav_arr, it = C._assemble_item(spec, i, 20260516 + i)
            wp = Path(out) / f"{it.item_id}.wav"
            A.write_wav(wp, wav_arr)
            wav = A.load_wav(wp)
            platform_adapter.transcript_source().drain()
            dec, utts = st.process(wav, {"category": cat, "ts": 0.0})
            lines = platform_adapter.transcript_source().drain()
            print(f"\n[{it.item_id}] expected={it.expected_text!r}")
            print(f"  stack_outcome={dec.outcome} reason={dec.reason!r}")
            print(f"  n_utts={len(utts)} wearer_utts="
                  f"{sum(1 for u in utts if u.is_wearer)} "
                  f"emitted_lines={lines}")
            if dec.outcome == "ACTIONABLE" and lines:
                import asyncio
                from app.anticipy.proactive_engine import ProactiveEngine
                try:
                    r = asyncio.run(ProactiveEngine().decide(
                        lines, ctx, "mac_mic"))
                    print(f"  ENGINE decision={getattr(r,'decision',None)!r} "
                          f"conf={getattr(r,'confidence',None)} "
                          f"reason={str(getattr(r,'evidence',''))[:90]!r}")
                except Exception as e:
                    import traceback
                    print(f"  ENGINE EXCEPTION {type(e).__name__}: {e}")
                    traceback.print_exc()
    return 0


if __name__ == "__main__":
    sys.exit(main())
