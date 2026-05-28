"""Anticipy day-in-the-life proactive product (NEW build, on top of
the FROZEN reasoning system p0..p11 and FROZEN action engine
phase-v4; both git-verified untouched at every gate).

The product is the boring high-frequency moment forty times a day:
"send it to them when you get a chance", "I'll book it". Anticipy
resolves the vague variables against the wearer's real life, decides
if/when/how to involve the wearer, acts through the real engine, and
never floods, never double-acts, never acts on the cancelled thing.

Seven layers + gated edges (see pipeline.py):
  A resolution engine   resolve it/them/that/the-usual against life
  B timing engine        now / deferred-to-condition / scheduled
  C completion detector  kill a pending action already satisfied
  D ambient cancel       retract a live queued action on "never mind"
  E comms decision+limiter urgency/reachability -> channel, debounce
  F surfacing tone        one clear proposal, never a stream
  G personalization       wearer shorthand learned across the day
  H onboarding + UI       new control layer, not the frozen Tauri app
  I loud-room hardening   negative-enrollment + curriculum + 2-mic

Safe failure is asymmetric and hard-coded: when resolution, timing
or addressee is uncertain, do NOT act, CONFIRM or LIFE_LOG. Over-
action and double-action are the disasters; bias hard to under-
action and confirm. Real external delivery and real two-mic
hardware are GATED and labelled unproven, never faked.
"""

__all__ = ["world", "scenario", "metrics", "pipeline"]
