"""Shared schedule-change calendar hold detection.

The owner-bank v2 misses exposed a general spoken shape:
"X moved/changed, block/capture the new time." It is not a per-persona rule.
It requires a schedule-change cue, an explicit capture cue, and a concrete time
anchor before it can become a reversible calendar hold.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ScheduleHold:
    title: str
    when: str


_CHANGE_CUE = re.compile(
    r"\b(?:moved?|rescheduled|rebooked|shifted|changed|delayed|bumped)\b",
    re.I,
)
_CAPTURE_CUE = re.compile(
    r"\b(?:block|calendar|cal|put\s+(?:that|it|this)\s+somewhere|"
    r"get\s+(?:that|it|this)\s+into\s+(?:my|the|our)\s+calendar)\b",
    re.I,
)
_CLOCK = r"(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)?|noon|midnight)"
_DAY = r"(?:(?:mon|tues?|wednes|thurs?|fri|satur|sun)(?:day)?|today|tomorrow)"
_DAYPART = r"(?:morning|afternoon|evening|night)"

_FROM_TO_AT_RE = re.compile(
    r"\bfrom\s+(?P<old_day>" + _DAY + r")\s+to\s+(?P<day>" + _DAY + r")"
    r"\s+(?:at\s+)?(?P<clock>" + _CLOCK + r")\b",
    re.I,
)
_TO_CLOCK_RE = re.compile(
    r"\bto\s+(?P<clock>" + _CLOCK + r")\s*(?P<day>" + _DAY + r")?\b"
    r"|\bto\s+(?P<day_first>" + _DAY + r")\s+(?:at\s+)?(?P<clock_after>" + _CLOCK + r")\b",
    re.I,
)
_BLOCK_DAYPART_RE = re.compile(
    r"\bblock\s+(?:the\s+)?(?P<part>" + _DAYPART + r")\b",
    re.I,
)
_DAY_RE = re.compile(r"\b" + _DAY + r"\b", re.I)

_FOR_TITLE_RE = re.compile(
    r"\bfor\s+(?:the\s+|a\s+|an\s+)?(?P<title>[^.;!?,]{3,70}?)"
    r"(?=\s+(?:so|because|since|before|after)\b|[.;!?,]|$)",
    re.I,
)
_MOVED_TITLE_RE = re.compile(
    r"\b(?:the\s+|my\s+|our\s+)?(?P<title>[\w'\- ]{2,50}?"
    r"(?:call|meeting|appointment|pickup|dropoff|ride|shift|checkup))\s+"
    r"(?:moved|rescheduled|rebooked|shifted|changed|delayed|bumped)\b",
    re.I,
)
_MOVED_OBJECT_RE = re.compile(
    r"\b(?:moved|rescheduled|rebooked|shifted|changed|delayed|bumped)\s+"
    r"(?P<title>[\w'\- ]{2,40}?(?:pickup|dropoff|ride|call|meeting|appointment|shift))\b",
    re.I,
)
_POSSESSIVE_PICKUP_RE = re.compile(
    r"\b(?P<title>[A-Z][\w'\-]+(?:'s)?\s+(?:pickup|dropoff))\s+"
    r"(?:moved|rescheduled|shifted|changed|delayed|bumped)\b"
)


def match_schedule_change_hold(text: str) -> Optional[ScheduleHold]:
    line = re.sub(r"\s+", " ", text or "").strip()
    if not line:
        return None
    if not _CHANGE_CUE.search(line) or not _CAPTURE_CUE.search(line):
        return None

    when = _extract_when(line)
    if not when:
        return None
    title = _extract_title(line)
    return ScheduleHold(title=title, when=when)


def _extract_when(line: str) -> str:
    m = _FROM_TO_AT_RE.search(line)
    if m:
        return f"{_clean(m.group('day'))} at {_clean(m.group('clock'))}"

    block = _BLOCK_DAYPART_RE.search(line)
    if block:
        prior = line[:block.start()]
        day_matches = list(_DAY_RE.finditer(prior))
        if day_matches:
            return f"{_clean(day_matches[-1].group(0))} {_clean(block.group('part'))}"
        return _clean(block.group("part"))

    m = _TO_CLOCK_RE.search(line)
    if m:
        clock = m.group("clock") or m.group("clock_after")
        day = m.group("day") or m.group("day_first") or _nearby_day(line, m.end())
        if day:
            return f"{_clean(day)} {_clean(clock)}"
        return _clean(clock)

    return ""


def _nearby_day(line: str, start: int) -> str:
    window = line[max(0, start - 80): min(len(line), start + 80)]
    matches = list(_DAY_RE.finditer(window))
    return matches[-1].group(0) if matches else ""


def _extract_title(line: str) -> str:
    block = _BLOCK_DAYPART_RE.search(line)
    if block:
        m = _FOR_TITLE_RE.search(line, block.end())
        if m:
            return _clean(m.group("title"))

    for pattern in (_POSSESSIVE_PICKUP_RE, _MOVED_TITLE_RE, _MOVED_OBJECT_RE):
        m = pattern.search(line)
        if m:
            title = _clean(m.group("title"))
            if title.lower().startswith("the "):
                title = title[4:]
            return title

    if re.search(r"\bpick\s*up|pickup\b", line, re.I):
        return "pickup"
    if re.search(r"\bdrop\s*off|dropoff\b", line, re.I):
        return "dropoff"
    return "Calendar hold"


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip(" .,!?:;\"'")
