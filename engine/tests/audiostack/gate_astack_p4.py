"""P4 gate: the FULL stack into the FROZEN engine, ENTIRE dirty
corpus end to end (mocked action), full honest scoreboard.

BINDING (hard build-failure if breached):
  false-trust <= 0.02 on STRANGER_LOUD + TV_PODCAST_PHONE +
    ABOUT_YOU_NOT_TO_YOU + SILENCE_AND_MEDIA_ONLY  (THE number)
  LOADBEARING_WORD_STRESS: zero blind actions, confirm >= 0.90
  WEARER_SILENT_DEGRADED: zero actions, DEGRADED 100%
  adversarial different-model recheck flag-rate <= 0.05
  corpus self_check (R1..R4) True
  frozen engine + reasoning + cascade git-clean

REPORTED HONEST (target shown, per spec sec 3/7/8 not gamed by
sacrificing false-trust, build continues):
  BOSS_INSTRUCTION + WEARER_DIRECT_COMMAND true-pass target >= 0.90
  BOSS_DRIVEBY caught target >= 0.80
  NOISY_REAL_ROOM true-pass target >= 0.70
Both rates printed together for every category, no rounding.
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

FROZEN = ["engine/app/action_engine", "desktop", "engine/app/anticipy",
          "engine/app/proactive/demand_detection.py",
          "engine/app/proactive/hedge_filter.py",
          "engine/app/proactive/intent_extraction.py",
          "engine/app/proactive/llm_adapter.py"]
HARD_NEG = ["STRANGER_LOUD", "TV_PODCAST_PHONE",
            "ABOUT_YOU_NOT_TO_YOU", "SILENCE_AND_MEDIA_ONLY"]
_ADV_SYS = ("A wearable earpiece decided to ACT on an overheard line. "
            "Given the line and what it should have been, answer ONE "
            "token: CORRECT if acting was right, or WRONG if acting was "
            "a mistake (stranger/TV/about-you/ambiguous should NOT act).")


def _adversarial(acted_items: list[dict], frac=0.10, seed=13) -> dict:
    from app.anticipy import platform_adapter
    if not acted_items:
        return {"sampled": 0, "flagged": 0, "flag_rate": 0.0, "pass": True}
    rng = random.Random(seed)
    k = max(1, int(len(acted_items) * frac))
    sample = rng.sample(acted_items, min(k, len(acted_items)))
    flagged = 0
    for it in sample:
        u = (f"LINE: {it['expected_text'] or it['item_id']!r}\n"
             f"TRUE LABEL: {it['label']} ({it['category']})\n"
             f"ENGINE: ACT")
        r = platform_adapter.adversarial_model_call(_ADV_SYS, u, max_tokens=8)
        if r.ok and (r.content or "").strip().upper().startswith("WRONG"):
            flagged += 1
    n = len(sample)
    fr = flagged / n if n else 0.0
    return {"sampled": n, "flagged": flagged, "flag_rate": fr,
            "pass": fr <= 0.05}


def main() -> int:
    from app.audiostack import corpus as C
    from app.audiostack import enrollment, metrics as M
    from app.audiostack.engine_bridge import (E2EResult, _ctx,
                                              run_end_to_end, to_item_result)
    from app.audiostack.stack import AudioStack
    from app.anticipy import action_handoff

    print("== ASTACK P4 GATE (full stack -> FROZEN engine, entire corpus) ==")
    action_handoff.use_mock()                 # P4: action mocked
    enrollment.enroll_synthetic_wearer("wearer")
    out = tempfile.mkdtemp(prefix="astack_p4_")
    man = C.assemble(out, scale=1.0)          # the ENTIRE fixed corpus
    sc_ok, sc_rep = C.self_check(man)
    print(f"  corpus n={man['n']} self_check(R1..R4)={sc_ok}")

    st = AudioStack("wearer")
    ctx = _ctx("wearer")
    results: list[M.ItemResult] = []
    acted_items: list[dict] = []
    for it in man["items"]:
        e = run_end_to_end(it, st, ctx)
        results.append(to_item_result(e))
        if e.end_to_end_acted:
            acted_items.append(it)

    sb = M.scoreboard(results)
    print(M.render(sb))
    cats = sb["categories"]

    def ft(c):
        return cats.get(c, {}).get("false_trust", 1.0)

    def tp(c):
        return cats.get(c, {}).get("true_pass", 0.0)

    adv = _adversarial(acted_items)
    print(f"  adversarial(diff-model Kimi): sampled={adv['sampled']} "
          f"flagged={adv['flagged']} flag_rate={adv['flag_rate']!r} "
          f"(<=0.05) -> {adv['pass']}")

    log: list[str] = []
    ok = True

    agg_neg_ft = sb["aggregate_hard_negative_false_trust"]
    neg_ok = all(ft(c) <= 0.02 for c in HARD_NEG) and agg_neg_ft <= 0.02
    log.append(f"  BINDING hard-negative false-trust per-cat="
               f"{ {c: ft(c) for c in HARD_NEG} } agg={agg_neg_ft!r} "
               f"(<=0.02) -> {neg_ok}")
    ok &= neg_ok

    lb = cats.get("LOADBEARING_WORD_STRESS", {})
    lb_ok = (sb["total_blind_fires"] == 0 and lb.get("confirm_rate", 0) >= 0.90)
    log.append(f"  BINDING LOADBEARING: blind_fires={sb['total_blind_fires']} "
               f"confirm={lb.get('confirm_rate', 0)!r} -> {lb_ok}")
    ok &= lb_ok

    wd = cats.get("WEARER_SILENT_DEGRADED", {})
    wd_ok = (wd.get("degraded_declared_rate", 0) == 1.0
             and tp("WEARER_SILENT_DEGRADED") == 0.0)
    log.append(f"  BINDING WEARER_SILENT_DEGRADED: "
               f"degraded={wd.get('degraded_declared_rate', 0)!r} "
               f"true_pass={tp('WEARER_SILENT_DEGRADED')!r} -> {wd_ok}")
    ok &= wd_ok

    ok &= adv["pass"]
    log.append(f"  BINDING adversarial flag_rate<=0.05 -> {adv['pass']}")
    log.append(f"  BINDING corpus self_check(R1..R4) -> {sc_ok}")
    ok &= sc_ok

    fr = subprocess.run(["git", "status", "--porcelain"] + FROZEN,
                        cwd=str(ENGINE.parent), capture_output=True, text=True)
    fc = fr.stdout.strip() == ""
    log.append(f"  BINDING frozen engine/reasoning/cascade clean -> {fc}")
    ok &= fc

    # reported-honest true-pass targets (NOT build-blocking; spec 3/7/8)
    for c, t in (("BOSS_INSTRUCTION_IN_CONVERSATION", 0.90),
                 ("WEARER_DIRECT_COMMAND", 0.90),
                 ("BOSS_DRIVEBY", 0.80),
                 ("NOISY_REAL_ROOM", 0.70)):
        v = tp(c)
        note = "MEETS" if v >= t else ("HONEST CEILING (spec 7/8, "
                                       "not gamed, build continues)")
        log.append(f"  REPORTED {c} true_pass={v!r} (target >={t}; {note})")

    for ln in log:
        print(ln)
    print(f"ASTACK_P4_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
