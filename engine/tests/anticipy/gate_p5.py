"""P5 gate: full proactive integration and the false ACT budget.

Runs the ENTIRE engine core corpus (all 11 categories, ~590 cases)
through the fully integrated engine with one unified context factory,
and requires every per category pass condition from build spec section
6 to hold SIMULTANEOUSLY, plus the adversarial second model check at
<= 5 percent. This is also where P1's deferred CLEAR_IMPLICIT is
re graded with the rewritten hedge and the four way decision policy.

Every case gets an isolated per case memory namespace so the
STORE_AS_LATENT writes of parallel cases never contaminate another
case's reference resolution. REFERENCE present cases seed the fixed
anchor vocabulary; everything else gets an onboarded profile.
"""

from __future__ import annotations

import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

ENGINE_CORE = [
    "EXPLICIT_COMMAND", "CLEAR_IMPLICIT", "DIRECT_USER_COMMAND",
    "BOSS_DIRECTED", "HEDGED_SOCIAL", "AMBIGUOUS_ADDRESSEE",
    "SARCASM_AND_NEGATION", "PURE_AMBIENT_NEGATIVE",
    "REFERENCE_RESOLUTION", "MULTI_SPEAKER_CROSSTALK",
    "NEVERMIND_RECONCILIATION",
]

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
    uid = f"p5-{cat[:6]}-{cid}"
    memory.reset(uid)

    if cat == "REFERENCE_RESOLUTION" and variant == "present":
        memory.seed(uid, ANCHORS)
        prof = UserProfile(
            user_id=uid, name="Omar", role_title="Founder",
            mandate="handle scheduling and errands proactively",
            people={"the boss": "Dana the lead investor", "us": "Omar and Sam"},
        )
        return UserContext.from_profile(prof)

    if cat == "REFERENCE_RESOLUTION" and variant == "absent":
        prof = UserProfile(
            user_id=uid, name="Omar", role_title="Founder",
            mandate="handle scheduling and errands proactively",
        )
        return UserContext.from_profile(prof)

    prof = UserProfile(
        user_id=uid, name="Omar", role_title="Founder",
        what_they_do="runs an AI hardware startup",
        mandate="handle scheduling, email, and errands proactively",
        people={"the boss": "Dana the lead investor", "us": "Omar and cofounder Sam"},
    )
    return UserContext.from_profile(prof)


def _source(case):
    return "direct" if case.get("category") == "DIRECT_USER_COMMAND" else "ambient"


def main() -> int:
    from app.anticipy import harness
    from app.anticipy.proactive_engine import make_decide_fn

    decide_fn = make_decide_fn(_ctx, _source)
    sb = harness.run_suite(ENGINE_CORE, decide_fn, "p5-proactive-complete", run_adversarial=True)
    print(harness.format_scoreboard(sb))

    b = sb["categories"]

    def ex(c):
        return b.get(c, {}).get("exact_correct", 0.0)

    def ov(c):
        return b.get(c, {}).get("over_action", 1.0)

    conds = {
        "EXPLICIT_COMMAND exact>=0.92": ex("EXPLICIT_COMMAND") >= 0.92,
        "CLEAR_IMPLICIT exact>=0.92": ex("CLEAR_IMPLICIT") >= 0.92,
        "DIRECT_USER_COMMAND exact>=0.92": ex("DIRECT_USER_COMMAND") >= 0.92,
        "BOSS_DIRECTED exact>=0.92": ex("BOSS_DIRECTED") >= 0.92,
        "HEDGED_SOCIAL over<=0.03": ov("HEDGED_SOCIAL") <= 0.03,
        "SARCASM over<=0.03": ov("SARCASM_AND_NEGATION") <= 0.03,
        "PURE_AMBIENT over<=0.03 (false-ACT budget)": ov("PURE_AMBIENT_NEGATIVE") <= 0.03,
        "AMBIGUOUS silent_act==0": b.get("AMBIGUOUS_ADDRESSEE", {}).get("silent_act", 1) == 0,
        "MULTI_SPEAKER no silent ACT": b.get("MULTI_SPEAKER_CROSSTALK", {}).get("pass", False),
        "REFERENCE present>=0.85 & absent all ASK": b.get("REFERENCE_RESOLUTION", {}).get("pass", False),
        "NEVERMIND final>=0.90": ex("NEVERMIND_RECONCILIATION") >= 0.90,
        "adversarial flag rate <=0.05": sb.get("adversarial", {}).get("pass", True),
    }
    print("\n-- P5 pass conditions --")
    for k, v in conds.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    ok = all(conds.values())
    print(f"P5_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
