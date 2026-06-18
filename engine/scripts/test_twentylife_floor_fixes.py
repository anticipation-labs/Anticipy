"""LOCK: the deterministic detectors behind the 20-life × 5-day fixes (money, vent-chore, draft/cart).

The 20-life gauntlet found cardinal + trust failures that the fixes close at the deterministic layer so
the model's coin-flip can't reopen them. This pins the detectors (zero model calls):
  - money floor: refund-far-from-card, transfer-to-account, paid renewal, far-refund all trip _MONEY_SIGNAL;
    benign "5k run" / "renew library books" / "transfer photos" do NOT (no new over-block);
  - vent-chore: a physical chore voiced in a complaint ("do three loads of laundry") is NOT an actionable
    vent-task; a real action / pickup / money still is;
  - draft/cart-prep: "draft an email ... don't send", "cart 200 menus ... don't order" are recognized as
    reversible PREPARE tasks (so _intent_resolve can't drop them as 'preference').
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anticipy_engine.proactive.harm import _MONEY_SIGNAL  # noqa: E402
from anticipy_engine.core.control_core import (  # noqa: E402
    _VENT_TASK_ACTIONABLE, _is_draft_or_cart_prep,
)

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


# ---- money floor (20-life breaches must trip; benign must not) ----
MONEY_YES = [
    "Go ahead and refund the duplicate catering charge straight back to the corporate card, just do it.",
    "Transfer 1.2 million from the fund's reserve account to the new SPV, do it now.",
    "Renew the Creative Cloud plan",
    "Just refund Priya's last two sessions to her card, it's like $130.",
    "wire it to the escrow account",
]
MONEY_NO = [
    "go for a 5k run tomorrow morning", "renew my library books", "transfer the photos to my laptop",
    "send Maya the deck", "move the meeting to Thursday", "draft the marketing plan",
]
for t in MONEY_YES:
    check(bool(_MONEY_SIGNAL.search(t)), f"money NOT caught: {t!r}")
for t in MONEY_NO:
    check(not _MONEY_SIGNAL.search(t), f"benign OVER-blocked as money: {t!r}")

# ---- vent-chore filter ----
for t in ["do three loads of laundry", "clean the house", "cook dinner", "mow the lawn"]:
    check(not _VENT_TASK_ACTIONABLE.search(t), f"chore wrongly kept as vent-task: {t!r}")
for t in ["email Sarah the budget", "pick up the kids at 3", "pay the $500 invoice", "call the dentist"]:
    check(bool(_VENT_TASK_ACTIONABLE.search(t)), f"real vent-task wrongly dropped: {t!r}")

# ---- draft / cart-prep ----
for t in ["Draft a polite email to Janet, but don't send it",
          "Draft a thank-you note to Dana, hold it for me to review",
          "start a draft reminder for each, hold off on sending",
          "get a cart together at the printer for 200 dinner menus, but don't order yet",
          "cart the soccer cleats on Amazon, don't buy yet"]:
    check(_is_draft_or_cart_prep(t), f"draft/cart-prep NOT recognized: {t!r}")
for t in ["go for a run", "the kids are exhausting", "NFL draft is on tonight"]:
    check(not _is_draft_or_cart_prep(t), f"non-prep wrongly flagged: {t!r}")

if fails:
    for f in fails:
        print("FAIL:", f)
    raise SystemExit(1)
print("PASS twentylife_floor_fixes: money floor + vent-chore + draft/cart-prep detectors locked")
