"""Layer B: the timing engine. The "when you get a chance" problem.

A resolved action is not automatically a NOW action. Classify its
time condition and, for a deferred action, infer the release
condition and schedule against it. Two hard rules (the safe
direction): a deferred action is NEVER executed immediately and is
NEVER silently dropped. Where the time condition is present but the
release cannot be inferred confidently, HOLD and surface a one-line
"now or later?" rather than guessing either way.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.proactive_day.world import SimWorld

# explicit clock / date -> scheduled at a concrete sim time
_TONIGHT = re.compile(r"\b(tonight|this evening)\b", re.I)
_DATE = re.compile(r"\b(today|tomorrow|monday|tuesday|wednesday|thursday|"
                    r"friday|saturday|sunday|next week)\b", re.I)
# condition -> deferred until a dependency/place/event
_AFTER_EVT = re.compile(r"\bafter (the )?(meeting|standup|sync|call|review)\b",
                        re.I)
_OPPORTUNISTIC = re.compile(r"\b(when you get a chance|later|at some point|"
                            r"when you can|whenever)\b", re.I)
_DEP_READY = re.compile(r"\bonce .* (ready|done|back|landed)\b", re.I)
_STANDING = re.compile(r"\b(every|always|the regular|each (day|week)|"
                       r"from now on)\b", re.I)


@dataclass
class TimePlan:
    when: str               # now | deferred | scheduled | standing | hold
    release: Optional[str]  # human description of the release condition
    at_s: Optional[float]   # concrete sim hour for 'scheduled'
    reason: str


def _next_event_end(world: SimWorld) -> Optional[float]:
    upcoming = [c for c in world.calendar
                if c.get("end", 0) >= world.now_s]
    if not upcoming:
        return None
    return min(upcoming, key=lambda c: c.get("start", 0)).get("end")


def classify(action, event: dict, world: SimWorld) -> TimePlan:
    """Return the time plan. `action` is the ResolvedAction (its
    .time_ref is the time phrase Layer A already found, if any).
    """
    txt = (event.get("text", "") or "").lower()
    tref = (getattr(action, "time_ref", None) or "")

    if _STANDING.search(txt):
        return TimePlan("standing", "recurring", None, "standing rule")

    if _TONIGHT.search(txt):
        return TimePlan("scheduled", "tonight", 19.0, "explicit tonight")

    m = _DATE.search(txt)
    if m:
        return TimePlan("scheduled", m.group(0), None,
                         f"explicit date: {m.group(0)}")

    if _AFTER_EVT.search(txt):
        end = _next_event_end(world)
        return TimePlan("deferred",
                        f"after {_AFTER_EVT.search(txt).group(0)}",
                        end, "after a calendar event")

    if _DEP_READY.search(txt):
        return TimePlan("deferred", _DEP_READY.search(txt).group(0), None,
                        "dependency-ready condition")

    if _OPPORTUNISTIC.search(txt) or _OPPORTUNISTIC.search(tref):
        return TimePlan("deferred", "opportunistic / when free", None,
                        "opportunistic deferral")

    # a time phrase was present (Layer A flagged tref) but none of the
    # known patterns matched it: do NOT guess now, do NOT drop -> HOLD
    # and surface a one-line now-or-later question.
    if tref:
        return TimePlan("hold", f"unclear: {tref}", None,
                        "time condition present but release not inferable")

    return TimePlan("now", None, None, "no time condition")
