"""Layer C (completion detector) + Layer D (ambient cancel). The
two safety-critical layers. Both operate on ALREADY-RESOLVED-AND-
QUEUED actions, which the frozen engine's own tests never covered.

Layer C: before a queued action is allowed to execute, check the
simulated world. If the outcome already occurred by ANY means (the
wearer sent it from their phone, the calendar already changed, mail
already sent) the pending action is SATISFIED and KILLED. Binding:
zero double-action.

Layer D: a cancel utterance ("actually never mind", "scratch that",
"forget it", "don't bother") that refers to a LIVE queued action
retracts it before it executes. The frozen NEVERMIND capability is
the cancel SIGNAL; the match to which queued action is by recency
(the most recent live queued action by the same speaker), which is
the deterministic, honest reference resolution for an ambient
cancel. Binding: zero execution of a cancelled action.
"""

from __future__ import annotations

import re
from typing import Optional

from app.proactive_day.world import SimWorld

_CANCEL_CUE = re.compile(
    r"\b(never\s*mind|nevermind|scratch that|forget it|forget that|"
    r"don'?t bother|cancel that|actually .*(instead|monday|later|"
    r"don'?t)|on second thought|skip (it|that)|no need)\b", re.I)


def is_cancel(text: str, frozen_decision: Optional[str] = None) -> bool:
    """True if this utterance is an ambient cancel. The frozen
    engine's retraction outcome is the primary signal when present
    (reused, not reimplemented); the cue regex is the backstop so a
    cancel is never missed (safe direction: a missed cancel that
    lets a retracted action run is the disaster).
    """
    if frozen_decision in ("RETRACT", "NEVERMIND", "CANCEL"):
        return True
    return bool(_CANCEL_CUE.search(text or ""))


def cancel_target(speaker: str, queued: dict) -> Optional[str]:
    """Match a cancel to the most recent LIVE queued action by the
    same speaker (recency = the deterministic ambient-cancel
    referent). Returns the ev_id to retract, or None.
    """
    best_id, best_ts = None, -1.0
    for ev_id, q in queued.items():
        if q.get("retracted") or q.get("killed") or q.get("executed"):
            continue
        if q.get("speaker", "WEARER") != speaker:
            continue
        if q.get("queued_at", 0.0) >= best_ts:
            best_ts, best_id = q.get("queued_at", 0.0), ev_id
    return best_id


def world_satisfied(action: dict, world: SimWorld) -> bool:
    """Layer C core: has the world already produced this action's
    outcome by any means? Delegates to the world's matcher (sent
    mail, calendar change, anything done manually).
    """
    return world.already_satisfied(action or {})
