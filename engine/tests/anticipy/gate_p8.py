"""P8 gate: real two way communication, the three inbound paths, C1
criticality, C2 resumable durable task state and reply matcher, C3 the
3 hour rule with both carve outs and the caution asymmetry.

These are logic and structural property tests. The fixed taxonomy
provides surface variety; the property under test is the comms layer
behaviour, so each case deterministically instantiates a concrete
scenario (seeded by its case_id) and exercises the REAL comms.py code,
then the grader checks the strict structural pass conditions.

Pass (build spec P8):
  - THREE_INBOUND_ROUTING: 100 percent correct path tag, zero
    misrouted replies
  - ASYNC_REPLY_MATCH: correct task resume >= 0.90, and the two open
    tasks one vague reply case sends EXACTLY one disambiguation, never
    a bombardment
  - THREE_HOUR_RULE: 100 percent correct on the carve outs (a single
    wrong money or ultra high proceed is a hard build failure),
    criticality never up classifies to a call when uncertain
"""

from __future__ import annotations

import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

CATEGORIES = ["THREE_INBOUND_ROUTING", "ASYNC_REPLY_MATCH", "THREE_HOUR_RULE"]


def _seed(cid: str) -> int:
    return int(cid[:8], 16) if cid else 0


def _decide(case: dict) -> dict:
    import asyncio

    from app.anticipy import comms
    from app.anticipy.comms import (
        Criticality, SuspendedTask, apply_three_hour_rule, classify_criticality,
        open_question, route_inbound, route_reply,
    )
    from app.anticipy.seams import InboundMessage

    cat = case.get("category")
    cid = case.get("case_id", "x")
    s = _seed(cid)
    uid = f"p8-{cat[:5]}-{cid}"

    if cat == "THREE_INBOUND_ROUTING":
        kind = s % 3
        if kind == 0:
            m = InboundMessage(source="ambient", text="the weather is nice today", user_id=uid)
            d = route_inbound(m, [])
            return {"route_correct": d.path == "ambient" and d.handled_by == "proactive_engine"}
        if kind == 1:
            m = InboundMessage(source="direct", text="book the dinner", user_id=uid)
            d = route_inbound(m, [])
            return {"route_correct": d.path == "direct" and d.handled_by == "proactive_engine"}
        # reply: must route to the right suspended workflow, never to
        # the proactive engine as a new ambient intent
        crit = Criticality("text", comms.RISK_NORMAL, "seed")
        t = open_question(uid, {"a": 1}, "What party size for the booking?", crit, now_s=1000.0)
        m = InboundMessage(source="reply", text="party of four please", user_id=uid,
                           in_reply_to=t.task_id, ts=1100.0)
        d = route_inbound(m, [t], now_s=1100.0)
        ok = (d.path == "reply" and d.handled_by == "reply_matcher"
              and d.reply_routing is not None
              and d.reply_routing.action == "resumed"
              and d.reply_routing.matched_task_id == t.task_id)
        return {"route_correct": ok, "reply_match_correct": ok}

    if cat == "ASYNC_REPLY_MATCH":
        crit = Criticality("text", comms.RISK_NORMAL, "seed")
        t1 = open_question(uid, {"k": "dinner"}, "Which restaurant should I book for dinner Friday?", crit, now_s=1000.0)
        t2 = open_question(uid, {"k": "flight"}, "Window or aisle seat for the flight to Boston?", crit, now_s=1000.0)
        if s % 2 == 0:
            # clear: reply unmistakably matches t2 (the flight seat)
            m = InboundMessage(source="reply", text="aisle seat for the Boston flight", user_id=uid, ts=4000.0)
            r = route_reply(m, [t1, t2], now_s=4000.0)
            return {"reply_match_correct": r.action == "resumed" and r.matched_task_id == t2.task_id}
        # the hard case: a genuinely vague reply across two open tasks
        # must send EXACTLY one disambiguation, never bombard, never
        # misresume
        m = InboundMessage(source="reply", text="yeah sure that's fine", user_id=uid, ts=4000.0)
        r = route_reply(m, [t1, t2], now_s=4000.0)
        return {"reply_match_correct": r.action == "disambiguated" and r.disambiguation_sent == 1
                and r.matched_task_id is None}

    # THREE_HOUR_RULE
    kind = s % 5
    base = 100000.0
    if kind == 0:  # within window: must wait, not proceed
        t = SuspendedTask(f"t{cid}", uid, "ship the normal update?", "text", comms.RISK_NORMAL, base)
        o = apply_three_hour_rule(t, base + 2 * 3600)
        return {"carveout_correct": (not o.proceeded) and o.waited, "why": "within-window-wait"}
    if kind == 1:  # normal/high past 3h: proceed and go the extra mile
        t = SuspendedTask(f"t{cid}", uid, "send the routine status email?", "text", comms.RISK_HIGH, base)
        o = apply_three_hour_rule(t, base + 4 * 3600)
        return {"carveout_correct": o.proceeded, "why": "high-proceeds"}
    if kind == 2:  # money: NEVER proceed on silence
        t = SuspendedTask(f"t{cid}", uid, "pay the $4,000 vendor invoice?", "text", comms.RISK_MONEY, base)
        o = apply_three_hour_rule(t, base + 9 * 3600)
        return {"carveout_correct": (not o.proceeded) and o.waited, "why": "money-waits"}
    if kind == 3:  # ultra high comms: NEVER proceed on silence
        t = SuspendedTask(f"t{cid}", uid, "send the resignation email to my boss?", "text", comms.RISK_ULTRA, base)
        o = apply_three_hour_rule(t, base + 9 * 3600)
        return {"carveout_correct": (not o.proceeded) and o.waited, "why": "ultra-waits"}
    # Two properties together. (a) the caution asymmetry: a genuinely
    # ambiguous interpersonal comm must be classified ultra_high so the
    # 3 hour rule waits, never proceeds. (b) the precision skew: C1 must
    # NOT up classify a trivial low stakes thing to a phone call when
    # uncertain (a wrong call is more trust destroying than a delayed
    # text). A call is only acceptable for a genuinely ultra_high
    # critical item, never for a trivial one.
    crit = asyncio.run(classify_criticality(
        "Reply to the investor's email confirming we will commit to the revised terms."
    ))
    ambiguous_ok = crit.risk_tier == comms.RISK_ULTRA and (crit.channel != "call" or crit.risk_tier == comms.RISK_ULTRA)
    trivial = asyncio.run(classify_criticality(
        "Remind me to water the office plants sometime this week."
    ))
    no_trivial_call = trivial.channel != "call"
    t = SuspendedTask(f"t{cid}", uid, "reply committing to the investor's revised terms?",
                      crit.channel, crit.risk_tier, base)
    o = apply_three_hour_rule(t, base + 9 * 3600)
    return {"carveout_correct": ambiguous_ok and (not o.proceeded) and no_trivial_call,
            "why": f"ambiguous->{crit.risk_tier} trivial_ch={trivial.channel}"}


def main() -> int:
    from app.anticipy import harness

    sb = harness.run_suite(CATEGORIES, _decide, "p8-comms", run_adversarial=False)
    print(harness.format_scoreboard(sb))
    b = sb["categories"]
    ri = b.get("THREE_INBOUND_ROUTING", {})
    am = b.get("ASYNC_REPLY_MATCH", {})
    th = b.get("THREE_HOUR_RULE", {})
    ri_ok = ri.get("pass", False)            # routing_100
    am_ok = am.get("exact_correct", 0.0) >= 0.90
    th_ok = th.get("pass", False)            # carveouts_100 (strict)
    print(f"  THREE_INBOUND_ROUTING 100% correct: {ri_ok} (exact={ri.get('exact_correct')})")
    print(f"  ASYNC_REPLY_MATCH >=0.90 (incl. one-disambiguation): {am_ok} (exact={am.get('exact_correct')})")
    print(f"  THREE_HOUR_RULE carve-outs 100%: {th_ok} (exact={th.get('exact_correct')})")
    ok = ri_ok and am_ok and th_ok
    print(f"P8_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
