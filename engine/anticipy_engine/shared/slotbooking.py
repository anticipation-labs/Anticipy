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

from dataclasses import dataclass
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
_SLOT_WITH_PERSON_RE = re.compile(
    r"\bbook(?:s|ing)?\b(?:\s+\w+){0,4}?\s+(?:that|the)\s+"
    r"(?P<slot>(?:[\w:-]+\s+){0,4})one\s+with\s+(?P<person>[A-Z][\w'\-]+)\b",
    re.I,
)
_AVAILABILITY_CUE_RE = re.compile(
    r"\b(?:can|could|available|availability|free|open|offered|has|have)\b",
    re.I,
)
_LOOK_AT_TITLE_RE = re.compile(r"\blook at\s+(?:the\s+)?(?P<title>[^.;,]{3,50})$", re.I)


@dataclass(frozen=True)
class SlotChoice:
    title: str
    when: str


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


def match_context_slot_choice_booking(text: str, context=None) -> Optional[SlotChoice]:
    """Resolve "book the Friday afternoon one with <person>" only when memory contains
    the same person and slot in an availability-shaped line.

    This is intentionally narrower than same-line slot booking. Without context
    proving what "one" refers to, it fails toward None and the harm-line asks.
    """
    t = text or ""
    m = _SLOT_WITH_PERSON_RE.search(t)
    if m is None:
        return None
    slot = re.sub(r"\s+", " ", m.group("slot") or "").strip(" ,.-")
    person = (m.group("person") or "").strip()
    if not slot or not person or not _SLOT_TIME_RE.search(slot):
        return None
    if _COMMERCE_DENY_RE.search(t):
        return None

    slot_l = slot.lower()
    person_re = re.compile(r"\b" + re.escape(person) + r"\b", re.I)
    for line in _context_lines(context):
        line_clean = re.sub(r"^\[[^\]]+\]\s*", "", line).strip()
        line_l = line_clean.lower()
        if slot_l not in line_l or person_re.search(line_clean) is None:
            continue
        if _COMMERCE_DENY_RE.search(line_clean) or not _AVAILABILITY_CUE_RE.search(line_clean):
            continue
        return SlotChoice(title=_context_title(line_clean, person, slot), when=slot)
    return None


def _context_lines(context) -> list[str]:
    if isinstance(context, dict) and isinstance(context.get("context"), dict):
        context = context["context"]
    if not isinstance(context, dict):
        return []
    lines: list[str] = []
    for key in ("notes", "open_loops", "history", "profile", "derived"):
        value = context.get(key)
        if isinstance(value, str):
            lines.extend(line.strip() for line in value.splitlines() if line.strip())
        elif isinstance(value, list):
            lines.extend(str(line).strip() for line in value if str(line).strip())
    return lines


def _context_title(line: str, person: str, slot: str) -> str:
    idx = line.lower().find(slot.lower())
    before = line[:idx].strip() if idx >= 0 else line
    m = _LOOK_AT_TITLE_RE.search(before)
    if m:
        title = re.sub(r"\s+", " ", m.group("title")).strip(" .,!?:;\"'")
        if title:
            return f"{title} with {person}"
    return f"{person} appointment"
