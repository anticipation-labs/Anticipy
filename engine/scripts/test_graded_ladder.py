"""L4 + L2 isolated units — no network, no Chrome, no model.

Covers exactly the two seams the plan pins:
  • L4 GRADED cost ladder (webvoyager._ladder_tier): a lone forbid / one no-progress step stays on
    the cheap ACT tier; a genuine stall (sub_stuck>=2) escalates to the mid-tier SMART; a deep stall
    (sub_stuck>=3) spends one capped-frontier ESCALATE. This replaces the old binary
    `escalate=(sub_stuck>=2) or (forbid is not None)` that forced EVERY post-forbid step onto SMART.
  • L2 give-up broadening (webvoyager._NO_ANSWER_RE / _looks_like_no_answer): "no product(s)/results
    found" and "has no ... information" now read as a NON-answer (routed to a scroll/re-search retry),
    while substantive answers are NOT misflagged.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_graded_ladder.py
"""
import os

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")

from anticipy_engine.agent.webvoyager import (
    _ladder_tier,
    _looks_like_no_answer,
)
from anticipy_engine.core.gateway import ACT, ESCALATE, SMART

fails = []


def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f" :: {detail}"))
    if not cond:
        fails.append(name)


def test_graded_ladder():
    # cheap ACT for no-stall / single no-progress (a LONE forbid no longer escalates — the whole point)
    check("sub_stuck=0 -> ACT (cheap default)", _ladder_tier(0) == ACT, _ladder_tier(0))
    check("sub_stuck=1 -> ACT (lone forbid stays cheap)", _ladder_tier(1) == ACT, _ladder_tier(1))
    # genuine stall -> mid-tier SMART
    check("sub_stuck=2 -> SMART (first rescue)", _ladder_tier(2) == SMART, _ladder_tier(2))
    # deep stall -> one capped-frontier ESCALATE (reachable only because the abandon wall is >=4)
    check("sub_stuck=3 -> ESCALATE (deep-stall frontier)", _ladder_tier(3) == ESCALATE, _ladder_tier(3))
    check("sub_stuck=4 -> ESCALATE (still frontier at abandon boundary)",
          _ladder_tier(4) == ESCALATE, _ladder_tier(4))
    # monotonic: never a CHEAPER tier as the stall deepens
    order = {ACT: 0, SMART: 1, ESCALATE: 2}
    seq = [order[_ladder_tier(n)] for n in range(6)]
    check("ladder is monotonic non-decreasing in stuck-depth", seq == sorted(seq), seq)


def test_no_answer_broadening():
    # NEW give-up phrases the old regex missed (the demowebshop class) -> now caught
    caught = [
        "The page has no product information.",
        "No products found.",
        "no products were found on this page",
        "There are no results found for that search.",
        "no matching results",
        "the site has no items matching",
        "No records found.",
    ]
    for s in caught:
        check(f"give-up caught: {s!r}", _looks_like_no_answer(s), s)
    # pre-existing cues still caught (no regression)
    for s in ("Not found on the page.", "I cannot determine the answer.", "N/A"):
        check(f"legacy give-up still caught: {s!r}", _looks_like_no_answer(s), s)
    # substantive answers must NOT be misflagged as give-ups
    real = [
        "The cheapest laptop is the Acme 14 at $499.",
        "Option 2",
        "There are 3 products: a mug, a hoodie, and a sticker.",
        "The first result is 'Introduction to Algorithms'.",
        "Added to cart and confirmed: blue backpack",
    ]
    for s in real:
        check(f"real answer NOT flagged: {s!r}", not _looks_like_no_answer(s), s)
    # a genuinely empty answer is (still) a non-answer
    check("empty string is a non-answer", _looks_like_no_answer(""), "empty")


def main():
    test_graded_ladder()
    test_no_answer_broadening()
    if fails:
        print(f"\nFAILED: {fails}")
        raise SystemExit(1)
    print("\nALL PASS: graded cost ladder (L4) + give-up broadening (L2)")


if __name__ == "__main__":
    main()
