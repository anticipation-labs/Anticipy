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
    _VENT_TASK_ACTIONABLE, _is_draft_or_cart_prep, _is_reminder_or_hold,
    _is_explicit_reversible_task,
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
    "i need to send 2k usd to my mom in mexico, cheapest way?",   # k/m shorthand (generalization sweep)
    "wire 5k usd to the contractor",
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

# ---- reminder / calendar-hold backstop (re-run gauntlet: ~40 of these dropped) ----
for t in ["Remind me to call the dentist tomorrow at 3",
          "Block my calendar Friday 9am for the neurologist",
          "Block 2pm for the buyer walkthrough at 88 Oak, do not let me forget",
          "The Halloran motion goes in by 5pm, do not let me forget",
          "page Dr. Lin and put it on my list to follow up at shift change",
          "set a reminder to finish the discharge summary tonight",
          "hold time Saturday 2pm for the open house"]:
    check(_is_reminder_or_hold(t), f"reminder/hold NOT recognized (drop risk): {t!r}")
for t in ["I blocked out the whole afternoon to think", "send Maya the deck", "the kids are exhausting"]:
    check(not _is_reminder_or_hold(t), f"non-reminder wrongly flagged: {t!r}")

# ---- broadened explicit-reversible backstop (re-run #2: multi-line vent-context drops) ----
# Real reversible tasks must surface; vents must NOT trip (would breach the vent floor since the
# top-of-loop backstop skips the model for these shapes).
REVERSIBLE_YES = [
    "Don't let me lose track of the Riverside science fair Saturday",
    "Block me an hour tomorrow afternoon to sync with Marcus",
    "Set a hold on my calendar for the staff meeting Tuesday at 3pm",
    "Pull up Dad's medication list before my shift",
    "make sure it's actually on my calendar",
    "nail that down for me",
    "draft a quick text to Priya asking if she can cover my shift",
]
REVERSIBLE_NO = [   # vents / rhetoricals — must stay silent
    "ugh remind me why I even do this job",
    "honestly I'm so done I could scream",
    "the kids are trying to end me",
    "if I win the lottery I'm buying an island",
    "I should just quit and move to the woods",
    "I could really use a vacation, my life is a mess",
]
for t in REVERSIBLE_YES:
    check(_is_explicit_reversible_task(t), f"reversible task NOT recognized (drop risk): {t!r}")
for t in REVERSIBLE_NO:
    check(not _is_explicit_reversible_task(t), f"vent/rhetorical wrongly flagged (vent-floor breach risk): {t!r}")

# ---- cart-without-checkout shapes (re-run #3: many dropped) ----
for t in ["Start a cart at Costco for the office snacks but don't check out",
          "get the cart ready but do NOT check out",
          "Set up a cart for the data-room software, do not check out",
          "reorder the Zyrtec into the cart but do NOT check out",
          "add the soccer cleats to my cart"]:
    check(_is_draft_or_cart_prep(t), f"cart-prep NOT recognized (drop risk): {t!r}")

# ---- absolute money hard-stop trigger: harm must categorize these as money (-> blocked at spine) ----
from anticipy_engine.proactive.harm import HarmLine  # noqa: E402
_h = HarmLine()
for t in ["Better wire the deposit to my daughter-in-law, it's four hundred dollars.",
          "Pay the firm's quarterly estimated taxes today, it's $14,200 to EFTPS, do not let me forget."]:
    check(_h.assess(t, {}).category == "money", f"money action NOT categorized money (block-bypass risk): {t!r}")

if fails:
    for f in fails:
        print("FAIL:", f)
    raise SystemExit(1)
print("PASS twentylife_floor_fixes: money floor + vent-chore + draft/cart-prep detectors locked")
