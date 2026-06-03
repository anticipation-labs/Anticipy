"""LiveMemoryBrain — stubbed seam between memory and the proactive engine.

- inject(context):  later, select the memory that matters for `context`.
                    Scaffold: returns the shape, selects nothing.
- capture(event):   fold a capture event into memory (history). Minimal wiring.
- maintain():       later, dedupe/decay/summarize. Scaffold: no-op stub.
"""
from __future__ import annotations

from typing import Dict, List

from ..memory.store import Memory
from ..shared.schema import CaptureEvent, MemoryItem


class LiveMemoryBrain:
    def __init__(self, memory: Memory) -> None:
        self.memory = memory

    def inject(self, context: str = "") -> Dict[str, object]:
        """Stub: real relevance selection lands next chunk. Returns shape only."""
        empty: List[MemoryItem] = []
        return {
            "context": context,
            "profile": empty,
            "open_loops": empty,
            "history": empty,
            "stub": True,
        }

    def capture(self, event: CaptureEvent) -> MemoryItem:
        """Fold a capture event into the history store (shared data language)."""
        return self.memory.history.write_text(event.text, people=[])

    def maintain(self) -> Dict[str, object]:
        """Stub: housekeeping does nothing yet (ran=False marks it a stub)."""
        return {"maintained": True, "ran": False}
