"""Is the compound firm-up command a deterministic ACT, or flicker?

Runs the EXACT compound.py firm_decision stimulus through the REAL
engine 5x and prints every decision. If it flickers ACT/STORE_AS_LATENT
the cause is provider/temp-0 variance (root-cause fix = provider
routing in platform_adapter); if it is consistently STORE_AS_LATENT the
scenario stimulus is genuinely not a firm command and must be
strengthened to actually be the direct command the scenario tests.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from app.anticipy.proactive_engine import ProactiveEngine  # noqa: E402
from app.anticipy.seams import UserContext, UserProfile  # noqa: E402

STIMULUS = "Book that dinner we talked about, Friday at 7 at the usual place."


async def one(i: int) -> str:
    prof = UserProfile(
        user_id="cmp-det", name="Omar", role_title="Founder",
        what_they_do="runs an AI hardware startup",
        mandate="Handle scheduling, dinner bookings and email proactively. "
        "Do not touch payroll or legal.",
        people={"the boss": "Dana", "us": "Omar and Priya, party of two"},
        trajectory_confidence=0.8, days_since_onboard=40,
    )
    eng = ProactiveEngine()
    r = await eng.decide(
        [{"speaker_id": "WEARER", "text": STIMULUS}],
        UserContext.from_profile(prof), "direct")
    print(f"run{i}: decision={r.decision} conf={getattr(r,'confidence',None)} "
          f"action={(r.intent or {}).get('action_category') if isinstance(r.intent,dict) else None}")
    return r.decision


async def main():
    decs = [await one(i) for i in range(5)]
    n_act = sum(d == "ACT" for d in decs)
    print(f"ACT {n_act}/5  decisions={decs}")
    print("VERDICT", "DETERMINISTIC_ACT" if n_act == 5 else (
        "FLICKER" if 0 < n_act < 5 else "DETERMINISTIC_NOT_ACT"))


if __name__ == "__main__":
    asyncio.run(main())
