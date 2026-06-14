"""ControlCore — assembles the whole brain and exposes a tiny driving surface.

One object that wires the bus, the model gateway, the glass-box, the scorecard,
the stub workers, the orchestrator, and the proactive engine together. The HTTP
layer and the tests drive it through `feed()` and `resume()`.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import hashlib
from pathlib import Path

from .browser_link import BrowserLink
from .bus import Bus
from .env import load_local_env
from .envelopes import Event, EventSource, Goal, GoalState, Job
from .gateway import ModelGateway, PROVIDER_OPENROUTER
from .glassbox import GlassBox
from .native_bridge_link import NativeBridgeLink
from .orchestrator import Approver, Orchestrator
from .proactive import ProactiveEngine
from .scorecard import Scorecard
from .store import GoalStore
from .workers import ChannelStub, ChannelWorker, MemoryWorker
from ..channels.call import CallChannel
from ..agent import site_hints
from ..channels.text import TextChannel
from ..hands import ApiHand, BrowserHand, MODE_LIVE, MODE_MOCK, NotFundedError
from ..hands.api_hand import INTENT_MAP
from ..live_memory.brain import LiveMemoryBrain
from ..memory.store import Memory, is_active_open_loop
from ..owner_mode import OwnerIngestResult, OwnerMode, OwnerObservedLine, OwnerTaskCard
from ..owner_onboarding import OwnerOnboardingIn, build_onboarding_plan


def _base(data_dir=None) -> Path:
    return Path(data_dir or os.environ.get("ANTICIPY_DATA_DIR", ".anticipy-data")).expanduser()


def _card_step_receipts(steps: list[dict]) -> list[dict]:
    """Human-readable receipts extracted from executed goal steps."""
    receipts: list[dict] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        args = step.get("args") or {}
        if not isinstance(args, dict):
            continue
        resolution = args.get("memory_resolution")
        if isinstance(resolution, dict):
            receipts.append({
                "type": "memory_resolution",
                "site": resolution.get("site"),
                "item": resolution.get("item"),
                "source_ref": resolution.get("source_ref"),
                "matched_hints": resolution.get("matched_hints") or [],
            })
        if step.get("intent") == "browse_task":
            result = step.get("result") or {}
            proof = result.get("proof") or {}
            output = result.get("output") or {}
            if isinstance(result, dict) and result.get("status") == "success" and isinstance(proof, dict):
                receipts.append({
                    "type": "browser_receipt",
                    "url": output.get("final_url") or proof.get("url") or args.get("url"),
                    "answer": output.get("answer") or "",
                    "screenshot": bool(proof.get("screenshot")),
                    "commerce_recipe": bool(proof.get("commerce_recipe") or output.get("commerce_recipe")),
                })
    return receipts


def _steps_create_open_loop(steps: list[dict]) -> bool:
    for step in steps:
        if not isinstance(step, dict) or step.get("intent") != "write_memory":
            continue
        args = step.get("args") or {}
        if isinstance(args, dict) and args.get("kind") == "open_loop":
            return True
    return False


def _status_for_open_loop(state: str) -> str:
    return "waiting" if state == "waiting" else "open" if state == "open" else state


def _owner_card_dedupe_key(card: OwnerTaskCard) -> str:
    """Stable replay key for the same owner utterance and shaped action.

    Pressing Go twice, replaying a listening transcript, or uploading the same
    transcript must not create a second external action or approval ask. Exact
    source text is deliberately part of the key: a materially different phrasing
    gets a fresh card, while an accidental replay lands on the durable record.
    """
    raw = "|".join([
        re.sub(r"\s+", " ", (card.source_text or "").strip().lower()),
        card.route,
        card.action,
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


_CONNECT_TOOL_BY_IDENTIFIER = {
    "calendar": "GoogleCalendar.CreateEvent",
    "google_calendar": "GoogleCalendar.CreateEvent",
    "gmail": "Gmail.SendEmail",
    "gmail.compose": "Gmail.WriteDraftEmail",
    "gmail.send": "Gmail.SendEmail",
    "gmail.threads": "Gmail.ListThreads",
}


def _connect_tool(fields: dict) -> str | None:
    identifier = str(fields.get("identifier") or "").strip().lower()
    name = str(fields.get("name") or "").strip().lower()
    if identifier in _CONNECT_TOOL_BY_IDENTIFIER:
        return _CONNECT_TOOL_BY_IDENTIFIER[identifier]
    if "gmail" in name:
        return "Gmail.SendEmail"
    if "calendar" in name:
        return "GoogleCalendar.CreateEvent"
    if "doc" in name:
        return "GoogleDocs.GetDocumentById"
    return INTENT_MAP.get(identifier)


class GatedApprover(Approver):
    """Human-path stub that also propagates the gate's approval flag onto the
    step args only after the owner has approved. Product core uses this as a
    lower safety rail: a planner-level high-risk step cannot auto-approve itself
    just because the top-level proactive gate thought the request was safe."""

    def __init__(self, approve: bool = False) -> None:
        self._approve = approve

    async def approve(self, goal, step) -> bool:
        if step.args.get("approved") is True:
            return True
        if (goal.proof or {}).get("owner_approved") is True:
            step.args["approved"] = True
            return True
        if self._approve:
            step.args["approved"] = True
        return self._approve


class ControlCore:
    def __init__(self, data_dir=None) -> None:
        load_local_env()  # make .env.local keys (Arcade, etc.) available
        base = _base(data_dir)
        self.data_dir = base
        self.browser_link = BrowserLink()
        self.glassbox = GlassBox(base / "glassbox.jsonl")
        self.scorecard = Scorecard(base / "scorecard.jsonl")
        self.bus = Bus(glassbox=self.glassbox)
        self.gateway = ModelGateway(endpoint=os.environ.get("ANTICIPY_MODEL_ENDPOINT"))

        # REAL memory: four drawers + the live memory agent, on the frozen contract.
        self.memory = Memory(data_dir=base)
        self.live_memory = LiveMemoryBrain(self.memory, gateway=self.gateway, scorecard=self.scorecard)
        self.owner_mode = OwnerMode()
        self.memory_worker = MemoryWorker(self.live_memory)

        # Browse hints: the agent's per-host facts are DATA (packaged seed + this
        # engine's learned overlay). Explicit wiring like pending_path/deferred_path
        # below — agent code never reads env or invents a path. The store is
        # process-global, so the last constructed core owns it (env-var semantics).
        site_hints.configure(base / "site_hints.json")

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
            # Same env discipline as ApiHand: mock default, live only explicit.
            # ANTICIPY_BROWSER_HAND_MODE narrows the knob for integrations that
            # need the real-WS browser leg while the API hand stays mock
            # (scripts/hands_loop.sh); it never widens a live default.
            mode=os.environ.get("ANTICIPY_BROWSER_HAND_MODE") or hands_mode,
        )
        self.channel = ChannelStub()  # send_email only — the real ChannelWorker owns text/call
        # Real channels (mock by default; live only with ANTICIPY_CHANNELS_MODE=live +
        # Twilio env). ONE TextChannel instance shared with the proactive ask path so
        # there is a single .sent audit trail.
        self.text_channel = TextChannel()
        self.call_channel = CallChannel()
        self.channel_worker = ChannelWorker(text=self.text_channel, call=self.call_channel,
                                            contact=self._user_contact)
        # Real workers register LAST so they own any intent a stub also claims; the real
        # MemoryWorker takes over read_context + write_memory, ChannelWorker send_text/call.
        for w in (self.channel, self.api_hand, self.browser_hand, self.memory_worker,
                  self.channel_worker):
            self.bus.register_worker(w)

        self.store = GoalStore(data_dir=base)
        # No-API app intents reroute to the browser hand via the orchestrator's
        # EXISTING reroute path (config, not a code change).
        alternates = {"post_to_x": "browse_task", "create_event": "browse_task", "message": "browse_task"}
        self.orchestrator = Orchestrator(
            self.bus, self.gateway, self.store, glassbox=self.glassbox, scorecard=self.scorecard,
            alternates=alternates, approver=GatedApprover(False), memory_context=self._mem_ctx,
        )
        self.proactive = ProactiveEngine(
            self.bus, self.gateway, self.orchestrator, glassbox=self.glassbox, scorecard=self.scorecard,
            channel=self.text_channel, user_contact=self._user_contact(),
            deferred_path=base / "decider_deferred.json",
            pending_path=base / "pending_asks.json",
        )
        # Owner cards awaiting a YES/NO: goal_id -> {record_path, card_id}, so resolve()
        # can write the resolved goal's outcome back onto the durable card record.
        # In-memory by design — the durable linkage survives in the record's
        # execution.goal_id field and resolve() falls back to scanning for it (F18).
        self._owner_card_goals: dict = {}
        # Per-line press-go locks: approve_remembered's load-check-build-drive must be
        # ATOMIC per line so two concurrent presses of the SAME line cannot both pass the
        # "prior goal not done yet" check and double-fire a real write. Keyed on the stable
        # goal_id derived from line_id; created under _press_go_locks_guard so the registry
        # itself is race-free.
        self._press_go_locks: dict[str, asyncio.Lock] = {}
        self._press_go_locks_guard = asyncio.Lock()

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

    @staticmethod
    def _user_contact() -> str:
        """The owner's reachable number — ONLY in live channel mode. Everywhere else
        (suite, stub/mock persona runs) the placeholder stands, so run artifacts and
        glassbox dumps never carry the real number (B8 fixed engine-side, scoped)."""
        if os.environ.get("ANTICIPY_CHANNELS_MODE") == "live":
            return (os.environ.get("OWNER_PHONE") or os.environ.get("ALERT_PHONE")
                    or os.environ.get("TWILIO_TO") or "+10000000000")
        return "+10000000000"

    @staticmethod
    def _owner_event_enabled() -> bool:
        return (os.environ.get("ANTICIPY_OWNER_INGEST", "") or "").strip().lower() in {"1", "true", "yes", "on"}

    def channel_status(self) -> dict:
        """Public-safe readiness for owner text/call channels.

        This exposes mode and missing setup only; never the phone number or Twilio
        secrets. The send path itself still decides live/mock at call time.
        """
        mode = (os.environ.get("ANTICIPY_CHANNELS_MODE") or "mock").strip().lower()
        twilio_configured = self.text_channel.configured() and self.call_channel.configured()
        owner_contact_configured = bool(
            os.environ.get("OWNER_PHONE") or os.environ.get("ALERT_PHONE") or os.environ.get("TWILIO_TO")
        )
        try:
            inbound_poll_seconds = float(os.environ.get("ANTICIPY_INBOUND_POLL_SECONDS", "15") or 0)
        except ValueError:
            inbound_poll_seconds = 0.0
        if mode != "live":
            status = "ready_to_enable" if twilio_configured and owner_contact_configured else "mock"
            label = (
                "Twilio and owner phone configured; live mode is off"
                if status == "ready_to_enable"
                else "mock"
            )
        elif not twilio_configured:
            status = "missing_twilio"
            label = "missing Twilio credentials"
        elif not owner_contact_configured:
            status = "missing_owner_contact"
            label = "missing owner phone"
        else:
            status = "live_ready"
            label = "live text/call ready"
        if mode != "live":
            inbound_status = status
            inbound_label = label
        elif not twilio_configured:
            inbound_status = "missing_twilio"
            inbound_label = "missing Twilio credentials"
        elif not owner_contact_configured:
            inbound_status = "missing_owner_contact"
            inbound_label = "missing owner phone"
        elif inbound_poll_seconds <= 0:
            inbound_status = "disabled"
            inbound_label = "inbound reply polling disabled"
        else:
            inbound_status = "live_ready"
            inbound_label = "inbound YES/NO replies active"
        if status == "live_ready" and inbound_status != "live_ready":
            label = f"{label}; {inbound_label}"
        return {
            "mode": "live" if mode == "live" else "mock",
            "status": status,
            "label": label,
            "twilio_configured": twilio_configured,
            "owner_contact_configured": owner_contact_configured,
            "text": status,
            "call": status,
            "inbound": {
                "status": inbound_status,
                "label": inbound_label,
                "poll_seconds": inbound_poll_seconds if inbound_poll_seconds > 0 else 0,
            },
        }

    def _sync_owner_loop_status(self, card_id: str, state: str) -> None:
        """Keep the memory ledger aligned with the visible owner card state."""
        status = _status_for_open_loop(state)
        for item in self.memory.open_loops.all():
            if item.fields.get("owner_card_id") != card_id:
                continue
            if item.status == status and item.fields.get("owner_card_state") == state:
                return
            item.status = status
            item.fields = {**item.fields, "owner_card_state": state}
            self.memory.open_loops.update(item)
            return

    def _sync_open_loop_item_status(self, item_id: str, state: str, *, card_id: str | None = None) -> bool:
        item = self.memory.open_loops.get(item_id)
        if item is None:
            return False
        status = _status_for_open_loop(state)
        if item.status == status and item.fields.get("owner_card_state") == state:
            return True
        fields = {**item.fields, "owner_card_state": state}
        if card_id:
            fields["resolved_by_owner_card_id"] = card_id
        item.status = status
        item.fields = fields
        self.memory.open_loops.update(item)
        return True

    def _sync_captured_loop_from_record(self, record: dict, state: str) -> None:
        owner_card = record.get("owner_card") if isinstance(record, dict) else None
        if not isinstance(owner_card, dict):
            return
        for proof in owner_card.get("proof") or []:
            if not isinstance(proof, dict) or proof.get("type") != "capture_memory_status":
                continue
            memory_id = proof.get("memory_id")
            if memory_id and self._sync_open_loop_item_status(memory_id, state, card_id=record.get("id")):
                proof["status"] = _status_for_open_loop(state)

    def _sync_capture_result_status(self, capture_result: dict | None, state: str,
                                    *, card_id: str | None = None) -> None:
        item = (capture_result or {}).get("item")
        if getattr(item, "kind", None) == "open_loop":
            self._sync_open_loop_item_status(item.id, state, card_id=card_id)

    @staticmethod
    def _has_external_context(ctx_output: dict | None, source_text: str) -> bool:
        """True when memory has context beyond the line just captured."""
        context = (ctx_output or {}).get("context") or {}
        source = (source_text or "").strip().lower()
        stop = {
            "that", "this", "thing", "things", "one", "item", "product",
            "cart", "buy", "buying", "checkout", "find", "found", "put",
            "add", "grab", "same", "still", "later", "dont", "don't",
            "with", "from", "into", "onto", "please", "before", "after",
        }
        source_terms = {t for t in re.findall(r"[a-z0-9]+", source)
                        if len(t) > 3 and t not in stop}
        for key in ("profile", "history", "derived", "open_loops"):
            for item in context.get(key, []) or []:
                text = str(item).strip().lower()
                if not text or text == source:
                    continue
                item_terms = {t for t in re.findall(r"[a-z0-9]+", text)
                              if len(t) > 3 and t not in stop}
                if len(source_terms & item_terms) >= 2:
                    return True
        return False

    async def feed(self, source: str, text: str, meta: dict | None = None) -> dict:
        meta = meta or {}
        # Owner-lane honesty seam: with ANTICIPY_OWNER_INGEST=1 the same /event pipe the
        # persona runner already drives goes through the owner card path instead, so the
        # unchanged runner+scorer measure owner cards with worst-persona honesty. The
        # owner_ingest_execute guard keeps execute_actions card feeds on the proactive
        # path (no recursion back into the owner lane).
        if self._owner_event_enabled() and not meta.get("owner_ingest_execute"):
            return await self.owner_event(source, text, meta)
        if not meta.get("owner_ingest_execute"):
            # owner-lane lines were already captured (with owner metadata) by
            # owner_ingest before the spine ran them (F17) — never capture twice
            self.live_memory.capturer.capture(text, source=source, meta=meta)  # CAPTURE before anything acts
        ev = Event(source=EventSource(source), text=text, meta=meta)
        await self.bus.publish(ev)                 # log the event to the glass-box
        return await self.proactive.on_event(ev)   # triage -> gate -> act/ask (gate reads memory)

    async def owner_event(self, source: str, text: str, meta: dict | None = None) -> dict:
        """One observed line through the owner card path, answered in the same shape as
        the proactive path ({decision, goal_id, ask_id, ...}) so realday.sh and
        persona_score.py grade owner cards without modification.

        F17 'one brain': the decision reported is the SPINE's verdict verbatim for
        spine-judged cards (act / ask / held / ignore — never a paper act or ask),
        "ask" for pre-gated blocked money cards (which never execute and never enter
        /pending), and "remember" for silent memory cards. No card means silence.
        """
        out = await self.owner_ingest(source, text, meta, execute_actions=True)
        rank = {"ask": 3, "blocked": 3, "do": 2, "remember": 1}
        top = None
        for card in out.get("cards", []):
            if top is None or rank.get(card.get("disposition"), 0) > rank.get(top.get("disposition"), 0):
                top = card
        execution = (top or {}).get("execution") or {}
        if top is None:
            decision, goal_id, reason, category, ask_id = (
                "ignore", None, "owner: no actionable card in line", "noise", None)
        elif top["disposition"] == "blocked":
            decision, goal_id, reason, category, ask_id = (
                "ask", top["id"], top.get("reason", ""), "blocked", None)
        elif top["disposition"] == "remember":
            decision, goal_id, reason, category, ask_id = (
                "remember", top["id"], top.get("reason", ""), "remember", None)
        else:
            # do/ask cards carry the spine's verdict — a card whose execution the
            # spine refused reports that refusal, never a paper act/ask (F17)
            decision = execution.get("decision") or "ignore"
            goal_id, reason = top["id"], top.get("reason", "")
            category, ask_id = top["disposition"], execution.get("ask_id")
        return {"decision": decision, "category": category, "reason": reason,
                "goal_id": goal_id, "ask_id": ask_id, "owner_lane": True,
                "cards": out.get("cards", [])}

    async def _spine_card(self, line: OwnerObservedLine, source: str, meta: dict) -> OwnerTaskCard | None:
        """F17 'one brain': the proven spine (triage -> decider -> harm-line ->
        orchestrator/hands) is the ONLY act/ask/silent decision-maker for owner
        lines. The regex classifier only shapes the durable card (title/route/args)
        and adds silent memory; it can no longer act or ask on its own. Money-shaped
        browser lines stay pre-gated blocked: never the spine's execution path,
        never /pending, never executed (the harm-line stance is final) — but a
        money-flavored line the spine's OWN triage confidently vents stays silent
        exactly as it would on the default path (F23)."""
        shaped = self.owner_mode.card_for_line(line, source)
        if shaped is not None and shaped.disposition == "blocked":
            # F23: the pre-gate's guarantee is that a money line can NEVER EXECUTE,
            # not that a money-flavored vent must interrupt. The consult is the
            # spine's own Room-1 triage instance — pure classification, no decider,
            # no harm-line, no orchestrator, no goal, no /pending — so the vent
            # judgment stays one brain (F17), and silence vs blocked are both
            # non-executing outcomes. Uncertainty keeps the ask: the live
            # ambiguity tiebreak fails OPEN (returns True on any error).
            if not self.proactive.triage.actionable(line.text):
                return None
            return shaped
        if shaped is not None and shaped.action == "find_or_cart_without_purchase":
            ctx = await self.bus.submit_job(Job(intent="read_context", args={"about": line.text}))
            if not self._has_external_context(ctx.output, line.text):
                goal = Goal(intent=line.text, description=shaped.title, state=GoalState.waiting)
                self.store.save(goal)
                ask_id = self.proactive._send_ask(
                    goal,
                    line.text,
                    "browser cart prep needs the exact item or source before acting",
                    "browser",
                )
                shaped.disposition = "ask"
                shaped.reason = "missing item/source context before carting"
                shaped.execution = {"decision": "ask", "goal_id": goal.id,
                                    "ask_id": ask_id, "goal_state": None}
                return shaped
        execution_text = (
            self.owner_mode.execution_text_for_card(shaped)
            if shaped is not None else line.text
        )
        out = await self.feed("app", execution_text,
                              {**meta, "owner_source": source,
                               "owner_ingest_execute": True,
                               "owner_source_text": line.text})
        decision = out.get("decision") or "ignore"
        execution = {"decision": decision, "goal_id": out.get("goal_id"),
                     "ask_id": out.get("ask_id"), "goal_state": None}
        if decision == "act" or decision in ("ask", "held") or out.get("ask_id"):
            if shaped is not None and shaped.disposition in ("do", "ask"):
                card = shaped
            else:
                # the spine caught a line the regex could not shape: the card
                # mirrors the spine's verdict with a generic shape
                card = OwnerTaskCard(
                    source=source,
                    line_no=line.line_no,
                    source_text=line.text,
                    title=f"Owner task: {line.text[:80]}",
                    disposition="do",
                    route="api",
                    action="execute_owner_task",
                    args={"task_text": line.text},
                    confidence=0.8,
                )
            card.disposition = "do" if decision == "act" else "ask"
            card.reason = out.get("reason") or card.reason or "proven spine verdict"
            card.execution = execution
            return card
        # spine says silent: regex shaping may still add SILENT memory (a remember
        # card or a durable open-loop record) — never a paper act or ask
        if shaped is None:
            return None
        if shaped.disposition != "remember":
            shaped.execution = execution
        return shaped

    async def owner_ingest(self, source: str, text: str, meta: dict | None = None,
                           execute_actions: bool = False) -> dict:
        """Shared owner path for transcript/MP3/listening/pay-to-try.

        It records the whole observed stream, extracts durable task cards, and writes
        those cards into the real memory drawers. With execute_actions, the cards are
        REAL: do cards run through the proven proactive spine (orchestrator + hands)
        with the outcome and proof mirrored onto the durable card record; ask cards
        become pending asks resolved by the existing YES/NO flow; money/blocked cards
        can never execute (the harm-line is final); remember cards carry read-back
        proof of their memory write.
        """
        meta = meta or {}
        observed = self.owner_mode.observe(text)
        captured_by_line: dict[int, dict] = {}
        for line in observed:
            captured_by_line[line.line_no] = self.live_memory.capturer.capture(
                line.text,
                source=source,
                meta={**meta, "owner_ingest": True, "line_no": line.line_no},
            )

        cards: list[OwnerTaskCard] = []
        ignored = 0
        ignored_captures: list[tuple[dict | None, int]] = []
        for line in observed:
            preview = self.owner_mode.card_for_line(line, source)
            if preview is not None:
                existing = self._existing_owner_card(preview)
                if existing is not None:
                    cards.append(existing)
                    continue
            if execute_actions:
                card = await self._spine_card(line, source, meta)
            else:
                card = preview
            if card is None:
                ignored += 1
                if execute_actions:
                    ignored_captures.append((captured_by_line.get(line.line_no), line.line_no))
                continue
            existing = self._existing_owner_card(card)
            if existing is not None:
                cards.append(existing)
                continue
            persisted = self._persist_card(card, source, execute_actions,
                                           captured_by_line.get(line.line_no))
            if not persisted:
                # vent caught by the persist-side cardinal-sin guard: nothing durable was
                # written, so it is not a card — treat it as ignored (no active memory).
                ignored += 1
                if execute_actions:
                    ignored_captures.append((captured_by_line.get(line.line_no), line.line_no))
                continue
            cards.append(card)

        # Do not close "ignored" captures while later lines in the same messy
        # transcript may still need them as memory context. A line like "I was
        # looking at X" is not a card by itself, but it can be the grounding for
        # "cart that thing" ten seconds later.
        if execute_actions:
            for capture_result, _line_no in ignored_captures:
                self._sync_capture_result_status(capture_result, "ignored")

        self.glassbox.log(
            "owner_ingest",
            {"source": source, "lines": len(observed), "cards": len(cards),
             "ignored": ignored, "execute_actions": execute_actions},
        )
        result = OwnerIngestResult(source=source, observed_lines=observed, cards=cards,
                                   ignored_line_count=ignored)
        return result.model_dump(mode="json")

    def _persist_card(self, card: OwnerTaskCard, source: str, execute_actions: bool,
                      capture_result: dict | None = None) -> bool:
        """Write one card into the real memory drawers and its durable goal-shaped
        record, mirroring REAL execution: done requires a goal that finished with
        proof (or a read-back memory write) — a card that never ran stays open.

        Returns False (and persists NOTHING durable) when the card is a vent that
        slipped through as a 'remember' shape — the cardinal-sin guard, defense in depth.
        """
        from ..live_memory.review_infer import is_vent_shape

        # CARDINAL-SIN GUARD (defense in depth): a 'remember' card writes the spoken line
        # into the ACTIVE profile drawer unconditionally. A vent ("I hate this", "kill me",
        # "I could scream", "I should just move to a beach") must NEVER become a durable
        # active profile memory — even in preview, persisting it is the cardinal-sin echo.
        # _card_for_line already drops vents, so this only fires if a remember card reaches
        # here some other way; it then persists nothing (no profile write, no record). Uses
        # the _VENT-family shape (not the countermand) so a genuine preference phrased with
        # "don't" ("I prefer you don't call after 9") is still remembered.
        if card.disposition == "remember" and is_vent_shape(card.source_text):
            self.glassbox.log("vent_not_persisted",
                              {"owner_card_id": card.id, "source": source,
                               "source_text": card.source_text})
            return False
        fields = {
            "owner_card_id": card.id,
            "owner_card_dedupe_key": _owner_card_dedupe_key(card),
            "source": source,
            "line_no": card.line_no,
            "source_text": card.source_text,
            "disposition": card.disposition,
            "route": card.route,
            "action": card.action,
            "args": card.args,
            "reason": card.reason,
        }
        if card.disposition == "remember":
            item = self.memory.profile.write_text(
                card.source_text,
                fields=fields,
                provenance=f"owner:{source}",
                confidence=card.confidence,
                importance=0.7,
                status="active",
            )
            drawer = self.memory.profile
            drawer_name = "profile"
        else:
            # the drawer remembers the person's actual words — synthetic card titles
            # ("Owner task: ...") in open loops polluted the planner's inject context
            # with tokens the speaker never said (browse steps grew on unrelated goals)
            item = self.memory.open_loops.write_text(
                card.source_text,
                fields={**fields, "title": card.title},
                provenance=f"owner:{source}",
                confidence=card.confidence,
                importance=0.85,
                status=("open" if card.disposition == "do" else "waiting"),
            )
            drawer = self.memory.open_loops
            drawer_name = "open_loops"
        card.proof.append({"type": "memory_write", "drawer": drawer_name, "memory_id": item.id})
        # read-back: a write only counts once the drawer returns it by id
        back = drawer.get(item.id)
        if back is not None:
            card.proof.append({"type": "memory_read_back", "memory_id": back.id, "text": back.text})

        record_path = self.data_dir / "owner_cards" / f"{card.id}.json"
        state, steps, goal_proof = "open", [], {}
        execution = card.execution or {}

        if card.disposition == "remember" and back is not None:
            # the card's action IS the memory write; the read-back makes it
            # executed-with-proof (no orchestrator involved, nothing external)
            state = "done"
            goal_proof = {"memory_id": item.id, "read_back": back.text}
        elif card.disposition == "blocked":
            # money/wall: NEVER executes — and never enters proactive.pending,
            # where a YES would start_goal it. The harm-line is final; the card
            # stays a ledgered open loop prepared up to the wall.
            card.execution = {"decision": "blocked", "goal_id": None, "ask_id": None,
                              "reason": "hard stop: money/wall cards never execute"}
            state = "blocked" if execute_actions else "open"
            if execute_actions:
                self.glassbox.log("blocked", {"goal_id": card.id, "category": "money",
                                              "reason": card.reason, "action": card.source_text})
        elif execution:
            # the spine already ran this line (F17 one brain, _spine_card): the
            # record mirrors what it actually DID. Spine refusal (ignore/suppressed/
            # deferred) has no goal -> the card stays a durable open loop and the
            # instrument shows no act.
            goal = self.store.load(execution["goal_id"]) if execution.get("goal_id") else None
            if goal is not None:
                execution["goal_state"] = goal.state.value
                steps = [s.model_dump(mode="json") for s in goal.steps]
                goal_proof = goal.proof or {}
                state = goal.state.value  # done only when every step carried proof
                card.proof.extend(_card_step_receipts(steps))
                if execution.get("ask_id") or execution.get("decision") in ("ask", "held"):
                    state = "waiting"
                    self._owner_card_goals[goal.id] = {"record_path": record_path,
                                                       "card_id": card.id}
            card.proof.append({"type": "engine_execution", **execution})

        card.status = state
        if drawer_name == "open_loops":
            self._sync_owner_loop_status(card.id, state)
        captured_item = (capture_result or {}).get("item")
        if getattr(captured_item, "kind", None) == "open_loop":
            status = _status_for_open_loop(state)
            should_sync_capture = state != "done" or not _steps_create_open_loop(steps)
            if should_sync_capture and self._sync_open_loop_item_status(captured_item.id, state, card_id=card.id):
                card.proof.append({
                    "type": "capture_memory_status",
                    "memory_id": captured_item.id,
                    "status": status,
                })
        # Durable card record, shaped like a goal (id/intent/steps/state) so the
        # factory's existing run collector and scorer read owner cards unchanged.
        card.proof.append({"type": "card_record", "path": str(record_path)})
        record = {
            "id": card.id,
            "dedupe_key": _owner_card_dedupe_key(card),
            "intent": card.action,
            "description": f"{card.title} — {card.source_text}",
            "state": state,
            "steps": steps,
            "proof": goal_proof,
            "owner_card": card.model_dump(mode="json"),
        }
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
        return True

    def _existing_owner_card(self, card: OwnerTaskCard) -> OwnerTaskCard | None:
        """Return the durable card for an accidental replay, before re-executing."""
        key = _owner_card_dedupe_key(card)
        cards_dir = self.data_dir / "owner_cards"
        if not cards_dir.is_dir():
            return None
        for path in sorted(cards_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            record_card = record.get("owner_card") if isinstance(record, dict) else None
            if not isinstance(record_card, dict):
                continue
            record_key = record.get("dedupe_key")
            if not record_key:
                try:
                    record_key = _owner_card_dedupe_key(OwnerTaskCard.model_validate(record_card))
                except Exception:
                    continue
            if record_key != key:
                continue
            card_data = {**record_card, "status": record.get("state") or record_card.get("status") or "open"}
            execution = card_data.get("execution")
            if isinstance(execution, dict):
                card_data["execution"] = {
                    **execution,
                    "goal_state": card_data["status"],
                    "ask_id": execution.get("ask_id") if card_data["status"] == "waiting" else None,
                }
            return OwnerTaskCard.model_validate(card_data)
        return None

    async def owner_onboard(self, body: OwnerOnboardingIn) -> dict:
        """Write first-run onboarding into the same memory ledger the engine uses."""
        plan = build_onboarding_plan(body)
        written = []
        for mem in plan.memories:
            item = self._upsert_onboarding_memory(mem, plan.source)
            written.append({"drawer": mem.drawer, "memory_id": item.id, "text": item.text,
                            "status": item.status, "fields": item.fields})
        self._close_connected_setup_loops(plan.memories)

        self.glassbox.log(
            "owner_onboarding",
            {"source": plan.source, "written": len(written),
             "missing_connections": plan.missing_connections},
        )
        return {"source": plan.source, "written": written,
                "missing_connections": plan.missing_connections}

    @staticmethod
    def _onboarding_key(fields: dict) -> str:
        kind = str(fields.get("kind") or "").strip().lower()
        source = "owner_onboarding"
        if kind == "owner_identity":
            return f"{source}:owner_identity"
        if kind == "preference":
            return f"{source}:preference:{str(fields.get('preference') or '').strip().lower()}"
        if kind == "person":
            return f"{source}:person:{str(fields.get('name') or '').strip().lower()}"
        if kind == "app_connection":
            identifier = str(fields.get("identifier") or "").strip().lower()
            name = str(fields.get("name") or "").strip().lower()
            return f"{source}:app_connection:{identifier or name}"
        if kind == "store_account":
            url = str(fields.get("url") or "").strip().lower()
            name = str(fields.get("name") or "").strip().lower()
            return f"{source}:store_account:{url or name}"
        if kind == "raw_onboarding_notes":
            return f"{source}:raw_notes"
        return f"{source}:{kind}:{str(fields).strip().lower()}"

    def _find_onboarding_item(self, drawer, key: str, fields: dict):
        for item in drawer.all():
            item_key = item.fields.get("onboarding_key") or self._onboarding_key(item.fields)
            if item_key == key:
                return item
            if fields.get("action") == "connect_account" and item.fields.get("action") == "connect_account":
                if str(item.fields.get("name") or "").strip().lower() == str(fields.get("name") or "").strip().lower():
                    return item
        return None

    def _upsert_onboarding_memory(self, mem, source: str):
        drawer = self.memory.profile if mem.drawer == "profile" else self.memory.open_loops
        key = self._onboarding_key(mem.fields)
        fields = {**mem.fields, "onboarding_key": key}
        item = self._find_onboarding_item(drawer, key, fields)
        if item is None:
            return drawer.write_text(
                mem.text,
                fields=fields,
                provenance=f"owner:{source}",
                confidence=mem.confidence,
                importance=mem.importance,
                status=mem.status,
            )
        item.text = mem.text
        item.fields = fields
        item.provenance = f"owner:{source}"
        item.confidence = mem.confidence
        item.importance = mem.importance
        item.status = mem.status
        return drawer.update(item)

    def _close_connected_setup_loops(self, memories) -> None:
        active_missing = {
            self._onboarding_key(mem.fields)
            for mem in memories
            if mem.drawer == "open_loops" and mem.fields.get("action") == "connect_account"
        }
        connection_keys = {
            self._onboarding_key(mem.fields): mem
            for mem in memories
            if mem.drawer == "profile" and mem.fields.get("kind") == "app_connection"
        }
        for item in self.memory.open_loops.all():
            if item.fields.get("action") != "connect_account":
                continue
            key = item.fields.get("onboarding_key") or self._onboarding_key(item.fields)
            if key in active_missing:
                continue
            conn = connection_keys.get(key)
            if conn is None or conn.fields.get("status") != "connected":
                continue
            item.status = "done"
            item.fields = {**item.fields, "onboarding_key": key, "resolved_from": "owner_onboarding_connected"}
            self.memory.open_loops.update(item)

    async def notify_user(self, text: str, recipient: str | None = None) -> dict:
        """Text the user — the 'ask' half of a wall handoff (pause -> ask -> resume).
        Routes through the REAL send_text worker (mock by default, Twilio when the
        channel env is live); the seam + glass-box trail are the same either way."""
        from .envelopes import Job

        to = (recipient or os.environ.get("ALERT_PHONE") or os.environ.get("TWILIO_TO")
              or self._user_contact())
        self.glassbox.log("handoff", {"event": "notify_user", "to": to, "text": text})
        try:
            res = await self.channel_worker.handle(Job(intent="send_text", args={"recipient": to, "body": text}))
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

    def memory_open_loops(self, limit: int = 50) -> dict:
        """Visible memory backlog: open/waiting loops the owner should be able to inspect."""
        active = [i for i in self.memory.open_loops.all() if is_active_open_loop(i)]
        active.sort(key=lambda i: i.updated_at or i.timestamp, reverse=True)
        loops = [i.model_dump(mode="json") for i in active[:max(0, limit)]]
        return {"loops": loops, "count": len(active)}

    def resolve_memory_loop(self, loop_id: str, status: str = "done") -> dict:
        """Owner closes a memory/setup loop. Owner-card loops must resolve through cards."""
        if status not in {"done", "blocked", "waiting", "open"}:
            return {"resolved": False, "reason": f"unsupported status: {status}"}
        item = self.memory.open_loops.get(loop_id)
        if item is None:
            return {"resolved": False, "reason": "unknown open loop"}
        if item.fields.get("owner_card_id"):
            return {
                "resolved": False,
                "reason": "owner-card loops must be resolved from the task card",
                "id": item.id,
                "status": item.status,
            }
        before = item.status
        item.status = status
        item.fields = {**item.fields, "resolved_from": "owner_mode", "previous_status": before}
        self.memory.open_loops.update(item)
        self.glassbox.log(
            "memory_loop_resolved",
            {"loop_id": item.id, "status": status, "previous_status": before, "text": item.text},
        )
        return {
            "resolved": True,
            "id": item.id,
            "status": item.status,
            "previous_status": before,
            "text": item.text,
        }

    def authorize_connection_loop(self, loop_id: str) -> dict:
        """Read-only connect helper for setup loops; never executes an action."""
        item = self.memory.open_loops.get(loop_id)
        if item is None:
            return {"ok": False, "reason": "unknown open loop"}
        fields = item.fields or {}
        if fields.get("action") != "connect_account":
            return {"ok": False, "reason": "loop is not a connection setup task", "id": item.id}
        if fields.get("owner_card_id"):
            return {"ok": False, "reason": "owner-card loops must resolve through the task card", "id": item.id}

        route = str(fields.get("route") or "").strip().lower()
        name = str(fields.get("name") or item.text).strip()
        if route == "browser":
            connected = bool(self.browser_link.connected or getattr(self.native_bridge_link, "connected", False))
            out = {
                "ok": True,
                "id": item.id,
                "name": name,
                "route": "browser",
                "status": "connected" if connected else "needs_setup",
                "message": "browser linked" if connected else "open Chrome and connect the Anticipy browser helper",
            }
            self.glassbox.log("connection_checked", out)
            return out

        if route != "api":
            out = {"ok": True, "id": item.id, "name": name, "route": route or "unknown",
                   "status": "needs_setup", "message": "manual setup required"}
            self.glassbox.log("connection_checked", out)
            return out

        tool = _connect_tool(fields)
        if not tool:
            out = {"ok": True, "id": item.id, "name": name, "route": "api",
                   "status": "needs_setup", "message": "no known connector for this app yet"}
            self.glassbox.log("connection_checked", out)
            return out
        if self.api_hand.mode != MODE_LIVE:
            out = {"ok": True, "id": item.id, "name": name, "route": "api", "tool": tool,
                   "status": "mock", "message": "live connector mode is required to generate a connect URL"}
            self.glassbox.log("connection_checked", out)
            return out
        try:
            client = self.api_hand._client_or_build()
            auth = client.tools.authorize(tool_name=tool, user_id=self.api_hand.user_id)
        except NotFundedError as exc:
            out = {"ok": True, "id": item.id, "name": name, "route": "api", "tool": tool,
                   "status": "needs_setup", "message": str(exc)}
            self.glassbox.log("connection_checked", out)
            return out
        except Exception as exc:  # noqa: BLE001 - setup help must not crash the app
            out = {"ok": True, "id": item.id, "name": name, "route": "api", "tool": tool,
                   "status": "needs_setup", "message": f"{type(exc).__name__}: {exc}"}
            self.glassbox.log("connection_checked", out)
            return out

        status = getattr(auth, "status", None) or "unknown"
        url = getattr(auth, "url", None)
        out = {"ok": True, "id": item.id, "name": name, "route": "api", "tool": tool,
               "status": "connected" if status == "completed" else "needs_auth",
               "connect_url": url,
               "message": "already connected" if status == "completed" else "open the connect URL and approve access"}
        self.glassbox.log("connection_checked", out)
        return out

    def owner_cards(self, limit: int = 50) -> dict:
        """Return recent durable owner cards for the app board.

        The UI is allowed to reload or reconnect without losing the visible work
        surface. The source of truth is the card record written beside each goal,
        not React state from the last ingest response.
        """
        cards_dir = self.data_dir / "owner_cards"
        if not cards_dir.is_dir():
            return {"cards": [], "count": 0}
        cards = []
        paths = sorted(cards_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in paths[:max(0, limit)]:
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            card = record.get("owner_card") or {}
            if not isinstance(card, dict):
                continue
            state = record.get("state") or card.get("status") or "open"
            card = {**card, "status": state}
            execution = card.get("execution")
            if isinstance(execution, dict):
                card["execution"] = {
                    **execution,
                    "goal_state": state,
                    "ask_id": execution.get("ask_id") if state == "waiting" else None,
                }
            resolution = record.get("resolution")
            if isinstance(resolution, dict):
                proof = list(card.get("proof") or [])
                if not any(p.get("type") == "resolution" for p in proof if isinstance(p, dict)):
                    proof.append({
                        "type": "resolution",
                        "decision": "approved" if resolution.get("approved") else "declined",
                        "goal_state": state,
                    })
                card["proof"] = proof
            cards.append(card)
        return {"cards": cards, "count": len(cards)}

    def _find_card_record(self, goal_id: str) -> dict | None:
        """Scan the durable owner card records for one whose execution targeted
        goal_id (ledger F18 fallback; only runs when the in-memory map missed)."""
        cards_dir = self.data_dir / "owner_cards"
        if not cards_dir.is_dir():
            return None
        for path in cards_dir.glob("*.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            execution = ((record.get("owner_card") or {}).get("execution") or {})
            if execution.get("goal_id") == goal_id:
                return {"record_path": str(path), "card_id": record.get("id")}
        return None

    async def resolve(self, ask_id: str, approved: bool) -> dict:
        """The app's approve/deny -> resolves the REAL paused goal (mirrors the text/call round-trip).
        If the goal came from an owner card, the resolution outcome (state + proof on
        YES, declined on NO) is written back onto the durable card record."""
        out = await self.proactive.resolve_ask(ask_id, approved)
        link = self._owner_card_goals.pop(out.get("goal_id"), None) if isinstance(out, dict) else None
        if link is None and isinstance(out, dict) and out.get("goal_id"):
            # F18 durable linkage: the in-memory map can be gone (restart, desync)
            # while the card record's execution.goal_id survives on disk — derive
            # the write-back from the record itself so a resolution NEVER strands
            # an owner card at "waiting".
            link = self._find_card_record(out["goal_id"])
        if link is not None:
            goal = self.store.load(out["goal_id"])
            try:
                record = json.loads(Path(link["record_path"]).read_text(encoding="utf-8"))
            except Exception:
                record = None
            if record is not None and goal is not None:
                if approved:
                    record["state"] = goal.state.value
                    record["steps"] = [s.model_dump(mode="json") for s in goal.steps]
                    record["proof"] = goal.proof or {}
                else:
                    record["state"] = "declined"
                if isinstance(record.get("owner_card"), dict):
                    record["owner_card"]["status"] = record["state"]
                record["resolution"] = {"ask_id": ask_id, "approved": approved}
                self._sync_captured_loop_from_record(record, record["state"])
                Path(link["record_path"]).write_text(
                    json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
                self._sync_owner_loop_status(link["card_id"], record["state"])
                self.glassbox.log("owner_card_resolved",
                                  {"card_id": link["card_id"], "ask_id": ask_id,
                                   "approved": approved, "state": record["state"]})
        return out

    async def approve_remembered(self, line_id: str) -> dict:
        """DEFAULT-DENY press-go: the owner presses go on ONE remembered line.

        This is the ONLY execution trigger for a remembered/inferred item, and only for
        the three whitelisted reversible intents. It is ADDITIVE: it reuses the review
        inference (display-only), the orchestrator funnel + GatedApprover (owner_approved),
        and the Slice-0 read-back gate verbatim. It touches no decision/trigger/harm code.

        STEP A INFER (reuse, read-only): pull the inert row by id and enrich it with the
        SAME ReviewEnricher.infer_line used by the read-only review. A vent yields an empty
        task here -> {approved:false} with NO goal, NO orchestrator call (the vent stop).

        STEP B MAP -> ONE intent + a pre-built Step (deterministic, conservative).

        STEP C WHITELIST GATE (default-deny, structural): execute ONLY if intent in
        WHITELIST; everything else is prepared-and-handed-back, never executed. Money/send/
        message land in handback because no such intent is in the set.

        CONCURRENCY: the whole load-check-build-drive runs under a per-line lock so two
        concurrent presses of the SAME line serialize. The second press, once it acquires
        the lock, finds the first press's goal already done and returns its receipt
        (idempotent) — exactly ONE real write. The lock is keyed on the stable goal_id
        derived from line_id, so different lines never block each other.
        """
        goal_id = "rmb-" + hashlib.sha256(line_id.encode()).hexdigest()[:24]
        lock = await self._press_go_lock_for(goal_id)
        async with lock:
            return await self._approve_remembered_locked(line_id, goal_id)

    async def _press_go_lock_for(self, goal_id: str) -> asyncio.Lock:
        async with self._press_go_locks_guard:
            lock = self._press_go_locks.get(goal_id)
            if lock is None:
                lock = asyncio.Lock()
                self._press_go_locks[goal_id] = lock
            return lock

    async def _approve_remembered_locked(self, line_id: str, goal_id: str) -> dict:
        from ..live_memory.review_infer import infer_line
        from ..live_memory.press_go import WHITELIST, map_inferred_to_step

        cap = self.live_memory.capturer
        row = next((r for r in cap.remember.all() if r.get("id") == line_id), None)
        if row is None:
            return {"approved": False, "line_id": line_id, "reason": "unknown remembered line"}

        # STEP A — INFER (reuse the display-only review inference, read-only).
        inferred = infer_line(str(row.get("text") or ""), people_hint=row.get("people"))
        task = str(inferred.get("task") or "").strip()
        if not task:
            # vent / narration: refuse — no goal, no orchestrator, no pending entry.
            self.glassbox.log("press_go_vent", {"line_id": line_id})
            return {"approved": False, "line_id": line_id, "inferred": inferred,
                    "reason": "no confident inferred task (vent/narration)"}

        # STEP B — MAP inferred task -> a single intent + pre-built Step (or handback).
        # The raw spoken line grounds a concrete event time (the review's due_phrase is
        # lossy); the whitelist DECISION is keyed off the inferred shape.
        mapped = map_inferred_to_step(inferred, raw_text=str(row.get("text") or ""))
        intent = mapped.get("intent")
        step = mapped.get("step")

        # STEP C — WHITELIST GATE. Default-deny: execute ONLY if the intent is in the set.
        if intent not in WHITELIST or step is None:
            # NON-WHITELIST branch: prepared-handback. NO Goal saved, orchestrator NEVER
            # called, nothing enters proactive.pending. Money/send/message land here.
            self.glassbox.log("press_go_handback",
                              {"line_id": line_id, "intent": intent or "(unmapped)",
                               "reason": mapped.get("non_whitelist_reason")})
            return {"approved": False, "prepared": True, "line_id": line_id,
                    "inferred_action": task, "intent": intent,
                    "would_do": mapped.get("would_do"),
                    "why_handback": (mapped.get("non_whitelist_reason")
                                     or "not a provably-safe reversible intent")}

        # Defense in depth: the produced step intent MUST be in WHITELIST before we drive.
        if step.intent not in WHITELIST:
            self.glassbox.log("press_go_handback",
                              {"line_id": line_id, "intent": step.intent,
                               "reason": "produced step intent not whitelisted"})
            return {"approved": False, "prepared": True, "line_id": line_id,
                    "inferred_action": task, "intent": step.intent,
                    "would_do": mapped.get("would_do"),
                    "why_handback": "produced step intent not whitelisted"}

        # WHITELIST branch — execute via the EXISTING funnel. Build a goal with ONE
        # pre-built whitelisted step + owner_approved proof, then drive it through the
        # orchestrator (GatedApprover reads owner_approved; the api_hand read-back gate
        # still independently confirms the artifact — Law 4). Same reuse pattern as
        # resolve_ask's already-stepped (_approve_waiting_goal + _drive) path, so no
        # planner can widen the single step into a non-whitelisted write.
        #
        # Line-level idempotency: ``goal_id`` is a STABLE id derived from the line_id (by
        # the locking wrapper) so re-pressing the same line reuses the same goal. If that
        # goal already ran to done, return its receipt without re-driving — the endpoint is
        # safe to re-press (no double-create of a calendar hold / draft). The per-line lock
        # held by the wrapper makes this load-check-build-drive atomic, so a CONCURRENT
        # second press also lands here only after the first completed and finds it done.
        prior = self.store.load(goal_id)
        if prior is not None and prior.state == GoalState.done:
            self.glassbox.log("press_go_idempotent",
                              {"line_id": line_id, "goal_id": goal_id})
            return {"approved": True, "executed": True, "idempotent": True,
                    "line_id": line_id, "intent": prior.intent, "goal_id": prior.id,
                    "state": prior.state.value, "would_do": mapped.get("would_do"),
                    "receipt": prior.proof or {}}
        goal = Goal(id=goal_id, intent=intent, description=mapped.get("would_do") or task,
                    steps=[step])
        goal.proof = {"owner_approved": True, "approved_from": "remembered",
                      "line_id": line_id}
        goal.state = GoalState.running
        self.store.save(goal)
        self.glassbox.log("press_go_execute",
                          {"line_id": line_id, "intent": intent, "goal_id": goal.id})
        goal = await self.orchestrator._drive(goal)

        receipt = goal.proof or {}
        return {"approved": True, "executed": True, "line_id": line_id, "intent": intent,
                "goal_id": goal.id, "state": goal.state.value,
                "would_do": mapped.get("would_do"), "receipt": receipt}

    # The human-readable tool each whitelisted intent WOULD call live. create_event and
    # send_email_draft route through the Arcade api_hand (authoritative INTENT_MAP);
    # write_memory is a LOCAL standing note (no external tool, never leaves the device).
    _DRYRUN_TOOL = {
        "create_event": "GoogleCalendar.CreateEvent",
        "send_email_draft": "Gmail.WriteDraftEmail",
        "write_memory": "Anticipy.Memory (local note — no external account)",
    }

    def dryrun_remembered(self, line_id: str) -> dict:
        """LIVE DRY-RUN PREVIEW: show EXACTLY what press-go WOULD do, WITHOUT doing it.

        Trust-before-connect. This runs the SAME default-deny press-go mapping as
        ``approve_remembered`` (the SAME review inference + the SAME ``map_inferred_to_step``
        + the SAME WHITELIST gate) but STOPS before execution: it NEVER builds or saves a
        Goal, NEVER calls ``orchestrator.start_goal`` / ``orchestrator._drive``, NEVER
        writes a memory note, and NEVER touches the api/browser hands. It only PLANS and
        SHOWS, so the owner can see his whole day's planned real actions before connecting
        any account.

        Returns a preview dict:
          whitelisted line ->
            {would_execute: True, line_id, intent,
             tool (e.g. GoogleCalendar.CreateEvent / Gmail.WriteDraftEmail),
             args (the EXACT args press-go would send), would_do,
             note: "This runs for real once you connect Google"}
          non-whitelisted line ->
            {would_execute: False, line_id, intent: None, handback: <human description>,
             why: <reason>}
          vent / narration ->
            {would_execute: False, line_id, intent: None, why: <vent stop>}
        """
        from ..live_memory.review_infer import infer_line
        from ..live_memory.press_go import WHITELIST, map_inferred_to_step

        cap = self.live_memory.capturer
        row = next((r for r in cap.remember.all() if r.get("id") == line_id), None)
        if row is None:
            return {"would_execute": False, "line_id": line_id, "intent": None,
                    "why": "unknown remembered line"}

        raw_text = str(row.get("text") or "")

        # STEP A — INFER (reuse the display-only review inference, read-only). A vent yields
        # an empty task -> preview says nothing would execute (the vent stop, surfaced).
        inferred = infer_line(raw_text, people_hint=row.get("people"))
        task = str(inferred.get("task") or "").strip()
        if not task:
            self.glassbox.log("dryrun_vent", {"line_id": line_id})
            return {"would_execute": False, "line_id": line_id, "intent": None,
                    "inferred": inferred,
                    "why": "no confident inferred task (vent/narration)"}

        # STEP B — MAP inferred task -> a single intent + pre-built Step (or handback). This
        # is the IDENTICAL call approve_remembered makes; the raw line grounds a concrete
        # event time. We read the plan but DO NOT drive it.
        mapped = map_inferred_to_step(inferred, raw_text=raw_text)
        intent = mapped.get("intent")
        step = mapped.get("step")

        # STEP C — WHITELIST GATE preview. Default-deny: only an intent in the set WOULD
        # execute. Everything else is shown as handback — exactly what approve would return,
        # minus any execution.
        if intent not in WHITELIST or step is None:
            self.glassbox.log("dryrun_handback",
                              {"line_id": line_id, "intent": intent or "(unmapped)"})
            return {"would_execute": False, "line_id": line_id, "intent": intent,
                    "inferred_action": task,
                    "handback": mapped.get("would_do"),
                    "why": (mapped.get("non_whitelist_reason")
                            or "not a provably-safe reversible intent")}

        # WHITELIST branch — show the concrete planned action. We surface the EXACT args the
        # whitelisted Step carries (the same args approve_remembered would send through the
        # orchestrator), the tool it WOULD call, and the connect-first note. NOTHING is
        # executed: no Goal is built or saved, the orchestrator is never invoked.
        args = dict(step.args)
        self.glassbox.log("dryrun_preview",
                          {"line_id": line_id, "intent": intent})
        return {"would_execute": True, "line_id": line_id, "intent": intent,
                "tool": self._DRYRUN_TOOL.get(intent, intent),
                "args": args, "would_do": mapped.get("would_do"),
                "note": ("This runs for real once you connect Google"
                         if intent in ("create_event", "send_email_draft")
                         else "This saves a local note when you press go (no account needed)")}
