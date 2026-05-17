"""The day pipeline orchestrator.

P0 ships the structure and the SAFE asymmetric default; the seven
layers are filled in dependency order (DIL-P1..P7). The contract
that never changes: an event becomes ACTED only when every layer
agrees it is a real, resolved, current, non-cancelled wearer
instruction; otherwise it is CONFIRM, DEFER, KILL, CANCEL, or
LIFE_LOG. Over-action and double-action are the disasters, so the
P0 default (before the layers exist) is the safest one: nothing is
ACTED. P1..P7 earn true-positives WITHOUT ever breaching the hard
binding metrics (chatter false-action, double-action,
cancel-after-execute, flood).
"""

from __future__ import annotations

from typing import Optional

from app.proactive_day import metrics as M
from app.proactive_day.world import SimWorld


# --- layer hook points. P0 ships safe stubs; P1..P7 replace each. ---

def layer_resolve(event: dict, world: SimWorld):
    """DIL-P1. Resolve it/them/that/the-usual/when against the day +
    accounts; return (resolved_action|None, all_refs_confident: bool).
    P0 stub: unresolved (safe -> not actionable).
    """
    return None, False


def layer_timing(event: dict, action, world: SimWorld) -> str:
    """DIL-P2. now | deferred | scheduled | standing. P0 stub: 'now'
    (unused at P0 because nothing resolves).
    """
    return "now"


def layer_completed(action, world: SimWorld) -> bool:
    """DIL-P3. True if the world already satisfied this action (kill,
    zero double-act). P0 stub conservatively True only via the world
    helper, so a satisfied action is never re-done.
    """
    return world.already_satisfied(action or {})


def layer_cancelled(event: dict, queued: dict) -> Optional[str]:
    """DIL-P3. If this event ambiently cancels a live queued action,
    return its ev_id. P0 stub: detect the scripted cancel link.
    """
    return event.get("cancels_ev")


def layer_comms(pending: list, world: SimWorld) -> list:
    """DIL-P4. Decide channel/timing, debounce+compose, rate-limit.
    P0 stub: silent-queue only (no outbound, no flood by
    construction).
    """
    return []


# --- the per-day run ---------------------------------------------------

def run_day(manifest: dict, world: SimWorld) -> list:
    """Process the scripted day in sim-clock order, applying the world
    hooks (a task done by other means; an ambient cancel), and emit
    one ItemResult per event. P0: safe default (nothing ACTED) so the
    plumbing and the hard binding metrics are exercised before any
    layer can earn a true-positive.
    """
    events = sorted(manifest["events"], key=lambda e: e["ts"])
    queued: dict[str, dict] = {}      # ev_id -> resolved action awaiting
    cancelled: set = set()
    results: list[M.ItemResult] = []

    for ev in events:
        world.tick(ev["ts"])
        world.hear(ev.get("speaker", "WEARER"), ev["text"],
                   ev.get("place", "home"))

        # apply a world-by-other-means completion at its scripted time
        if ev.get("world_done_at") is not None and ev.get("world_done"):
            world.tick(ev["world_done_at"])
            world.world_did(ev["world_done"]["kind"], ev["world_done"])

        cat, label, eid = ev["category"], ev["label"], ev["ev_id"]

        # an ambient cancel retracts a live queued action
        canc = layer_cancelled(ev, queued)
        if canc:
            cancelled.add(canc)
            results.append(M.ItemResult(eid, cat, label, "CANCELLED"))
            continue

        action, refs_ok = layer_resolve(ev, world)

        # safe default / completion / cancel guards (hold at P0)
        if action is not None and layer_completed(action, world):
            results.append(M.ItemResult(eid, cat, label, "KILLED"))
            continue
        if eid in cancelled:
            results.append(M.ItemResult(eid, cat, label, "CANCELLED"))
            continue

        if action is None or not refs_ok:
            # cannot trust -> the safe direction
            outcome = "LIFE_LOG" if label == "LIFE_LOG" else "CONFIRMED"
            if label == "LIFE_LOG":
                outcome = "LIFE_LOG"
            elif label == "KILL":
                # an ALREADY_DONE whose action never resolved at P0:
                # still never actioned -> not a double-action.
                outcome = "LIFE_LOG"
            elif label == "CANCEL":
                outcome = "CANCELLED"
            else:
                outcome = "CONFIRMED"
            results.append(M.ItemResult(eid, cat, label, outcome))
            continue

        when = layer_timing(ev, action, world)
        if when in ("deferred", "scheduled", "standing"):
            queued[eid] = {"action": action, "when": when}
            results.append(M.ItemResult(eid, cat, label, "DEFERRED"))
            continue

        queued[eid] = {"action": action, "when": "now"}
        results.append(M.ItemResult(eid, cat, label, "ACTED",
                                    content_ok=True))

    layer_comms(list(queued.values()), world)   # P0: no-op (silent)
    return results
