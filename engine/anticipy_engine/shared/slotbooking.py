"""Anaphoric slot-choice booking — one shared shape for BOTH consumers.

"Dr. Patel's office called back about the checkup, they have Friday 9am or
next Tuesday 2. Book the Friday 9am one." The offered-slot anaphor's head is
"one", so the harm-line's verb..noun reservation/calendar shapes (noun within
~20 chars of the verb) structurally never see the appointment — the line fell
to the fail-safe ask purely for shape, not safety (sibling of F29's
vocabulary gap).

The shape accepts ONLY when, in the SAME line:
  - a book-verb takes a determiner-fronted slot anaphor whose head is "one",
  - the slot modifiers carry a concrete time-ish token ("Friday 9am" — an
    unanchored "the earlier one" needs the offer context a deterministic rule
    cannot resolve, so it stays an ask),
  - a closed-class appointment noun anchors what is being booked, and
  - no commerce/travel noun appears (a slot-priced purchase — "book the 9am
    one, the flight" — keeps its fail-safe/money reading).
Every deny bound fails toward None. Money is not checked here: the harm-line
tests its hard rules FIRST, so a spend verb never reaches this shape.

Imported by the harm-line (the ACT decision) and the stub planner (the
grounded create_event plan), so the decision-layer ACT population is exactly
the population the plan layer can complete — the F29 anti-drift lesson
(shared/storesite.py precedent).
"""
from __future__ import annotations

import re
from typing import Optional

_SLOT_BOOKING_RE = re.compile(
    r"\bbook(?:s|ing)?\b[\w' ]{0,20}\b(?:that|the)\s+(?P<slot>(?:[\w:-]+\s+){0,3})one\b",
    re.I,
)
_SLOT_TIME_RE = re.compile(
    r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|today|tomorrow|"
    r"tonight|noon|midnight|morning|afternoon|evening)\b|\d",
    re.I,
)
_APPT_ANCHOR_RE = re.compile(
    r"\b(?:appointment|appointments|checkup|checkups|check-up|check-ups|"
    r"cleaning|cleanings|visit|visits)\b",
    re.I,
)
_COMMERCE_DENY_RE = re.compile(
    r"\b(?:flight|flights|train|trains|bus|buses|hotel|hotels|airbnb|rental|rentals|"
    r"car|cars|ticket|tickets|seat|seats|cruise|cruises|tour|tours|upgrade|upgrades|"
    r"package|packages|fare|fares)\b",
    re.I,
)
# the booked thing, for an honest event title: optional possessive + the anchor
# noun, verbatim from the line ("Maya's checkup")
_APPT_TITLE_RE = re.compile(
    r"\b(?:[\w']+'s\s+)?(?:appointment|checkup|check-up|cleaning|visit)s?\b",
    re.I,
)


def match_slot_choice_booking(text: str) -> Optional[str]:
    """The spoken slot ("Friday 9am") iff the line is an appointment-anchored,
    commerce-denied slot-choice booking; None otherwise (deny fails toward None)."""
    t = text or ""
    m = _SLOT_BOOKING_RE.search(t)
    if m is None:
        return None
    slot = re.sub(r"\s+", " ", m.group("slot") or "").strip(" ,.-")
    if not slot or not _SLOT_TIME_RE.search(slot):
        return None
    if not _APPT_ANCHOR_RE.search(t):
        return None
    if _COMMERCE_DENY_RE.search(t):
        return None
    return slot


def appointment_title(text: str) -> str:
    """Verbatim possessive+appointment-noun span ("Maya's checkup") or ""."""
    m = _APPT_TITLE_RE.search(text or "")
    return re.sub(r"\s+", " ", m.group(0)).strip() if m else ""
