from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import re
import threading
import time
import uuid
from typing import Any


_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


@dataclass
class ScheduledItem:
    id: str
    transcript: str
    plan: dict[str, Any] | None
    due_at: float
    created_at: float
    status: str = "pending"
    fired_at: float | None = None
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        row = asdict(self)
        row["due_at_iso"] = datetime.fromtimestamp(
            self.due_at, tz=timezone.utc
        ).isoformat()
        row["created_at_iso"] = datetime.fromtimestamp(
            self.created_at, tz=timezone.utc
        ).isoformat()
        if self.fired_at:
            row["fired_at_iso"] = datetime.fromtimestamp(
                self.fired_at, tz=timezone.utc
            ).isoformat()
        return row


class ProductScheduler:
    """Small product-owned proactive scheduler.

    This replaces imports of a missing frozen scheduler module. It is
    intentionally in-memory because the product server already owns the
    running local session; durable reminders can later be backed by the
    same API without touching frozen proactive code.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: list[ScheduledItem] = []
        self._clock_offset = 0.0

    def now(self) -> float:
        return time.time() + self._clock_offset

    def reset(self) -> None:
        with self._lock:
            self._items.clear()
            self._clock_offset = 0.0

    def schedule_from_transcript(
        self,
        transcript: str,
        plan: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        due = _extract_due_time(transcript, self.now())
        if due is None:
            return None
        item = ScheduledItem(
            id=f"proactive-{uuid.uuid4().hex[:12]}",
            transcript=transcript,
            plan=plan,
            due_at=due,
            created_at=self.now(),
            reason="future_time_reference",
            metadata={"parser": "product_scheduler_v1"},
        )
        with self._lock:
            self._items.append(item)
        return item.to_json()

    def advance_clock(self, seconds: float) -> dict[str, Any]:
        seconds = max(0.0, float(seconds or 0.0))
        with self._lock:
            self._clock_offset += seconds
            fired = self._fire_due_locked()
        return {
            "advanced_seconds": seconds,
            "now": self.now(),
            "fired": fired,
            "fired_count": len(fired),
        }

    def fire_due(self) -> dict[str, Any]:
        """Mark items due by wall clock as fired."""
        with self._lock:
            fired = self._fire_due_locked()
        return {
            "now": self.now(),
            "fired": fired,
            "fired_count": len(fired),
        }

    def _fire_due_locked(self) -> list[dict[str, Any]]:
        fired: list[dict[str, Any]] = []
        now = self.now()
        for item in self._items:
            if item.status == "pending" and item.due_at <= now:
                item.status = "fired"
                item.fired_at = now
                fired.append(item.to_json())
        return fired

    def queue(self) -> list[dict[str, Any]]:
        self.fire_due()
        with self._lock:
            rows = [item.to_json() for item in self._items]
        rows.sort(key=lambda r: (0 if r["status"] == "fired" else 1, r["due_at"]))
        return rows


def _extract_due_time(transcript: str, now_ref=time.time) -> float | None:
    low = re.sub(r"\s+", " ", (transcript or "").lower()).strip()
    if not low:
        return None
    now = float(now_ref() if callable(now_ref) else now_ref)
    match = re.search(r"\bin\s+(\d{1,3})\s*(seconds?|minutes?|hours?|days?)\b", low)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        if unit.startswith("second"):
            return now + amount
        if unit.startswith("minute"):
            return now + amount * 60
        if unit.startswith("hour"):
            return now + amount * 3600
        return now + amount * 86400
    if re.search(r"\btomorrow\b", low):
        return now + 86400
    if re.search(r"\bnext\s+week\b", low):
        return now + 7 * 86400
    for name, weekday in _WEEKDAYS.items():
        if re.search(rf"\b(?:next\s+)?{name}\b", low):
            current = datetime.fromtimestamp(now)
            days = (weekday - current.weekday()) % 7
            if days == 0 or re.search(rf"\bnext\s+{name}\b", low):
                days += 7
            return now + days * 86400
    if re.search(r"\b(?:due|before|by)\b", low):
        return now + 86400
    return None


_SCHEDULER = ProductScheduler()


def get_scheduler() -> ProductScheduler:
    return _SCHEDULER
