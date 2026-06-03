"""ControlCore — assembles the whole brain and exposes a tiny driving surface.

One object that wires the bus, the model gateway, the glass-box, the scorecard,
the stub workers, the orchestrator, and the proactive engine together. The HTTP
layer and the tests drive it through `feed()` and `resume()`.
"""
from __future__ import annotations

import os
from pathlib import Path

from .bus import Bus
from .envelopes import Event, EventSource
from .gateway import ModelGateway
from .glassbox import GlassBox
from .orchestrator import Orchestrator
from .proactive import ProactiveEngine
from .scorecard import Scorecard
from .store import GoalStore
from .workers import BrowserStub, ChannelStub, ConnectorStub, MemoryStub


def _base(data_dir=None) -> Path:
    return Path(data_dir or os.environ.get("ANTICIPY_DATA_DIR", ".anticipy-data")).expanduser()


class ControlCore:
    def __init__(self, data_dir=None) -> None:
        base = _base(data_dir)
        self.glassbox = GlassBox(base / "glassbox.jsonl")
        self.scorecard = Scorecard(base / "scorecard.jsonl")
        self.bus = Bus(glassbox=self.glassbox)
        self.gateway = ModelGateway(endpoint=os.environ.get("ANTICIPY_MODEL_ENDPOINT"))
        for w in (ChannelStub(), MemoryStub(), ConnectorStub(), BrowserStub()):
            self.bus.register_worker(w)
        self.store = GoalStore(data_dir=base)
        self.orchestrator = Orchestrator(
            self.bus, self.gateway, self.store, glassbox=self.glassbox, scorecard=self.scorecard
        )
        self.proactive = ProactiveEngine(
            self.bus, self.gateway, self.orchestrator, glassbox=self.glassbox, scorecard=self.scorecard
        )

    async def start(self) -> None:
        await self.bus.start()

    async def stop(self) -> None:
        await self.bus.stop()

    async def feed(self, source: str, text: str, meta: dict | None = None) -> dict:
        ev = Event(source=EventSource(source), text=text, meta=meta or {})
        await self.bus.publish(ev)                 # log the event to the glass-box
        return await self.proactive.on_event(ev)   # triage -> gate -> act/ask

    async def resume(self) -> list:
        return await self.orchestrator.resume_waiting()
