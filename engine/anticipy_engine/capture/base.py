"""The capture seam interface.

A ``CaptureSource`` produces ``CaptureEvent``s and hands them to a sink (the
engine's intake). The engine depends on THIS interface only, so any source —
the Mac mic today, the pendant-through-phone tomorrow — plugs into the same
socket without the engine changing.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from ..shared.schema import CaptureEvent, CaptureSourceName

# The engine gives a source one of these to push events into.
EventSink = Callable[[CaptureEvent], None]


class CaptureSource(ABC):
    """Abstract input. Subclasses set ``name`` and implement start/stop."""

    name: CaptureSourceName

    def __init__(self, sink: EventSink) -> None:
        self._sink = sink

    @abstractmethod
    def start(self) -> None:
        """Begin producing events into the sink."""

    @abstractmethod
    def stop(self) -> None:
        """Stop producing events."""

    def _emit(self, text: str) -> CaptureEvent:
        """Build a CaptureEvent in the shared data language and push it to the sink."""
        event = CaptureEvent(source=self.name, text=text)
        self._sink(event)
        return event
