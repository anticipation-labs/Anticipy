"""Risk assessor: silent / notify / confirm / ask. Never declines.

Companion to the confirm-card surface. `assess(intent, binding,
memory_context)` returns a RiskAssessment whose `proceed_mode` is one
of: silent | notify | confirm | ask. There is no `decline` mode.
Pure-Python, no network. Safe from the binder, dispatcher, proactive
engine, and the HTTP surface at `/api/risk/assess`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional


MONEY_VERBS = {
    "pay", "paid", "payment", "purchase", "buy", "bought", "checkout",
    "subscribe", "subscription", "charge", "charged", "transfer", "wire",
    "donate", "tip", "order", "preorder", "renew", "renewal", "refund",
    "invoice", "billing", "deposit", "withdraw",
}

IRREVERSIBLE_VERBS = {
    "send", "publish", "post", "tweet", "delete", "remove", "destroy",
    "wipe", "drop", "cancel", "unsubscribe", "share", "submit", "book",
    "reserve", "schedule",
}

THIRD_PARTY_VERBS = {
    "email", "text", "message", "dm", "call", "ping", "post", "share",
    "send", "tweet", "publish", "reply", "forward",
}

ROUTINE_VERBS = {
    "note", "remind", "reminder", "draft", "create", "add", "open",
    "search", "find", "show", "read", "review", "save", "snooze",
}

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
    "thousand": 1000, "million": 1_000_000,
}


# Phrases that indicate a deadline within roughly the next hour. Match
# the bullet list in feedback_channel_by_urgency.md plus a couple of
# spoken variants the pendant ASR is likely to surface.
_TIME_SENSITIVE_PATTERNS = (
    r"\bby\s+eod\b",
    r"\bend\s+of\s+(?:the\s+)?day\b",
    r"\bin\s+(?:the\s+)?next\s+hour\b",
    r"\bwithin\s+(?:the\s+)?(?:next\s+)?hour\b",
    r"\bwithin\s+\d+\s+(?:min(?:ute)?s?|hours?)\b",
    r"\bin\s+\d+\s+(?:min(?:ute)?s?|hours?)\b",
    r"\bbefore\s+(?:the\s+)?call\b",
    r"\bbefore\s+(?:the\s+)?meeting\b",
    r"\bbefore\s+noon\b",
    r"\bbefore\s+lunch\b",
    r"\bby\s+noon\b",
    r"\bby\s+lunch\b",
    r"\bbefore\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)\b",
    r"\bby\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)\b",
    r"\bat\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)\b",
    r"\btomorrow\s+morning\b",
    r"\bthis\s+morning\b",
    r"\bthis\s+afternoon\b",
    r"\btonight\b",
    r"\basap\b",
    r"\bright\s+now\b",
    r"\burgent(?:ly)?\b",
    r"\bimmediately\b",
    r"\bnow\b(?=\s|$)",
)

# Phrases that EXPLICITLY rule out the time-sensitive class (longer
# horizons). When one of these matches we keep the default
# not_time_sensitive verdict even when an ambiguous date-like phrase
# also appears.
_NOT_TIME_SENSITIVE_PATTERNS = (
    r"\bthis\s+week\b",
    r"\bnext\s+week\b",
    r"\bby\s+friday\b",
    r"\bby\s+monday\b",
    r"\bby\s+tuesday\b",
    r"\bby\s+wednesday\b",
    r"\bby\s+thursday\b",
    r"\bby\s+saturday\b",
    r"\bby\s+sunday\b",
    r"\bwhenever\b",
    r"\bno\s+rush\b",
    r"\beventually\b",
)


@dataclass
class RiskAssessment:
    """Outcome of `assess()`. Never carries a `decline` mode.

    `time_sensitivity` is a coarse classifier sitting alongside
    `level`. The channel router (engine/app/product/channel_router.py)
    multiplexes (level, time_sensitivity) into voice / SMS / email /
    silent per the channel-by-urgency matrix
    (feedback_channel_by_urgency.md). Default is
    "not_time_sensitive" so a missing-signal utterance never escalates
    to a phone call.
    """

    level: str  # "low" | "medium" | "high"
    proceed_mode: str  # "silent" | "notify" | "confirm" | "ask"
    confirm_card_required: bool = False
    reasons: list[str] = field(default_factory=list)
    money_amount: Optional[float] = None
    irreversibility_score: float = 0.0
    # B031: callers thought 0.7 was a sentinel masking a no-op classifier.
    # `irreversibility_source` makes the origin explicit:
    #   "verb_match" - the score came from a matched IRREVERSIBLE_VERBS token
    #   "money_floor" - the score was bumped to 0.7 because money was detected
    #   "dnt_floor" - the score was floored to 0.9 by a do_not_touch match
    #   "third_party_floor" - the score was floored to 0.4 by a 3rd-party recipient
    #   "no_match" - no signal triggered; score is the genuine 0.0
    irreversibility_source: str = "no_match"
    third_party_impact: bool = False
    surface_target: str = ""
    time_sensitivity: str = "not_time_sensitive"  # "time_sensitive" |
    # "not_time_sensitive"

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "proceed_mode": self.proceed_mode,
            "confirm_card_required": bool(self.confirm_card_required),
            "reasons": list(self.reasons),
            "money_amount": (None if self.money_amount is None
                             else float(self.money_amount)),
            "irreversibility_score": float(self.irreversibility_score),
            "irreversibility_source": str(self.irreversibility_source),
            "third_party_impact": bool(self.third_party_impact),
            "surface_target": str(self.surface_target or ""),
            "time_sensitivity": str(self.time_sensitivity
                                    or "not_time_sensitive"),
        }


def _flatten(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        return " ".join(_flatten(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten(v) for v in value)
    return str(value)


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in re.findall(r"[a-zA-Z]+", text or "")}


def _has_external_recipient(text: str, binding: dict[str, Any]) -> bool:
    if re.search(r"@[a-zA-Z0-9.\-_]+\.[a-zA-Z]{2,}", text or ""):
        return True
    for key in ("recipient", "recipients", "to", "contact", "person"):
        v = binding.get(key) if isinstance(binding, dict) else None
        if isinstance(v, str) and v.strip():
            return True
        if isinstance(v, (list, tuple)) and any(str(x).strip() for x in v):
            return True
    return False


def _words_to_number(phrase: str) -> Optional[int]:
    parts = [p for p in re.split(r"[\s-]+", phrase.strip()) if p]
    total, current, matched = 0, 0, False
    for word in parts:
        if word not in _NUMBER_WORDS:
            continue
        matched = True
        value = _NUMBER_WORDS[word]
        if value >= 1000:
            current = max(current, 1) * value
            total += current
            current = 0
        elif value == 100:
            current = max(current, 1) * 100
        else:
            current += value
    return (total + current) if matched else None


_NUMERIC_QUALIFIERS = {
    "k": 1_000,
    "thousand": 1_000,
    "m": 1_000_000,
    "mm": 1_000_000,
    "million": 1_000_000,
    "b": 1_000_000_000,
    "bn": 1_000_000_000,
    "billion": 1_000_000_000,
}


def _apply_qualifier(blob: str, amount: float, match_end: int) -> float:
    """B014: if the number is immediately followed by 'million', 'thousand',
    'k', 'M', etc., scale by that factor. Without this, '$1 million' parses
    as $1 and risk decisions miss the magnitude entirely.
    """
    tail = blob[match_end:match_end + 40]
    m = re.match(r"\s*([a-z]+)", tail)
    if not m:
        return amount
    word = m.group(1).lower()
    factor = _NUMERIC_QUALIFIERS.get(word)
    if factor:
        return amount * factor
    return amount


def parse_money_amount(text: str) -> Optional[float]:
    """Handles $50, $1,200.50, 50 dollars, fifty dollars, one thousand dollars,
    plus B014 qualifiers ($1 million, $5k, $2.5M, $1 billion)."""
    if not text:
        return None
    blob = text.lower()
    m = re.search(r"\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)", blob)
    if m:
        try:
            amount = float(m.group(1).replace(",", ""))
            return _apply_qualifier(blob, amount, m.end())
        except ValueError:
            pass
    m = re.search(
        r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*(dollars?|usd|bucks)\b", blob,
    )
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            pass
    word_block = re.search(
        r"((?:(?:[a-z]+[\s-]+){0,5}[a-z]+))\s*(?:dollars?|usd|bucks)\b",
        blob,
    )
    if word_block:
        amount = _words_to_number(word_block.group(1))
        if amount is not None:
            return float(amount)
    return None


def _irreversibility(tokens: set[str]) -> float:
    if "draft" in tokens and not (tokens & {
        "send", "publish", "post", "delete", "cancel", "transfer",
    }):
        return 0.0
    score = 0.5 if (tokens & IRREVERSIBLE_VERBS) else 0.0
    if tokens & {"delete", "wipe", "destroy"}:
        score = 1.0
    elif "send" in tokens:
        score = max(score, 0.7)
    elif tokens & {"publish", "post"}:
        score = max(score, 0.8)
    elif "cancel" in tokens and (tokens & {"subscription", "membership"}):
        score = max(score, 0.8)
    return score


def detect_time_sensitivity(text: str) -> str:
    """Return "time_sensitive" or "not_time_sensitive".

    A surface deadline phrase like "by EOD", "before the call at 3pm",
    "in the next hour" snaps the verdict to time_sensitive. A longer-
    horizon phrase like "this week" or "by Friday" pulls it back to
    not_time_sensitive even when an ambiguous "Friday" token is also
    present. Default is not_time_sensitive: when in doubt, the channel
    router will pick SMS over a phone call so the user is not woken up
    for a routine task.
    """
    if not text:
        return "not_time_sensitive"
    blob = text.lower()
    for pattern in _NOT_TIME_SENSITIVE_PATTERNS:
        if re.search(pattern, blob):
            return "not_time_sensitive"
    for pattern in _TIME_SENSITIVE_PATTERNS:
        if re.search(pattern, blob):
            return "time_sensitive"
    return "not_time_sensitive"


def _list_field(binding: dict[str, Any], key: str) -> list[str]:
    raw = binding.get(key) if isinstance(binding, dict) else None
    if not raw:
        return []
    if isinstance(raw, str):
        return [raw] if raw.strip() else []
    if isinstance(raw, (list, tuple, set)):
        return [str(x) for x in raw if str(x).strip()]
    return []


def assess(intent: Any, binding: Any = None,
           memory_context: Any = None) -> RiskAssessment:
    """Score risk and pick a proceed_mode. Never returns `decline`."""
    binding = binding if isinstance(binding, dict) else {}
    memory_context = memory_context if isinstance(memory_context, dict) else {}
    combined = f"{_flatten(intent)}\n{_flatten(binding)}".strip()
    tokens = _tokens(combined)
    surface_target = str(binding.get("surface_target") or "")
    money_amount = parse_money_amount(combined)
    money_hit = bool(money_amount and money_amount > 0) or bool(
        tokens & MONEY_VERBS)
    irr = _irreversibility(tokens)
    third_party = bool(tokens & THIRD_PARTY_VERBS) and \
        _has_external_recipient(combined, binding)
    dnt_hits = _list_field(binding, "do_not_touch_warnings")
    missing = _list_field(binding, "missing_slots")
    time_sensitivity = detect_time_sensitivity(combined)

    def build(level, mode, *, confirm, reasons,
              irr_floor=None, tp=None,
              irr_source: str | None = None) -> RiskAssessment:
        final_score = (
            max(irr, irr_floor) if irr_floor is not None else irr)
        if irr_source:
            src = irr_source
        elif irr_floor is not None and irr_floor > irr:
            src = "money_floor" if irr_floor == 0.7 else f"floor_{irr_floor}"
        elif irr > 0:
            src = "verb_match"
        else:
            src = "no_match"
        return RiskAssessment(
            level=level, proceed_mode=mode,
            confirm_card_required=confirm, reasons=list(reasons),
            money_amount=money_amount,
            irreversibility_score=final_score,
            irreversibility_source=src,
            third_party_impact=(third_party if tp is None else tp),
            surface_target=surface_target,
            time_sensitivity=time_sensitivity,
        )

    if dnt_hits:
        return build("high", "ask", confirm=True, irr_floor=0.9,
                     irr_source="dnt_floor",
                     reasons=[
                         f"do_not_touch matched: {', '.join(dnt_hits)[:200]}"])
    if money_hit:
        reason = (f"money intent detected (amount={money_amount})"
                  if money_amount else "money intent detected (verb match)")
        return build("high", "confirm", confirm=True, irr_floor=0.7,
                     irr_source="money_floor",
                     reasons=[reason])
    if missing:
        return build("medium", "ask", confirm=False,
                     reasons=[f"missing_slots: {', '.join(missing)[:200]}"])
    if irr >= 0.7:
        return build("high" if irr >= 0.9 else "medium",
                     "confirm", confirm=True,
                     reasons=[f"irreversible action (score={irr:.2f})"])
    if third_party:
        sensitive = bool(memory_context.get("relationship_sensitive")
                         or memory_context.get("sensitive"))
        msg = "third-party recipient detected"
        if sensitive:
            msg += " (relationship marked sensitive)"
        return build("medium", "confirm" if sensitive else "notify",
                     confirm=sensitive, irr_floor=0.4,
                     irr_source="third_party_floor", reasons=[msg])
    if irr >= 0.3:
        return build("medium", "confirm", confirm=True,
                     reasons=["medium-risk irreversible verb detected"])
    routine = ("routine personal action"
               if (tokens & ROUTINE_VERBS or not tokens)
               else "no risk markers found; default low/silent")
    return build("low", "silent", confirm=False, reasons=[routine])


def explain(assessment: RiskAssessment) -> str:
    """Human-readable description for the confirm card or status log."""
    if not isinstance(assessment, RiskAssessment):
        return "no assessment available."
    parts = [
        f"Risk {assessment.level}, proceed via {assessment.proceed_mode}."
    ]
    if assessment.money_amount:
        parts.append(f"Money amount: ${assessment.money_amount:,.2f}.")
    if assessment.third_party_impact:
        parts.append("Affects someone other than you.")
    if assessment.irreversibility_score >= 0.7:
        parts.append("This action is hard to undo.")
    elif assessment.irreversibility_score >= 0.3:
        parts.append("This action is partly reversible.")
    if assessment.confirm_card_required:
        parts.append("A confirm card will appear before any action runs.")
    if assessment.reasons:
        parts.append("Reasons: " + "; ".join(assessment.reasons) + ".")
    return " ".join(parts)


__all__ = [
    "RiskAssessment",
    "assess",
    "detect_time_sensitivity",
    "explain",
    "parse_money_amount",
]
