"""Layer E (comms decision + rate limiter) + Layer F (surfacing
tone/volume). The focus of the product: never flood, one clear
proposal, the right channel at the right time, and a time-critical
item still makes its deadline.

Per pending item: urgency, wearer reachability, interrupt-cost,
wait-cost -> a channel (silent_queue | text | email | call |
call2). HARD rate limiter: ONE composed message per debounce
batch across ALL channels; a debounce-and-compose window holds and
MERGES related items before reaching the wearer; escalation to a
call only when urgency is high AND the wait-cost is real; a second
call only when critical and unanswered. The debounce never delays
a time-critical (seconds) item past its deadline (it short-circuits
the window). Reuses the FROZEN comms.classify_criticality for the
risk tier read-only; it does NOT redefine risk.

All delivery is the SIMULATED recording sink (world.emit). Real
Telnyx/SES/calls are wired behind this same interface but GATED and
unproven (labelled in the report).
"""

from __future__ import annotations

from typing import Optional

from app.proactive_day.world import Outbound, SimWorld

DEBOUNCE_S = 0.10            # sim-hours; merge related items in this window
SECONDS_DEADLINE_S = 0.02    # a 'seconds' item must surface within this

_URGENCY_RANK = {"never": 0, "hours": 1, "minutes": 2, "seconds": 3}


def _frozen_risk(text: str) -> str:
    """Read-only reuse of the FROZEN engine's existing risk class."""
    import asyncio

    from app.anticipy import comms as _fc

    try:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            c = asyncio.run(_fc.classify_criticality(text))
            return c.risk_tier
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(
                lambda: asyncio.run(_fc.classify_criticality(text))
            ).result(timeout=20)
    except Exception:
        return "normal"


def _channel(urgency: str, reach: str, risk: str) -> str:
    """The safe channel choice. do_not_interrupt is respected unless
    the item is genuinely critical; a call is reserved for high
    urgency with a real wait-cost; a second call only for critical.
    """
    u = _URGENCY_RANK.get(urgency, 1)
    if u == 0:
        return "silent_queue"
    if reach == "do_not_interrupt" and u < 3:
        return "silent_queue"            # never interrupt for non-critical
    if u >= 3:                            # seconds: critical
        return "call"                     # (call2 only if unanswered)
    if u == 2 and risk in ("ultra_high", "money"):
        return "call"                     # high urgency + real wait-cost
    if u == 2:
        return "text"
    return "text" if reach == "free" else "email"


def decide_and_send(pending: list, world: SimWorld) -> list:
    """pending: [{ev_id, action, urgency, reach, queued_at, ...}].
    Debounce + compose + rate-limit, then emit to the simulated
    sink. Returns the list of Outbound emitted. Invariants:
      - <= 1 Outbound per pending item per debounce window
      - one composed message per batch (merged by recipient)
      - no non-critical interrupt during do_not_interrupt
      - a 'seconds' item is emitted within SECONDS_DEADLINE_S of its
        queue time (debounce never blows its deadline)
    """
    if not pending:
        return []

    # group into debounce batches by (recipient, ~time window). A
    # 'seconds' item opens its own immediate batch (short-circuit).
    pend = sorted(pending, key=lambda p: p.get("queued_at", 0.0))
    batches: list[list] = []
    cur: list = []
    cur_key = None
    for p in pend:
        urg = p.get("urgency", "hours")
        recip = (p.get("action", {}) or {}).get("target") or "wearer"
        t = p.get("queued_at", 0.0)
        if urg == "seconds":
            batches.append([p])          # immediate, its own batch
            continue
        key = (recip, round(t / max(DEBOUNCE_S, 1e-6)))
        if cur and key == cur_key:
            cur.append(p)
        else:
            if cur:
                batches.append(cur)
            cur, cur_key = [p], key
    if cur:
        batches.append(cur)

    emitted: list[Outbound] = []
    for b in batches:
        # the batch's channel = the most-demanding member's channel
        urg = max((p.get("urgency", "hours") for p in b),
                  key=lambda u: _URGENCY_RANK.get(u, 1))
        reach = b[0].get("reach", "free")
        risk = _frozen_risk(" ".join(
            str((p.get("action", {}) or {}).get("object", "")) for p in b))
        ch = _channel(urg, reach, risk)
        if ch == "silent_queue":
            # queued silently: NO outbound at all (this is the
            # no-flood, no-interrupt safe path).
            continue
        ids = [p["ev_id"] for p in b]
        recip = (b[0].get("action", {}) or {}).get("target") or "wearer"
        # ONE composed proposal for the whole batch (Layer F: one
        # clear proposal, never a stream).
        body = ("Found "
                + (f"{len(ids)} things to handle" if len(ids) > 1
                   else "1 thing to handle")
                + f" for {recip}. Want me to proceed?")
        # a 'seconds' item must land within its deadline: emit at the
        # earliest of (now, queued_at + SECONDS_DEADLINE_S).
        qt = min(p.get("queued_at", 0.0) for p in b)
        send_ts = (qt + (SECONDS_DEADLINE_S if urg == "seconds"
                         else DEBOUNCE_S))
        ob = Outbound(ts=send_ts, channel=ch, to=str(recip),
                      body=body, pending_ids=ids)
        world.emit(ob)
        emitted.append(ob)
    return emitted
