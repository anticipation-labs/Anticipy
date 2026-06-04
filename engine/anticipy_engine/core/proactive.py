"""The proactive engine — the decider. ACT-FIRST, ask-only-before-harm.

Loop over Events:
  1. triage (Room 1; cheap, local, NO smart model): drop the ~99% that isn't actionable.
  2. read memory context (cheap worker) for the harm-line's gray middle.
  3. the HARM-LINE (Room 2): is this detrimental? confident-no -> ACT (hand a Goal to the
     orchestrator and DO IT); yes or UNSURE -> ASK (pause; never execute until approved).
  4. record every decision (+ category, memory_forced) to the glass-box and scorecard.

The harm-line is deterministic + inspectable (proactive/harm.py); the smart model is used
only when a decision is genuinely hard. Triage cues live in proactive/triage.py.
(GateConfig is a vestigial knob bag from the skeleton — retained for construction compat.)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from ..proactive.harm import HarmLine
from ..proactive.triage import Triage
from ..proactive.trigger import TriggerWatcher
from .bus import Bus
from .envelopes import Event, EventSource, Goal, Job, now_ts
from .gateway import ModelGateway
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
        self.harm = HarmLine()                  # Room 2: act-first, ask-only-before-harm
        self.trigger = TriggerWatcher()         # Room 3: time + open-loop watcher (fire-once)
        self.memory_forced_asks = 0             # Deferred-2: asks forced by weak memory confidence

    async def on_event(self, event: Event) -> dict:
        # 1) triage — cheap, local, no smart model; most events die here (Room 1)
        if not self._triage(event):
            self._record(event, "ignore", "triaged out (not actionable)")
            return {"decision": "ignore", "triaged": True, "goal_id": None}

        # 2) read memory context (the harm-line uses it for the gray middle; cheap worker, no smart)
        ctx = await self.bus.submit_job(Job(intent="read_context", args={"about": event.text}))
        mem = ctx.output or {}

        # 3) THE HARM-LINE (Room 2) — act-first: is this detrimental? deterministic; fail-safe to ask.
        verdict = self.harm.assess(event.text, mem)

        # 4) act (JUST DO IT) / ask (pause before harm; Room 4 makes the ask a real round-trip)
        goal_id = None
        if not verdict.detrimental:
            goal = await self.orchestrator.start_goal(Goal(intent=event.text, description=event.text))
            goal_id = goal.id
            decision = "act"
        else:
            decision = "ask"
            self._raise_to_human(event, verdict.reason)
        # HARD SUB-GATE: a detrimental verdict NEVER produced a goal (no silent harm — 100%).
        assert not (verdict.detrimental and goal_id is not None), "harm-line breach: detrimental action executed"
        self._record(event, decision, verdict.reason, category=verdict.category,
                     memory_forced=verdict.memory_forced)
        return {"decision": decision, "category": verdict.category, "reason": verdict.reason,
                "detrimental": verdict.detrimental, "memory_forced": verdict.memory_forced, "goal_id": goal_id}

    async def trigger_tick(self, now: Optional[float] = None) -> list:
        """Room 3: watch the commitment ledger against the clock. Each due/elapsed loop fires a
        proactive follow-up through the SAME harm-line path (NO new input event), exactly once."""
        now = now if now is not None else now_ts()
        res = await self.bus.submit_job(Job(intent="list_open_loops", args={}))
        loops = (res.output or {}).get("loops", [])
        fired = self.trigger.tick(loops, now)
        out = []
        for loop in fired:
            task = loop.get("task") or loop.get("text") or "your commitment"
            ev = Event(source=EventSource.system, text=f"Follow up on your commitment: {task}")
            decision = await self.on_event(ev)          # SAME triage -> harm-line -> act/ask path
            if self.glassbox is not None:
                self.glassbox.log("trigger_fired", {"loop_id": loop.get("id"), "task": task,
                                                     "decision": decision["decision"]})
            out.append({"loop_id": loop.get("id"), "task": task, **decision})
        return out

    # ---- steps ----
    def _triage(self, event: Event) -> bool:
        return self.triage.actionable(event.text)   # Room 1: high-recall bouncer, zero smart calls in stub

    def _raise_to_human(self, event: Event, reason: str) -> None:
        if self.glassbox is not None:
            self.glassbox.log("ask_human", {"event_id": event.id, "text": event.text, "reason": reason})

    def _record(self, event: Event, decision: str, reason: str,
                category: str = "", memory_forced: bool = False) -> None:
        if memory_forced:
            self.memory_forced_asks += 1
        if self.glassbox is not None:
            self.glassbox.log("decision", {"event_id": event.id, "text": event.text, "decision": decision,
                                           "category": category, "reason": reason, "memory_forced": memory_forced})
            if memory_forced:
                self.glassbox.log("memory_forced_ask",
                                  {"event_id": event.id, "text": event.text, "reason": reason})
        if self.scorecard is not None:
            self.scorecard.record_decision(decision, event.id, reason)
