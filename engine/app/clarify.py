"""
Vague-task detection — moved out of router.py so the router stays pure-LLM.

Why this is in its own module: the no-hardcoding rule applies to routing
decisions (chat/question/action). Asking ONE clarifying question for an
under-specified action like "book a flight" — before burning a 30-second
browser session that is going to fail — is a UX gate, not a routing or
classification decision. We surface a clarifying question deterministically
because the LLM has already classified this as an action; what we are
adding is a budget protector ("don't start a browser if mandatory slots
are missing"), not a classifier.

The patterns here are NOT used to decide intent — they are used to decide
whether to *ask the user one question first*. Removing this module is safe;
the action will still execute, it will just fail and waste tokens.

For future hardening: replace this with an LLM "required-slot completeness"
check (the extension already does this in extension/agent.js). When the
slot-completeness LLM call lands, this module becomes the deterministic
floor under it.
"""

from __future__ import annotations

import re


# Map a normalized leading verb (or phrase) to a clarifying question.
# Order matters within each list — first match wins.
_VAGUE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"^(order|buy|purchase|get me)\s+(some\s+)?(dog\s*food|cat\s*food|pet\s*food)\b", re.IGNORECASE),
        "Sure — which brand and bag size, and where should I order from (Chewy, Amazon, somewhere local)?",
    ),
    (
        re.compile(r"^(order|buy|purchase|get me)\s+(some\s+)?groceries\b", re.IGNORECASE),
        "Got it — which store (Instacart, Amazon Fresh, Whole Foods…) and what should I add to the cart?",
    ),
    (
        re.compile(r"^(order|buy|purchase|get me)\s+(some\s+)?flowers\b", re.IGNORECASE),
        "Happy to. Who are they for, what's your budget, and where should they be delivered?",
    ),
    (
        re.compile(r"^(book|reserve)\s+a?\s*flight\b", re.IGNORECASE),
        "Which dates, and where are you flying from and to?",
    ),
    (
        re.compile(r"^(book|reserve)\s+a?\s*(restaurant|table|reservation|dinner|lunch)\b", re.IGNORECASE),
        "Which restaurant, what date and time, and how many people?",
    ),
    (
        re.compile(r"^(book|reserve)\s+a?\s*(hotel|room|stay)\b", re.IGNORECASE),
        "Where are you staying, which dates, and how many guests?",
    ),
    (
        re.compile(r"^send\s+(an?\s+)?email\b", re.IGNORECASE),
        "Who should I send it to, and what should it say?",
    ),
    (
        re.compile(r"^send\s+(an?\s+)?(message|text|sms)\b", re.IGNORECASE),
        "Who am I messaging, and what should the message say?",
    ),
    (
        re.compile(r"^schedule\s+(a\s+)?(meeting|call|appointment)\b", re.IGNORECASE),
        "Who should I schedule it with, and what date and time work?",
    ),
    (
        re.compile(r"^(buy|purchase|order)\b\s*$", re.IGNORECASE),
        "What would you like me to buy, and from which site?",
    ),
    (
        re.compile(r"^(book|reserve)\b\s*$", re.IGNORECASE),
        "What would you like me to book?",
    ),
    (
        re.compile(r"^cancel\b\s*$", re.IGNORECASE),
        "What would you like me to cancel? A subscription, a reservation, an order?",
    ),
]

# Action verbs that, on their own with little context, almost certainly need
# clarification. Used as a coarse second-pass filter.
_SHORT_VAGUE_TRIGGERS = (
    "order", "buy", "purchase", "book", "reserve", "schedule",
    "cancel", "send", "message", "email",
)


def needs_clarification(text: str) -> str | None:
    """
    Return a clarifying question if the action request is too vague to act on,
    or None if it looks specific enough to attempt.

    Heuristic, deterministic — no LLM call. Runs only after classify() returns
    "action", so we know there's at least an action keyword.
    """
    cleaned = text.strip()
    if not cleaned:
        return None

    for pattern, question in _VAGUE_PATTERNS:
        if pattern.search(cleaned):
            # Only ask the bespoke question if the user hasn't already supplied
            # the details. Heuristic: a "specific enough" version of these
            # commands tends to be longer than ~40 chars OR includes a number
            # (date/time/quantity), an @ (email/handle), or a domain.
            if (
                len(cleaned) > 40
                or re.search(r"\d", cleaned)
                or "@" in cleaned
                or re.search(r"\b\w+\.(com|org|net|io|co|app)\b", cleaned, re.IGNORECASE)
            ):
                return None
            return question

    word_count = len(cleaned.split())
    if word_count <= 2:
        first = cleaned.split()[0].lower().rstrip(",.;:!?")
        if first in _SHORT_VAGUE_TRIGGERS:
            return (
                "I can help with that — could you give me a bit more detail "
                "about what you need?"
            )

    return None
