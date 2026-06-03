"""ControlCore — assembles the whole brain and exposes a tiny driving surface.

One object that wires the bus, the model gateway, the glass-box, the scorecard,
the stub workers, the orchestrator, and the proactive engine together. The HTTP
layer and the tests drive it through `feed()` and `resume()`.
"""
from __future__ import annotations

import os
from pathlib import Path

from .browser_link import BrowserLink
from .bus import Bus
from .env import load_local_env
from .envelopes import Event, EventSource
from .gateway import ModelGateway
from .glassbox import GlassBox
from .orchestrator import Approver, Orchestrator
from .proactive import ProactiveEngine
from .scorecard import Scorecard
from .store import GoalStore
from .workers import ChannelStub, MemoryStub
from ..hands import ApiHand, BrowserHand, MODE_MOCK


def _base(data_dir=None) -> Path:
    return Path(data_dir or os.environ.get("ANTICIPY_DATA_DIR", ".anticipy-data")).expanduser()


class GatedApprover(Approver):
    """Human-path stub that also propagates the gate's approval flag onto the
    step args, so the hand's defense-in-depth (refuse high-risk without the flag)
    is satisfied. Done in the approver — no orchestrator change."""

    def __init__(self, approve: bool = True) -> None:
        self._approve = approve

    async def approve(self, goal, step) -> bool:
        if self._approve:
            step.args["approved"] = True
        return self._approve


class ControlCore:
    def __init__(self, data_dir=None) -> None:
        load_local_env()  # make .env.local keys (Arcade, etc.) available
        base = _base(data_dir)
        self.browser_link = BrowserLink()
        self.glassbox = GlassBox(base / "glassbox.jsonl")
        self.scorecard = Scorecard(base / "scorecard.jsonl")
        self.bus = Bus(glassbox=self.glassbox)
        self.gateway = ModelGateway(endpoint=os.environ.get("ANTICIPY_MODEL_ENDPOINT"))

        # REAL hands replace connector_stub + browser_stub on the frozen contract.
        # channel_stub (reaching the user: call/text) and memory_stub stay (later chunks).
        hands_mode = os.environ.get("ANTICIPY_HANDS_MODE", MODE_MOCK)
        # Arcade user_id must match the signed-in Arcade.dev account ("users only" mode)
        user_id = os.environ.get("ARCADE_USER_ID") or os.environ.get("ADMIN_EMAIL", "omar@anticipy.ai")
        self.api_hand = ApiHand(user_id=user_id, mode=hands_mode)
        self.browser_hand = BrowserHand(
            self.browser_link, timeout=float(os.environ.get("ANTICIPY_BROWSE_TIMEOUT", "30"))
        )
        self.channel = ChannelStub()  # reaching the user (text/call); delivery stubbed for now
        # Real hands register LAST so they own any intent a stub also claims.
        for w in (self.channel, MemoryStub(), self.api_hand, self.browser_hand):
            self.bus.register_worker(w)

        self.store = GoalStore(data_dir=base)
        # No-API app intents reroute to the browser hand via the orchestrator's
        # EXISTING reroute path (config, not a code change).
        alternates = {"post_to_x": "browse_task", "create_event": "browse_task", "message": "browse_task"}
        self.orchestrator = Orchestrator(
            self.bus, self.gateway, self.store, glassbox=self.glassbox, scorecard=self.scorecard,
            alternates=alternates, approver=GatedApprover(True),
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

    async def notify_user(self, text: str, recipient: str | None = None) -> dict:
        """Text the user — the 'ask' half of a wall handoff (pause -> ask -> resume).
        Delivery is stubbed until the real channel lands; the seam + glass-box trail
        are real, and it routes through the same send_text worker the product uses."""
        from .envelopes import Job

        to = recipient or os.environ.get("ALERT_PHONE") or os.environ.get("TWILIO_TO") or "user"
        self.glassbox.log("handoff", {"event": "notify_user", "to": to, "text": text})
        try:
            res = await self.channel.handle(Job(intent="send_text", args={"recipient": to, "body": text}))
            return res.model_dump(mode="json")
        except Exception as e:  # a notify failure must never crash the agent run
            self.glassbox.log("handoff", {"event": "notify_failed", "error": str(e)})
            return {"error": str(e)}

    async def resume(self) -> list:
        return await self.orchestrator.resume_waiting()
