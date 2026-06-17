"""Follow-up scheduling (packet 06 / done-experience: "I set a follow-up for two weeks").

A competent assistant doesn't just handle a task — when the outcome depends on someone else (a send
to a person, a support/return/refund chase, a vendor follow-up), it schedules a CHECK for later and
tells the owner. This computes, deterministically, whether a finished/parked obligation warrants a
follow-up and when — surfaced on the card as `follow_up` so the UI shows it and the trigger system can
fire it. It is conservative + safe: NEVER follows up a vent/joke (ignored, never a card), a pure
preference (remember), or the money wall (blocked) — so it cannot become spam or act on emotion.
"""
from __future__ import annotations

import re

# actions whose outcome depends on an external party -> a follow-up check is warranted
_FOLLOWUP_ACTIONS = {
    "draft_or_confirm_message",        # a message to a real person -> did they get/answer it?
    "browser_action",                  # a web task on a real site -> did it complete?
    "find_or_cart_without_purchase",   # a cart/return/refund path -> check the outcome
    "prepare_purchase_path_without_payment",
}
# language that implies an external dependency even when the action is generic
_AWAIT = re.compile(
    r"\b(send|email|chase|follow up|deliver|submit|return|refund|reply|confirm|order|ship|"
    r"call (the )?(support|vendor|client|customer)|get back to|hear back)\b", re.I)

_DAY = 24 * 3600
_DEFAULT_DELAY_DAYS = 2


def plan_follow_up(card: dict, now_ts: float) -> dict | None:
    """Return a {when_ts, in_days, note, reason} follow-up plan, or None if none is warranted.
    Deterministic + safe: vents/prefs/money never get a follow-up."""
    disp = card.get("disposition")
    if disp in ("remember", "blocked", "ignore"):
        return None
    action = card.get("action") or ""
    text = (card.get("source_text") or "")
    warranted = action in _FOLLOWUP_ACTIONS or bool(_AWAIT.search(text))
    if not warranted:
        return None
    return {
        "when_ts": now_ts + _DEFAULT_DELAY_DAYS * _DAY,
        "in_days": _DEFAULT_DELAY_DAYS,
        "note": f"Follow up on: {text[:90]}",
        "reason": "outcome depends on someone else — I'll check back and nudge if needed",
    }
