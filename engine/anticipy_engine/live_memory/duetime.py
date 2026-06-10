"""Due-time grounding — spoken time phrases -> tz-aware absolute datetimes.

Deterministic rules, zero model calls. The anchor is WHEN THE WORDS WERE SAID
(event meta `observed_at`), never engine processing time: capture-time-as-event-time
once produced a real but semantically wrong artifact, so temporal grounding must
come from the utterance's own clock. Conservative by design: when no pattern
matches confidently, return None — the loop keeps its raw "due" text and only the
stale-nudge path applies.

Ambiguity rules (deterministic; documented here, nowhere else):
  - bare hour with am/pm  -> that time; if already past the anchor, the next day.
  - bare hour, no am/pm   -> the next future occurrence, preferring daytime
                             (07:00-21:59) over night; "at 3" said at 5pm grounds
                             to tomorrow 3pm, not 3am.
  - hour 13-23            -> 24-hour clock ("at 15:30").
  - day word, no time     -> 09:00 that day ("tomorrow", "friday").
  - weekday naming today  -> today if the time is still ahead, else +7 days.
  - noon already past     -> the next day's noon.
  - tonight               -> 20:00 (or a pm-biased "at H"); past 20:00 -> no ground.
  - end of day / eod      -> 17:00; once past -> no ground.
A fixed-offset anchor (ISO offset, no zone name) grounds day arithmetic in that
offset; across a DST change that can drift an hour. meta["timezone"] (a zone name)
gives exact walls when observed_at is naive.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

REMIND_LEAD_S = 15 * 60.0   # remind_ts = due_ts - 15 minutes

_WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
             "friday": 4, "saturday": 5, "sunday": 6}

_TIME_PART = r"(\d{1,2})(?::(\d{2}))?(?:\s*(am|pm)\b)?"
_RE_IN = re.compile(r"\bin\s+(an?|\d+)\s+(minutes?|mins?|hours?|hrs?|days?|weeks?)\b", re.I)
_RE_TOMORROW = re.compile(r"\btomorrow\b(?:\s+(?:at\s+)?" + _TIME_PART + r")?", re.I)
_RE_WEEKDAY = re.compile(
    r"\b(?:on\s+|next\s+|by\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b"
    r"(?:\s+(?:at\s+)?" + _TIME_PART + r")?", re.I)
_RE_AT = re.compile(r"\bat\s+" + _TIME_PART, re.I)
_RE_NOON = re.compile(r"\bnoon\b", re.I)
_RE_TONIGHT = re.compile(r"\btonight\b", re.I)
_RE_EOD = re.compile(r"\b(?:end of (?:the )?day|eod)\b", re.I)


def anchor_from_meta(meta: Optional[dict]) -> dt.datetime:
    """The grounding clock: meta observed_at (tz-aware) > observed_at + meta timezone
    > local now. Never naive."""
    meta = meta or {}
    raw = meta.get("observed_at")
    if isinstance(raw, str) and raw:
        try:
            d = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            d = None
        if d is not None:
            if d.tzinfo is None:
                tz = None
                if meta.get("timezone"):
                    try:
                        tz = ZoneInfo(str(meta["timezone"]))
                    except Exception:
                        tz = None
                d = d.replace(tzinfo=tz) if tz is not None else d.astimezone()
            return d
    return dt.datetime.now().astimezone()


def _hm(groups: Tuple[str, str, str]) -> Optional[Tuple[int, int, Optional[str]]]:
    """(hour_str, minute_str, ampm_str) -> validated (hour, minute, ampm) or None."""
    hour = int(groups[0])
    minute = int(groups[1] or 0)
    ampm = (groups[2] or "").lower() or None
    if minute > 59 or hour > 23 or (ampm and not 1 <= hour <= 12):
        return None
    return hour, minute, ampm


def _day_time(parsed: Optional[Tuple[int, int, Optional[str]]]) -> Optional[Tuple[int, int]]:
    """Clock reading for a time attached to an explicit day. Daytime bias for bare
    1-12 hours: 8-11 -> am, else pm (people say 'tomorrow at 9' for 09:00 but
    'friday at 3' for 15:00)."""
    if parsed is None:
        return None
    hour, minute, ampm = parsed
    if ampm:
        return hour % 12 + (12 if ampm == "pm" else 0), minute
    if hour >= 13:
        return hour, minute
    if hour == 0:
        return None
    return (hour if 8 <= hour <= 11 else hour % 12 + 12), minute


def _combine(day: dt.date, hour: int, minute: int, tz) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hour, minute), tzinfo=tz)


def _standalone_at(text: str) -> Optional[Tuple[int, int, Optional[str]]]:
    m = _RE_AT.search(text)
    return _hm((m.group(1), m.group(2), m.group(3))) if m else None


def parse_due(text: str, anchor: dt.datetime) -> Optional[dt.datetime]:
    """Ground the due-time phrase in `text` against `anchor`. None = not confident."""
    t = text or ""
    if anchor.tzinfo is None:
        anchor = anchor.astimezone()
    tz = anchor.tzinfo

    m = _RE_IN.search(t)
    if m:
        n = 1 if m.group(1).lower() in ("a", "an") else int(m.group(1))
        unit = m.group(2).lower()
        for stem, secs in (("min", 60), ("hour", 3600), ("hr", 3600),
                           ("day", 86400), ("week", 7 * 86400)):
            if unit.startswith(stem):
                return anchor + dt.timedelta(seconds=n * secs)
        return None

    m = _RE_TOMORROW.search(t)
    if m:
        embedded = _hm((m.group(1), m.group(2), m.group(3))) if m.group(1) else None
        hm = _day_time(embedded or _standalone_at(t)) or (9, 0)
        return _combine(anchor.date() + dt.timedelta(days=1), hm[0], hm[1], tz)

    m = _RE_WEEKDAY.search(t)
    if m:
        wd = _WEEKDAYS[m.group(1).lower()]
        embedded = _hm((m.group(2), m.group(3), m.group(4))) if m.group(2) else None
        hm = _day_time(embedded or _standalone_at(t)) or (9, 0)
        days_ahead = (wd - anchor.weekday()) % 7
        cand = _combine(anchor.date() + dt.timedelta(days=days_ahead), hm[0], hm[1], tz)
        if cand <= anchor:
            cand += dt.timedelta(days=7)
        return cand

    if _RE_TONIGHT.search(t):
        at = _standalone_at(t)
        if at is not None and 1 <= at[0] <= 12:
            hm = (at[0] % 12 + 12, at[1])   # tonight -> pm, always
        else:
            hm = (20, 0)
        cand = _combine(anchor.date(), hm[0], hm[1], tz)
        return cand if cand > anchor else None

    if _RE_EOD.search(t):
        cand = _combine(anchor.date(), 17, 0, tz)
        return cand if cand > anchor else None

    if _RE_NOON.search(t):
        cand = _combine(anchor.date(), 12, 0, tz)
        return cand if cand > anchor else cand + dt.timedelta(days=1)

    at = _standalone_at(t)
    if at is not None:
        hour, minute, ampm = at
        if ampm:
            cand = _combine(anchor.date(), hour % 12 + (12 if ampm == "pm" else 0), minute, tz)
            return cand if cand > anchor else cand + dt.timedelta(days=1)
        if hour >= 13:
            cand = _combine(anchor.date(), hour, minute, tz)
            return cand if cand > anchor else cand + dt.timedelta(days=1)
        if hour == 0:
            return None
        # ambiguous 1-12: next future occurrence, daytime (07:00-21:59) preferred
        cands = sorted(
            c for d in (0, 1) for h24 in (hour % 12, hour % 12 + 12)
            if (c := _combine(anchor.date() + dt.timedelta(days=d), h24, minute, tz)) > anchor
        )
        for c in cands:
            if 7 <= c.hour <= 21:
                return c
        return cands[0] if cands else None

    return None
