"""Engine-side intake — the only place the engine receives capture.

A ``CaptureSource`` pushes ``CaptureEvent``s here. The engine reads from this
intake, never from a device directly, which is what makes the capture seam
swappable (mic today, pendant later).
"""
from __future__ import annotations

from typing import List

from ..shared.schema import CaptureEvent


class Intake:
    def __init__(self) -> None:
        self._events: List[CaptureEvent] = []

    def receive(self, event: CaptureEvent) -> None:
        """Sink handed to a CaptureSource. Buffers received events."""
        self._events.append(event)

    @property
    def events(self) -> List[CaptureEvent]:
        return list(self._events)

    @property
    def last(self) -> CaptureEvent:
        return self._events[-1]
