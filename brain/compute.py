"""Arithmetic is COMPUTED — never searched, never held.

On 2026-08-23, live, the owner said "5 PM CS—CST is what? PST." He wanted one
number: 3 PM. What he got was a web-research summary of a timezone-converter
page whose only concrete time was a 6 AM example — and, separately, a card
HELD FOR APPROVAL reading "i'm holding the 5 pm cst conversion to pst",
because the read-only verb list had no word for computing and the safe
default holds. Both failures are the same missing organ: the system had no
way to just KNOW a thing that is knowable from arithmetic.

This module is that organ. The contract:

  * compute_answer(goal) returns the one-line answer, or None. None means
    "not mine" — the caller falls back to research exactly as before, so a
    miss here can never make anything worse.
  * Deterministic, stdlib-only, zero network, zero model calls. This is the
    one lane where pattern-matching is LEGAL under HARNESS-LAWS.md Law 1:
    recognizing "5 PM CST" as arithmetic is an effect-channel judgment
    (computing changes nothing in the world), not a meaning judgment.
  * Wrong-but-confident is worse than silent: anything ambiguous returns
    None rather than a guess.

v1 speaks timezones only, because that is the failure that actually
happened. Grow it by failure, like everything else in this brain.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

# North-American reading of the abbreviations, deliberately. "CST" is also
# China Standard Time, but this product ships US/Canada and its owner says
# CST meaning Chicago. The IANA zone (not a fixed offset) is what makes the
# answer right in both halves of the year: in August "5 PM CST" is really
# 5 PM CDT, and Chicago-to-LA is two hours regardless — the zone math
# absorbs the owner's loose label where a hardcoded offset would not.
_ZONES = {
    "pt": "America/Los_Angeles", "pst": "America/Los_Angeles",
    "pdt": "America/Los_Angeles",
    "mt": "America/Denver", "mst": "America/Denver", "mdt": "America/Denver",
    "ct": "America/Chicago", "cst": "America/Chicago", "cdt": "America/Chicago",
    "et": "America/New_York", "est": "America/New_York",
    "edt": "America/New_York",
    "at": "America/Halifax", "ast": "America/Halifax", "adt": "America/Halifax",
    "utc": "UTC", "gmt": "UTC",
}

_ZONE_WORD = r"(?:p|m|c|e|a)(?:s|d)?t|utc|gmt"

# The shapes people actually say, measured off the one recorded failure and
# its neighbours: "5 PM CST is what PST", "convert 5 pm cst to pst",
# "what is 5pm CST in PST", "5 CST in PST". Time first, source zone, target
# zone — everything else in the sentence is noise and stays unmatched.
_CONVERT_RE = re.compile(
    r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?\s*"
    rf"({_ZONE_WORD})\b"
    r".{0,40}?\b(?:to|in|is\s+what|as|vs)\s*"
    rf"({_ZONE_WORD})\b",
    re.IGNORECASE,
)


def _label(zone_key: str) -> str:
    # Answer in the owner's own vocabulary: he said PST, the answer says
    # PST — correcting him to "PDT" is pedantry wearing a lab coat.
    return zone_key.upper()


def compute_answer(goal: str, now: Optional[datetime] = None) -> Optional[str]:
    """One line of arithmetic truth, or None for everything else."""
    g = (goal or "").strip()
    if not g:
        return None
    m = _CONVERT_RE.search(g)
    if not m:
        return None
    hour_s, minute_s, ampm, src_key, dst_key = m.groups()
    src = _ZONES.get(src_key.lower())
    dst = _ZONES.get(dst_key.lower())
    if not src or not dst:
        return None
    hour = int(hour_s)
    minute = int(minute_s or 0)
    if hour > 23 or minute > 59:
        return None
    ampm = (ampm or "").replace(".", "").lower()
    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    elif not ampm and hour <= 7:
        # "5 CST" with no meridiem: nobody schedules for 5 AM by accident.
        # Bare small hours read as afternoon/evening — the same reading a
        # person in the room would make. Bigger bare hours (8-12) stay as
        # said; past 12 it was 24-hour time all along.
        hour += 12
    # DST correctness needs a real date; "today" in the SOURCE zone is what
    # the owner means when no date is spoken.
    base = (now or datetime.now(ZoneInfo(src))).astimezone(ZoneInfo(src))
    when = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    out = when.astimezone(ZoneInfo(dst))
    def fmt(dt: datetime) -> str:
        h = dt.hour % 12 or 12
        mer = "AM" if dt.hour < 12 else "PM"
        return f"{h}:{dt.minute:02d} {mer}" if dt.minute else f"{h} {mer}"
    answer = f"{fmt(when)} {_label(src_key)} is {fmt(out)} {_label(dst_key)}"
    if out.date() != when.date():
        answer += " the day before" if out.date() < when.date() \
            else " the next day"
    return answer + "."
