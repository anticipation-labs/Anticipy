"""The proactive engine — the decider. ACT-FIRST, ask-only-before-harm.

Loop over Events:
  1. triage (Room 1; cheap, local, NO smart model): drop the ~99% that isn't actionable.
  1.5 the DECIDER (Room 1.5; cheap model, LIVE ONLY — None in stub): did the person
     actually COMMIT? SILENT drops the event; ASK forces the ask path; ACT defers to
     the harm-line. One-way: it can never turn the harm-line's ASK into an ACT.
     UNAVAILABLE (no model read — quota/transport outage, ledger F7) defers the event
     past the quota window for a bounded trigger_tick retry; exhausted retries drop
     it with an honest reason. An unread line never acts.
  2. read memory context (cheap worker) for the harm-line's gray middle.
  3. the HARM-LINE (Room 2): is this detrimental? confident-no -> ACT (hand a Goal to the
     orchestrator and DO IT); yes or UNSURE -> ASK (pause; never execute until approved).
  4. record every decision (+ category, memory_forced) to the glass-box and scorecard.

The harm-line is deterministic + inspectable (proactive/harm.py); the smart model is used
only when a decision is genuinely hard. Triage cues live in proactive/triage.py.
(GateConfig is a vestigial knob bag from the skeleton — retained for construction compat.)
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from ..channels.text import TextChannel
from ..proactive.budget import AnnoyanceBudget
from ..proactive.debounce import AskDebounce
from ..proactive.decider import (
    ASK as DECIDER_ASK,
    Decider,
    SILENT as DECIDER_SILENT,
    UNAVAILABLE as DECIDER_UNAVAILABLE,
)
from ..proactive.harm import HarmLine
from ..proactive.triage import Triage
from ..proactive.trigger import TriggerWatcher
from .bus import Bus
from .envelopes import Event, EventSource, Goal, GoalState, Job, now_ts
from .gateway import PROVIDER_OPENROUTER, ModelGateway
from .orchestrator import Orchestrator

# Room 1.5 outage handling (ledger F7): a per-minute quota window (the live brain is
# Gemini free tier) resets within 60s, so one deferral must outlast it; the second
# retry covers a burst where the retry tick itself re-exhausts the window. Beyond
# that the engine fails toward silence, honestly labeled — never act on an unread line.
DECIDER_RETRY_SECONDS = 75.0
DECIDER_MAX_RETRIES = 2


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
        decider=None,
        deferred_path=None,
    ) -> None:
        self.bus = bus
        self.gateway = gateway
        self.orchestrator = orchestrator
        self.glassbox = glassbox
        self.scorecard = scorecard
        self.config = config or GateConfig()
        self.triage = Triage(gateway=gateway)   # Room 1: the bouncer (cheap, first, free in stub)
        # Room 1.5: cheap-model commitment judgment — LIVE ONLY. Stub mode gets no
        # decider so the suite and stub-tier evals stay deterministic. One-way safe:
        # it may move a decision toward SILENT/ASK, never an ASK into ACT (see on_event).
        self.decider = decider if decider is not None else (
            Decider(gateway, glassbox=glassbox)
            if gateway.provider == PROVIDER_OPENROUTER else None)
        self.harm = HarmLine()                  # Room 2: act-first, ask-only-before-harm
        self.trigger = TriggerWatcher()         # Room 3: time + open-loop watcher (fire-once)
        self.channel = channel or TextChannel() # Room 4: where the ask goes out (Twilio live/mock)
        self.user_contact = user_contact        # the user's number/handle for asks (set in prod)
        self.pending = {}                       # ask_id -> {goal_id, action, reason, category} (awaiting reply)
        self.budget = AnnoyanceBudget()         # Room 5: cap proactive interruptions; learn from declines
        self.debounce = AskDebounce()           # Room 2.6: ambient money-transfer asks wait out the retraction
        self.memory_forced_asks = 0             # Deferred-2: asks forced by weak memory confidence
        self.decider_deferred = []              # Room 1.5 outage queue: [{event, due}] awaiting a retry tick
        self._decider_attempts = {}             # event.id -> deferrals so far (capped at DECIDER_MAX_RETRIES)
        # Outage-queue persistence (ledger F7 residual / D16 family): an engine restart
        # during a quota window must not eat the lines the decider never read. LIVE-ONLY
        # on both ends — a stub engine has no decider, and an unread line must never
        # re-enter the pipeline without one, so stub boots neither restore nor touch the
        # file (it waits for the next live boot). No path (the default) = no IO at all.
        self._deferred_path = Path(deferred_path) if deferred_path else None
        if self._deferred_path is not None and self.decider is not None:
            self._restore_deferred()

    async def on_event(self, event: Event, now: Optional[float] = None) -> dict:
        now = now if now is not None else now_ts()
        # 0) Room 2.6 — while a money-transfer ask is held, the very next utterances can
        #    take it back ("scratch that", "don't send him anything"): the retraction
        #    consumes this event and the held ask dies silently (on money the engine
        #    fails toward silence, never act). Surviving holds tick down; an exhausted
        #    window flushes the SAME ask, late.
        if self.debounce.has_held():
            cancelled = self.debounce.cancel_on_retraction(event.text, now)
            if cancelled:
                for h in cancelled:
                    goal = self.orchestrator.store.load(h["goal_id"])
                    goal.state = GoalState.failed
                    self.orchestrator.store.save(goal)
                    if self.glassbox is not None:
                        self.glassbox.log("ask_retracted", {"goal_id": h["goal_id"],
                                                            "action": h["action"],
                                                            "retraction": event.text})
                    await self.bus.submit_job(Job(intent="write_memory",
                                                  args={"text": f"User retracted: {h['action']}",
                                                        "kind": "history"}))
                self._record(event, "ignore", "retraction of a just-held money ask -> silent")
                return {"decision": "ignore", "triaged": False, "goal_id": None,
                        "retracted_goal_ids": [h["goal_id"] for h in cancelled]}
            for h in self.debounce.event_passed(now):
                self._flush_held(h)

        # 1) triage — cheap, local, no smart model; most events die here (Room 1)
        if not self._triage(event):
            self._record(event, "ignore", "triaged out (not actionable)")
            return {"decision": "ignore", "triaged": True, "goal_id": None}

        # 1.5) the decider (Room 1.5; LIVE ONLY, None in stub) — did the person actually
        #      COMMIT? SILENT kills the event here (no memory read, no goal, no ask).
        #      ASK forces the ask path below even when the harm-line reads safe. ACT
        #      defers to the harm-line — the decider never overrides an ASK into ACT.
        decider_word = None
        if self.decider is not None:
            decider_word = await self.decider.decide(event.text)
            if decider_word == DECIDER_UNAVAILABLE:
                # No model read happened (quota/transport outage, ledger F7). Deafness
                # must not masquerade as judgment: defer the event past the quota
                # window for a bounded retry; when retries exhaust, drop it with an
                # honest reason. Either way, an unread line NEVER acts.
                attempt = self._decider_attempts.get(event.id, 0)
                if attempt < DECIDER_MAX_RETRIES:
                    self._decider_attempts[event.id] = attempt + 1
                    retry_at = now + DECIDER_RETRY_SECONDS
                    self.decider_deferred.append({"event": event, "due": retry_at})
                    self._persist_deferred()
                    if self.glassbox is not None:
                        self.glassbox.log("decider_deferred",
                                          {"event_id": event.id, "text": event.text,
                                           "attempt": attempt + 1, "retry_at": retry_at})
                    self._record(event, "deferred",
                                 "decider unavailable (no model read) -> deferred for retry")
                    return {"decision": "deferred", "triaged": True, "decider": decider_word,
                            "goal_id": None, "retry_at": retry_at}
                self._decider_attempts.pop(event.id, None)
                self._record(event, "ignore",
                             "decider unavailable after retries -> fail silent "
                             "(never act on an unread line)")
                return {"decision": "ignore", "triaged": True, "decider": decider_word,
                        "goal_id": None}
            self._decider_attempts.pop(event.id, None)   # a real verdict arrived
            if decider_word == DECIDER_SILENT:
                self._record(event, "ignore", "decider: not a real commitment -> silent")
                return {"decision": "ignore", "triaged": True, "decider": decider_word,
                        "goal_id": None}

        # 2) read memory context (the harm-line uses it for the gray middle; cheap worker, no smart)
        ctx = await self.bus.submit_job(Job(intent="read_context", args={"about": event.text}))
        mem = ctx.output or {}

        # 3) THE HARM-LINE (Room 2) — act-first: is this detrimental? deterministic; fail-safe to ask.
        verdict = self.harm.assess(event.text, mem)

        # 4) act (JUST DO IT) / ask (PAUSE before harm, send the ask; Room 4 round-trip)
        goal_id = ask_id = None
        description = self._goal_description(event)
        # one-way merge: ACT requires BOTH the harm-line safe AND (no decider or decider ACT)
        forced_ask = decider_word == DECIDER_ASK and not verdict.detrimental
        reason = ("decider: binding or half-formed -> confirm before acting"
                  if forced_ask else verdict.reason)
        if not verdict.detrimental and not forced_ask:
            goal = await self.orchestrator.start_goal(Goal(intent=event.text, description=description))
            goal_id = goal.id
            decision = "act"
        else:
            goal = Goal(intent=event.text, description=description, state=GoalState.waiting)
            self.orchestrator.store.save(goal)        # persist the PAUSED goal (NOT executed)
            goal_id = goal.id
            # Room 5: cap PROACTIVE (engine-initiated) interruptions + suppress declined types.
            # User-initiated asks are never suppressed (the user is present and asked).
            proactive = event.source == EventSource.system
            suppress = self.budget.suppressed(event.text, verdict.category, now) if proactive else None
            if suppress:
                decision = "suppressed"   # not executed AND not asked -> no silent harm, no annoyance
                if self.glassbox is not None:
                    self.glassbox.log("suppressed", {"goal_id": goal_id, "category": verdict.category,
                                                     "reason": suppress, "action": event.text})
            elif self.debounce.should_hold(event.text, verdict.category, event.meta):
                # Room 2.6: a money TRANSFER command heard in ambient speech waits one
                # breath — people retract these seconds later. Goal stays paused; the
                # ask is sent only if no retraction arrives within the window.
                decision = "held"
                self.debounce.hold(goal_id, event.text, reason, verdict.category, now)
                if self.glassbox is not None:
                    self.glassbox.log("ask_held", {"goal_id": goal_id, "category": verdict.category,
                                                   "action": event.text})
            else:
                decision = "ask"
                ask_id = self._send_ask(goal, event.text, reason, verdict.category)
                self._raise_to_human(event, reason)
                if proactive:
                    self.budget.record_interruption(now)
            # HARD SUB-GATE: a paused goal is WAITING — no step executed until approved (no silent harm).
            assert self.orchestrator.store.load(goal_id).state == GoalState.waiting, "paused action must not execute"
        self._record(event, decision, reason, category=verdict.category,
                     memory_forced=verdict.memory_forced)
        return {"decision": decision, "category": verdict.category, "reason": reason,
                "detrimental": verdict.detrimental, "memory_forced": verdict.memory_forced,
                "decider": decider_word, "goal_id": goal_id, "ask_id": ask_id}

    def _restore_deferred(self) -> None:
        """Reload the outage queue written by a previous live engine (F7/D16): each
        entry re-enters the FULL pipeline at its due tick exactly as if the process
        had never died — the attempt count rides along so the DECIDER_MAX_RETRIES
        bound holds ACROSS restarts. Any failure here fails toward silence: boot
        with an empty queue, log honestly, set the unreadable file aside."""
        p = self._deferred_path
        if not p.exists():
            return
        try:
            restored, attempts = [], {}
            for e in json.loads(p.read_text()):
                event = Event.model_validate(e["event"])
                restored.append({"event": event, "due": float(e["due"])})
                attempts[event.id] = int(e["attempt"])
            self.decider_deferred = restored
            self._decider_attempts.update(attempts)
            if self.glassbox is not None:
                self.glassbox.log("decider_deferred_restored",
                                  {"count": len(restored), "path": str(p)})
        except Exception as exc:
            self.decider_deferred = []
            self._decider_attempts = {}
            try:
                p.rename(p.with_suffix(p.suffix + ".corrupt"))
            except OSError:
                pass
            if self.glassbox is not None:
                self.glassbox.log("decider_deferred_restore_failed",
                                  {"path": str(p), "error": str(exc)})

    def _persist_deferred(self) -> None:
        """Atomically snapshot the outage queue on every mutation. A disk failure
        must never break the live decision path — log it and carry on in memory."""
        if self._deferred_path is None or self.decider is None:
            return
        p = self._deferred_path
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(
                [{"event": d["event"].model_dump(mode="json"), "due": d["due"],
                  "attempt": self._decider_attempts.get(d["event"].id, 0)}
                 for d in self.decider_deferred], indent=2)
            tmp = p.with_suffix(p.suffix + ".tmp")
            tmp.write_text(payload)
            os.replace(tmp, p)
        except OSError as exc:
            if self.glassbox is not None:
                self.glassbox.log("decider_deferred_persist_failed",
                                  {"path": str(p), "error": str(exc)})

    def _flush_held(self, h: dict) -> None:
        """A held money ask survived its retraction window — send the SAME ask, late."""
        goal = self.orchestrator.store.load(h["goal_id"])
        ask_id = self._send_ask(goal, h["action"], h["reason"], h["category"])
        if self.glassbox is not None:
            self.glassbox.log("ask_flushed", {"ask_id": ask_id, "goal_id": h["goal_id"],
                                              "action": h["action"]})

    def _send_ask(self, goal: Goal, action: str, reason: str, category: str = "") -> str:
        """Send the ask over the channel and register it pending a reply."""
        ask_id = goal.id
        msg = (f"Anticipy wants to: {action}\nWhy it paused: {reason}\nReply YES to proceed, NO to skip.")
        sent = self.channel.send(self.user_contact, msg)
        self.pending[ask_id] = {"goal_id": goal.id, "action": action, "reason": reason, "category": category}
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
        self.budget.record_decline(p["action"], p.get("category", ""))   # Room 5: suppress this type next time
        await self.bus.submit_job(Job(intent="write_memory",
                                      args={"text": f"User declined to: {p['action']}", "kind": "history"}))
        if self.glassbox is not None:
            self.glassbox.log("ask_declined", {"ask_id": ask_id, "goal_id": goal.id, "action": p["action"]})
        return {"ask_id": ask_id, "approved": False, "goal_id": goal.id, "declined_action": p["action"]}

    async def trigger_tick(self, now: Optional[float] = None) -> list:
        """Room 3: watch the commitment ledger against the clock. Each due/elapsed loop fires a
        proactive follow-up through the SAME harm-line path (NO new input event), exactly once.
        A TIME-GROUNDED reminder (remind_ts set at capture) is a NOTIFY — tell the user, don't
        open a goal or a YES/NO ask — unless its text is detrimental, which keeps the ask path."""
        now = now if now is not None else now_ts()
        # Room 2.6 time flush: the stream went quiet, so a held money ask that outlived
        # its retraction window goes out now instead of waiting for more speech.
        for h in self.debounce.due(now):
            self._flush_held(h)
        # Room 1.5 outage retries (ledger F7): events deferred because the decider had
        # no model read re-enter the FULL pipeline once their window elapses (capture
        # already holds the line; only the decision was deferred). A retry may defer
        # again — the attempt cap in on_event bounds it.
        due_deferred = [d for d in self.decider_deferred if d["due"] <= now]
        if due_deferred:
            self.decider_deferred = [d for d in self.decider_deferred if d["due"] > now]
            # persist BEFORE re-entry: a crash mid-retry can only LOSE these events
            # (fail toward silence), never restore-and-replay one that already acted
            self._persist_deferred()
            for d in due_deferred:
                redo = await self.on_event(d["event"], now=now)
                if self.glassbox is not None:
                    self.glassbox.log("decider_retry", {"event_id": d["event"].id,
                                                        "decision": redo.get("decision")})
        res = await self.bus.submit_job(Job(intent="list_open_loops", args={}))
        loops = (res.output or {}).get("loops", [])
        fired = self.trigger.tick(loops, now)
        out = []
        for loop in fired:
            task = loop.get("task") or loop.get("text") or "your commitment"
            if loop.get("remind_ts") is not None:
                decision = await self._fire_reminder(loop, task, now)
            else:
                ev = Event(source=EventSource.system, text=f"Follow up on your commitment: {task}")
                decision = await self.on_event(ev, now=now)   # SAME triage -> harm-line -> act/ask; budget applies
            if self.glassbox is not None:
                self.glassbox.log("trigger_fired", {"loop_id": loop.get("id"), "task": task,
                                                     "decision": decision["decision"]})
            out.append({"loop_id": loop.get("id"), "task": task, **decision})
        return out

    async def _fire_reminder(self, loop: dict, task: str, now: float) -> dict:
        """A due reminder fires as a NOTIFY: re-gate the loop text on the harm-line; only a
        safe/reversible reminder goes straight out over the channel (budget-capped, counted
        as an interruption) and the loop is marked waiting. Detrimental text falls back to
        the ask round-trip — money/sends never fire silently."""
        ctx = await self.bus.submit_job(Job(intent="read_context", args={"about": task}))
        verdict = self.harm.assess(task, ctx.output or {})
        if verdict.detrimental:
            ev = Event(source=EventSource.system, text=f"Follow up on your commitment: {task}")
            return await self.on_event(ev, now=now)
        suppress = self.budget.suppressed(task, verdict.category, now)
        if suppress:
            if self.glassbox is not None:
                self.glassbox.log("suppressed", {"loop_id": loop.get("id"), "category": verdict.category,
                                                 "reason": suppress, "action": task})
            return {"decision": "suppressed", "category": verdict.category, "reason": suppress,
                    "detrimental": False, "memory_forced": False, "goal_id": None, "ask_id": None}
        sent = self.channel.send(self.user_contact, f"Reminder: {task}")
        self.budget.record_interruption(now)
        await self.bus.submit_job(Job(intent="mark_loop",
                                      args={"id": loop.get("id"), "status": "waiting"}))
        if self.glassbox is not None:
            self.glassbox.log("notify", {"loop_id": loop.get("id"), "task": task,
                                         "channel": self.channel.name, "to": self.user_contact,
                                         "sent": bool(sent.get("sent"))})
        if self.scorecard is not None:
            self.scorecard.record_decision("notify", loop.get("id") or "",
                                           "time-grounded reminder fired -> notify")
        return {"decision": "notify", "category": verdict.category,
                "reason": "time-grounded reminder fired -> notify (no ask)",
                "detrimental": False, "memory_forced": False, "goal_id": None, "ask_id": None}

    # ---- steps ----
    def _goal_description(self, event: Event) -> str:
        meta = event.meta or {}
        context_keys = (
            "observed_at",
            "capture_started_at",
            "transcript_offset_seconds",
            "transcript_end_offset_seconds",
            "timezone",
        )
        lines = [f"{key}={meta[key]}" for key in context_keys if meta.get(key) is not None]
        if not lines:
            return event.text
        return event.text + "\n\nCAPTURE_CONTEXT:\n" + "\n".join(lines)

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
