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

def frozen_is_instruction(event: dict) -> str:
    """Reuse the FROZEN reasoning engine (read-only, via its public
    decide over the existing seam shape) to decide whether this
    utterance is an actionable wearer instruction at all. This is the
    validated hedge/demand/addressee brain (0.0 over-action on hard
    negatives in the reasoning build); chatter / hypothetical /
    3rd-party -> IGNORE/STORE -> not an instruction. The frozen
    engine is NOT modified. Returns the raw decision string.
    """
    import asyncio

    from app.anticipy.proactive_engine import ProactiveEngine
    from app.anticipy.seams import UserContext, UserProfile

    spk = event.get("speaker", "WEARER")
    line = [{"speaker_id": "WEARER" if spk == "WEARER" else "S1",
             "text": event.get("text", ""), "ts": float(event.get("ts", 0))}]
    ctx = UserContext.from_profile(UserProfile(
        user_id="dil-wearer", name="Omar", role_title="Founder",
        what_they_do="runs an AI hardware startup",
        mandate="Handle scheduling, dinner and email proactively. "
                "Do not touch payroll or legal.",
        people={"the boss": "Dana", "us": "Omar and Priya"},
        trajectory_confidence=0.0, days_since_onboard=3))
    try:
        r = asyncio.run(ProactiveEngine().decide(line, ctx, "mac_mic"))
        return getattr(r, "decision", "IGNORE")
    except Exception:
        return "IGNORE"   # fail SAFE: not an instruction


def layer_resolve(event: dict, world: SimWorld):
    """DIL-P1 (Layer A). Returns (ResolvedAction|None, all_confident).
    Only consults resolution if the FROZEN engine judged this an
    actionable instruction; chatter -> (None, False) -> LIFE_LOG.
    An unresolved reference is NEVER guessed (safe direction).
    """
    from app.proactive_day import resolve as _R

    decision = frozen_is_instruction(event)
    if decision not in ("ACT", "ASK"):
        return None, False, "not_instruction"     # -> LIFE_LOG
    ra = _R.resolve(event.get("text", ""), world,
                    named_thing=event.get("slots", {}).get("thing"),
                    named_person=event.get("slots", {}).get("name"))
    return ra, ra.all_confident, ("ok" if ra.all_confident
                                  else f"unresolved:{ra.unresolved}")


def layer_timing(event: dict, action, world: SimWorld) -> str:
    """DIL-P2 (Layer B). now | deferred | scheduled | standing | hold.
    A time-conditioned action is never 'now' (never executed
    immediately) and is never dropped; an uninferable condition
    becomes 'hold' (surface one-line now-or-later), not a guess.
    """
    from app.proactive_day import timing as _T

    return _T.classify(action, event, world).when


def layer_completed(action, world: SimWorld) -> bool:
    """DIL-P3 (the world helper is live from P1). True if the world
    already satisfied this action by ANY means -> kill it, zero
    double-act. Accepts a ResolvedAction or a dict.
    """
    if action is None:
        return False
    a = action if isinstance(action, dict) else {
        "kind": getattr(action, "kind", None),
        "target": getattr(action, "target", None),
        "object": getattr(action, "object", None)}
    return world.already_satisfied(a)


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

        action, refs_ok, why = layer_resolve(ev, world)

        # completion guard (the world already did it by other means)
        if action is not None and layer_completed(action, world):
            results.append(M.ItemResult(eid, cat, label, "KILLED"))
            continue
        if eid in cancelled:
            results.append(M.ItemResult(eid, cat, label, "CANCELLED"))
            continue

        # the safe asymmetric direction, decided from CONTENT (the
        # frozen engine's instruction judgement + Layer A resolution),
        # NEVER from the mix-time label:
        #  not an instruction (chatter/hypothetical/3rd-party) -> LIFE_LOG
        #  an instruction with an unresolved load-bearing ref  -> CONFIRM
        if action is None:
            results.append(M.ItemResult(eid, cat, label, "LIFE_LOG"))
            continue
        if not refs_ok:
            results.append(M.ItemResult(eid, cat, label, "CONFIRMED"))
            continue

        when = layer_timing(ev, action, world)
        if when in ("deferred", "scheduled", "standing"):
            # queued against the inferred condition: NOT executed now,
            # NOT dropped.
            queued[eid] = {"action": vars(action), "when": when}
            results.append(M.ItemResult(eid, cat, label, "DEFERRED"))
            continue
        if when == "hold":
            # time condition present but release not inferable: surface
            # one clear now-or-later question; not executed, not dropped.
            results.append(M.ItemResult(eid, cat, label, "CONFIRMED"))
            continue

        queued[eid] = {"action": vars(action), "when": "now"}
        # content_ok: a confidently-resolved action that did not act on
        # any None reference (zero act on unresolved is structural:
        # unresolved -> CONFIRMED above, never reaches here).
        content_ok = (action.verb != "" and not (
            action.kind in ("send_email",) and action.target is None))
        results.append(M.ItemResult(eid, cat, label, "ACTED",
                                    content_ok=content_ok))

    layer_comms(list(queued.values()), world)   # P0: no-op (silent)
    return results
