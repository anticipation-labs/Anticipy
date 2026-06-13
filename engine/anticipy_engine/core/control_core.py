"""ControlCore — assembles the whole brain and exposes a tiny driving surface.

One object that wires the bus, the model gateway, the glass-box, the scorecard,
the stub workers, the orchestrator, and the proactive engine together. The HTTP
layer and the tests drive it through `feed()` and `resume()`.
"""
from __future__ import annotations

import json
import os
import re
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
from ..hands import ApiHand, BrowserHand, MODE_MOCK
from ..live_memory.brain import LiveMemoryBrain
from ..memory.store import Memory
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
            alternates=alternates, approver=GatedApprover(True), memory_context=self._mem_ctx,
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
        for line in observed:
            if execute_actions:
                card = await self._spine_card(line, source, meta)
            else:
                card = self.owner_mode.card_for_line(line, source)
            if card is None:
                ignored += 1
                if execute_actions:
                    self._sync_capture_result_status(captured_by_line.get(line.line_no), "ignored")
                continue
            cards.append(card)
            self._persist_card(card, source, execute_actions, captured_by_line.get(line.line_no))

        self.glassbox.log(
            "owner_ingest",
            {"source": source, "lines": len(observed), "cards": len(cards),
             "ignored": ignored, "execute_actions": execute_actions},
        )
        result = OwnerIngestResult(source=source, observed_lines=observed, cards=cards,
                                   ignored_line_count=ignored)
        return result.model_dump(mode="json")

    def _persist_card(self, card: OwnerTaskCard, source: str, execute_actions: bool,
                      capture_result: dict | None = None) -> None:
        """Write one card into the real memory drawers and its durable goal-shaped
        record, mirroring REAL execution: done requires a goal that finished with
        proof (or a read-back memory write) — a card that never ran stays open."""
        fields = {
            "owner_card_id": card.id,
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
            "intent": card.action,
            "description": f"{card.title} — {card.source_text}",
            "state": state,
            "steps": steps,
            "proof": goal_proof,
            "owner_card": card.model_dump(mode="json"),
        }
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")

    async def owner_onboard(self, body: OwnerOnboardingIn) -> dict:
        """Write first-run onboarding into the same memory ledger the engine uses."""
        plan = build_onboarding_plan(body)
        written = []
        for mem in plan.memories:
            if mem.drawer == "profile":
                item = self.memory.profile.write_text(
                    mem.text,
                    fields=mem.fields,
                    provenance=f"owner:{plan.source}",
                    confidence=mem.confidence,
                    importance=mem.importance,
                    status=mem.status,
                )
            else:
                item = self.memory.open_loops.write_text(
                    mem.text,
                    fields=mem.fields,
                    provenance=f"owner:{plan.source}",
                    confidence=mem.confidence,
                    importance=mem.importance,
                    status=mem.status,
                )
            written.append({"drawer": mem.drawer, "memory_id": item.id, "text": item.text,
                            "status": item.status, "fields": item.fields})

        self.glassbox.log(
            "owner_onboarding",
            {"source": plan.source, "written": len(written),
             "missing_connections": plan.missing_connections},
        )
        return {"source": plan.source, "written": written,
                "missing_connections": plan.missing_connections}

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
        active = [i for i in self.memory.open_loops.all() if i.status in ("open", "waiting")]
        active.sort(key=lambda i: i.updated_at or i.timestamp, reverse=True)
        loops = [i.model_dump(mode="json") for i in active[:max(0, limit)]]
        return {"loops": loops, "count": len(active)}

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
