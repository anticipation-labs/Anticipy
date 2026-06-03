"""ProactiveEngine — the core loop slot (stub).

Wired as the primary driver: each ``tick`` reads context from the live-memory
seam and *could* route actions through the action layer. No real deciding yet —
proposals are always empty in the scaffold. Real proactive logic lands in the
proactive chunk; this file's wiring does not change.
"""
from __future__ import annotations

from ..actions.layer import ActionLayer
from ..live_memory.brain import LiveMemoryBrain
from ..shared.schema import ActionRequest


class ProactiveEngine:
    def __init__(self, live_memory: LiveMemoryBrain, actions: ActionLayer) -> None:
        self.live_memory = live_memory
        self.actions = actions
        self.ticks = 0

    def tick(self) -> dict:
        """One pass of the primary loop. Reads context; proposes nothing (stub)."""
        self.ticks += 1
        context = self.live_memory.inject("proactive tick")
        proposals: list = []  # real proactive decisions land in the proactive chunk
        return {
            "tick": self.ticks,
            "read_context": bool(context),
            "proposals": proposals,
            "stub": True,
        }

    def act(self, request: ActionRequest) -> dict:
        """Proves the loop can drive the action layer (gated)."""
        return self.actions.handle(request)
