"""Channel-by-urgency router for notifications + confirm prompts.

Implements the matrix from feedback_channel_by_urgency.md:

    Criticality   Time-sensitive    Channel
    CRITICAL      yes               voice_call (Twilio Programmable
                                    Voice; interrupts the user)
    CRITICAL      no                sms (single SMS, no interrupt)
    HIGH          mixed             sms_plus_email (both, for receipt
                                    + reach)
    MEDIUM        no                email (or in-app popover)
    LOW           no                silent (log only; surface on
                                    demand)

The router is pure-Python so it composes anywhere: the SMS pre-
confirm gate, the proactive notifier cascade, and any future
notification surface. The caller maps the returned Channel back to a
concrete delivery function (twilio_voice, twilio_sms, etc.).

Inputs:
  criticality      Free-form string. Accepts "critical" / "high" /
                   "medium" / "low" (case-insensitive). Also accepts
                   the risk_assessor's `level` field
                   ("high" / "medium" / "low") plus the explicit
                   "critical" tier the matrix calls out. When the
                   level is "high" with money_intent OR irreversibility
                   >= 0.9 (signature, payment, medical), the caller
                   should pass "critical" instead of "high".
  time_sensitive   Bool. When True, the deadline is within the next
                   ~1 hour. The risk_assessor's `time_sensitivity`
                   field ("time_sensitive" | "not_time_sensitive")
                   maps cleanly: time_sensitive == True iff value ==
                   "time_sensitive".

Output:
  A Channel enum value (one of VOICE_CALL, SMS, SMS_PLUS_EMAIL,
  EMAIL, SILENT). The string `.value` of each is stable and is what
  callers serialise into the persisted pending-confirm record so the
  audit trail can replay the decision.
"""

from __future__ import annotations

import enum
from typing import Any


class Channel(str, enum.Enum):
    """How to reach the user. Ordered from most-intrusive (top) to
    least-intrusive (bottom). The order matters for the SMS pre-
    confirm gate's fallback ladder: a CRITICAL+time_sensitive action
    falls back to SMS if voice fails, and silent never escalates.
    """

    VOICE_CALL = "voice_call"
    SMS = "sms"
    SMS_PLUS_EMAIL = "sms_plus_email"
    EMAIL = "email"
    SILENT = "silent"


_CRITICALITY_ALIASES = {
    "critical": "critical",
    "crit": "critical",
    "high": "high",
    "h": "high",
    "medium": "medium",
    "med": "medium",
    "mid": "medium",
    "m": "medium",
    "low": "low",
    "l": "low",
}


def _normalise_criticality(value: Any) -> str:
    raw = ""
    if isinstance(value, str):
        raw = value.strip().lower()
    elif value is not None:
        raw = str(value).strip().lower()
    return _CRITICALITY_ALIASES.get(raw, "low")


def _coerce_time_sensitive(value: Any) -> bool:
    """Accept the str-form of risk_assessor.time_sensitivity OR a
    plain bool. Anything else falls back to False (safe default: do
    not wake the user)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in {"time_sensitive", "true", "1", "yes", "y"}:
            return True
        return False
    if value in (1,):
        return True
    return False


def select_channel(criticality: Any, time_sensitive: Any) -> Channel:
    """Apply the matrix. Pure-Python, no side effects.

    Inputs are coerced defensively so a caller passing the
    risk_assessor's dict-form result (string criticality + string
    time_sensitivity) gets the same answer as a caller passing
    booleans.
    """
    crit = _normalise_criticality(criticality)
    is_time_sensitive = _coerce_time_sensitive(time_sensitive)

    if crit == "critical":
        return Channel.VOICE_CALL if is_time_sensitive else Channel.SMS
    if crit == "high":
        # The matrix lists HIGH as "mixed" time-sensitivity. We always
        # send both SMS + email for HIGH so the user gets the
        # interrupt-reach of SMS plus the durable record of email.
        return Channel.SMS_PLUS_EMAIL
    if crit == "medium":
        return Channel.EMAIL
    return Channel.SILENT


def channel_for_assessment(level: Any, time_sensitivity: Any,
                           *,
                           money_amount: Any = None,
                           irreversibility_score: Any = None) -> Channel:
    """Convenience wrapper that lifts a risk_assessor result into the
    matrix. Pass `level` (low/medium/high) and `time_sensitivity`
    (the string form from RiskAssessment.to_dict()). The optional
    money_amount and irreversibility_score promote a HIGH assessment
    to CRITICAL when:

      - any money_amount > 0 is named (irreversible payment), OR
      - irreversibility_score >= 0.9 (delete, wipe, destroy class).

    The promotion mirrors the criticality signals listed in the
    feedback matrix: money irreversible, legal signature, patient lab
    order all map to CRITICAL.
    """
    crit_input = level
    try:
        score = float(irreversibility_score) \
            if irreversibility_score is not None else 0.0
    except (TypeError, ValueError):
        score = 0.0
    try:
        amount = float(money_amount) if money_amount is not None else 0.0
    except (TypeError, ValueError):
        amount = 0.0
    if _normalise_criticality(level) == "high" and (
            amount > 0 or score >= 0.9):
        crit_input = "critical"
    return select_channel(crit_input, time_sensitivity)


__all__ = [
    "Channel",
    "channel_for_assessment",
    "select_channel",
]
