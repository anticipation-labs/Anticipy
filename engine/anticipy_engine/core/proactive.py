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

from ..channels.text import TextChannel
from ..proactive.harm import HarmLine
from ..proactive.triage import Triage
from ..proactive.trigger import TriggerWatcher
from .bus import Bus
from .envelopes import Event, EventSource, Goal, GoalState, Job, now_ts
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
        channel=None,
        user_contact: str = "+10000000000",
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
        self.channel = channel or TextChannel() # Room 4: where the ask goes out (Twilio live/mock)
        self.user_contact = user_contact        # the user's number/handle for asks (set in prod)
        self.pending = {}                       # ask_id -> {goal_id, action, reason} (awaiting reply)
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

        # 4) act (JUST DO IT) / ask (PAUSE before harm, send the ask; Room 4 round-trip)
        goal_id = ask_id = None
        if not verdict.detrimental:
            goal = await self.orchestrator.start_goal(Goal(intent=event.text, description=event.text))
            goal_id = goal.id
            decision = "act"
        else:
            decision = "ask"
            goal = Goal(intent=event.text, description=event.text, state=GoalState.waiting)
            self.orchestrator.store.save(goal)        # persist the PAUSED goal (NOT executed)
            goal_id = goal.id
            ask_id = self._send_ask(goal, event.text, verdict.reason)
            self._raise_to_human(event, verdict.reason)
            # HARD SUB-GATE: a detrimental goal is WAITING — no step executed until approved (no silent harm).
            assert self.orchestrator.store.load(goal_id).state == GoalState.waiting, "detrimental action must be paused"
        self._record(event, decision, verdict.reason, category=verdict.category,
                     memory_forced=verdict.memory_forced)
        return {"decision": decision, "category": verdict.category, "reason": verdict.reason,
                "detrimental": verdict.detrimental, "memory_forced": verdict.memory_forced,
                "goal_id": goal_id, "ask_id": ask_id}

    def _send_ask(self, goal: Goal, action: str, reason: str) -> str:
        """Send the ask over the channel and register it pending a reply."""
        ask_id = goal.id
        msg = (f"Anticipy wants to: {action}\nWhy it paused: {reason}\nReply YES to proceed, NO to skip.")
        sent = self.channel.send(self.user_contact, msg)
        self.pending[ask_id] = {"goal_id": goal.id, "action": action, "reason": reason}
        if self.glassbox is not None:
            self.glassbox.log("ask_sent", {"ask_id": ask_id, "goal_id": goal.id, "channel": self.channel.name,
                                           "to": self.user_contact, "sent": bool(sent.get("sent"))})
        return ask_id

    async def resolve_ask(self, ask_id: str, approved: bool) -> dict:
        """The reply round-trip: YES resumes the EXACT paused goal to done; NO drops it and writes
        the decline to memory (so Room 5 can suppress that action-type next time)."""
        p = self.pending.pop(ask_id, None)
        if p is None:
            return {"ask_id": ask_id, "resolved": False, "reason": "unknown or already-resolved ask"}
        goal = self.orchestrator.store.load(p["goal_id"])
        if approved:
            goal = await self.orchestrator.start_goal(goal)   # resume the EXACT paused goal -> run to done
            if self.glassbox is not None:
                self.glassbox.log("ask_approved", {"ask_id": ask_id, "goal_id": goal.id, "state": goal.state.value})
            return {"ask_id": ask_id, "approved": True, "goal_id": goal.id, "state": goal.state.value}
        goal.state = GoalState.failed                          # declined -> drop the paused goal
        self.orchestrator.store.save(goal)
        await self.bus.submit_job(Job(intent="write_memory",
                                      args={"text": f"User declined to: {p['action']}", "kind": "history"}))
        if self.glassbox is not None:
            self.glassbox.log("ask_declined", {"ask_id": ask_id, "goal_id": goal.id, "action": p["action"]})
        return {"ask_id": ask_id, "approved": False, "goal_id": goal.id, "declined_action": p["action"]}

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
