"""P1 gate: Layer 1 conversation membership (wearer anchor +
turn-taking), Layer-1 ALONE (Layers 2/3 are still safe stubs).

Scored at the MEMBERSHIP layer, because turning a member into an
ACT needs the Layer 2/3 gates built in P2/P3. The binding property:
a non-wearer-conversation source (stranger, TV, silence) must
produce ZERO conversation members (Layer-1-alone false-trust well
within the 0.02 final budget); and a real in-conversation
instruction must still be admitted (BOSS_INSTRUCTION true-pass not
destroyed). Real Kokoro speech, real ESC-50 acoustics, real
Resemblyzer speaker ID, real silero turn timing. No mocks.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

P1_CATS = ["BOSS_INSTRUCTION_IN_CONVERSATION", "STRANGER_LOUD",
           "TV_PODCAST_PHONE", "SILENCE_AND_MEDIA_ONLY"]
FROZEN = ["engine/app/action_engine", "desktop", "engine/app/anticipy",
          "engine/app/proactive/demand_detection.py",
          "engine/app/proactive/hedge_filter.py",
          "engine/app/proactive/intent_extraction.py",
          "engine/app/proactive/llm_adapter.py"]


def _expected_member_present(item: dict, members) -> bool:
    """For a positive item, did Layer 1 admit the instruction-bearing
    (non-wearer partner) utterance? Match on expected_text overlap.
    """
    exp = (item.get("expected_text") or "").lower().split()
    if not exp:
        return any(not m.is_wearer for m in members)
    for m in members:
        if m.is_wearer:
            continue
        got = m.text.lower()
        if sum(1 for w in exp if w in got) / max(1, len(exp)) >= 0.4:
            return True
    return False


def main() -> int:
    from app.audiostack import corpus, enrollment
    from app.audiostack.stack import AudioStack, ANCHOR_THRESHOLD

    print("== ASTACK P1 GATE (Layer 1 membership) ==")
    print(f"  measured anchor threshold = {ANCHOR_THRESHOLD}")
    enrollment.enroll_synthetic_wearer("wearer")
    out = tempfile.mkdtemp(prefix="astack_p1_")
    # assemble only the 4 P1 categories at a real slice
    from app.audiostack import corpus as C
    keep = [c for c in C.CATEGORY_SPEC if c.name in P1_CATS]
    orig = C.CATEGORY_SPEC
    try:
        C.CATEGORY_SPEC = keep
        man = C.assemble(out, scale=0.30)
    finally:
        C.CATEGORY_SPEC = orig

    st = AudioStack("wearer")
    by_cat: dict[str, list[bool]] = {c: [] for c in P1_CATS}
    pos_pass: list[bool] = []
    for it in man["items"]:
        wav = __import__("app.audiostack.audio", fromlist=["load_wav"]).load_wav(it["wav_path"])
        _utts, members = st.membership_only(wav, {"category": it["category"]})
        cat = it["category"]
        if it["label"] == "ACTIONABLE":
            ok = _expected_member_present(it, members)
            pos_pass.append(ok)
            by_cat[cat].append(ok)
        else:
            leaked = len(members) > 0
            by_cat[cat].append(not leaked)

    log = []
    ok = True

    # false-trust on the negative categories = members admitted / n
    for neg in ("STRANGER_LOUD", "TV_PODCAST_PHONE", "SILENCE_AND_MEDIA_ONLY"):
        res = by_cat[neg]
        n = len(res)
        ft = (sum(1 for r in res if not r) / n) if n else 1.0
        good = ft <= 0.02
        log.append(f"  {neg}: n={n} layer1_false_trust={ft!r} (<=0.02) -> {good}")
        ok = ok and good

    bi = by_cat["BOSS_INSTRUCTION_IN_CONVERSATION"]
    tp = (sum(1 for r in bi if r) / len(bi)) if bi else 0.0
    bi_ok = tp >= 0.70   # honest interim; final >=0.90 at P4. not destroyed.
    log.append(f"  BOSS_INSTRUCTION: n={len(bi)} layer1_true_pass={tp!r} "
               f"(interim >=0.70, final >=0.90 @P4) -> {bi_ok}")
    ok = ok and bi_ok

    fr = subprocess.run(["git", "status", "--porcelain"] + FROZEN,
                        cwd=str(ENGINE.parent), capture_output=True, text=True)
    frozen_clean = fr.stdout.strip() == ""
    log.append(f"  frozen paths clean -> {frozen_clean}")
    ok = ok and frozen_clean

    for ln in log:
        print(ln)
    print(f"ASTACK_P1_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
