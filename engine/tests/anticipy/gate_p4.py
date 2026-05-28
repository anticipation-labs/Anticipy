"""P4 gate: Mem0 style memory with reconciliation, reference
resolution against memory and profile.

Generates REFERENCE_RESOLUTION (present and absent variants) and
NEVERMIND_RECONCILIATION. Pass (build spec P4):
  - REFERENCE_RESOLUTION present exact-correct >= 0.85 (resolves from
    memory/profile, ACT)
  - REFERENCE_RESOLUTION absent ALWAYS ASK (never a guessed ACT)
  - NEVERMIND_RECONCILIATION final-state correct >= 0.90 (the retracted
    intent is removed from memory)

Each case gets an isolated per case memory namespace so parallel cases
do not contaminate each other. Present cases seed a known anchor set
(the controllable equivalent of accrued memory plus the onboarding
profile); absent cases have no anchors at all.
"""

from __future__ import annotations

import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

CATEGORIES = ["REFERENCE_RESOLUTION", "NEVERMIND_RECONCILIATION"]

# Exactly the fixed present-variant reference vocabulary, so the
# proven resolve_reference reliably matches present cases. Absent
# cases use phrases with no anchor here, so they cannot resolve.
ANCHORS = {
    "the usual place": "Carbone on Thompson St",
    "the usual order": "oat milk flat white, no foam",
    "my usual spot": "the corner table at Cafe Reggio",
    "the boss": "Dana, the lead investor",
    "the team": "the engineering standup group",
    "my regular": "the Tuesday 9am dental cleaning slot",
}


def _ctx(case):
    from app.anticipy import memory
    from app.anticipy.seams import UserContext, UserProfile

    cid = case.get("case_id", "x")
    cat = case.get("category")
    variant = case.get("variant")

    if cat == "REFERENCE_RESOLUTION" and variant == "present":
        uid = f"p4-refp-{cid}"
        memory.reset(uid)
        memory.seed(uid, ANCHORS)
        prof = UserProfile(
            user_id=uid, name="Omar", role_title="Founder",
            mandate="handle scheduling and errands proactively",
            people={"the boss": "Dana the lead investor", "us": "Omar and Sam"},
        )
        return UserContext.from_profile(prof)

    if cat == "REFERENCE_RESOLUTION" and variant == "absent":
        uid = f"p4-refa-{cid}"
        memory.reset(uid)  # genuinely no anchors anywhere
        prof = UserProfile(
            user_id=uid, name="Omar", role_title="Founder",
            mandate="handle scheduling and errands proactively",
        )  # no people anchors
        return UserContext.from_profile(prof)

    uid = f"p4-nv-{cid}"
    memory.reset(uid)
    prof = UserProfile(
        user_id=uid, name="Omar", role_title="Founder",
        mandate="handle scheduling and errands proactively",
        people={"us": "Omar and Sam"},
    )
    return UserContext.from_profile(prof)


def main() -> int:
    from app.anticipy import harness
    from app.anticipy.proactive_engine import make_decide_fn

    decide_fn = make_decide_fn(_ctx, lambda c: "ambient")
    sb = harness.run_suite(CATEGORIES, decide_fn, "p4-memory", run_adversarial=True)
    print(harness.format_scoreboard(sb))

    b = sb["categories"]
    ref = b["REFERENCE_RESOLUTION"]
    nv = b["NEVERMIND_RECONCILIATION"]
    ref_ok = ref.get("pass", False)  # grader: present>=0.85 AND absent all ASK
    nv_ok = nv.get("exact_correct", 0.0) >= 0.90
    adv_ok = sb.get("adversarial", {"pass": True}).get("pass", True)

    print(f"  REFERENCE_RESOLUTION: pass={ref_ok} present_ACT={ref.get('present_act_rate')} absent_all_ASK={ref.get('absent_all_ask')}")
    print(f"  NEVERMIND final-state >=0.90: {nv_ok} (exact={nv.get('exact_correct')})")
    print(f"  adversarial pass: {adv_ok}")
    ok = ref_ok and nv_ok and adv_ok
    print(f"P4_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
