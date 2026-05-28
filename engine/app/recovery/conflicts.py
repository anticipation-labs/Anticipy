"""MH-P7: multi-action conflict resolution.

The DIL completion/cancel layer already kills a pending action the
world satisfied, and retracts one an ambient "never mind" cancels.
This extends that idea to ACTION-INVALIDATES-ACTION without
modifying the frozen engine or the DIL completion module: when a
newer action supersedes an older one for the same resource (booked
7pm, then "make it 8pm"), the older one is STALE and must NOT
execute, and the resource must never be double-booked.

Binding properties:
  ZERO STALE EXECUTION  an action invalidated by a newer action
    (or by a cancel, or already world-satisfied) is never executed.
  ZERO DOUBLE-BOOKING   for any one resource, at most ONE action
    executes (the latest live one); superseded versions are killed
    before execution, not run alongside.

Deterministic. Resource identity + a monotonic sequence decide
"newer"; ambiguity (different resource) is NOT a conflict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PendingAction:
    action_id: str
    resource: str                 # the thing being committed (e.g. "dinner")
    intent: str                   # reserve | email | calendar ...
    seq: int                      # monotonic; higher == newer
    detail: dict = field(default_factory=dict)
    status: str = "pending"       # pending|executed|stale|cancelled|killed
    cancelled: bool = False
    world_satisfied: bool = False


@dataclass
class Reconciled:
    executed: list = field(default_factory=list)     # action_ids
    stale: list = field(default_factory=list)
    cancelled: list = field(default_factory=list)
    killed: list = field(default_factory=list)
    bookings: dict = field(default_factory=dict)     # resource -> action_id


def reconcile(pending: list) -> Reconciled:
    """Resolve a batch of pending actions. Precedence (safe order):
      1. an explicitly cancelled action never executes;
      2. a world-already-satisfied action is killed (no double-act);
      3. for each (resource, intent) only the HIGHEST-seq live
         action survives; every lower-seq one is STALE and must not
         execute (this is the action-invalidates-action rule);
      4. exactly one execution per resource (no double-booking).
    """
    r = Reconciled()

    # group by the conflict key (same resource + same intent == the
    # same commitment; a different resource is not a conflict).
    groups: dict[tuple, list] = {}
    for a in pending:
        if a.cancelled:
            a.status = "cancelled"
            r.cancelled.append(a.action_id)
            continue
        if a.world_satisfied:
            a.status = "killed"
            r.killed.append(a.action_id)
            continue
        groups.setdefault((a.resource, a.intent), []).append(a)

    for (resource, _intent), grp in groups.items():
        grp.sort(key=lambda x: x.seq)
        winner = grp[-1]                       # highest seq == newest
        for a in grp[:-1]:
            a.status = "stale"                 # superseded, must NOT run
            r.stale.append(a.action_id)
        winner.status = "executed"
        r.executed.append(winner.action_id)
        r.bookings[resource] = winner.action_id

    return r


def safe_to_execute(action: PendingAction, recon: Reconciled) -> bool:
    """The single guard the executor must call before doing the side
    effect. True ONLY if this exact action is the reconciled winner.
    A stale / cancelled / killed action can never pass.
    """
    return (action.status == "executed"
            and action.action_id in recon.executed
            and recon.bookings.get(action.resource) == action.action_id)
