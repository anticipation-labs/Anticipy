"""P1 gate: the preserved cascade still performs through the new
portable spine.

Generates ONLY EXPLICIT_COMMAND and CLEAR_IMPLICIT (the easy and medium
clear paths). Pass condition from the build spec section 6 and phase P1:
both categories exact correct >= 0.92. If it does not pass, the PORT
broke it, not the cascade logic, and the fix is in the wiring, never in
the preserved prompts.
"""

from __future__ import annotations

import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

CATEGORIES = ["EXPLICIT_COMMAND", "CLEAR_IMPLICIT"]


def main() -> int:
    from app.anticipy import harness
    from app.anticipy.proactive_engine import make_decide_fn
    from app.anticipy.seams import UserContext

    decide_fn = make_decide_fn(lambda case: UserContext(user_id="p1-tester", autonomy_level=0.92))
    sb = harness.run_suite(CATEGORIES, decide_fn, "p1-cascade-revalidated", run_adversarial=True)
    print(harness.format_scoreboard(sb))

    blocks = sb["categories"]
    ok = all(blocks[c].get("exact_correct", 0.0) >= 0.92 for c in CATEGORIES)
    adv = sb.get("adversarial", {"pass": True})
    ok = ok and adv.get("pass", True)
    print(f"P1_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
