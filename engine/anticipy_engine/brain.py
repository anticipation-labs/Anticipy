"""The Brain — wires every room together behind the engine's HTTP surface.

This is the hub's orchestration: a capture event enters through the CaptureSource
seam (never a device directly), the engine reads it from intake, calls think(),
and writes a scrap into the history store. The proactive loop, action layer, and
channels are all instantiated and reachable, ready for later chunks.
"""
from __future__ import annotations

from .actions.layer import ActionLayer
from .capture.intake import Intake
from .capture.mac_mic import MacMicSource
from .channels import Channels
from .live_memory.brain import LiveMemoryBrain
from .memory.store import Memory
from .model import think
from .proactive.engine import ProactiveEngine


class Brain:
    def __init__(self) -> None:
        self.memory = Memory()
        self.live_memory = LiveMemoryBrain(self.memory)
        self.intake = Intake()
        self.actions = ActionLayer()
        self.proactive = ProactiveEngine(self.live_memory, self.actions)
        self.channels = Channels()
        # The one capture source today; emits into the engine intake via the seam.
        self.mic = MacMicSource(sink=self.intake.receive)
        self.extension_connected = False

    def handle_capture(self, text: str, source: str = "mac_mic") -> dict:
        """The hello-loop path: capture -> intake -> think -> history write."""
        if source != "mac_mic":
            raise ValueError(f"source '{source}' is not available in the scaffold")
        self.mic.emit_stub(text)            # 1) enters via the CaptureSource seam
        event = self.intake.last            # 2) engine receives via intake (not the mic)
        thought = think(event.text)         # 3) engine calls think()
        scrap = self.memory.history.write_text(  # 4) writes a scrap into history
            f"heard '{event.text}' | thought: {thought}"
        )
        return {"event": event.model_dump(), "thought": thought, "scrap": scrap.model_dump()}

    def mark_extension_connected(self, client: str = "chrome") -> dict:
        self.extension_connected = True
        return {"connected": True, "client": client}

    def status(self) -> dict:
        return {
            "engine": "ok",
            "extension_connected": self.extension_connected,
            "history_count": len(self.memory.history.all()),
        }
