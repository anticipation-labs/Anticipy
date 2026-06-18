"""ControlCore — assembles the whole brain and exposes a tiny driving surface.

One object that wires the bus, the model gateway, the glass-box, the scorecard,
the stub workers, the orchestrator, and the proactive engine together. The HTTP
layer and the tests drive it through `feed()` and `resume()`.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import re
import hashlib
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .browser_link import BrowserLink
from .bus import Bus
from .env import load_local_env
from .envelopes import Event, EventSource, Goal, GoalState, Job, JobStatus
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
from ..hands.token_vault import TokenBroker, TokenVault
from ..live_memory.brain import LiveMemoryBrain
from ..memory.store import Memory, is_active_open_loop
from ..owner_mode import OwnerIngestResult, OwnerMode, OwnerObservedLine, OwnerTaskCard
from ..owner_onboarding import OwnerOnboardingIn, build_onboarding_plan


def _base(data_dir=None) -> Path:
    return Path(data_dir or os.environ.get("ANTICIPY_DATA_DIR", ".anticipy-data")).expanduser()


# DETERMINISTIC ASIDE FLOOR (model-independent). A past/perfect interrogative directed at
# someone else — "Did you grab the dry cleaning on the way home?", "Have you emailed Sarah
# yet?", "Didn't you already call the dentist?" — is a CHECK on another person's action, never
# the owner's own new task. The MOAT model strips the "did you …?" wrapper and over-extracts a
# bare imperative ("grab the dry cleaning") that then reads as actionable, so the /owner/ingest
# split path turned a question into an ASK (the cardinal sin: a vent/aside must stay silent).
# The proactive path's deterministic triage already silences these; this makes the SAME guard a
# hard floor on the model path. Scoped to PAST/PERFECT auxiliaries only, so a present/future
# request to the assistant ("Can you remind me to call mom at 3?") is untouched. Fails to silence.
_INTERROGATIVE_ASIDE = re.compile(
    r"^\s*(did|didn'?t|do|does|doesn'?t|have|haven'?t|has|hasn'?t|had|hadn'?t|"
    r"were|weren'?t|was|wasn'?t|are|aren'?t|is|isn'?t)\s+(you|we|they|he|she|it|u|your|the)\b",
    re.I)
# A PAST/PERFECT completion-check aimed at the listener — "did you ...", "have you ...",
# "didn't you ..." — anywhere in a question, so real-speech lead-ins ("hey did you ...?",
# "anyway, did you ...?", "um so have you ...?") and rambling multi-clause questions are caught
# too (the audit found "hey did you remind Jenny to send the slides at 4 like I asked" leaking a
# fabricated timed reminder). Present-tense requests to the assistant ("can you remind me ...?")
# do NOT match (no did/have/had), so they stay catchable.
_QUESTION_TO_OTHER = re.compile(
    r"\b(did|didn'?t|have|haven'?t|has|hasn'?t|had|hadn'?t|were|weren'?t|was|wasn'?t)\s+(you|u|ya)\b",
    re.I)


def _is_interrogative_aside(text: str) -> bool:
    # A "did/have you ..." completion-check aimed at the listener is silent whether or not the
    # spoken line kept its question mark ("hey did you remind Jenny to send the slides at 4 like
    # I asked" has none) — plus any start-anchored interrogative. Present-tense requests to the
    # assistant ("can you remind me ...") never match (no did/have/had aux), so they stay catchable.
    t = (text or "").strip()
    return bool(_INTERROGATIVE_ASIDE.match(t)) or bool(_QUESTION_TO_OTHER.search(t))


def _parse_iso_dt_local(value):
    """Parse an RFC3339/ISO-8601 datetime to a tz-aware UTC datetime; None if unparseable.

    Used to time-window a real calendar read for the onboarding profile. A naive value is
    treated as UTC. Anything that isn't a parseable string yields None (and so is dropped, not
    guessed) — the anti-fabrication discipline applies even to a single bad timestamp."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _iter_message_lists(value):
    """Yield each list-of-messages found one level into a Gmail read result.

    Gmail.ListThreads / ListEmails wrap their rows under a key like 'threads' / 'emails' /
    'messages'. We yield any top-level list value so the parser stays robust to the exact key
    without inventing structure. Non-dict input yields nothing."""
    if not isinstance(value, dict):
        return
    for v in value.values():
        if isinstance(v, list):
            yield v


def _gmail_counterparty(item) -> str:
    """Best-effort sender/correspondent address from a Gmail thread/email row, or "" if absent.

    Reads only fields Gmail actually returns ('from'/'sender'/'from_email'); never fabricates a
    name. Empty string when the row carries no usable address — that row then contributes no
    correspondent fact."""
    if not isinstance(item, dict):
        return ""
    for key in ("from", "sender", "from_email", "fromAddress", "from_address"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, dict):
            addr = val.get("email") or val.get("address")
            if isinstance(addr, str) and addr.strip():
                return addr.strip()
    return ""


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


# --- Semantic obligation consolidation (F-012: one real-world obligation = one card) -------------
# The moat can extract the SAME obligation from several lines — a relayed request ("Mom: call Amazon
# about the plant") plus the speaker's confirmation ("Yeah, I'll handle it" -> "handle the Amazon
# plant order") plus a reworded variant. Exact-text dedupe (_owner_card_dedupe_key) can't see these
# as the same. We collapse on an OBJECT SIGNATURE: drop filler + pronouns + time + generic light
# verbs, keep the entity/object tokens (crudely singularized). Two tasks are the same obligation when
# one object-signature CONTAINS the other (so "amazon plant" == "amazon plant order"), which merges
# the dup forms WITHOUT merging genuinely different objects ("Sarah budget" vs "Sarah deck").
_OBLIGATION_STOP = {
    # articles / pronouns / determiners
    "a", "an", "the", "this", "that", "these", "those", "it", "its", "i", "im", "me", "my", "mine",
    "you", "your", "yours", "he", "him", "his", "she", "her", "hers", "they", "them", "their",
    "we", "us", "our", "one", "some", "any",
    # prepositions / conjunctions
    "to", "for", "of", "on", "in", "at", "by", "with", "about", "from", "into", "over", "before",
    "after", "and", "or", "but", "so", "as", "up", "out", "off", "down", "re",
    # auxiliaries / modals / politeness / filler
    "is", "are", "was", "were", "be", "been", "am", "do", "does", "did", "will", "would", "can",
    "could", "should", "shall", "may", "might", "must", "please", "yeah", "yes", "yep", "ok", "okay",
    "sure", "just", "really", "gotta", "gonna", "wanna", "need", "needs", "got", "get", "gets",
    "getting", "let", "lets", "make", "makes", "making", "want", "wants", "okayy", "hey", "hi",
    "thanks", "pls", "confirm", "task", "owner",
    # generic light action verbs (the OBJECT identifies the obligation, not the verb)
    "handle", "handled", "deal", "dealt", "sort", "sorted", "take", "takes", "taking", "care",
    "look", "looks", "looking", "manage", "managed", "remember", "remind", "reminded", "set", "put",
    "go", "going", "keep", "kept", "ensure", "check",
    # time words
    "today", "tomorrow", "tonight", "now", "later", "soon", "morning", "afternoon", "evening",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "week", "weekend",
    "am", "pm",
}


def _obligation_sig(text: str) -> frozenset:
    """Object signature of a task: the entity/object tokens, filler+verbs+time stripped, crudely
    singularized. Empty when the task is too thin to key on (then it is never auto-merged)."""
    sig = set()
    for tok in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if tok in _OBLIGATION_STOP:
            continue
        if len(tok) <= 2 and not tok.isdigit():
            continue
        if len(tok) > 4:  # crude stem so plurals/tenses match: ordered->order, plants->plant
            tok = re.sub(r"(ings|ing|ed|es|s)$", "", tok)
        sig.add(tok)
    return frozenset(sig)


# Generic verbs/nouns that name HOW (communication channel) or a vague WHAT, never the obligation's
# identity. Two obligations that differ ONLY by these tokens are the SAME real obligation: the moat
# rewords a backchannel confirmation ("yeah, I'll handle it") into a synonym of the original task
# ("call Amazon about the monitor" -> "handle the Amazon monitor issue"); the identity that survives is
# the salient entity+object {amazon, monitor}, so {amazon,call,monitor} and {amazon,issue,monitor} must
# collapse to one card (anti-spam, Omar's #1). Stored in STEMMED form (matching _obligation_sig's stem)
# and kept DELIBERATELY small + concrete so genuinely different objects (monitor vs desk) never merge.
_OBLIGATION_GENERIC = {
    "call", "email", "text", "contact", "ping", "reach", "phone", "ring",
    "message", "messag", "msg", "send", "sent", "deliver", "share",
    "issue", "problem", "matter", "regard", "situation", "stuff",
}


def _obligation_core(sig: frozenset) -> frozenset:
    """The identity tokens of an obligation: salient entity/object only, with generic communication
    verbs + filler problem-nouns removed. {amazon,call,monitor} and {amazon,issue,monitor} both -> {amazon,monitor}."""
    return frozenset(t for t in sig if t not in _OBLIGATION_GENERIC)


