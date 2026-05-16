"""Progressive autonomy ramp. Resolves the cold start tension.

A newly onboarded agent is deliberately biased to ask more and act
less, like a competent new hire who confirms before acting in week one.
The confidence required to ACT autonomously starts high and lowers as
the profile fills, memory accumulates, and the trajectory log proves the
agent right. It is never stupid early because it confirms instead of
guessing; it earns the right to act without confirming. This is a real
coded policy with a measurable ramp, not a slogan.

The ACT threshold is the minimum confidence at which a resolved,
unhedged, authorized actionable intent fires as ACT rather than being
held as STORE_AS_LATENT or surfaced as ASK.
"""

from __future__ import annotations

from app.anticipy.seams import UserContext

# Operating points (precision skewed: when in doubt, do not act).
COLD_START = 0.97   # no profile yet: confirm almost everything
ONBOARDED = 0.92    # profile populated: competent but still cautious
SEASONED = 0.85     # trajectory has proven the agent right repeatedly

# The build spec section 1 floor for ACT: confidence >= 0.85. The ramp
# never goes below this; earning trust lowers the bar to it, not under.
FLOOR = 0.85


def act_threshold(ctx: UserContext) -> float:
    """The confidence an authorized, references resolved, not genuinely
    hedged actionable intent must reach to fire as ACT.

    Ramp inputs, all from the (stubbed in P2, filled in P7) profile seam:
      - no profile            -> COLD_START
      - profile populated     -> ONBOARDED, then lowered by accrued
                                 trajectory confidence toward FLOOR
      - days since onboard     gently relaxes alongside trajectory proof
    """
    prof = ctx.profile
    if prof is None or not prof.is_populated():
        return COLD_START

    base = ONBOARDED
    # trajectory_confidence in [0,1]: 0 keeps the onboarded bar, 1 earns
    # the seasoned bar. Linear, clamped, never below the spec floor.
    tconf = max(0.0, min(1.0, float(getattr(prof, "trajectory_confidence", 0.0))))
    earned = base - (base - SEASONED) * tconf

    # a small day based relaxation, capped, so a long lived account with
    # no contrary evidence still trends down but trajectory proof
    # dominates
    days = max(0, int(getattr(prof, "days_since_onboard", 0)))
    day_relax = min(0.03, days * 0.001)

    return round(max(FLOOR, earned - day_relax), 4)


def autonomy_state(ctx: UserContext) -> dict:
    """Inspectable ramp state for the trajectory log and the P9
    measurable ramp assertion.
    """
    return {
        "threshold": act_threshold(ctx),
        "has_profile": ctx.profile is not None and ctx.profile.is_populated(),
        "trajectory_confidence": getattr(ctx.profile, "trajectory_confidence", 0.0) if ctx.profile else 0.0,
        "days_since_onboard": getattr(ctx.profile, "days_since_onboard", 0) if ctx.profile else 0,
    }
