"""MacMicSource — the one real-ish source today (still a stub).

Real microphone capture + transcription is wired in a later chunk. For the
scaffold, ``emit_stub`` lets us inject a fake utterance as if the mic heard it,
so the rest of the wiring can be exercised end to end.
"""
from __future__ import annotations

from .base import CaptureSource
from ..shared.schema import CaptureEvent


class MacMicSource(CaptureSource):
    name = "mac_mic"

    def __init__(self, sink) -> None:
        super().__init__(sink)
        self._running = False

    def start(self) -> None:
        # Stub: no real audio yet. Marks the source active.
        self._running = True

    def stop(self) -> None:
        self._running = False

    def emit_stub(self, text: str) -> CaptureEvent:
        """Scaffold-only: pretend the mic heard ``text`` and emit it."""
        return self._emit(text)
