"""The proactive engine skeleton — the decider.

Loop over Events:
  1. triage (cheap, local, NO smart model): drop the obvious nothing.
  2. gate: read context, then make the real decision (smart model allowed here) —
     one of act_silently / do_and_notify / ask_first / ignore.
  3. act -> create a Goal and hand to the orchestrator; ask_first -> human path.
  4. record every decision to the glass-box and the scorecard.

Build the framework; the judgment QUALITY is tuned later on real data. Thresholds
and cues live in GateConfig so tuning is a config change, not a rewrite.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional, Tuple

from ..proactive.triage import Triage
from .bus import Bus
from .envelopes import Event, Goal, Job
from .gateway import SMART, ModelGateway
from .orchestrator import Orchestrator


@dataclass
class GateConfig:
    # triage: cues that make an event "possibly actionable" (configurable)
    actionable_cues: Tuple[str, ...] = (
        "send", "book", "schedule", "reschedule", "email", "remind", "call",
        "set up", "draft", "meet", "reply", "wire", "pay", "transfer", "buy",
        "cancel", "delete", "move", "follow up",
    )
    # gate scoring knobs (used by the real gate later; configurable now)
    min_confidence: float = 0.5
    act_silently_max_risk: float = 0.2
    ask_first_min_risk: float = 0.6


class ProactiveEngine:
    def __init__(
        self,
        bus: Bus,
        gateway: ModelGateway,
        orchestrator: Orchestrator,
        glassbox=None,
        scorecard=None,
        config: Optional[GateConfig] = None,
    ) -> None:
        self.bus = bus
        self.gateway = gateway
        self.orchestrator = orchestrator
        self.glassbox = glassbox
        self.scorecard = scorecard
        self.config = config or GateConfig()
        self.triage = Triage(gateway=gateway)   # Room 1: the bouncer (cheap, first, free in stub)

    async def on_event(self, event: Event) -> dict:
        # 1) triage — cheap, local, no smart model; most events die here
        if not self._triage(event):
            self._record(event, "ignore", "triaged out (no actionable cue)")
            return {"decision": "ignore", "triaged": True, "goal_id": None}

        # 2) gate — read context (cheap worker), then the real decision (smart)
        ctx = await self.bus.submit_job(Job(intent="read_context", args={"about": event.text}))
        context = (ctx.output or {}).get("context", {})
        decision_raw = await self.gateway.think(self._gate_prompt(event, context), tier=SMART, caller="gate")
        parsed = self._parse_decision(decision_raw)
        decision, reason = parsed["decision"], parsed.get("reason", "")
        self._record(event, decision, reason)

        # 3) act / ask
        goal_id = None
        if decision in ("act_silently", "do_and_notify"):
            goal = await self.orchestrator.start_goal(Goal(intent=event.text, description=event.text))
            goal_id = goal.id
        elif decision == "ask_first":
            self._raise_to_human(event, reason)
        return {"decision": decision, "reason": reason, "goal_id": goal_id}

    # ---- steps ----
    def _triage(self, event: Event) -> bool:
        return self.triage.actionable(event.text)   # Room 1: high-recall bouncer, zero smart calls in stub

    def _gate_prompt(self, event: Event, context: dict) -> str:
        return f"Decide how to handle this event given context.\nEVENT: {event.text}\nCONTEXT: {context}"

    @staticmethod
    def _parse_decision(raw: str) -> dict:
        return json.loads(raw)

    def _raise_to_human(self, event: Event, reason: str) -> None:
        if self.glassbox is not None:
            self.glassbox.log("ask_human", {"event_id": event.id, "text": event.text, "reason": reason})

    def _record(self, event: Event, decision: str, reason: str) -> None:
        if self.glassbox is not None:
            self.glassbox.log("decision", {"event_id": event.id, "text": event.text,
                                           "decision": decision, "reason": reason})
        if self.scorecard is not None:
            self.scorecard.record_decision(decision, event.id, reason)
