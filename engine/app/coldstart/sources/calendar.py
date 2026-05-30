"""Google Calendar source extractor for the cold-start dossier inhale.

Returns:

    {
        "source": "calendar",
        "ok": bool,
        "events_next_7d": [
            {"title": str, "when": str, "attendees": [str]}
        ],
        "recurring_meetings": [
            {"title": str, "cadence": str, "attendees": [str]}
        ],
        "week_shape": {
            "meeting_count": int,
            "busiest_day": str,         # "Mon" .. "Sun"
            "first_meeting_hour": int,  # 0-23
            "last_meeting_hour": int,   # 0-23
        },
        "error": str,
    }

Recurring meetings = titles that appear >= 2 times in the next 7 days,
                     OR explicitly tagged 'recurring' by the extension.
Week shape = lightweight summary the clarifier uses to infer cadence
            ("you're a Tue/Thu founder", "your day starts at 7am").

If Calendar is signed-out, ok=False with empty lists.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from . import _bridge_protocol as _bp


CALENDAR_WEEK_URL = "https://calendar.google.com/calendar/r/week"


_WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _norm_attendees(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for x in raw:
        s = str(x or "").strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out[:20]


def _events_next_7d(rows: list[dict], cap: int = 30) -> list[dict]:
    out: list[dict] = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        title = str(r.get("title") or "").strip()
        if not title:
            continue
        when = str(r.get("when") or r.get("start") or "").strip()
        out.append({
            "title": title[:160],
            "when": when[:80],
            "attendees": _norm_attendees(r.get("attendees")),
        })
        if len(out) >= cap:
            break
    return out


def _recurring_meetings(rows: list[dict]) -> list[dict]:
    """Title appears >= 2 times OR row says recurring=True."""
    counts: Counter[str] = Counter()
    explicit_titles: set[str] = set()
    attendees_for: dict[str, list[str]] = {}
    cadence_for: dict[str, str] = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        title = str(r.get("title") or "").strip()
        if not title:
            continue
        norm = title.lower()
        counts[norm] += 1
        attendees_for.setdefault(norm, []).extend(
            _norm_attendees(r.get("attendees")))
        if r.get("recurring"):
            explicit_titles.add(norm)
        cadence = str(r.get("cadence") or "").strip()
        if cadence:
            cadence_for[norm] = cadence
    by_display: dict[str, str] = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        t = str(r.get("title") or "").strip()
        if t and t.lower() not in by_display:
            by_display[t.lower()] = t

    out: list[dict] = []
    for norm, freq in counts.most_common():
        if freq < 2 and norm not in explicit_titles:
            continue
        # Dedupe attendees per meeting
        atts: list[str] = []
        seen: set[str] = set()
        for a in attendees_for.get(norm, []):
            k = a.lower()
            if k in seen:
                continue
            seen.add(k)
            atts.append(a)
        out.append({
            "title": by_display.get(norm, norm)[:160],
            "cadence": cadence_for.get(norm, "weekly" if freq >= 2 else ""),
            "attendees": atts[:10],
        })
        if len(out) >= 10:
            break
    return out


def _week_shape(rows: list[dict]) -> dict:
    """Aggregate cadence stats over the supplied events."""
    if not rows:
        return {
            "meeting_count": 0,
            "busiest_day": "",
            "first_meeting_hour": 0,
            "last_meeting_hour": 0,
        }
    day_counts: Counter[str] = Counter()
    hours: list[int] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        when = str(r.get("when") or r.get("start") or "")
        # Look for "Mon", "Tue", ... anywhere in the when string.
        for d in _WEEKDAY_NAMES:
            if d in when:
                day_counts[d] += 1
                break
        # Pull HH or HH:MM out, prefer the first match.
        hm = re.search(r"\b([01]?\d|2[0-3]):?([0-5]\d)?\b", when)
        if hm:
            try:
                hours.append(int(hm.group(1)))
            except ValueError:
                pass
    busiest_day = ""
    if day_counts:
        busiest_day, _ = day_counts.most_common(1)[0]
    return {
        "meeting_count": len([
            r for r in rows if isinstance(r, dict) and r.get("title")]),
        "busiest_day": busiest_day,
        "first_meeting_hour": min(hours) if hours else 0,
        "last_meeting_hour": max(hours) if hours else 0,
    }


async def extract(bridge: Any) -> dict:
    """Drive the wearer's Chrome to read Google Calendar week view.

    Extension is expected to return:

        {"events": [{title, when, attendees, recurring, cadence}, ...]}
    """
    payload = {
        "type": "extract_dossier_source",
        "source": "calendar",
        "url": CALENDAR_WEEK_URL,
        "window_days": 7,
    }
    try:
        resp = await _bp.dispatch(bridge, payload)
    except Exception as exc:
        return {
            "source": "calendar",
            "ok": False,
            "events_next_7d": [],
            "recurring_meetings": [],
            "week_shape": {
                "meeting_count": 0,
                "busiest_day": "",
                "first_meeting_hour": 0,
                "last_meeting_hour": 0,
            },
            "error": f"dispatch raised: {type(exc).__name__}: {exc}",
        }

    if not isinstance(resp, dict) or not resp.get("ok"):
        return {
            "source": "calendar",
            "ok": False,
            "events_next_7d": [],
            "recurring_meetings": [],
            "week_shape": {
                "meeting_count": 0,
                "busiest_day": "",
                "first_meeting_hour": 0,
                "last_meeting_hour": 0,
            },
            "error": str((resp or {}).get("error") or "extension reported not ok"),
        }

    data = resp.get("data") or {}
    if not isinstance(data, dict):
        data = {}
    events = data.get("events") or []
    if not isinstance(events, list):
        events = []

    return {
        "source": "calendar",
        "ok": True,
        "events_next_7d": _events_next_7d(events),
        "recurring_meetings": _recurring_meetings(events),
        "week_shape": _week_shape(events),
    }


__all__ = ["extract", "CALENDAR_WEEK_URL"]
