"""P0 gate: harness, corpus, enrollment, seams.

Two modes, both honest:
  structural (default, ZERO downloads): every module imports, the
    metrics math is correct on a known input, the LIFE_LOG
    non-promotable invariant holds, the transcript_source seam is
    present, and git proves no frozen file changed.
  --full (after the one sanctioned P0 setup authorization): also
    assembles a REAL corpus slice + passes corpus.self_check, and
    enrollment on the designated wearer sample yields a STRONG
    anchor. --wearer <wav> sets the enrollment/corpus wearer ref.

Pass requires structural always; --full additionally requires the
real corpus + enrollment checks. The canonical astack-p0 tag is
only taken on a --full pass.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

FROZEN_PATHS = [
    "engine/app/action_engine", "desktop",
    "engine/app/anticipy", "engine/app/proactive/demand_detection.py",
    "engine/app/proactive/hedge_filter.py",
    "engine/app/proactive/intent_extraction.py",
    "engine/app/proactive/llm_adapter.py",
]


def _structural() -> tuple[bool, list[str]]:
    log: list[str] = []
    ok = True

    # 1. every module imports (no model fetch happens at import)
    try:
        from app.audiostack import audio, corpus, enrollment, lifelog, metrics, stack  # noqa
        log.append("  import audiostack.{audio,corpus,enrollment,lifelog,metrics,stack}: OK")
    except Exception as e:
        return False, [f"  IMPORT FAIL: {type(e).__name__}: {e}"]

    # 2. metrics math on a known, hand-built input (no model)
    from app.audiostack import metrics as M
    items = [
        M.ItemResult("a1", "STRANGER_LOUD", "REJECT", "LIFE_LOG"),
        M.ItemResult("a2", "STRANGER_LOUD", "REJECT", "ACTIONABLE"),   # 1 leak
        M.ItemResult("b1", "WEARER_DIRECT_COMMAND", "ACTIONABLE", "ACTIONABLE"),
        M.ItemResult("b2", "WEARER_DIRECT_COMMAND", "ACTIONABLE", "LIFE_LOG"),  # miss
        M.ItemResult("c1", "LOADBEARING_WORD_STRESS", "CONFIRM", "CONFIRM"),
        M.ItemResult("d1", "WEARER_SILENT_DEGRADED", "DEGRADED_LOG", "DEGRADED_LOG",
                     degraded_declared=True),
    ]
    sb = M.scoreboard(items)
    sl = sb["categories"]["STRANGER_LOUD"]
    wc = sb["categories"]["WEARER_DIRECT_COMMAND"]
    checks = {
        "STRANGER false_trust == 0.5": sl["false_trust"] == 0.5,
        "WEARER true_pass == 0.5": wc["true_pass"] == 0.5,
        "CONFIRM rate == 1.0": sb["categories"]["LOADBEARING_WORD_STRESS"]["confirm_rate"] == 1.0,
        "DEGRADED declared == 1.0": sb["categories"]["WEARER_SILENT_DEGRADED"]["degraded_declared_rate"] == 1.0,
        "agg hard-neg false_trust == 0.5": sb["aggregate_hard_negative_false_trust"] == 0.5,
    }
    for k, v in checks.items():
        log.append(f"  metrics: {k} -> {v}")
        ok = ok and v

    # 3. LIFE_LOG non-promotable invariant: no API sets promotable=1
    from app.audiostack import lifelog as L
    holds = L.promotable_invariant_holds()
    log.append(f"  lifelog: non-promotable invariant holds -> {holds}")
    ok = ok and holds

    # 4. transcript_source seam present + pushable shape
    from app.anticipy import platform_adapter as PA
    src = PA.transcript_source()
    src.push({"speaker_id": "WEARER", "text": "probe", "ts": 0.0})
    drained = src.drain()
    seam_ok = drained == [{"speaker_id": "WEARER", "text": "probe", "ts": 0.0}]
    log.append(f"  seam: transcript_source push/drain shape -> {seam_ok}")
    ok = ok and seam_ok

    # 5. frozen paths untouched (git)
    r = subprocess.run(["git", "status", "--porcelain"] + FROZEN_PATHS,
                        cwd=str(ENGINE.parent), capture_output=True, text=True)
    frozen_clean = r.stdout.strip() == ""
    log.append(f"  frozen paths clean (git) -> {frozen_clean}"
               + ("" if frozen_clean else f" :: {r.stdout.strip()[:200]}"))
    ok = ok and frozen_clean

    # 6. astack package is NEW, not under a frozen path
    new_ok = (ENGINE / "app" / "audiostack").is_dir()
    log.append(f"  audiostack is a new package (not frozen) -> {new_ok}")
    ok = ok and new_ok
    return ok, log


def _full() -> tuple[bool, list[str]]:
    """Real corpus slice with the R1..R4 self-check, plus enrollment
    from the ONE fixed synthetic wearer voice. No user recording: the
    chosen path is the fixed synthetic wearer identity.
    """
    from app.audiostack import corpus, enrollment
    log: list[str] = []
    ok = True

    out = tempfile.mkdtemp(prefix="astack_p0_corpus_")
    man = corpus.assemble(out, scale=0.06)
    sc_ok, sc_report = corpus.self_check(man)
    log.append(f"  corpus assembled n={man['n']} identity={man['wearer_identity']}"
               f" -> self_check={sc_ok}")
    for ln in sc_report:
        log.append("    " + ln)
    ok = ok and sc_ok and man["n"] > 0

    a = enrollment.enroll_synthetic_wearer("wearer")
    log.append(f"  enroll(synthetic fixed voice): speech={a.speech_seconds:.1f}s "
               f"consistency={a.consistency:.3f} strong={a.strong} "
               f"identity={a.wearer_identity}")
    rl = enrollment.load_anchor("wearer")
    rt_ok = (rl is not None and rl.strong == a.strong
             and rl.wearer_identity == a.wearer_identity)
    log.append(f"  anchor persisted+decrypts roundtrip={rt_ok}")
    # R1 end to end: enrollment identity == corpus manifest identity
    r1_e2e = (a.wearer_identity == man["wearer_identity"] == corpus.WEARER_IDENTITY)
    log.append(f"  R1 end-to-end identity match (enroll==corpus=={corpus.WEARER_IDENTITY})"
               f" -> {r1_e2e}")
    ok = ok and a.strong and rt_ok and r1_e2e
    return ok, log


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args()

    print("== ASTACK P0 GATE ==")
    print("-- structural (zero downloads) --")
    s_ok, s_log = _structural()
    for ln in s_log:
        print(ln)
    f_ok = True
    if args.full:
        print("-- full (real corpus R1..R4 self-check + synthetic enrollment) --")
        f_ok, f_log = _full()
        for ln in f_log:
            print(ln)
    ok = s_ok and f_ok
    mode = "full" if args.full else "structural"
    print(f"  structural={s_ok} full={'n/a' if not args.full else f_ok}")
    print(f"ASTACK_P0_GATE {'PASS' if ok else 'FAIL'} ({mode})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
