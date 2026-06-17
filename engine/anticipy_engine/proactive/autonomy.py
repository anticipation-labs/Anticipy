"""Autonomy-mode classifier (packet 02_PRD_AUTONOMY_MODEL).

Every detected obligation is assigned exactly ONE autonomy mode. The default is autonomy: a competent
assistant does low-risk reversible work end-to-end; it only stops at a TRUE irreversible boundary, asks
only when genuinely ambiguous, and never acts on a vent. This maps the engine's existing safe decision
(disposition/route/action) onto the six modes + a one-line reason, so the product + the certification
harness can read the chosen mode and its rejected alternatives.

Modes: AUTO_DO · AUTO_DO_WITH_OPT_OUT · PREPARE_THEN_STOP · CLARIFY_FIRST · REMEMBER_ONLY · IGNORE.
"""
from __future__ import annotations

MODES = ("AUTO_DO", "AUTO_DO_WITH_OPT_OUT", "PREPARE_THEN_STOP",
         "CLARIFY_FIRST", "REMEMBER_ONLY", "IGNORE")

# routes/actions a competent assistant just DOES (reversible, no money, no external send)
_AUTO_ACTIONS = {
    "create_calendar_or_reminder", "timed_reminder", "write_memory", "write_profile_memory",
    "execute_owner_task", "find_or_cart_without_purchase", "browse_task", "research_or_find_item",
    "ask_clarifying_question", "prepare_internal_note",
}


def classify_autonomy(card: dict) -> dict:
    """Return {mode, why, rejected:[...]} for a finished owner card dict."""
    disp = card.get("disposition")
    action = card.get("action")
    execd = (card.get("execution") or {}).get("decision")

    if disp == "remember":
        mode, why = "REMEMBER_ONLY", "preference/fact — recorded, no action"
    elif disp == "blocked":
        mode, why = "PREPARE_THEN_STOP", "money/checkout is the true irreversible boundary — prepared, stopped"
    elif action == "draft_or_confirm_message":
        mode, why = "PREPARE_THEN_STOP", "external send to a real person — prepared, stop at final send"
    elif action == "browser_action":
        mode, why = "AUTO_DO_WITH_OPT_OUT", "visible web task — I'm on it; reversible (throwaway browser, no buy)"
    elif disp == "do" or execd == "act":
        mode, why = "AUTO_DO", "low-risk reversible work — completed end-to-end with proof"
    elif disp == "ask" and action == "ask_clarifying_question":
        mode, why = "CLARIFY_FIRST", "ambiguous referent/recipient — smallest clarifying question"
    elif disp == "ask":
        mode, why = "CLARIFY_FIRST", "needs one confirmation before acting"
    else:
        mode, why = "IGNORE", "no real obligation"
    return {"mode": mode, "why": why, "rejected": [m for m in MODES if m != mode]}