def _same_obligation(a: frozenset, b: frozenset) -> bool:
    """Same real-world obligation when both signatures are non-empty and ANY of:
    - one SIGNATURE contains the other ("amazon plant" == "amazon plant order"); OR
    - their identity CORES are equal ("call Amazon about the monitor" == "handle the Amazon monitor
      issue" -> both core {amazon, monitor}); OR
    - the smaller core (an OBJECT-bearing core, >=2 salient tokens) is fully contained in the other —
      a reminder/followup about the SAME deliverable folds into its thread ("get Sam the revised deck"
      core {sam,revised,deck} swallows "remind me before I send the revised deck" core {revised,deck}).
      The >=2 floor stops a bare person-only core ({sam}) from over-merging two distinct tasks."""
    if not a or not b:
        return False
    if a <= b or b <= a:
        return True
    ca, cb = _obligation_core(a), _obligation_core(b)
    if not ca or not cb:
        return False
    if ca == cb:
        return True
    small, big = (ca, cb) if len(ca) <= len(cb) else (cb, ca)
    return len(small) >= 2 and small <= big


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
        # Per-person API mesh (hands/token_vault.py): back the hand with the encrypted
        # per-user token vault so a user who connected their OWN app (Gmail, a niche CRM
        # like Cosmolex) authenticates with THEIR short-lived token, not the shared
        # ARCADE_API_KEY. No connected app / absent ANTICIPY_VAULT_KEY -> safe fallback to
        # the shared key (back-compat), never a fake token. The broker is plain Python the
        # model cannot reach into; SecretToken redacts the plaintext on every leak path.
        self.token_vault = TokenVault(data_dir=base)
        self.api_hand = ApiHand(user_id=user_id, mode=hands_mode,
                                broker=TokenBroker(self.token_vault))
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

    def _owner_timezone(self) -> tuple[dt.tzinfo, str | None]:
        """Read the owner's onboarded timezone from the PROFILE drawer (the owner_identity
        item carries ``fields['timezone']``, e.g. 'America/New_York').

        Returns (tzinfo, name). When the owner has not onboarded a timezone (or it is not a
        resolvable zone), falls back to the server-local tz so grounding still works — but a
        real onboarded zone makes a press-go calendar hold carry the OWNER's offset, not the
        server's. Read-only; never writes.
        """
        for item in self.memory.profile.all():
            tz_name = str((item.fields or {}).get("timezone") or "").strip()
            if not tz_name:
                continue
            try:
                return ZoneInfo(tz_name), tz_name
            except (ZoneInfoNotFoundError, ValueError, KeyError):
                continue  # malformed onboarded zone -> fall through to server-local
        local = dt.datetime.now().astimezone().tzinfo
        return local, None

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

    def _follow_up_loop_id(self, card_id: str) -> str:
        """Stable, per-card id for the follow-up fire-site loop, so re-ingesting the same
        obligation rewrites the SAME row (INSERT OR REPLACE) — never a duplicate, never a
        second trigger firing for one obligation."""
        return f"followup:{card_id}"

    def _schedule_follow_up(self, card: dict, plan: dict, now: float) -> dict:
        """FIRE-SITE for follow-ups: turn the computed plan into a durable, fireable open_loop
        carrying remind_ts == when_ts, linked to the originating card id + its proof. The
        existing trigger system (proactive.trigger_tick -> _fire_reminder) then delivers the
        nudge at when_ts over the SAME TextChannel reminders use — no parallel scheduler.

        Returns the (possibly time-corrected) plan to surface on the card so the card and the
        ledger agree. IDEMPOTENT: if a follow-up loop already exists for this card, its
        already-scheduled when_ts is preserved (re-ingest never churns the time), and it is
        only re-armed if it has not yet fired.
        """
        card_id = card.get("id") or ""
        if not card_id:
            return plan
        loop_id = self._follow_up_loop_id(card_id)
        existing = self.memory.open_loops.get(loop_id)
        if existing is not None:
            # Already scheduled. Preserve the original when_ts (no churn). If it has already
            # fired, do NOT re-arm it — fire-once holds across re-ingests too.
            kept_when = existing.fields.get("remind_ts", plan["when_ts"])
            plan = {**plan, "when_ts": kept_when,
                    "in_days": max(0, round((kept_when - now) / (24 * 3600)))}
            return plan
        task = plan.get("note") or (card.get("source_text") or "Follow up")
        # carry the originating card's proof + id so the fired nudge is provably LINKED to the
        # exact obligation it is chasing (not a free-floating reminder).
        self.memory.open_loops.write_text(
            task,
            id=loop_id,
            fields={
                "task": task,
                "kind": "follow_up",
                "remind_ts": float(plan["when_ts"]),   # the trigger's due condition
                "follow_up_for_card_id": card_id,
                "follow_up_for_source_text": card.get("source_text") or "",
                "follow_up_reason": plan.get("reason") or "",
                "origin_proof": card.get("proof") or [],
            },
            provenance="follow_up_schedule",
            importance=0.6,
            status="open",          # active + fireable until the trigger fires it
        )
        self.glassbox.log("follow_up_scheduled",
                          {"loop_id": loop_id, "card_id": card_id,
                           "when_ts": plan["when_ts"], "in_days": plan.get("in_days"),
                           "task": task[:120]})
        return plan

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

    def _apply_force_ask(self, card: "OwnerTaskCard | None",
                         line: OwnerObservedLine) -> "OwnerTaskCard | None":
        """The cardinal-sin lever for a vent-adjacent real task (line.force_ask). Such a task is
        CAUGHT (the product is the inference) but may NEVER auto-act in the heat. Coerce any card
        into a confirm-first ASK with NO execution: a 'do' becomes 'ask', a 'blocked' money card
        stays a hard stop (money is the only line we never cross — it must not relax to a fireable
        ask), a 'remember' stays silent memory. Execution is stripped so nothing fires. A non-
        force_ask card is returned unchanged."""
        if card is None or not getattr(line, "force_ask", False):
            return card
        if card.disposition == "blocked":
            # money/wall: the hard stop is stronger than ask — keep it blocked (never executes).
            return card
        if card.disposition == "remember":
            return card   # silent durable memory only — never an act
        card.disposition = "ask"
        card.reason = card.reason or "real task voiced inside a vent — confirm before acting"
        card.execution = None   # strip any spine verdict; a vent-adjacent task never executes
        return card

    def _generic_force_ask_card(self, line: OwnerObservedLine, source: str) -> OwnerTaskCard:
        """A confirm-first ASK card for a vent-adjacent real task the regex preview didn't shape
        (a bare task like "call the dentist"). Shared by the execute spine AND the preview path so
        a preview never shows FEWER tasks than the real run catches.

        Deliberately display-only (no backing goal / no ask_id): a task voiced inside a VENT is
        HELD per the mission ("a real task voiced inside emotion is held/asked, never auto-acted in
        the heat") — surfaced so the owner sees it, but never wired to auto-execute, which keeps the
        cardinal-sin floor (safety_mega_eval: a vent must produce nothing actionable). Clean
        (non-vent) model-caught tasks get a real executable goal via the moat_task rescue instead."""
        return OwnerTaskCard(
            source=source, line_no=line.line_no, source_text=line.text,
            title=f"Confirm task: {line.text[:80]}", disposition="ask", route="voice_text",
            action="confirm_owner_task", args={"task_text": line.text}, confidence=0.7,
            reason="real task voiced inside a vent — confirm before acting",
        )

    def _confirm_task_goal(self, line: OwnerObservedLine) -> tuple[str, str, str]:
        """Build a PAUSED, resolvable goal for a model-caught task so the app's YES actually
        EXECUTES it — instead of a dead display card that does nothing on press (the "where's the
        action engine / I press yes and nothing happens" bug). Mirrors approve_remembered's proven
        funnel but leaves the goal WAITING: it is NEVER driven here (no auto-act — the cardinal-sin
        guard holds for vent-adjacent tasks), only /resolve (an explicit human YES) drives it.

        Maps the task the same way press-go does: a concrete calendar hold -> create_event (real,
        read-back-verified on YES); everything else (a call, a vague to-do) -> a write_memory
        open-loop so YES at least puts it on the durable list. Money/vent never reach here — money
        is pre-gated to a blocked card and a pure vent yields no task. Returns (ask_id, goal_id,
        would_do)."""
        import datetime as dt
        from ..live_memory.press_go import map_inferred_to_step, WHITELIST
        from .envelopes import Goal, GoalState, Step, Risk
        task = (line.text or "").strip()
        tz, _name = self._owner_timezone()
        owner_now = dt.datetime.now(tz)
        inferred = {"task": task, "people": [], "due_phrase": "", "confidence": "high"}
        mapped = map_inferred_to_step(inferred, raw_text=task, now=owner_now, tz=tz)
        intent = mapped.get("intent")
        step = mapped.get("step")
        would = mapped.get("would_do") or f"Do: {task}"
        if intent not in WHITELIST or step is None:
            # not auto-executable (a call, a message, a vague to-do) -> on YES record it as a
            # durable tracked commitment so it shows on the list; honest (we can't place the call).
            step = Step(intent="write_memory",
                        args={"kind": "open_loop", "text": task, "approved": True}, risk=Risk.low)
            would = f"Keep this on your list: {task}"
        goal = Goal(intent=task, description=would, steps=[step], state=GoalState.waiting)
        self.store.save(goal)
        ask_id = self.proactive._send_ask(goal, task, "confirm before I act", category="")
        return ask_id, goal.id, would

    @staticmethod
    def _web_start_url(task: str) -> str:
        """Pick the site for a web task from plain language. Known sites start directly there (most
        reliable); otherwise a Google search lets the agent navigate. Never the user's logged-in
        Chrome — the throwaway browser, where the runner's money/checkout/login guard applies."""
        t = (task or "").lower()
        sites = {
            "amazon": "https://www.amazon.com", "opentable": "https://www.opentable.com",
            "doordash": "https://www.doordash.com", "ubereats": "https://www.ubereats.com",
            "uber eats": "https://www.ubereats.com", "yelp": "https://www.yelp.com",
            "instacart": "https://www.instacart.com", "walmart": "https://www.walmart.com",
            "best buy": "https://www.bestbuy.com", "target": "https://www.target.com",
            "google": "https://www.google.com",
        }
        for key, url in sites.items():
            if key in t:
                return url
        return "https://www.google.com"

    def _browser_action_ask(self, line: OwnerObservedLine, source: str) -> OwnerTaskCard:
        """THE BROWSER ACTION ROUND-TRIP (Omar's centerpiece): a web task ("find me a standing desk
        on Amazon") is surfaced as a TEXTED, plain-English ask the owner answers by SMS — "Hey, I
        heard you want to … — want me to take a look? Reply YES." On YES (core.resolve) the working
        browser agent runs on the real site and the result is TEXTED back. Never auto-runs (confirm
        first); the runner's money/checkout/login guard means it can find/read but never buys."""
        task = (line.text or "").strip()
        url = self._web_start_url(task)
        # Deterministic ask id: re-ingesting the same web task reuses the SAME pending ask (and the
        # same card id), so a replayed transcript never spawns duplicate browser asks (idempotent
        # round-trip — guards the re-ingest-spam regression; see docs/agent_os/FAILURES.md F-011).
        ask_id = "br_" + hashlib.sha256(f"browser_action|{source}|{task}".encode("utf-8")).hexdigest()[:18]
        # Register the pending ask directly (resolvable by the app YES button AND by an SMS "YES");
        # category=browser_action routes the YES to the browser agent in core.resolve.
        self.proactive.pending[ask_id] = {
            "goal_id": ask_id, "action": task, "reason": "browser task — confirm before I look",
            "category": "browser_action", "browser_task": task, "browser_url": url}
        self.proactive._persist_pending()
        # Text the owner the plain-English ask NOW (bypasses the in-app suppression — for a web
        # action the owner wants the text). One ask at a time -> a bare "YES" resolves it.
        msg = (f"Hey — I heard you want to {task}. Want me to take a look and report back? "
               f"Just reply YES or NO.")
        try:
            self.text_channel.send(self._user_contact(), msg)
            self.glassbox.log("browser_ask_sent", {"ask_id": ask_id, "task": task, "url": url})
        except Exception as exc:
            self.glassbox.log("browser_ask_send_error", {"ask_id": ask_id, "error": str(exc)})
        return OwnerTaskCard(
            id=ask_id,
            source=source, line_no=line.line_no, source_text=line.text,
            title=f"Look this up for you: {task[:70]}", disposition="ask", route="browser",
            action="browser_action", args={"task_text": task, "start_url": url}, confidence=0.8,
            reason="I'll handle this on the web once you say yes",
            execution={"decision": "ask", "goal_id": ask_id, "ask_id": ask_id, "goal_state": "waiting"})

    def _support_chore_opt_out(self, line: OwnerObservedLine, source: str) -> OwnerTaskCard:
        """THE AUTONOMY LAW (AUTO_DO_WITH_OPT_OUT): a reversible external-service chore — contact a
        company / support about an order/refund/return/delivery/cancellation/issue ("call Amazon
        about that plant I ordered") — must START, not wait for a yes. This is the ANTI-approval-
        machine path: disposition=do (started), route=browser, action=browser_action (autonomy.py
        maps browser_action -> AUTO_DO_WITH_OPT_OUT), so the card shows "I'm on it … — tell me to
        stop", never a Yes/Not-now approval. A STOP control is registered (proactive.pending keyed
        by the card id, category=opt_out_stop) so /owner/stop can halt it.

        It still hard-stops at the true irreversible boundary: match_support_chore excludes any
        spend verb, money still blocks, and a third-party SEND to a person is a different class.
        In MOCK hands it prepares (shows "I'm on it (preparing) — tell me to stop"); in LIVE hands
        it drives the support/browser arm on the real site and texts the result back."""
        task = (line.text or "").strip()
        url = self._web_start_url(task)
        # Deterministic id so a replay of the same chore reuses the same card / running job.
        card_id = "oc_" + hashlib.sha256(f"opt_out|{source}|{task}".encode("utf-8")).hexdigest()[:18]
        live = self.browser_hand.mode == MODE_LIVE
        # Register the STOP control. opt_out chores run unless the owner stops them; this is what
        # /owner/stop cancels (and what the UI's STOP button hits).
        self.proactive.pending[card_id] = {
            "goal_id": card_id, "action": task, "reason": "reversible chore — started, stop me if you want",
            "category": "opt_out_stop", "browser_task": task, "browser_url": url, "stopped": False}
        self.proactive._persist_pending()
        msg = (f"On it — I'm handling \"{task}\" for you now. Tell me to stop if you'd rather I didn't.")
        try:
            self.text_channel.send(self._user_contact(), msg)
            self.glassbox.log("opt_out_started", {"card_id": card_id, "task": task, "url": url,
                                                  "live": live})
        except Exception as exc:
            self.glassbox.log("opt_out_send_error", {"card_id": card_id, "error": str(exc)})
        if live:
            # LIVE: drive the support/browser arm now (async, so it never blocks the ingest reply).
            # The result is texted back and landed on the card, exactly like the confirm-first arm.
            state = "running"
            reason = "I'm on it — tell me to stop"
            try:
                asyncio.create_task(self._run_browser_and_confirm(task, url, card_id))
            except RuntimeError:
                # no running loop (unit/preview) -> stay prepared; nothing fires
                state = "preparing"
                reason = "I'm on it (preparing) — tell me to stop"
        else:
            # MOCK hands: prepare only (no real site drive). Honest copy: preparing, opt-out open.
            state = "preparing"
            reason = "I'm on it (preparing) — tell me to stop"
        return OwnerTaskCard(
            id=card_id,
            source=source, line_no=line.line_no, source_text=line.text,
            title=f"On it: {task[:70]}", disposition="do", route="browser",
            action="browser_action",
            args={"task_text": task, "start_url": url, "opt_out": True, "stop_id": card_id},
            confidence=0.8, status=state,
            reason=reason,
            execution={"decision": "act", "goal_id": card_id, "ask_id": None,
                       "goal_state": state, "opt_out": True})

    def stop_owner_card(self, card_id: str) -> dict:
        """STOP control for an AUTO_DO_WITH_OPT_OUT chore: the owner said 'stop'. Marks the pending
        opt-out stopped (so any in-flight/queued work halts) and flips the durable card record to
        'stopped' so the board reflects it. Reversible chores are the ONLY thing this touches."""
        p = self.proactive.pending.get(card_id)
        if isinstance(p, dict) and p.get("category") == "opt_out_stop":
            p["stopped"] = True
            self.proactive.pending.pop(card_id, None)
            self.proactive._persist_pending()
        path = self.data_dir / "owner_cards" / f"{card_id}.json"
        stopped = False
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            record = None
        if isinstance(record, dict):
            record["state"] = "stopped"
            if isinstance(record.get("owner_card"), dict):
                record["owner_card"]["status"] = "stopped"
                ex = record["owner_card"].get("execution")
                if isinstance(ex, dict):
                    ex["goal_state"] = "stopped"
            try:
                path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
                stopped = True
            except Exception:
                stopped = False
            self._sync_owner_loop_status(card_id, "stopped")
        self.glassbox.log("opt_out_stopped", {"card_id": card_id, "stopped": stopped})
        return {"card_id": card_id, "stopped": stopped}

    async def _run_browser_and_confirm(self, task: str, url: str, ask_id: str) -> None:
        """Run the browser agent on the real site and TEXT the owner the result (the confirmation
        leg of the round-trip). Kicked from core.resolve on a YES so it never blocks the reply."""
        from ..hands.browser_use_link import browse_act
        self.glassbox.log("browser_action_start", {"ask_id": ask_id, "task": task, "url": url})
        # BEFORE text: tell the owner it's starting (Omar wants a message right before AND after).
        try:
            self.text_channel.send(self._user_contact(), f"On it — I'm looking into \"{task}\" on the web now. I'll text you what I find.")
        except Exception:
            pass
        res = None
        try:
            res = await asyncio.to_thread(browse_act, task, url=url, max_steps=16)
            ok = bool(getattr(res, "success", False))
            answer = (getattr(res, "result", "") or "").strip()
        except Exception as exc:
            ok, answer = False, ""
            self.glassbox.log("browser_action_error", {"ask_id": ask_id, "error": str(exc)})
        # LAND THE RESULT ON THE DURABLE CARD (parity with the API arm's read-back proof):
        # the card was flipped to 'running' on YES; now write the resolved browser receipt
        # (final url + screenshot flag/path + the answer) back onto the record and persist,
        # so the board shows the OUTCOME of the web task, not a stranded 'running'.
        final_url = (getattr(res, "url", None) or url) if res is not None else url
        screenshot = bool(getattr(res, "screenshot", False)) if res is not None else False
        screenshot_path = getattr(res, "screenshot_path", None) if res is not None else None
        self._land_browser_result_on_card(
            ask_id, success=ok, answer=answer, url=final_url,
            screenshot=screenshot, screenshot_path=screenshot_path)
        if ok and answer:
            msg = f"Done — {answer[:500]}"
        else:
            msg = (f"I tried to {task} but couldn't finish it on the site. Want me to try again "
                   f"or hand it to you?")
        try:
            self.text_channel.send(self._user_contact(), msg)
        except Exception:
            pass
        self.glassbox.log("browser_action_done", {"ask_id": ask_id, "success": ok,
                                                  "result": (answer[:200] if answer else None)})

    def _land_browser_result_on_card(self, ask_id: str, *, success: bool, answer: str,
                                     url: str | None, screenshot: bool,
                                     screenshot_path: str | None = None) -> None:
        """Write the resolved BROWSER RECEIPT onto the durable owner card record (card.id == ask_id):
        a `proof` (url + screenshot flag/path) plus a `browser_result` block (answer + success) and the
        final state (done on a real answer, else failed). This is the browser arm's equivalent of the
        API arm's `record['proof'] = goal.proof` write-back — without it the card stays at 'running'
        forever and the found result/screenshot/URL never land where the board reads them. Persists the
        record (the centerpiece path previously skipped this), and syncs the owner-loop status."""
        path = self.data_dir / "owner_cards" / f"{ask_id}.json"
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        state = "done" if (success and (answer or "").strip()) else "failed"
        proof = {
            "type": "browser_receipt",
            "url": url,
            "screenshot": bool(screenshot),
            "answer": (answer or "")[:1000],
        }
        if screenshot_path:
            proof["screenshot_path"] = screenshot_path
        record["state"] = state
        record["proof"] = proof
        record["browser_result"] = {
            "success": bool(success),
            "answer": (answer or "")[:1000],
            "url": url,
            "screenshot": bool(screenshot),
            "screenshot_path": screenshot_path,
        }
        if isinstance(record.get("owner_card"), dict):
            record["owner_card"]["status"] = state
            # Mirror the receipt onto the card body so owner_cards() surfaces it on the board.
            self._set_card_execution_proof(record["owner_card"], proof, state)
        try:
            path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
        except Exception:
            return
        self._sync_owner_loop_status(ask_id, state)
        self.glassbox.log("browser_result_on_card",
                          {"card_id": ask_id, "state": state, "success": bool(success),
                           "url": url, "screenshot": bool(screenshot)})

    @staticmethod
    def _set_card_execution_proof(owner_card: dict, proof: dict, state: str) -> None:
        """Attach the browser receipt to the card's execution block so the durable
        card carries proof (mirrors how the API arm's proof rides the card)."""
        execution = owner_card.get("execution")
        if not isinstance(execution, dict):
            execution = {}
            owner_card["execution"] = execution
        execution["proof"] = proof
        execution["goal_state"] = state

    @staticmethod
    def _timed_reminder_card(line: OwnerObservedLine, source: str,
                             capture_result: dict | None) -> OwnerTaskCard | None:
        """A self-reminder the spine has nothing to DO about right now ("take my meds at 9pm",
        "set a focus block at 2pm") is still a REAL timed reminder: the capture grounded a
        remind_ts and the trigger fires it at the due time (the 2:45-call use case). The caller
        previously marked such a line 'ignored', which DEACTIVATED its loop -> the reminder
        silently never fired. Surface it as a Ready card ('I'll remind you when it's due') and —
        critically — keep its loop ACTIVE (the caller skips the ignored-sync when this returns a
        card). Money/vent never reach here: a money line is a blocked card, a vent never captures
        an open_loop (capture's vent guard), so only a clean reversible timed task qualifies."""
        item = (capture_result or {}).get("item")
        if getattr(item, "kind", None) != "open_loop":
            return None
        fields = getattr(item, "fields", None) or {}
        if not fields.get("remind_ts"):
            return None
        return OwnerTaskCard(
            source=source, line_no=line.line_no, source_text=line.text,
            title=f"Reminder set: {line.text[:80]}", disposition="do", route="api",
            action="timed_reminder", args={"task_text": line.text,
                                            "remind_ts": fields.get("remind_ts")},
            confidence=0.8, reason="timed action — I'll remind you when it's due",
            status="open",
        )

    async def _spine_card(self, line: OwnerObservedLine, source: str, meta: dict) -> OwnerTaskCard | None:
        """F17 'one brain': the proven spine (triage -> decider -> harm-line ->
        orchestrator/hands) is the ONLY act/ask/silent decision-maker for owner
        lines. The regex classifier only shapes the durable card (title/route/args)
        and adds silent memory; it can no longer act or ask on its own. Money-shaped
        browser lines stay pre-gated blocked: never the spine's execution path,
        never /pending, never executed (the harm-line stance is final) — but a
        money-flavored line the spine's OWN triage confidently vents stays silent
        exactly as it would on the default path (F23)."""
        # VENT-ADJACENT REAL TASK (force_ask): the model pulled this real task out of a vented
        # breath. It must be SURFACED as a confirm-first ask, but the spine must NEVER EXECUTE it
        # in the heat (that is the exact path a prior attempt used to re-introduce the cardinal
        # sin). So we DO NOT run the executing spine here at all: shape a durable ask card from the
        # regex preview (or a generic ask) and return it un-executed. Money still pre-gates blocked.
        if getattr(line, "force_ask", False):
            shaped = self.owner_mode.card_for_line(line, source)
            if shaped is not None and shaped.disposition == "blocked":
                return shaped   # money hard stop owns it; never executes
            if shaped is not None and shaped.disposition == "remember":
                return shaped   # silent memory only
            if shaped is not None:
                shaped.disposition = "ask"
                shaped.reason = "real task voiced inside a vent — confirm before acting"
                shaped.execution = None   # vent-adjacent task is HELD (display-only), never auto-acts
                return shaped
            return self._generic_force_ask_card(line, source)
        shaped = self.owner_mode.card_for_line(line, source)
        if shaped is not None and shaped.disposition == "blocked":
            # A real MONEY line must ALWAYS surface as blocked ("Left for you") — money is the hard
            # stop and must be VISIBLE, never silently dropped. card_for_line's is_vent guard already
            # drops money-FLAVORED VENTS before they ever become a blocked card; the old
            # triage.actionable() gate here ADDITIONALLY dropped REAL money lines that triage
            # misjudged as not-actionable, so "refund the customer $50" / "reimburse the client 1100"
            # VANISHED on the execute path while preview correctly blocked them (relentless bug-hunt).
            # Keep only the vent-shape belt-and-suspenders: a genuine vent shape stays silent, every
            # real money line surfaces as a non-executing blocked card. Money never executes either way.
            from ..live_memory.review_infer import is_vent_shape as _ivs2
            if _ivs2(line.text):
                return None
            return shaped
        # THE AUTONOMY LAW (SEAM 1): a reversible external-service chore — contact a company /
        # support about an order/refund/return/delivery/cancellation/issue ("call Amazon about that
        # plant I ordered") — must START, not wait for a yes. It is NOT an approval ask: route it to
        # the support/browser arm as AUTO_DO_WITH_OPT_OUT ("I'm on it — tell me to stop"). Checked
        # AFTER the money pre-gate so money/pay/checkout still BLOCKS first; match_support_chore
        # itself excludes any spend verb, and a third-party SEND to a person is a different class
        # (it carries no company+issue pair). Runs only on the executing spine path (not preview).
        from ..shared.support_chore import match_support_chore
        if match_support_chore(line.text) is not None:
            self.glassbox.log("support_chore_opt_out",
                              {"line": line.text[:140], "reason": "reversible service chore -> AUTO_DO_WITH_OPT_OUT"})
            return self._support_chore_opt_out(line, source)
        # INTERNAL NOTE (SEAM 3): "the retainer note is in the CRM" is reversible internal admin, not
        # money. owner_mode shaped it as a confident do (prepare_internal_note). There is no generic
        # CRM/notes arm wired yet, so the honest AUTO_DO is to PREPARE the note (capture what we'd
        # write) and surface it as a do-card — never a money block, never a dead clarify. Handled
        # directly (not via the decider, which silences this loose admin phrasing -> the moat_task
        # rescue then mislabels it a clarify). The capture path already wrote the line as durable
        # memory; _persist_card records the prep with read-back proof.
        if shaped is not None and shaped.action == "prepare_internal_note":
            self.glassbox.log("internal_note_prepared",
                              {"line": line.text[:140],
                               "reason": "internal note/record -> reversible admin (no money)"})
            shaped.disposition = "do"
            shaped.reason = ("CRM/notes not connected — I've kept the note text ready; "
                             "I'd write this in the record")
            shaped.execution = {"decision": "act", "goal_id": None, "ask_id": None,
                                "goal_state": "open", "internal_note": True}
            return shaped
        if shaped is not None and shaped.action == "find_or_cart_without_purchase":
            # PREPARE WHEN CONFIDENT (Omar's law, 2026-06-16 decision): if memory/onboarding resolves
            # the exact item + store, auto-prepare the cart — it falls through to execute as a
            # browse_task in a THROWAWAY browser (the runner's money/checkout guard means it can
            # find/cart but NEVER buys) and carries a memory_resolution receipt. When the item/source
            # is NOT resolvable, fall back to the confirm-first browser round-trip (Omar's centerpiece):
            # ONE deterministic texted ask, answered by YES — no duplicate ask, no stray goal (F-011).
            ctx = await self.bus.submit_job(Job(intent="read_context", args={"about": line.text}))
            if not self._has_external_context(ctx.output, line.text):
                return self._browser_action_ask(line, source)
            # Resolved -> mark so the confirm-first gate SKIPS it; fall through to auto-execute below.
            shaped.args["resolved_cart"] = True
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
        # THE MODEL DRIVES (Omar's core directive): the MOAT confidently extracted this as a clean
        # real task, but the deterministic regex triage just voted SILENT because the phrasing is
        # loose ("call mom", "do that email of the thing next weekend"). A regex must NEVER silently
        # VETO a model-caught task into nothing — that is the exact failure ("you keep dropping the
        # real tasks because they aren't phrased like a command"). Surface the model's catch as a
        # confirm-first ASK. The ONLY hard overrides stay: the spine BLOCKED it (money/wall ->
        # decision != ignore, handled above) or the deterministic vent/harm floor flags it a vent or
        # money/detrimental line — those stay silent. Never an auto-act.
        # Rescue on ANY silent outcome (ignore / suppressed / deferred), not just "ignore": the
        # decider model returns these intermittently for the same loose self-commitment, which made
        # a real task drop ~1-in-5 runs (audit gap). "blocked" is the money/wall hard-stop and is
        # the ONE silent-branch decision we never rescue (handled by the category!=money guard too).
        if getattr(line, "moat_task", False) and decision != "blocked":
            from ..live_memory.review_infer import is_vent_shape
            if not is_vent_shape(line.text):
                verdict = self.proactive.harm.assess(line.text, {})
                # MONEY is the only hard-stop that must never surface as an actionable ask
                # (it stays blocked/Left-for-you). Every other harm category (binding_send=email,
                # casual_send, auth_wall, unclassified=call/book/sort-out) is exactly a
                # confirm-first ASK — surface it, don't drop it. (detrimental=True covers ALL of
                # these, which is why gating on it wrongly suppressed real tasks.)
                if getattr(verdict, "category", None) != "money":
                    self.glassbox.log("moat_task_rescued",
                                      {"line": line.text[:140],
                                       "reason": "model caught a real task the triage silenced"})
                    # back it with a PAUSED resolvable goal so the app's YES actually executes it
                    # (real calendar hold / tracked commitment) — never a dead display card.
                    ask_id, goal_id, _w = self._confirm_task_goal(line)
                    return OwnerTaskCard(
                        source=source, line_no=line.line_no, source_text=line.text,
                        title=f"Confirm task: {line.text[:80]}", disposition="ask",
                        route="voice_text", action="confirm_owner_task",
                        args={"task_text": line.text}, confidence=0.7,
                        reason="caught this from how you said it — confirm before I act",
                        execution={"decision": "ask", "goal_id": goal_id,
                                   "ask_id": ask_id, "goal_state": "waiting"})
        # spine says silent: regex shaping may still add SILENT memory (a remember
        # card or a durable open-loop record) — never a paper act or ask
        if shaped is None:
            return None
        if shaped.disposition != "remember":
            shaped.execution = execution
        return shaped

    async def _expand_tasks_with_model(self, observed):
        """THE MOAT — the REAL anti-spam: the brain surfaces only what is genuinely there, so there
        is nothing to throttle. For each observed line the funded model splits it into its distinct
        tasks AND judges the whole breath vent-or-not (the nuanced call a regex cannot make). A
        VENTED line yields NOTHING (emotion only suppresses — the cardinal-sin guard at the model
        layer). A clean multi-task line yields ONE candidate per task ("call the dentist, book
        dinner, email Sarah" -> 3, the catch-rate win). Model unavailable (stub/error) -> the line
        passes through UNCHANGED, so the deterministic path and the whole test suite are untouched.
        Every emitted task still runs the full downstream pipeline (triage vent-guard + harm-line),
        so the model is the PRIMARY guard with the deterministic guards as a backstop."""
        if self.gateway.provider != PROVIDER_OPENROUTER:
            return observed
        from ..proactive.extract import extract
        out, n = [], 0
        # Rolling CONTEXT of the earlier lines in this same transcript, so the model can resolve
        # vague references in a later line ("that thing" -> "the Henderson contract" named earlier).
        # Bounded to the last few lines (recent referents); empty for a single-line/proactive call,
        # which keeps that path (and the safety eval) byte-identical to before.
        prior_lines: list[str] = []
        for line in observed:
            context = "\n".join(prior_lines[-8:])
            prior_lines.append(line.text)
            # DETERMINISTIC ASIDE FLOOR: a question to someone else ("Did you grab the dry
            # cleaning?") is never the owner's task. Drop it BEFORE the model can strip the
            # interrogative wrapper and over-extract a bare imperative -> an ASK on a vent/aside.
            if _is_interrogative_aside(line.text):
                self.glassbox.log("extract_aside_silenced", {"line": line.text[:140]})
                continue
            try:
                res = await extract(self.gateway, line.text, context=context)
            except Exception:
                res = None
            if res is None or not res.available:
                n += 1
                out.append(OwnerObservedLine(line_no=n, text=line.text))   # deterministic fallback
                continue
            if res.vent:
                # The breath carries emotion — but the model may have separated a REAL task from
                # the vent itself ("email Sarah the budget" inside "...I should just quit..."). The
                # product is the inference: those real tasks must STILL be caught. They are emitted
                # as force_ask lines so the spine/preview can only ASK (confirm-first) and NEVER
                # auto-act in the heat. A PURE vent (no real task) yields [] here -> nothing surfaces,
                # exactly as before (the cardinal-sin guard holds). The vent clause itself is never
                # emitted as a task by the model, so it produces no card.
                vent_tasks = res.vent_adjacent_tasks()
                if not vent_tasks:
                    self.glassbox.log("extract_vent_silenced", {"line": line.text[:140]})
                    continue   # pure vent -> no card
                for t in vent_tasks:
                    n += 1
                    out.append(OwnerObservedLine(line_no=n, text=t["task"], force_ask=True))
                self.glassbox.log("extract_vent_tasks_held",
                                  {"line": line.text[:140],
                                   "tasks": [t["task"] for t in vent_tasks]})
                continue
            tasks = res.actionable()
            if not tasks:
                n += 1
                out.append(OwnerObservedLine(line_no=n, text=line.text))   # thin read -> don't lose the line
                continue
            # NOTE: do NOT gate clean tasks on triage.actionable() here. The triage marks a RELAYED
            # or IMPLIED task ("Maya said can you pick up Leila at 3:15", "my sister mentioned mom's
            # prescription needs picking up Friday") as non-actionable too — and those are EXACTLY
            # the unspoken tasks the MOAT exists to catch (the product). Gating on triage silenced
            # them. The aside/report-vs-task distinction is the MOAT model's job (extract.py prompt);
            # the cheap deterministic floor here is only the narrow interrogative-aside guard above.
            for t in tasks:
                n += 1
                out.append(OwnerObservedLine(line_no=n, text=t["task"], moat_task=True))
            self.glassbox.log("extract_tasks", {"line": line.text[:140],
                              "tasks": [t["task"] for t in tasks]})
        return out

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
        # Asks caught from THIS app paste show in-app ("Waiting for your yes"); they must NOT also
        # SMS the owner (that is the banned spam — every task buzzing the phone). Suppress ask
        # delivery for the duration of the ingest; time-due reminders (trigger_tick) still text.
        self.proactive._suppress_ask_delivery = True
        try:
            out = await self._owner_ingest_inner(
                source, text, meta, execute_actions, observed=None)
        finally:
            self.proactive._suppress_ask_delivery = False
        # PROACTIVE FIND-NOTIFICATION (owner directive): when the engine FINDS something it can't act
        # on without the owner's okay — money (the hard stop), a send to a person, anything
        # irreversible — it must IDENTIFY it and TELL the owner over text, in real human words (never
        # a canned script), and it CANNOT act without their explicit approval. ONE consolidated heads-
        # up (no per-item flood). Words only — nothing is executed here. Only for AMBIENT capture
        # (mic / audio / listening / pendant) where the owner isn't already watching the app; a typed
        # in-app paste shows the same finds in the UI, so we don't double-buzz the phone. Best-effort:
        # a notify failure never breaks ingest.
        _AMBIENT = {"mac_mic", "start_listening", "audio_upload", "mp3", "pendant_phone"}
        if execute_actions and source in _AMBIENT:
            try:
                from ..proactive.agent_reply import notify_finds
                msg = await notify_finds(self.gateway, out.get("cards") or [])
                if msg and self.text_channel.configured():
                    sent = self.text_channel.send(self._user_contact(), msg)
                    self.glassbox.log("finds_notified",
                                      {"to": self._user_contact(), "text": msg,
                                       "live": (sent or {}).get("mock") is False})
            except Exception as e:  # pragma: no cover - never let a notify break ingest
                self.glassbox.log("finds_notify_failed", {"error": str(e)})
        return out

    def _intent_resolve(self, observed, raw_lines):
        """GATE MIDDLE-1: intent-shaped memory handoff. Build ranked INTENT THREADS from the raw
        transcript, resolve each task's VAGUE reference against them ("that desk thing" -> the Jarvis
        standing desk, not Mia pickup; "send it" -> the Sam deck), and drop preference/referent
        statements from the action path (remembered, never a card). An ambiguous reference is left
        un-resolved so the downstream asks the smallest clarification — never a wrong guess.
        Returns (filtered_observed, middle_trace) with the seven proof fields per resolution."""
        from ..proactive.intent_threads import (
            build_threads, classify, resolve_reference, _head_noun, _is_bare_ref,
        )
        threads = build_threads(raw_lines)
        captured = [{"text": t.text, "kind": t.kind} for t in threads]
        resolutions, kept = [], []
        for line in observed:
            text = getattr(line, "text", "") or ""
            if classify(text) == "preference":
                resolutions.append({"line": text, "kind": "preference",
                                    "decision": "remembered as referent — no card"})
                continue
            if _head_noun(text) or _is_bare_ref(text):
                self_idx = next((t.idx for t in threads if t.text == text), len(threads))
                resolved, tr = resolve_reference(text, threads, self_idx)
                if resolved != text:
                    line.text = resolved
                resolutions.append({
                    "line": text, "resolved_to": resolved, "head": tr.get("head"),
                    "ranked_candidates": tr.get("candidates"), "chosen_referent": tr.get("chosen"),
                    "rejected_referents": tr.get("rejected"),
                    "decision": "resolved" if resolved != text else "ambiguous — ask smallest clarification",
                })
            kept.append(line)
        trace = {"captured_memories": captured, "resolutions": resolutions}
        try:
            self.glassbox.log("intent_middle_trace", trace)
        except Exception:
            pass
        return kept, trace

    @staticmethod
    def _consolidate_obligations(observed):
        """F-012 anti-spam: collapse moat-expanded lines that name the SAME real-world obligation so
        one obligation yields one card. "Mom: call Amazon about the plant" + "Yeah, I'll handle it"
        (-> "handle the Amazon plant order") + a reworded variant all share the object signature
        {amazon, plant} and collapse to ONE line (the earliest/original wording kept). Genuinely
        different objects never merge. Safety is preserved: if ANY clustered line is vent-adjacent
        (force_ask), the kept line stays force_ask (the vent guard can only get stricter, never lost).
        Thin/empty-signature lines are never auto-merged (kept as-is)."""
        kept = []          # list of [line, sig]
        for line in observed:
            sig = _obligation_sig(getattr(line, "text", ""))
            merged = False
            if sig:
                for entry in kept:
                    if _same_obligation(sig, entry[1]):
                        # fold into the existing obligation; propagate the stricter guards
                        if getattr(line, "force_ask", False):
                            entry[0].force_ask = True
                        if getattr(line, "moat_task", False):
                            entry[0].moat_task = True
                        # keep the broader signature so further variants still match
                        entry[1] = entry[1] | sig
                        merged = True
                        break
            if not merged:
                kept.append([line, sig])
        return [entry[0] for entry in kept]

    async def _owner_ingest_inner(self, source, text, meta, execute_actions, observed=None):
        raw_observed = self.owner_mode.observe(text)
        raw_lines = [l.text for l in raw_observed]
        observed = await self._expand_tasks_with_model(raw_observed)   # THE MOAT: model splits + judges
        # DETERMINISTIC VENT-ADJACENT BACKSTOP: when the moat fails to split a vent-prefixed line
        # ("ugh my brain is fried, but remind me to send Maya the email before Friday") into its
        # embedded obligation, the cardinal-sin guard would drop the whole line and the real task
        # is lost (the lone 'mixed' miss in the 10k cert). If a vented line carries a CONCRETE
        # directed task (a send to a NAMED person, or a pickup with a time), mark it force_ask so
        # the proven held-ask path surfaces it as a confirm-first ASK — never an auto-act, so the
        # vent floor is preserved. Tight signal: a pure emotional vent never qualifies.
        from ..live_memory.review_infer import is_vent as _is_vent
        from ..owner_mode import vent_adjacent_directed_task as _vent_adj
        for _ln in observed:
            if (not getattr(_ln, "force_ask", False)
                    and _is_vent(_ln.text) and _vent_adj(_ln.text)):
                _ln.force_ask = True
        # PRESERVE THE NO-BUY BOUND THROUGH THE MOAT (narrow + safe): the owner's explicit "...put it in
        # the cart, DON'T buy it" is a deliberate purchase ceiling that should keep a money-flavored
        # shopping line as a reversible CART-PREP, not the money wall. The moat sometimes rewords the
        # line and DROPS "don't buy it" -> it wrongly becomes BLOCKED/Left-for-you (surfaced by GUI
        # testing of "standing desk under $400 ... don't buy it"). ONLY when the whole day is a SINGLE
        # shopping line that lost a stated no-buy bound do we re-attach it (the unambiguous case);
        # multi-line days are left untouched so a no-buy on one item never leaks onto an unrelated
        # shopping/order line. Conservative: can only ever push toward NO-purchase, never toward buying.
        from ..owner_mode import _BROWSER as _BROWSER_RE, _NO_BUY as _NO_BUY_RE
        _shop = [l for l in observed if _BROWSER_RE.search(l.text)]
        if (len(observed) == 1 and len(_shop) == 1
                and _NO_BUY_RE.search("\n".join(raw_lines)) and not _NO_BUY_RE.search(_shop[0].text)):
            _shop[0].text = _shop[0].text.rstrip(". ") + " — don't buy it"
        observed, middle_trace = self._intent_resolve(observed, raw_lines)  # GATE MIDDLE-1: ranked recall
        observed = self._consolidate_obligations(observed)   # F-012: one real obligation = one card
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
                    cards.append(self._apply_force_ask(existing, line))
                    continue
            if execute_actions:
                card = await self._spine_card(line, source, meta)
            else:
                card = preview
                # PREVIEW == REALITY: a vent-adjacent real task whose regex preview is empty (a bare
                # "call the dentist") still surfaces as a confirm-first ask, exactly as the execute
                # spine catches it — so a preview never shows FEWER tasks than the real run would.
                if card is None and getattr(line, "force_ask", False):
                    card = self._generic_force_ask_card(line, source)
                # PREVIEW == REALITY (moat_task): the model CONFIDENTLY caught a real task the regex
                # didn't shape ("remind me to refill the inhaler", "send the deck to Sequoia by EOD",
                # "cancel the WeWork"). On the EXECUTE path _spine_card's moat-task rescue surfaces it
                # as a confirm-first ask; PREVIEW must do the SAME or it silently DROPS real tasks and
                # shows fewer than the live run (the 'you keep dropping my tasks' bug, found by the
                # relentless bug-hunt: ~half of moat_task lines vanished in preview). Mirror the execute
                # conditions exactly: not a vent shape, and not the money wall (money stays blocked via
                # card_for_line's interlock above / handled below; never auto-acted).
                elif card is None and getattr(line, "moat_task", False):
                    from ..live_memory.review_infer import is_vent_shape as _ivs
                    if not _ivs(line.text):
                        _verdict = self.proactive.harm.assess(line.text, {})
                        if getattr(_verdict, "category", None) != "money":
                            card = self._generic_force_ask_card(line, source)
            # A vent-adjacent real task (force_ask) may be CAUGHT but NEVER auto-act in the heat:
            # downgrade any do/blocked-money to a confirm-first ASK and strip any execution. This
            # is the absolute lever that keeps a vent from ever producing an act (the cardinal sin).
            card = self._apply_force_ask(card, line)
            # BROWSER ACTION (Omar's centerpiece): a web task ("find me a standing desk on Amazon")
            # becomes a TEXTED plain-English ask; on YES (app or SMS) the browser agent runs on the
            # real site and texts the result. Money browser cards stay blocked (never reach here as
            # a do/ask). Only on the real execute path; not for a vent-adjacent held card.
            if (execute_actions and card is not None
                    and getattr(card, "route", None) == "browser"
                    and getattr(card, "disposition", None) not in ("blocked", "remember")
                    and getattr(card, "action", None) != "browser_action"
                    and not (getattr(card, "args", None) or {}).get("resolved_cart")
                    and not getattr(line, "force_ask", False)):
                # An UNRESOLVED web task (no confident item/store) becomes ONE deterministic
                # confirm-first browser ask. A RESOLVED cart (args.resolved_cart) skips this and
                # auto-prepares the cart (Omar's "prepare when confident"). One web task -> one ask;
                # the deterministic ask id keeps re-ingest idempotent. See docs/agent_os/FAILURES.md F-011.
                card = self._browser_action_ask(line, source)
                cards.append(card)
                continue
            if card is None:
                # A self-reminder the spine silences NOW ("take my meds at 9pm") is still a real
                # TIMED reminder when the capture grounded a remind_ts: show it as Ready and KEEP
                # its loop active so the trigger fires it — never deactivate it (that silently
                # killed the 2:45-call use case). Only fires on execute (preview has no capture).
                if execute_actions:
                    rcard = self._timed_reminder_card(
                        line, source, captured_by_line.get(line.line_no))
                    if rcard is not None:
                        self.glassbox.log("timed_reminder_kept",
                                          {"line": line.text[:140],
                                           "remind_ts": rcard.args.get("remind_ts")})
                        cards.append(rcard)
                        continue
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
        out = result.model_dump(mode="json")
        out["middle_trace"] = middle_trace   # GATE MIDDLE-1 proof (captured memories + resolutions)
        # Autonomy mode per card (packet 02): the chosen mode + why, for product + certification.
        from ..proactive.autonomy import classify_autonomy
        from ..proactive.follow_up import plan_follow_up
        import time as _time
        _now = _time.time()
        # FOLLOW-UP SCHEDULING (packet 06): an obligation whose outcome depends on someone else gets a
        # follow-up check, surfaced on the card AND scheduled as a durable, fireable open_loop so the
        # SAME trigger system that fires reminders delivers the nudge at when_ts. Conservative —
        # never for vents/prefs/money. Idempotent: a re-ingest of the same line reuses the existing
        # scheduled when_ts (no churn) and never double-schedules (stable loop id per card).
        for c in out.get("cards", []):
            fu = plan_follow_up(c, _now)
            if fu:
                # write/refresh the fire-site loop FIRST so the persisted (preserved) when_ts is
                # the one surfaced on the card — the card and the ledger never disagree.
                fu = self._schedule_follow_up(c, fu, _now)
                c["follow_up"] = fu
        # NO-SELF-ATTESTATION INVARIANT (cert floor): a card may NOT be 'done'/auto-acted without
        # independent read-back proof. If an action path emitted a do-card with empty proof (a rare
        # nondeterministic slip), it is NOT done — downgrade to a confirm-first ask so "done" always
        # means proven. Structurally prevents the "auto-done with no proof" critical.
        for c in out.get("cards", []):
            # ONLY a card that CLAIMS it executed (decision==act) without proof is a violation.
            # A held/vent-adjacent card (execution None / decision != act) is legitimately proof-less
            # and must NOT be touched (flipping it would make a vent produce an ask — a cardinal breach).
            # An AUTO_DO_WITH_OPT_OUT chore is legitimately IN FLIGHT (started, not done) — it is not
            # claiming a verified 'done', so it is exempt (flipping it back to an ask is the exact
            # approval-machine bug the autonomy law forbids).
            if (c.get("execution") or {}).get("opt_out"):
                continue
            if (c.get("execution") or {}).get("decision") == "act" and not c.get("proof"):
                c["disposition"] = "ask"
                ex = dict(c.get("execution") or {})
                ex["decision"] = "ask"
                c["execution"] = ex
                c["status"] = "open"
                c["reason"] = "prepared, but I couldn't verify it was done — confirm before relying on it"
        autonomy = []
        for c in out.get("cards", []):
            a = classify_autonomy(c)
            c["autonomy_mode"] = a["mode"]
            c["autonomy_why"] = a["why"]
            # SEAM 2: PERSIST autonomy_mode (+ why) onto the DURABLE card record. classify_autonomy
            # runs here, AFTER _persist_card wrote the record — so the record (what GET /owner/cards
            # returns, which the UI board reads) carried autonomy_mode=None. Stamp it onto the record
            # now so the board can pick the lane/verb (the "On it — you can stop me" vs Yes/Not-now
            # split). Best-effort: a missing record (preview / replay) is simply skipped.
            if execute_actions:
                self._stamp_autonomy_on_record(c.get("id"), a["mode"], a["why"])
            # full classification proof (packet 02): input span, chosen mode, REJECTED modes,
            # action plan, result, proof types.
            autonomy.append({
                "input_span": (c.get("source_text") or "")[:120],
                "chosen_mode": a["mode"], "why": a["why"], "rejected_modes": a["rejected"],
                "action_plan": {"route": c.get("route"), "action": c.get("action")},
                "result": c.get("disposition"),
                "proof": [p.get("type") for p in (c.get("proof") or []) if isinstance(p, dict)],
            })
        out["middle_trace"]["autonomy"] = autonomy
        return out

    def _stamp_autonomy_on_record(self, card_id: str | None, mode: str, why: str) -> None:
        """Write the classified autonomy mode (+why) onto the durable owner-card record so
        GET /owner/cards (the board source of truth) carries it. Idempotent; best-effort."""
        if not card_id:
            return
        path = self.data_dir / "owner_cards" / f"{card_id}.json"
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(record, dict):
            return
        record["autonomy_mode"] = mode
        if isinstance(record.get("owner_card"), dict):
            record["owner_card"]["autonomy_mode"] = mode
            record["owner_card"]["autonomy_why"] = why
        try:
            path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
        except Exception:
            return

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
            captured_loop = (capture_result or {}).get("item")
            loop_fields = {**fields, "title": card.title}
            # DEDUPE — one dictated task -> exactly ONE active+fireable open_loop.
            # The capture path (capturer.capture, run first in owner_ingest) already wrote
            # a RAW open_loop for this same line whenever the line is a commitment shape; it
            # carries the spoken due/remind grounding and is the live reminder. This
            # card-persist path also writes an open_loop (the card-board record). With BOTH
            # active for the same task the backlog showed it twice and the trigger (which
            # scans every active loop) could fire two reminders. FIX: when a raw capture
            # loop already exists for this line, designate IT as the single authoritative
            # active+fireable row and mark THIS owner-card loop a dedupe echo of it — kept
            # for the card board + status sync, but suppressed from the backlog and stamped
            # fired_at so it can never double-fire the trigger. When no raw capture loop
            # exists (a line the spine caught that capture did not shape as a commitment),
            # this owner-card loop is the only row and surfaces/fires normally.
            has_capture_loop = getattr(captured_loop, "kind", None) == "open_loop"
            if has_capture_loop:
                # explicit linkage via the capture path's stable content key (capture.py),
                # not just text equality — the two writers now coordinate on a shared key
                loop_fields["deduped_by_capture_loop"] = captured_loop.id
                loop_fields["capture_key"] = (captured_loop.fields or {}).get("capture_key")
                loop_fields.setdefault("fired_at",
                                       dt.datetime.now(dt.timezone.utc).timestamp())
            item = self.memory.open_loops.write_text(
                card.source_text,
                fields=loop_fields,
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
        elif execution.get("opt_out"):
            # AUTO_DO_WITH_OPT_OUT (SEAM 1): a reversible external-service chore that STARTED (not an
            # approval ask). There is no paused goal — the work is in flight (live) or prepared
            # (mock); the card carries its own preparing/running state. Honor it and record a START
            # receipt so the no-self-attestation invariant (which flips a proof-less act->ask) does
            # NOT mistake an in-flight chore for an unproven 'done'. The browser arm lands the real
            # receipt on the record when it finishes (live), exactly like the confirm-first arm.
            state = card.status or execution.get("goal_state") or "preparing"
            card.proof.append({"type": "opt_out_started",
                               "goal_id": execution.get("goal_id"),
                               "state": state, "stop_id": (card.args or {}).get("stop_id")})
            card.proof.append({"type": "engine_execution", **execution})
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

    async def onboard_scan_api(self) -> dict:
        """SERVER-SIDE onboarding — the reliable 'it knows you' step, no Chrome-extension round-trip.
        Discovers the user's CONNECTED accounts straight from the live API mesh (the vault holds
        their real OAuth tokens) and feeds them to the per-person mesh via the same onboard_discover
        path (source 'api_scan'). A connected account is real and provable — Anticipy already acts
        through it — so this is honest onboarding, not a Chrome scrape pretending to be one."""
        uid = self.api_hand.user_id
        # service label -> a representative Arcade tool whose authorization == the account being
        # connected. (Live API runs through Arcade's managed OAuth, not the local vault, so the
        # vault can be empty while the account is fully connected — authorize is the real signal.)
        PROBE = {"Google Calendar": "GoogleCalendar.ListEvents", "Gmail": "Gmail.ListEmails",
                 "Slack": "Slack.SendMessageToChannel", "Notion": "Notion.GetPageContentById"}
        discovered = []
        if self.api_hand.mode == MODE_LIVE:
            try:
                client = self.api_hand._client_or_build()
            except Exception as exc:
                client = None
                self.glassbox.log("onboard_scan_api_error", {"error": f"{type(exc).__name__}: {exc}"})
            if client is not None:
                for label, tool in PROBE.items():
                    try:
                        auth = client.tools.authorize(tool_name=tool, user_id=uid)
                        if getattr(auth, "status", None) == "completed":
                            # Arcade CONFIRMED connected -> mark connected (the local vault is empty
                            # in managed-OAuth mode, so 'connected' tells the mesh the truth).
                            discovered.append({"service": label, "logged_in": True, "connected": True})
                    except Exception:
                        continue   # a single service probe failing must never abort onboarding
        # fall back to any locally-vaulted services too (covers a vault-backed deployment)
        for key, label in {"gmail": "Gmail", "googlecalendar": "Google Calendar",
                           "slack": "Slack", "notion": "Notion"}.items():
            if self.token_vault.has(uid, key) and not any(d["service"] == label for d in discovered):
                discovered.append({"service": label, "logged_in": True})
        result = await self.onboard_discover(discovered, source="api_scan")
        # Now that the CONNECTED accounts are known, actually READ them and derive honest
        # profile facts so the brain knows the user from day one (the North Star). Best-effort:
        # a read failure must never crash onboarding. Each fact traces to a real read — if the
        # reads come back thin, we invent NOTHING and say so verbatim (the cardinal-sin guard).
        try:
            profile_facts = await self._read_onboarding_profile()
        except Exception as exc:  # noqa: BLE001 — onboarding must survive any read failure
            self.glassbox.log("onboard_scan_api_profile_error",
                              {"error": f"{type(exc).__name__}: {exc}"})
            profile_facts = []
        result["profile_facts"] = profile_facts
        if not profile_facts:
            # Thin-data: surface the exact honest line. NOTHING was invented.
            result["profile_summary"] = "No facts assembled. Nothing was invented."
        self.glassbox.log("onboard_scan_api", {"connected": len(discovered),
                          "services": [d["service"] for d in discovered], "mode": self.api_hand.mode,
                          "profile_facts": len(profile_facts)})
        result["scan"] = "api"
        return result

    async def _read_onboarding_profile(self) -> list:
        """READ the user's real connected accounts through the live api_hand and derive a few
        HONEST profile facts so the brain knows the user from day one. The onboarding cardinal
        sin is fabricating a fact: every fact returned here traces to real read data — we derive
        NOTHING from nothing. If the reads are empty/error/not-connected, we return [] and invent
        nothing (the caller then surfaces "No facts assembled. Nothing was invented.").

        Reads (via api_hand): read_calendar -> GoogleCalendar.ListEvents,
        read_contacts -> Gmail.ListThreads, read_email -> Gmail.ListEmails. Each read returns its
        artifact in Result.output['value']; a not-connected account comes back needs_human and is
        simply skipped (no fact, no crash). The derived facts are WRITTEN to the profile drawer
        (the same path owner onboarding uses) and the list is returned."""
        facts: list[dict] = []

        cal_value = await self._onboarding_read_value("read_calendar")
        facts.extend(self._calendar_profile_facts(cal_value))

        contacts_value = await self._onboarding_read_value("read_contacts")
        email_value = await self._onboarding_read_value("read_email")
        facts.extend(self._correspondent_profile_facts(contacts_value, email_value))

        written = [self._write_profile_fact(f) for f in facts]
        return [w for w in written if w is not None]

    async def _onboarding_read_value(self, intent: str):
        """Run ONE real read via the live api_hand and return its artifact value, or None.

        None means: the read failed, the account is not connected (needs_human / connect), or the
        artifact was empty. A None never becomes a fact — that is the anti-fabrication guard. Never
        raises (best-effort): any exception degrades to None so onboarding can't crash on a read."""
        try:
            job = Job(intent=intent)
            result = await self.api_hand.handle(job)
        except Exception as exc:  # noqa: BLE001 — a single read must never abort onboarding
            self.glassbox.log("onboard_profile_read_error",
                              {"intent": intent, "error": f"{type(exc).__name__}: {exc}"})
            return None
        # Only a real success carries an artifact. needs_human (account not connected) /failed
        # carry no value, so they contribute no facts — exactly the thin-data path.
        if result.status != JobStatus.success:
            return None
        value = (result.output or {}).get("value")
        if isinstance(value, str):
            # Reads normally return a dict; a stringified value is unparseable structure -> no fact.
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                return None
        return value if isinstance(value, dict) else None

    def _calendar_profile_facts(self, value) -> list:
        """Honest facts from a REAL GoogleCalendar.ListEvents read. Empty/missing -> no facts.

        We count events in the NEXT TWO WEEKS (a claim we can stand behind), name the busiest
        weekday in that window, and — only when someone genuinely RECURS (appears as a non-self
        attendee on >= 2 events) — name the most frequent contact. Each fact carries its own
        evidence count so it can never outrun the data."""
        if not isinstance(value, dict):
            return []
        events = value.get("events")
        if not isinstance(events, list) or not events:
            return []
        import collections
        now = dt.datetime.now(dt.timezone.utc)
        horizon = now + dt.timedelta(days=14)
        in_window = 0
        weekday = collections.Counter()
        attendees: "collections.Counter" = collections.Counter()
        for ev in events:
            if not isinstance(ev, dict):
                continue
            start = ev.get("start") or {}
            raw = start.get("dateTime") or start.get("date") if isinstance(start, dict) else None
            when = _parse_iso_dt_local(raw)
            if when is not None and now <= when <= horizon:
                in_window += 1
                weekday[when.strftime("%A")] += 1
            for att in (ev.get("attendees") or []):
                if not isinstance(att, dict):
                    continue
                email = att.get("email")
                # the user themselves is not a "contact"; skip self + the organizer-is-self rows
                if email and not att.get("self"):
                    attendees[email] += 1
        facts: list[dict] = []
        if in_window > 0:
            facts.append({
                "key": "calendar:upcoming_events",
                "text": f"You have {in_window} event{'s' if in_window != 1 else ''} "
                        f"in the next two weeks.",
                "evidence": {"source": "GoogleCalendar.ListEvents", "count": in_window,
                             "window_days": 14},
            })
            top_day, top_n = weekday.most_common(1)[0]
            if top_n >= 1:
                facts.append({
                    "key": "calendar:busiest_weekday",
                    "text": f"Your busiest day in the next two weeks is {top_day} "
                            f"({top_n} event{'s' if top_n != 1 else ''}).",
                    "evidence": {"source": "GoogleCalendar.ListEvents", "weekday": top_day,
                                 "count": top_n},
                })
        # Only claim "frequent contact" when someone TRULY recurs (>= 2 events). One shared event
        # is not a relationship — claiming it would be the fabrication that ends trust.
        if attendees:
            name, n = attendees.most_common(1)[0]
            if n >= 2:
                facts.append({
                    "key": "calendar:frequent_contact",
                    "text": f"You're in frequent contact with {name} "
                            f"({n} shared events).",
                    "evidence": {"source": "GoogleCalendar.ListEvents", "contact": name,
                                 "count": n},
                })
        return facts

    def _correspondent_profile_facts(self, contacts_value, email_value) -> list:
        """Honest facts from REAL Gmail reads (ListThreads / ListEmails). When Gmail is not
        connected both values are None and this returns [] — no fact, no fabrication. When
        connected, name the most frequent correspondent only if they genuinely recur (>= 2)."""
        import collections
        senders: "collections.Counter" = collections.Counter()
        total = 0
        for value in (contacts_value, email_value):
            if not isinstance(value, dict):
                continue
            for items in _iter_message_lists(value):
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    total += 1
                    addr = _gmail_counterparty(item)
                    if addr:
                        senders[addr] += 1
        facts: list[dict] = []
        if total > 0:
            facts.append({
                "key": "email:recent_volume",
                "text": f"You have {total} recent email thread{'s' if total != 1 else ''} "
                        f"in your inbox.",
                "evidence": {"source": "Gmail", "count": total},
            })
        if senders:
            name, n = senders.most_common(1)[0]
            if n >= 2:
                facts.append({
                    "key": "email:frequent_correspondent",
                    "text": f"You're in frequent email contact with {name} "
                            f"({n} recent threads).",
                    "evidence": {"source": "Gmail", "correspondent": name, "count": n},
                })
        return facts

    def _write_profile_fact(self, fact: dict):
        """Upsert ONE derived profile fact into the profile drawer (the same drawer owner
        onboarding writes to, so the brain reads it through the normal inject path). Keyed by a
        stable onboarding_key so re-running the scan updates rather than duplicates. Returns the
        fact text on success, None on a write failure (best-effort; never crashes onboarding)."""
        text = fact.get("text")
        if not text:
            return None
        key = f"onboarding_profile:{fact.get('key')}"
        fields = {
            "kind": "onboarding_profile_fact",
            "onboarding_key": key,
            "source": "api_scan",
            "derived_from": "live_account_read",
            "evidence": fact.get("evidence", {}),
        }
        try:
            drawer = self.memory.profile
            existing = None
            for item in drawer.all():
                if (item.fields or {}).get("onboarding_key") == key:
                    existing = item
                    break
            if existing is None:
                drawer.write_text(text, fields=fields, provenance="owner:api_scan",
                                  confidence=1.0, importance=0.7, status="active")
            else:
                existing.text = text
                existing.fields = fields
                existing.provenance = "owner:api_scan"
                existing.confidence = 1.0
                existing.importance = 0.7
                existing.status = "active"
                drawer.update(existing)
        except Exception as exc:  # noqa: BLE001 — a write failure must not crash onboarding
            self.glassbox.log("onboard_profile_write_error",
                              {"key": key, "error": f"{type(exc).__name__}: {exc}"})
            return None
        return text

    async def onboard_discover(self, discovered, source: str = "chrome_scrape") -> dict:
        """Ingest a logged-in-Chrome connection SCAN (the extension's discover_connections
        intent) into the per-person mesh, via the SAME path typed onboarding uses. A discovered
        service Anticipy already holds a vault token for is marked connected; the rest become
        'Connect X' open-loops (api route for known services, browser for niche CRMs). Discovery
        only — NO credentials/tokens are entered here."""
        from ..onboarding.connection_scan import scan_to_onboarding
        # Bound the work: a real person is logged into a handful of services, not hundreds.
        # Non-list input -> empty (never crash); the cap also protects owner_onboard's per-item
        # drawer rescans from an O(n^2) blowup on a pathological payload (skeptic-found).
        if not isinstance(discovered, (list, tuple)):
            discovered = []
        items = [x for x in discovered if isinstance(x, dict)][:100]
        uid = self.api_hand.user_id
        onb = scan_to_onboarding(
            items, source=source,
            vault_has=lambda key: self.token_vault.has(uid, key),
        )
        result = await self.owner_onboard(onb)
        result["connections"] = [c.model_dump() for c in onb.connections]
        result["discovered_count"] = len(items)
        # Glass-box the real scrape so it is PROVABLE the onboarding "scrapes you" step fired
        # and fed the per-person mesh. Emit ONLY when the scan actually ingested connections —
        # an empty/no-op scan is not an onboarding event and must never look like one (honesty:
        # the reality gate reads this back, so it can only ever say REAL when a real scan landed).
        if onb.connections:
            self.glassbox.log("onboard_discover", {
                "source": source,
                "discovered_count": len(items),
                "connected_count": sum(1 for c in onb.connections if c.status == "connected"),
                "connections": [
                    {"name": c.name, "status": c.status, "route": c.route}
                    for c in onb.connections
                ],
            })
        return result

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
        """Detrimental actions paused awaiting the user's yes/no — what the app surfaces.

        Excludes opt_out_stop entries: an AUTO_DO_WITH_OPT_OUT chore is STARTED, not awaiting a
        yes — its pending entry is only the STOP handle (resolved by /owner/stop). Surfacing it
        here would wrongly render it as a Yes/Not-now approval (the approval-machine bug)."""
        return [{"ask_id": aid, "action": p["action"], "reason": p["reason"],
                 "category": p.get("category", ""), "goal_id": p["goal_id"]}
                for aid, p in self.proactive.pending.items()
                if p.get("category") != "opt_out_stop"]

    def memory_open_loops(self, limit: int = 50) -> dict:
        """Visible memory backlog: open/waiting loops the owner should be able to inspect."""
        import time as _t
        _now = _t.time()

        def _surfaced(i) -> bool:
            if not is_active_open_loop(i):
                return False
            # A SCHEDULED, not-yet-due follow-up is not ACTIVE work yet: it surfaces as a NUDGE
            # when it fires (proactive._fire_reminder at remind_ts), and the owner sees the
            # planned check-in on the card itself (card.follow_up). Showing it now would make a
            # done/parked task look open again and echo its raw source_text into the active list.
            if i.fields.get("kind") == "follow_up" and not i.fields.get("fired_at"):
                rt = i.fields.get("remind_ts")
                if rt is not None and float(rt) > _now:
                    return False
            return True

        active = [i for i in self.memory.open_loops.all() if _surfaced(i)]
        # DEDUPE — one dictated task -> exactly ONE backlog row. The owner-ingest path
        # writes two open_loops for one commitment: a RAW capture loop (the speaker's words,
        # the live reminder grounding) and an OWNER-CARD loop (the card-board record). When
        # BOTH are active for the same task the backlog showed it twice. Collapse same-text
        # active loops to one, PREFERRING the owner-card loop — it carries the card linkage,
        # so the surfaced row is the protected one (resolve must go through the card). A raw
        # loop with no active owner-card sibling (e.g. a do-card reminder whose card already
        # finished) still surfaces; a loop the spine caught with no raw sibling is untouched.
        by_task: dict = {}
        for i in active:
            # group same-task rows on the shared capture content key when present
            # (the two writers stamp the same capture_key), else normalized text
            key = i.fields.get("capture_key") or " ".join((i.text or "").split()).lower()
            kept = by_task.get(key)
            if kept is None:
                by_task[key] = i
                continue
            # prefer the owner-card loop; otherwise keep the most recently updated
            i_card = bool(i.fields.get("owner_card_id"))
            kept_card = bool(kept.fields.get("owner_card_id"))
            if i_card and not kept_card:
                by_task[key] = i
            elif i_card == kept_card and (i.updated_at or i.timestamp) > (kept.updated_at or kept.timestamp):
                by_task[key] = i
        deduped = list(by_task.values())
        deduped.sort(key=lambda i: i.updated_at or i.timestamp, reverse=True)
        loops = [i.model_dump(mode="json") for i in deduped[:max(0, limit)]]
        return {"loops": loops, "count": len(deduped)}

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
            # SEAM 2: surface the persisted autonomy mode so the board can pick the lane/verb.
            if not card.get("autonomy_mode") and record.get("autonomy_mode"):
                card["autonomy_mode"] = record.get("autonomy_mode")
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

    def _resolve_browser_card_record(self, ask_id: str, approved: bool) -> None:
        """Write a browser round-trip resolution onto its durable owner card (card.id == ask_id):
        YES -> 'running' (the agent runs async + texts the result), NO -> 'declined'. owner_cards()
        derives status / execution.goal_state / the resolution proof from record state+resolution,
        so a declined web task shows 'declined' on the board, not a stranded 'open' (F-011)."""
        path = self.data_dir / "owner_cards" / f"{ask_id}.json"
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        state = "running" if approved else "declined"
        record["state"] = state
        record["resolution"] = {"ask_id": ask_id, "approved": approved}
        if isinstance(record.get("owner_card"), dict):
            record["owner_card"]["status"] = state
        try:
            path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
        except Exception:
            return
        if not approved:
            self._sync_owner_loop_status(ask_id, "declined")

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
        # BROWSER-ACTION round-trip: a YES (from the app OR an SMS "YES") kicks the browser agent on
        # the real site and texts the result back. Handled here, before the goal funnel, because it
        # runs async (1-3 min) and must not block the reply.
        p = self.proactive.pending.get(ask_id)
        if isinstance(p, dict) and p.get("category") == "browser_action":
            self.proactive.pending.pop(ask_id, None)
            self.proactive._persist_pending()
            # Reflect the resolution on the durable owner card (card.id == ask_id) so the board shows
            # the outcome: YES -> running (the agent runs async + texts back), NO -> declined (F-011).
            self._resolve_browser_card_record(ask_id, approved)
            if approved:
                asyncio.create_task(self._run_browser_and_confirm(
                    p.get("browser_task") or p.get("action") or "",
                    p.get("browser_url") or "https://www.google.com", ask_id))
                self.glassbox.log("browser_action_approved", {"ask_id": ask_id})
                return {"ask_id": ask_id, "approved": True, "browser_action": True,
                        "state": "running", "goal_id": ask_id}
            self.glassbox.log("browser_action_declined", {"ask_id": ask_id})
            return {"ask_id": ask_id, "approved": False, "declined_action": p.get("action"),
                    "goal_id": ask_id}
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

        This is the ONLY execution trigger for a remembered/inferred item, and only for the
        whitelisted reversible intents that can be independently read back (create_event,
        write_memory). It is ADDITIVE: it reuses the review inference (display-only), the
        orchestrator funnel + GatedApprover (owner_approved), and the Slice-0 read-back gate
        verbatim. It touches no decision/trigger/harm code.

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
        from ..live_memory.press_go import (WHITELIST, action_content_key,
                                            map_inferred_to_step)

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
        # lossy); the whitelist DECISION is keyed off the inferred shape. TIMEZONE: ground
        # the calendar hold in the OWNER's onboarded zone (profile drawer) so start/end ISO
        # carry the owner's offset, not the server's — pass the owner tz-aware now + tz.
        tz, _tz_name = self._owner_timezone()
        owner_now = dt.datetime.now(tz)
        mapped = map_inferred_to_step(inferred, raw_text=str(row.get("text") or ""),
                                      now=owner_now, tz=tz)
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

        # CONTENT-level idempotency: the same task captured TWICE arrives as two DIFFERENT
        # remembered lines -> two different line_ids -> two different goal_ids, so the
        # line-keyed check above would miss them and a second real calendar hold would form.
        # Dedupe on the ACTION CONTENT instead (intent + normalized summary + grounded
        # start). If a DONE goal already carries this content_key, short-circuit to ITS
        # receipt — exactly ONE real write for the same action, however many lines say it.
        # Held under the same per-line lock as everything else here; a same-content goal
        # from a DIFFERENT line is found by scanning the store (its own line's lock does not
        # gate this one, but the first writer's goal is already done by the time we scan).
        content_key = action_content_key(intent, step)
        if content_key:
            for g in self.store.all():
                if (g.id != goal_id and g.state == GoalState.done
                        and (g.proof or {}).get("content_key") == content_key):
                    self.glassbox.log("press_go_content_idempotent",
                                      {"line_id": line_id, "goal_id": g.id,
                                       "content_key": content_key})
                    return {"approved": True, "executed": True, "idempotent": True,
                            "line_id": line_id, "intent": g.intent, "goal_id": g.id,
                            "state": g.state.value, "would_do": mapped.get("would_do"),
                            "receipt": g.proof or {}}

        goal = Goal(id=goal_id, intent=intent, description=mapped.get("would_do") or task,
                    steps=[step])
        goal.proof = {"owner_approved": True, "approved_from": "remembered",
                      "line_id": line_id, "content_key": content_key}
        goal.state = GoalState.running
        self.store.save(goal)
        self.glassbox.log("press_go_execute",
                          {"line_id": line_id, "intent": intent, "goal_id": goal.id})
        goal = await self.orchestrator._drive(goal)

        # Re-stamp the content_key onto the finished goal: _drive replaces goal.proof with
        # the step read-back receipts (Law 4), which would drop the key and defeat the
        # content-dedup scan above. Persist it back into the proof so the NEXT same-content
        # press finds this done goal and returns its receipt (one real write per action).
        if content_key and goal.state == GoalState.done:
            goal.proof = {**(goal.proof or {}), "content_key": content_key}
            self.store.save(goal)

        receipt = goal.proof or {}
        return {"approved": True, "executed": True, "line_id": line_id, "intent": intent,
                "goal_id": goal.id, "state": goal.state.value,
                "would_do": mapped.get("would_do"), "receipt": receipt}

    # The human-readable tool each AUTO-EXECUTABLE (whitelisted) intent WOULD call live.
    # create_event routes through the Arcade api_hand (authoritative INTENT_MAP) and is read
    # back via ListEvents; write_memory is a LOCAL standing note (no external tool, never
    # leaves the device). send_email_draft is NOT here — a draft is a prepared-handback (no
    # wired drafts read-back yet), so it never reaches this whitelist preview branch.
    _DRYRUN_TOOL = {
        "create_event": "GoogleCalendar.CreateEvent",
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
        # is the IDENTICAL call approve_remembered makes (SAME owner timezone grounding, so
        # the preview's start/end ISO carry the owner's offset — the preview must match what
        # approve would really do). The raw line grounds a concrete event time. We read the
        # plan but DO NOT drive it.
        tz, _tz_name = self._owner_timezone()
        owner_now = dt.datetime.now(tz)
        mapped = map_inferred_to_step(inferred, raw_text=raw_text,
                                      now=owner_now, tz=tz)
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
                         if intent == "create_event"
                         else "This saves a local note when you press go (no account needed)")}
