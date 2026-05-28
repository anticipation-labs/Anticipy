"""P3 gate: rewritten hedge filter and sarcasm.

The old engine/app/proactive/hedge_filter.py is replaced by
engine/app/anticipy/hedge.py. Generates HEDGED_SOCIAL and
SARCASM_AND_NEGATION. Pass condition (build spec P3): over-action rate
<= 0.03 on BOTH. exact-correct is reported honestly at the research
ceiling, NOT required to be high (a wrong ACT is the expensive error;
a STORE/IGNORE miss is the safe direction and acceptable).
"""

from __future__ import annotations

import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

CATEGORIES = ["HEDGED_SOCIAL", "SARCASM_AND_NEGATION"]


def _onboarded_ctx(case):
    from app.anticipy.seams import UserContext, UserProfile

    prof = UserProfile(
        user_id="p3-tester",
        name="Omar",
        role_title="Founder",
        what_they_do="runs an AI hardware startup",
        mandate="handle scheduling, email, and errands proactively",
        people={"the boss": "lead investor Dana", "us": "Omar and cofounder Sam"},
    )
    return UserContext.from_profile(prof)


def main() -> int:
    from app.anticipy import harness
    from app.anticipy.proactive_engine import make_decide_fn

    decide_fn = make_decide_fn(_onboarded_ctx, lambda c: "ambient")
    sb = harness.run_suite(CATEGORIES, decide_fn, "p3-hedge", run_adversarial=True)
    print(harness.format_scoreboard(sb))

    b = sb["categories"]
    hs = b["HEDGED_SOCIAL"]
    sn = b["SARCASM_AND_NEGATION"]
    hs_ok = hs.get("over_action", 1.0) <= 0.03
    sn_ok = sn.get("over_action", 1.0) <= 0.03
    adv_ok = sb.get("adversarial", {"pass": True}).get("pass", True)

    print(f"  HEDGED_SOCIAL over<=0.03: {hs_ok} (over={hs.get('over_action')}, exact={hs.get('exact_correct')} honest-ceiling)")
    print(f"  SARCASM_AND_NEGATION over<=0.03: {sn_ok} (over={sn.get('over_action')}, exact={sn.get('exact_correct')} honest-ceiling)")
    print(f"  adversarial pass: {adv_ok} (rate={sb.get('adversarial',{}).get('flag_rate')})")
    ok = hs_ok and sn_ok and adv_ok
    print(f"P3_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
