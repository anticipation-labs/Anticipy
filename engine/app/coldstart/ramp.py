"""MH-P10: the onboarding cold-start experience.

The hard tension: on day 0 the system knows nothing about the
wearer, so it must NOT act autonomously much, but it also must not
drown them in questions or it loses them in the retention-critical
first run.

The autonomy threshold itself is NOT redefined here. The FROZEN
engine already owns the validated progressive ramp
(app.anticipy.autonomy.act_threshold: a high bar on day 0 that
lowers only as trajectory_confidence and days_since_onboard grow).
This layer REUSES that read-only and adds exactly the cold-start
experience around it:

  - a non-annoying ASK budget per day (excess candidates are
    deferred / life-logged, never flooded);
  - a trust-earning loop (a confirmed-correct proposal nudges
    trajectory_confidence up; a correction nudges it down) that
    feeds the frozen ramp's own input;
  - the safety bindings are invariant across every day: chatter is
    never actioned, an ultra-high item is always confirmed
    regardless of ramp level. The ramp can only make the system
    MORE conservative, never less safe.

Nothing frozen is modified; the frozen ramp is the single source
of the ACT threshold.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ASK_CAP_PER_DAY = 4               # non-annoying surfacing budget early
TRUST_UP = 0.12                   # a confirmed-correct proposal earns
TRUST_DOWN = 0.20                 # a correction costs more than it earns


def frozen_threshold(days_since_onboard: int,
                      trajectory_confidence: float,
                      onboarded: bool) -> float:
    """The ACT threshold straight from the FROZEN autonomy ramp.
    Read-only reuse via the public seam; never redefined here.

    `onboarded` models the real cold-start transition: BEFORE the
    wearer completes the onboarding intake the profile is not
    populated and the frozen ramp returns its highest COLD_START
    bar (confirm almost everything). AFTER intake the profile is
    populated and the frozen ramp lowers ONBOARDED -> SEASONED as
    trajectory_confidence accrues. Both branches are the frozen
    engine's own behaviour, not redefined here.
    """
    from app.anticipy.autonomy import act_threshold
    from app.anticipy.seams import UserContext, UserProfile

    if not onboarded:
        # unpopulated profile -> frozen returns COLD_START.
        return float(act_threshold(UserContext.from_profile(UserProfile(
            user_id="coldstart", name="", role_title="",
            what_they_do="", mandate=""))))
    return float(act_threshold(UserContext.from_profile(UserProfile(
        user_id="coldstart", name="Omar", role_title="Founder",
        what_they_do="runs an AI hardware startup",
        mandate="Handle scheduling and email proactively.",
        days_since_onboard=max(0, int(days_since_onboard)),
        trajectory_confidence=max(0.0, min(1.0,
                                           float(trajectory_confidence)))))))


def earn_trust(tconf: float, confirmed_correct: bool) -> float:
    d = TRUST_UP if confirmed_correct else -TRUST_DOWN
    return max(0.0, min(1.0, float(tconf) + d))


@dataclass
class DayLog:
    day: int
    threshold: float
    acted: int = 0
    asked: int = 0
    deferred_over_cap: int = 0
    chatter_false_action: int = 0
    ultra_high_unconfirmed: int = 0


@dataclass
class ColdStartRun:
    days: list = field(default_factory=list)
    tconf_trace: list = field(default_factory=list)


def simulate_first_days(script: list) -> ColdStartRun:
    """`script` is [day0_items, day1_items, ...]; each item is a dict
    {conf, kind}, kind in {clear, vague, chatter, ultra_high}. Returns
    per-day behaviour. The frozen threshold decides ACT vs hold; the
    ASK budget caps surfacing; the safety bindings are enforced
    regardless of the ramp.
    """
    run = ColdStartRun()
    tconf = 0.0
    for day, items in enumerate(script):
        # The wearer completes the onboarding intake on day 0; from
        # day 1 on the profile is populated and the frozen ramp can
        # graduate. Day 0 is genuinely pre-onboarding (COLD_START).
        onboarded = day >= 1
        thr = frozen_threshold(day, tconf, onboarded)
        dl = DayLog(day=day, threshold=round(thr, 4))
        for it in items:
            kind = it.get("kind")
            conf = float(it.get("conf", 0.0))

            if kind == "chatter":
                # safety binding: NEVER actioned, ever, any day.
                continue
            if kind == "ultra_high":
                # safety binding: always confirmed, never auto-acted,
                # regardless of how far the ramp has progressed.
                if dl.asked < ASK_CAP_PER_DAY:
                    dl.asked += 1
                else:
                    dl.deferred_over_cap += 1
                continue

            if conf >= thr:
                dl.acted += 1
                # a correct autonomous act also earns a little trust
                tconf = earn_trust(tconf, confirmed_correct=True)
            else:
                # hold as a question, within the non-annoying cap; the
                # wearer's confirmation is what earns trust early.
                if dl.asked < ASK_CAP_PER_DAY:
                    dl.asked += 1
                    tconf = earn_trust(tconf, confirmed_correct=True)
                else:
                    dl.deferred_over_cap += 1
        run.days.append(dl)
        run.tconf_trace.append(round(tconf, 4))
    return run
