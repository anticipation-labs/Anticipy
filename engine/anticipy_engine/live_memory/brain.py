"""LiveMemoryBrain — stubbed seam between memory and the proactive engine.

- inject(context):  later, select the memory that matters for `context`.
                    Scaffold: returns the shape, selects nothing.
- capture(event):   fold a capture event into memory (history). Minimal wiring.
- maintain():       later, dedupe/decay/summarize. Scaffold: no-op stub.
"""
from __future__ import annotations

from typing import Dict, List

from ..memory.store import Memory
from ..shared.schema import CaptureEvent
from .capture import Capturer
from .inject import Injector


class LiveMemoryBrain:
    def __init__(self, memory: Memory, gateway=None) -> None:
        self.memory = memory
        self.capturer = Capturer(memory, gateway=gateway)
        self.injector = Injector(memory, gateway=gateway)

    def inject(self, context: str = "", k=None) -> Dict[str, object]:
        """REAL hybrid retrieval (semantic+keyword+recency+importance), budgeted,
        with ALL open/waiting loops always surfaced."""
        return self.injector.inject(context, k=k)

    def capture(self, event: CaptureEvent) -> Dict[str, object]:
        """REAL capture: keep/drop gate -> classify -> dedupe -> route to a drawer.
        Returns {kept, kind, item, reason, smart_calls}."""
        return self.capturer.capture(event.text, source=getattr(event, "source", ""))

    def maintain(self) -> Dict[str, object]:
        """Stub: housekeeping does nothing yet (ran=False marks it a stub)."""
        return {"maintained": True, "ran": False}
