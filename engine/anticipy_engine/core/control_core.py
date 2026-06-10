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
from .gateway import ModelGateway, PROVIDER_OPENROUTER
from .glassbox import GlassBox
from .native_bridge_link import NativeBridgeLink
from .orchestrator import Approver, Orchestrator
from .proactive import ProactiveEngine
from .scorecard import Scorecard
from .store import GoalStore
from .workers import ChannelStub, MemoryWorker
from ..hands import ApiHand, BrowserHand, MODE_MOCK
from ..live_memory.brain import LiveMemoryBrain
from ..memory.store import Memory


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

        # REAL memory: four drawers + the live memory agent, on the frozen contract.
        self.memory = Memory(data_dir=base)
        self.live_memory = LiveMemoryBrain(self.memory, gateway=self.gateway, scorecard=self.scorecard)
        self.memory_worker = MemoryWorker(self.live_memory)

        # REAL hands replace connector_stub + browser_stub on the frozen contract.
        # channel_stub (reaching the user: call/text) stays (later chunk).
        hands_mode = os.environ.get("ANTICIPY_HANDS_MODE", MODE_MOCK)
        # Arcade user_id must match the signed-in Arcade.dev account ("users only" mode)
        user_id = os.environ.get("ARCADE_USER_ID") or os.environ.get("ADMIN_EMAIL", "omar@anticipy.ai")
        self.api_hand = ApiHand(user_id=user_id, mode=hands_mode)
        agent_gateway = self.gateway if self.gateway.provider == PROVIDER_OPENROUTER else None
        native_bridge = None
        if (os.environ.get("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "1") or "").strip().lower() not in {"0", "false", "no", "off"}:
            native_bridge = NativeBridgeLink()
        self.native_bridge_link = native_bridge
        self.browser_hand = BrowserHand(
            self.browser_link,
            timeout=float(os.environ.get("ANTICIPY_BROWSE_TIMEOUT", "30")),
            gateway=agent_gateway,
            max_steps=int(os.environ.get("ANTICIPY_AGENT_MAX_STEPS", "18")),
            agent_timeout=float(os.environ.get("ANTICIPY_AGENT_TIMEOUT", "240")),
            notifier=self.notify_user,
            fallback_link=native_bridge,
        )
        self.channel = ChannelStub()  # reaching the user (text/call); delivery stubbed for now
        # Real workers register LAST so they own any intent a stub also claims; the real
        # MemoryWorker takes over read_context + write_memory.
        for w in (self.channel, self.api_hand, self.browser_hand, self.memory_worker):
            self.bus.register_worker(w)

        self.store = GoalStore(data_dir=base)
        # No-API app intents reroute to the browser hand via the orchestrator's
        # EXISTING reroute path (config, not a code change).
        alternates = {"post_to_x": "browse_task", "create_event": "browse_task", "message": "browse_task"}
        self.orchestrator = Orchestrator(
            self.bus, self.gateway, self.store, glassbox=self.glassbox, scorecard=self.scorecard,
            alternates=alternates, approver=GatedApprover(True), memory_context=self._mem_ctx,
        )
        self.proactive = ProactiveEngine(
            self.bus, self.gateway, self.orchestrator, glassbox=self.glassbox, scorecard=self.scorecard
        )

    async def start(self) -> None:
        await self.bus.start()

    async def stop(self) -> None:
        await self.bus.stop()

    def _mem_ctx(self, about: str) -> dict:
        """INJECT seam for the orchestrator's plan: relevant memory for `about`."""
        inj = self.live_memory.inject(about)
        return {
            "notes": inj["text"],
            "open_loops": [i.text for i in inj["open_loops"]],
            "profile": [i.text for i in inj["profile"]],
            "history": [i.text for i in inj["history"]],
            "derived": [i.text for i in inj["derived"]],
        }

    async def feed(self, source: str, text: str, meta: dict | None = None) -> dict:
        self.live_memory.capturer.capture(text, source=source, meta=meta)  # CAPTURE before anything acts
        ev = Event(source=EventSource(source), text=text, meta=meta or {})
        await self.bus.publish(ev)                 # log the event to the glass-box
        return await self.proactive.on_event(ev)   # triage -> gate -> act/ask (gate reads memory)

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

    # ---- Room 6: the "needs you" surface (decisions flow brain -> app -> back) ----
    def pending_asks(self) -> list:
        """Detrimental actions paused awaiting the user's yes/no — what the app surfaces."""
        return [{"ask_id": aid, "action": p["action"], "reason": p["reason"],
                 "category": p.get("category", ""), "goal_id": p["goal_id"]}
                for aid, p in self.proactive.pending.items()]

    async def resolve(self, ask_id: str, approved: bool) -> dict:
        """The app's approve/deny -> resolves the REAL paused goal (mirrors the text/call round-trip)."""
        return await self.proactive.resolve_ask(ask_id, approved)
