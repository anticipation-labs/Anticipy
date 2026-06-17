"""Follow-up scheduling (packet 06 / done-experience: "I set a follow-up for two weeks").

A competent assistant doesn't just handle a task — when the outcome depends on someone else (a send
to a person, a support/return/refund chase, a vendor follow-up), it schedules a CHECK for later and
tells the owner. This computes, deterministically, whether a finished/parked obligation warrants a
follow-up and when — surfaced on the card as `follow_up` so the UI shows it and the trigger system can
fire it. It is conservative + safe: NEVER follows up a vent/joke (ignored, never a card), a pure
preference (remember), or the money wall (blocked) — so it cannot become spam or act on emotion.

WHEN a follow-up is warranted (tightened — no nuisance nudges):
  - the card's ACTION is one whose outcome depends on an external party (a message to a person,
    a browser task on a real site, a cart/return/refund path), OR
  - the source text carries an explicit EXTERNAL-DEPENDENCY phrase ("send X to Priya",
    "make sure it lands", "hear back", "get back to me", "chase the vendor") — NOT a bare verb
    that merely appears somewhere in the line ("I should reply-all less" must NOT get a nudge).
Excluded categories never get one: remember (a preference), blocked (the money wall),
ignore (a vent). A money card never gets a follow-up even if it slipped past blocked.

DETERMINISM / IDEMPOTENCY: `when_ts` is anchored to a STABLE base time for the obligation
(the caller passes the card's own capture/created time, not a fresh wall clock), so re-ingesting
the same line does not churn the scheduled time. The fire-site additionally preserves an
already-scheduled `when_ts` if the follow-up loop already exists.
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
# Dispositions that NEVER warrant a follow-up: a vent (ignore), a preference (remember),
# the money wall (blocked). Defense in depth alongside the explicit category check below.
_NO_FOLLOWUP_DISPOSITIONS = {"remember", "blocked", "ignore"}
# Categories that must never get a follow-up even if the disposition slipped (money wall).
_NO_FOLLOWUP_CATEGORIES = {"money"}

# Language that implies a real EXTERNAL DEPENDENCY — tightened so an ordinary mention of a
# bare verb ("I'll reply to him eventually", "remember to confirm my own RSVP") does NOT trip it.
# Either: a directed send/deliver TO a named/other party, a chase/await of someone else's
# response, or an explicit "make sure it lands / went through" outcome-check phrase.
_AWAIT = re.compile(
    r"\b(?:"
    # directed send/deliver/submit/return to an external party (verb ... to/for someone)
    r"(?:send|email|deliver|submit|ship|forward|return|refund|drop\s+off)\b[^.?!]*?\b(?:to|for)\b"
    r"|"
    # awaiting / chasing another party's response
    r"chase|follow\s*up\b|hear\s+back|get\s+back\s+to|waiting\s+(?:on|for)|"
    r"reply\s+(?:to|from)|respond\s+to|"
    r"call\s+(?:the\s+)?(?:support|vendor|client|customer|landlord|bank|office)|"
    # explicit outcome-check phrasing — the thing must actually LAND
    r"make\s+sure\s+(?:it|they|he|she|that|this)\b|"
    r"(?:make\s+sure\s+)?(?:it|they)\s+(?:landed|lands|went\s+through|got\s+(?:it|there)|arrived)|"
    r"confirm\s+(?:they|he|she|it|receipt|delivery|the\s+order)"
    r")\b", re.I)

_DAY = 24 * 3600
_DEFAULT_DELAY_DAYS = 2


def warrants_follow_up(card: dict) -> bool:
    """Deterministic gate (no time): does this card's obligation depend on someone else?
    vents/prefs/money never qualify; an external-dependency ACTION or an explicit
    external-dependency phrase does; a bare verb mention does not."""
    disp = card.get("disposition")
    if disp in _NO_FOLLOWUP_DISPOSITIONS:
        return False
    # money never gets a follow-up even if it reached here without disposition==blocked
    category = (card.get("category") or (card.get("execution") or {}).get("category") or "")
    if category in _NO_FOLLOWUP_CATEGORIES:
        return False
    action = card.get("action") or ""
    if action in _FOLLOWUP_ACTIONS:
        return True
    text = card.get("source_text") or ""
    return bool(_AWAIT.search(text))


def plan_follow_up(card: dict, now_ts: float) -> dict | None:
    """Return a {when_ts, in_days, note, reason} follow-up plan, or None if none is warranted.
    Deterministic + safe: vents/prefs/money never get a follow-up. `now_ts` should be a STABLE
    base time for this obligation (the card's capture/created time), not a fresh wall clock, so
    re-ingesting the same line does not churn `when_ts`."""
    if not warrants_follow_up(card):
        return None
    text = card.get("source_text") or ""
    return {
        "when_ts": now_ts + _DEFAULT_DELAY_DAYS * _DAY,
        "in_days": _DEFAULT_DELAY_DAYS,
        "note": f"Follow up on: {text[:90]}",
        "reason": "outcome depends on someone else — I'll check back and nudge if needed",
    }
