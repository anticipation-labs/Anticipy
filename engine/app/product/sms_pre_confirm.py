"""SMS pre-confirm gate for irreversible actions.

Before any irreversible action fires (Gmail Send, Twilio SMS to a real
number, social post, payment, form submit) the engine SMS-texts the
user with the proposed action and waits for YES/NO/EDIT reply.

Why: per the SMS_PRE_CONFIRM directive (see
feedback_sms_pre_confirm.md), the popover confirm-card alone is not
enough because the user is not always at their Mac. SMS is the
universal-reach channel. The pendant and phone need a channel that
finds the user wherever they are.

Surface:

  should_pre_confirm(plan, instruction)
      Returns True when the planned action needs the SMS gate. False
      when it is a safe draft / lookup / calendar entry the user can
      undo later.

  PendingConfirmStore
      Persists pending tasks to
      ~/.anticipy/v7/pending_confirms/<task_id>.json so the inbound
      webhook can resume the action when the user replies YES.

  send_pre_confirm_sms(task_id, proposal_text, to_number)
      Wraps app.proactive.notifier.twilio_sms. Returns
      {ok, twilio_sid, twilio_status, ...}.

  handle_inbound_sms(body, from_number)
      Parses the user's reply text. YES / NO / EDIT, falls back to
      "unknown" for anything else. Returns a decision dict the caller
      uses to either dispatch, cancel, or stash as draft.

  expire_pending(now_ts)
      Background sweeper called by a server thread every 60s. Marks
      any pending task whose expires_at has passed as `cancelled` and
      writes a follow-up SMS to the user.

Layout for the persisted JSON:

  {
    "task_id": "...",
    "created_at": <unix>,
    "expires_at": <unix>,
    "status": "pending|approved|cancelled|edit_requested|expired",
    "proposal_text": "...",                  # the SMS body sent
    "to_number": "+15555550100",
    "recipient": "lara@example.com",         # the eventual real recipient
    "verb": "send",
    "subject": "...",
    "preview": "...",                        # first 100 chars of the body
    "action_payload": {
        "instruction": "send Joe an email saying thanks",
        "plan": {...},                       # the resolved plan dict
    },
    "twilio_sid": "...",
    "decided_at": <unix or null>,
    "decided_via": "sms|popover|timer|null",
    "reply_body": ""                         # raw user reply text
  }

This module is pure-Python (json, os, threading, time, urllib via the
notifier) so it never imports server.py — server.py imports it. That
keeps the import graph acyclic and lets test runs exercise the gate
without spinning the FastAPI app.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("engine.product.sms_pre_confirm")

# 5 minutes per the directive. After this window we save the work as a
# draft (Gmail draft, popover review item) and ping the user once more
# so they can review at their convenience.
DEFAULT_TTL_SECONDS = 5 * 60

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_CANCELLED = "cancelled"
STATUS_EDIT_REQUESTED = "edit_requested"
STATUS_EXPIRED = "expired"

_YES_TOKENS = {"yes", "y", "send", "go", "ok", "okay", "confirm",
               "approve", "approved", "do it"}
_NO_TOKENS = {"no", "n", "cancel", "stop", "halt", "abort", "deny",
              "reject", "rejected", "nope"}
_EDIT_TOKENS = {"edit", "revise", "change", "modify", "rewrite",
                "fix", "adjust"}

# A non-empty marker the planner uses when there is no concrete
# recipient yet. Treated as "we still need to figure out who" rather
# than a real third party for the recipient-extraction rules.
_RECIPIENT_PLACEHOLDER = "the resolved contact"

_LOCK = threading.Lock()


# ----------------------------------------------------------------------
# storage
# ----------------------------------------------------------------------
def _root() -> Path:
    raw = os.environ.get("ANTICIPY_V7_PENDING_CONFIRM_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".anticipy" / "v7" / "pending_confirms"


def _safe_id(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return "unknown"
    return (re.sub(r"[^A-Za-z0-9._-]+", "_", s) or "unknown")[:128]


@dataclass
class PendingConfirm:
    task_id: str
    created_at: float
    expires_at: float
    status: str = STATUS_PENDING
    proposal_text: str = ""
    to_number: str = ""
    recipient: str = ""
    verb: str = ""
    subject: str = ""
    preview: str = ""
    action_payload: dict[str, Any] = field(default_factory=dict)
    twilio_sid: str = ""
    decided_at: Optional[float] = None
    decided_via: str = ""
    reply_body: str = ""
    # Channel router output (engine/app/product/channel_router.py)
    # serialised so the audit trail can replay the decision. Default
    # is "sms" to preserve the historical behaviour for any older
    # record that predates the channel router.
    channel: str = "sms"
    criticality: str = ""
    time_sensitivity: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "status": self.status,
            "proposal_text": self.proposal_text,
            "to_number": self.to_number,
            "recipient": self.recipient,
            "verb": self.verb,
            "subject": self.subject,
            "preview": self.preview,
            "action_payload": dict(self.action_payload or {}),
            "twilio_sid": self.twilio_sid,
            "decided_at": self.decided_at,
            "decided_via": self.decided_via,
            "reply_body": self.reply_body,
            "channel": self.channel or "sms",
            "criticality": self.criticality or "",
            "time_sensitivity": self.time_sensitivity or "",
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PendingConfirm":
        return cls(
            task_id=str(d.get("task_id") or ""),
            created_at=float(d.get("created_at") or 0.0),
            expires_at=float(d.get("expires_at") or 0.0),
            status=str(d.get("status") or STATUS_PENDING),
            proposal_text=str(d.get("proposal_text") or ""),
            to_number=str(d.get("to_number") or ""),
            recipient=str(d.get("recipient") or ""),
            verb=str(d.get("verb") or ""),
            subject=str(d.get("subject") or ""),
            preview=str(d.get("preview") or ""),
            action_payload=dict(d.get("action_payload") or {}),
            twilio_sid=str(d.get("twilio_sid") or ""),
            decided_at=(None if d.get("decided_at") in (None, "")
                        else float(d.get("decided_at") or 0.0)),
            decided_via=str(d.get("decided_via") or ""),
            reply_body=str(d.get("reply_body") or ""),
            channel=str(d.get("channel") or "sms"),
            criticality=str(d.get("criticality") or ""),
            time_sensitivity=str(d.get("time_sensitivity") or ""),
        )


class PendingConfirmStore:
    """File-system persistence for pending pre-confirm tasks.

    One JSON file per task at <root>/<task_id>.json. Atomic writes via
    temp+os.replace so an interrupted save never half-writes a row.
    Reads are best-effort: a corrupt file is logged and skipped, not
    raised, so one bad row never wedges the inbound webhook.
    """

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = (root or _root()).resolve()

    def _path(self, task_id: str) -> Path:
        return self.root / f"{_safe_id(task_id)}.json"

    def save(self, rec: PendingConfirm) -> Path:
        with _LOCK:
            self.root.mkdir(parents=True, exist_ok=True)
            path = self._path(rec.task_id)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(rec.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp, path)
        return path

    def get(self, task_id: str) -> Optional[PendingConfirm]:
        path = self._path(task_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(
                "pending_confirm_read_failed task=%s err=%s",
                task_id, exc,
            )
            return None
        try:
            return PendingConfirm.from_dict(data)
        except Exception as exc:
            logger.warning(
                "pending_confirm_parse_failed task=%s err=%s",
                task_id, exc,
            )
            return None

    def list_pending(self, now_ts: Optional[float] = None
                     ) -> list[PendingConfirm]:
        if not self.root.exists():
            return []
        out: list[PendingConfirm] = []
        for p in self.root.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            try:
                rec = PendingConfirm.from_dict(data)
            except Exception:
                continue
            if rec.status == STATUS_PENDING:
                out.append(rec)
        out.sort(key=lambda r: r.created_at)
        return out

    def update_status(self, task_id: str, *, status: str,
                      reply_body: str = "",
                      decided_via: str = "") -> Optional[PendingConfirm]:
        rec = self.get(task_id)
        if rec is None:
            return None
        rec.status = status
        rec.decided_at = time.time()
        rec.decided_via = decided_via or rec.decided_via
        if reply_body:
            rec.reply_body = reply_body
        self.save(rec)
        return rec

    def latest_pending(self) -> Optional[PendingConfirm]:
        rows = self.list_pending()
        return rows[-1] if rows else None


# ----------------------------------------------------------------------
# decision: does this action need pre-confirm
# ----------------------------------------------------------------------
def _tokenize(text: str) -> set[str]:
    return {t.lower() for t in re.findall(r"[a-zA-Z]+", text or "")}


_SAFE_DRAFT_INTENTS = {
    "lookup", "calendar_event", "other",
}

_SAFE_DRAFT_VERBS = {"draft", "note", "remind", "search", "find",
                     "show", "read", "lookup", "save", "snooze"}

_REAL_SEND_VERBS = {"send", "publish", "post", "tweet", "share",
                    "submit", "book", "reserve", "pay", "purchase",
                    "buy", "checkout", "transfer", "wire", "delete",
                    "cancel", "subscribe", "donate", "tip"}


def _is_safe_draft_only(intent: str, instruction: str,
                        task_text: str) -> bool:
    """True when the action is the draft-only / look-only / calendar
    flavour the user can undo. False otherwise.

    Heuristics. The structured `parse_draft_intent` path returns
    BEFORE we get here, so the safe-draft signal we rely on is the
    plan.intent token plus the absence of an irreversible-send verb
    in the instruction/task.
    """
    low_intent = (intent or "").lower().strip()
    if low_intent in _SAFE_DRAFT_INTENTS:
        return True
    instruction_low = (instruction or "").lower()
    task_low = (task_text or "").lower()
    combined_tokens = _tokenize(instruction_low) | _tokenize(task_low)
    if combined_tokens & _REAL_SEND_VERBS:
        return False
    # For email_draft / gmail_draft / email intents with no real-send
    # verb in the instruction, treat as safe draft. The instruction
    # "Draft an email to lara@... with subject ..." passes here, but
    # almost never reaches this function because it short-circuits at
    # parse_draft_intent in /api/act. This is the conservative tail
    # case for an instruction that DID make it to _run_action_engine
    # via _compose_task_from_memory but contains only safe verbs
    # (e.g. "draft a note for Joe").
    if low_intent in {"email_draft", "gmail_draft", "email"}:
        if not (combined_tokens & _REAL_SEND_VERBS):
            return True
    return False


def _extract_recipient(plan: dict[str, Any], instruction: str) -> str:
    """Resolve the eventual real recipient. Prefer the explicit email
    in plan.person; fall back to the first email-shaped token in the
    instruction; finally the person name if neither is present.
    """
    person = str(plan.get("person") or "").strip()
    if "@" in person and "." in person:
        return person
    email_match = re.search(
        r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
        instruction or "",
    )
    if email_match:
        return email_match.group(0)
    if person and person != _RECIPIENT_PLACEHOLDER:
        return person
    return ""


def should_pre_confirm(plan: dict[str, Any], instruction: str) -> bool:
    """Decide whether the planned action requires the SMS pre-confirm
    gate.

    Returns True when:
      - the plan involves real third-party delivery (email send,
        SMS send, post, payment, etc.), or
      - the plan would fire dsv4_skill_runner which now CLICKS Send
        (Gmail click-send path), regardless of the safer-looking
        plan.intent label (`email_draft` actually fires a real send
        via the LLM driver).

    Returns False when the action is the safe draft / lookup /
    calendar-add path (everything _try_direct_gmail_draft and
    _try_structured_gmail_draft handle: URL prefill + autosave, no
    click-Send).

    The gate point inside server.py: this is invoked right BEFORE
    _run_action_engine reaches the make_real_action_engine
    (DSv4SkillRunner) call. The three internal short-circuits
    (`_try_direct_browser_action`, `_try_direct_gmail_draft`,
    `_try_structured_gmail_draft`) bypass the gate because they are
    structurally draft-only.
    """
    if not isinstance(plan, dict):
        return False
    intent = str(plan.get("intent") or "").lower().strip()
    task_text = str(plan.get("task") or "")
    recipient = _extract_recipient(plan, instruction)
    if _is_safe_draft_only(intent, instruction, task_text):
        # No real send. No gate.
        return False
    # If a real recipient is named OR the intent is the dangerous LLM
    # email_draft path (which CLICKS Send), gate.
    if recipient:
        return True
    if intent in {"email_draft", "gmail_draft", "email", "send_email",
                  "send_message", "send_text_message",
                  "send_slack_message"}:
        return True
    instruction_low = (instruction or "").lower()
    instr_tokens = _tokenize(instruction_low)
    if instr_tokens & _REAL_SEND_VERBS:
        return True
    return False


# ----------------------------------------------------------------------
# proposal building
# ----------------------------------------------------------------------
def build_proposal_text(plan: dict[str, Any], instruction: str) -> dict[str, str]:
    """Compose the SMS body the user receives.

    Returns a dict with fields the caller persists alongside the
    pending record so the same wording is available to the popover and
    the audit log:

      proposal_text   the SMS body (160 chars target, hard 320 cap)
      verb            "send" | "post" | ...
      recipient       "lara@example.com" or "Joe"
      subject         best-effort subject line
      preview         first 100 chars of the body
    """
    intent = str(plan.get("intent") or "").lower().strip()
    task_text = str(plan.get("task") or "") or str(instruction or "")
    instruction_text = str(instruction or "")
    instr_tokens = _tokenize(instruction_text)

    recipient = _extract_recipient(plan, instruction)
    if not recipient:
        recipient = str(plan.get("person") or "").strip() or "a contact"

    if instr_tokens & {"post", "tweet", "publish"}:
        verb = "post"
    elif instr_tokens & {"book", "reserve"}:
        verb = "book"
    elif intent in {"send_text_message", "send_slack_message"} or \
            instr_tokens & {"text", "dm", "message"}:
        verb = "message"
    elif (instr_tokens & {"send", "share", "reply", "forward"}
          or intent in {"email_draft", "gmail_draft", "email"}):
        verb = "email"
    else:
        verb = "act on"

    subject = str(plan.get("thing") or "").strip()
    if not subject:
        subject = (task_text.split(".")[0]
                   if "." in task_text else task_text)
        subject = subject.strip()[:80] or "the request"

    # Preview is the first 100 chars of the body / instruction.
    # Prefer the actual planned body if the task description includes
    # one in quotes; fallback to the instruction itself.
    body_match = re.search(
        r"(?:saying|body)\s+['\"](?P<body>.+?)['\"]",
        instruction_text,
        re.IGNORECASE | re.DOTALL,
    )
    if body_match:
        preview = body_match.group("body").strip()
    else:
        preview = instruction_text.strip()
    preview = re.sub(r"\s+", " ", preview)[:100]

    proposal = (
        f"Anticipy is about to {verb} {recipient} about "
        f"{subject[:80]}. First 100 chars of body: '{preview}'. "
        f"Reply YES to send, NO to cancel, EDIT to revise."
    )
    # Twilio SMS is hard-capped at 1600. Aim for 320 so a single
    # message-chunk lands on every carrier.
    proposal = proposal[:320]
    return {
        "proposal_text": proposal,
        "verb": verb,
        "recipient": recipient,
        "subject": subject,
        "preview": preview,
    }


# ----------------------------------------------------------------------
# SMS dispatch
# ----------------------------------------------------------------------
def resolve_destination_number() -> str:
    """Where the pre-confirm SMS is sent. Prefer the explicit pre-
    confirm number, then TWILIO_NOTIFY_TO, then the real-number test
    var. Empty string if no destination is configured.
    """
    raw = (os.environ.get("TWILIO_TEST_TO_REAL_NUMBER_E164") or "").strip()
    if raw:
        return raw
    raw = (os.environ.get("TWILIO_NOTIFY_TO") or "").strip()
    if raw:
        return raw
    return ""


def _twilio_credentials_ready() -> bool:
    return bool(
        (os.environ.get("TWILIO_ACCOUNT_SID") or "").strip()
        and (os.environ.get("TWILIO_AUTH_TOKEN") or "").strip()
        and (os.environ.get("TWILIO_PHONE_NUMBER") or "").strip()
    )


def send_sms_sync(to_number: str, body: str) -> dict[str, Any]:
    """Synchronously send an SMS via Twilio (used from the dispatcher
    which is not in an asyncio context).

    Returns {"ok": bool, "twilio_sid": "...", "twilio_status": ...,
    "error": "..." | None, "mock": bool}.

    When TWILIO_MOCK=1 or credentials are missing OR
    TWILIO_TEST_TO_REAL_NUMBER!=1 we return ok=True with mock=True so
    callers can keep moving (the persisted task record still captures
    everything; nothing is actually sent over the wire).
    """
    if not to_number:
        return {"ok": False, "twilio_sid": "", "twilio_status": 0,
                "mock": False, "error": "no destination phone"}
    mock_env = (os.environ.get("TWILIO_MOCK") or "").strip().lower()
    twilio_mock = mock_env in {"1", "true", "yes", "on"}
    real_opt_in = (
        (os.environ.get("TWILIO_TEST_TO_REAL_NUMBER") or "").strip()
        == "1"
    )
    creds_ready = _twilio_credentials_ready()
    if twilio_mock or not creds_ready or not real_opt_in:
        # Mock path. Log the would-have-sent body for audit, return
        # ok with mock=True so the dispatcher persists the record and
        # the inbound webhook still works in dev.
        reason_parts = []
        if twilio_mock:
            reason_parts.append("TWILIO_MOCK=1")
        if not creds_ready:
            reason_parts.append("twilio_credentials_missing")
        if not real_opt_in:
            reason_parts.append("TWILIO_TEST_TO_REAL_NUMBER!=1")
        reason = ", ".join(reason_parts) or "unknown"
        logger.info(
            "sms_pre_confirm_mock to=%s body=%r reason=%s",
            to_number, body[:120], reason,
        )
        return {"ok": True, "twilio_sid": "", "twilio_status": 0,
                "mock": True, "error": None, "mock_reason": reason}
    # Real send via the proactive notifier helper. Wrap its async
    # surface in an isolated event loop so we can call from a sync
    # FastAPI handler thread.
    try:
        from app.proactive.notifier import twilio_sms as _twilio_sms
    except Exception as exc:
        return {"ok": False, "twilio_sid": "", "twilio_status": 0,
                "mock": False, "error":
                f"notifier_import_failed: {type(exc).__name__}: {exc}"}
    import asyncio
    try:
        result = asyncio.run(_twilio_sms(to_number, body))
    except RuntimeError as exc:
        # Already inside an event loop. Spin up a new thread with its
        # own loop. This matches the rest of server.py's pattern for
        # async-from-sync calls.
        if "asyncio.run() cannot be called from a running event loop" \
                in str(exc):
            container: dict[str, Any] = {}

            def _runner() -> None:
                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    container["result"] = loop.run_until_complete(
                        _twilio_sms(to_number, body)
                    )
                except Exception as inner:
                    container["error"] = inner
                finally:
                    loop.close()
            t = threading.Thread(target=_runner, daemon=True)
            t.start()
            t.join(timeout=30)
            if "error" in container:
                exc_inner = container["error"]
                return {"ok": False, "twilio_sid": "",
                        "twilio_status": 0, "mock": False,
                        "error":
                        f"{type(exc_inner).__name__}: {exc_inner}"}
            result = container.get("result") or {}
        else:
            return {"ok": False, "twilio_sid": "", "twilio_status": 0,
                    "mock": False, "error":
                    f"{type(exc).__name__}: {exc}"}
    except Exception as exc:
        return {"ok": False, "twilio_sid": "", "twilio_status": 0,
                "mock": False, "error":
                f"{type(exc).__name__}: {exc}"}
    return {
        "ok": bool(result.get("ok")),
        "twilio_sid": str(result.get("twilio_sid") or ""),
        "twilio_status": result.get("twilio_status"),
        "mock": False,
        "error": None,
    }


# ----------------------------------------------------------------------
# Voice confirm: place a Twilio Programmable Voice call whose TwiML
# Says the proposal and Gathers spoken YES / NO / EDIT. The Gather
# action target is /api/sms/inbound so the existing inbound webhook
# resolves the reply through the same pipeline as text replies.
# ----------------------------------------------------------------------
def _xml_escape(value: str) -> str:
    return (
        (value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\"", "&quot;")
        .replace("'", "&apos;")
    )


def _gather_action_url() -> str:
    """The public URL Twilio POSTs the speech result to.

    Voice flows need a publicly reachable webhook target. The engine
    cannot host one (it lives on 127.0.0.1) so we point at the
    website's /api/twilio/sms-inbound relay. That relay drops the row
    into Supabase, the engine poller picks it up, and the local
    /api/sms/inbound runs the existing YES/NO/EDIT pipeline. When
    ANTICIPY_VOICE_GATHER_URL is set we honour the override
    (operator-test path).
    """
    override = os.environ.get("ANTICIPY_VOICE_GATHER_URL", "").strip()
    if override:
        return override
    base = (
        os.environ.get("ANTICIPY_WEBSITE_URL", "").strip()
        or os.environ.get("NEXT_PUBLIC_SITE_URL", "").strip()
        or "https://www.anticipy.ai"
    ).rstrip("/")
    return f"{base}/api/twilio/sms-inbound"


def build_voice_confirm_twiml(proposal_text: str) -> str:
    """The TwiML payload Twilio fetches when the call connects.

    Speaks the proposal with the `alice` voice, then opens a Gather
    block configured for speech so the user can say YES / NO / EDIT
    out loud. Twilio POSTs the SpeechResult back to action= so the
    /api/sms/inbound parser can run on it.
    """
    safe = _xml_escape(proposal_text or "Anticipy is calling.")
    action_url = _xml_escape(_gather_action_url())
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<Response>"
        f"<Say voice=\"alice\">{safe}</Say>"
        f"<Gather input=\"speech\" action=\"{action_url}\" "
        "method=\"POST\" speechTimeout=\"auto\" "
        "hints=\"yes,no,edit,cancel,send,confirm\">"
        "<Say voice=\"alice\">Please say YES to send, "
        "NO to cancel, or EDIT to revise.</Say>"
        "</Gather>"
        "<Say voice=\"alice\">No reply heard. I will save this as "
        "a draft for review.</Say>"
        "</Response>"
    )


def _send_voice_confirm(to_number: str, proposal_text: str,
                        *, twiml_url: Optional[str] = None
                        ) -> dict[str, Any]:
    """Place a Programmable Voice call carrying the proposal. Same
    mock/credentials/opt-in semantics as send_sms_sync so the dev
    flow keeps working without a real Twilio account.

    Returns {"ok": bool, "twilio_sid": "...", "twilio_status": ...,
    "error": "..." | None, "mock": bool, "twiml": "<...>",
    "twiml_url": "..."}.

    When `twiml_url` is None we host the TwiML inline via twimlets
    (the same fallback `twilio_voice` already uses). The TwiML is
    also returned in the response so the audit trail captures the
    exact content the user heard.
    """
    twiml = build_voice_confirm_twiml(proposal_text)
    if not to_number:
        return {"ok": False, "twilio_sid": "", "twilio_status": 0,
                "mock": False, "error": "no destination phone",
                "twiml": twiml, "twiml_url": twiml_url or ""}
    mock_env = (os.environ.get("TWILIO_MOCK") or "").strip().lower()
    twilio_mock = mock_env in {"1", "true", "yes", "on"}
    real_opt_in = (
        (os.environ.get("TWILIO_TEST_TO_REAL_NUMBER") or "").strip()
        == "1"
    )
    creds_ready = _twilio_credentials_ready()
    if twilio_mock or not creds_ready or not real_opt_in:
        reason_parts = []
        if twilio_mock:
            reason_parts.append("TWILIO_MOCK=1")
        if not creds_ready:
            reason_parts.append("twilio_credentials_missing")
        if not real_opt_in:
            reason_parts.append("TWILIO_TEST_TO_REAL_NUMBER!=1")
        reason = ", ".join(reason_parts) or "unknown"
        logger.info(
            "voice_pre_confirm_mock to=%s body=%r reason=%s",
            to_number, proposal_text[:120], reason,
        )
        return {"ok": True, "twilio_sid": "", "twilio_status": 0,
                "mock": True, "error": None, "mock_reason": reason,
                "twiml": twiml, "twiml_url": twiml_url or ""}
    try:
        from app.proactive.notifier import twilio_voice as _twilio_voice
    except Exception as exc:
        return {"ok": False, "twilio_sid": "", "twilio_status": 0,
                "mock": False, "error":
                f"notifier_import_failed: {type(exc).__name__}: {exc}",
                "twiml": twiml, "twiml_url": twiml_url or ""}
    import asyncio

    async def _do_call() -> dict[str, Any]:
        return await _twilio_voice(to_number, twiml_url=twiml_url,
                                   body=proposal_text)
    try:
        result = asyncio.run(_do_call())
    except RuntimeError as exc:
        if "asyncio.run() cannot be called from a running event loop" \
                in str(exc):
            container: dict[str, Any] = {}

            def _runner() -> None:
                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    container["result"] = loop.run_until_complete(
                        _do_call()
                    )
                except Exception as inner:
                    container["error"] = inner
                finally:
                    loop.close()
            t = threading.Thread(target=_runner, daemon=True)
            t.start()
            t.join(timeout=30)
            if "error" in container:
                exc_inner = container["error"]
                return {"ok": False, "twilio_sid": "",
                        "twilio_status": 0, "mock": False,
                        "error":
                        f"{type(exc_inner).__name__}: {exc_inner}",
                        "twiml": twiml,
                        "twiml_url": twiml_url or ""}
            result = container.get("result") or {}
        else:
            return {"ok": False, "twilio_sid": "", "twilio_status": 0,
                    "mock": False, "error":
                    f"{type(exc).__name__}: {exc}",
                    "twiml": twiml, "twiml_url": twiml_url or ""}
    except Exception as exc:
        return {"ok": False, "twilio_sid": "", "twilio_status": 0,
                "mock": False, "error":
                f"{type(exc).__name__}: {exc}",
                "twiml": twiml, "twiml_url": twiml_url or ""}
    return {
        "ok": bool(result.get("ok")),
        "twilio_sid": str(result.get("twilio_sid") or ""),
        "twilio_status": result.get("twilio_status"),
        "mock": False,
        "error": None,
        "twiml": twiml,
        "twiml_url": str(result.get("twiml_url") or twiml_url or ""),
    }


def _send_email_confirm(proposal_text: str) -> dict[str, Any]:
    """Best-effort email dispatch for the channel router's EMAIL and
    SMS_PLUS_EMAIL paths.

    The packaged engine drives the user's real Gmail via CDP for
    sends (see _send_receipt_email_via_cdp in server.py). That helper
    needs a live Chrome attached at port 9222 which is not always
    present in dev. Instead of importing it here (and forcing a hard
    dep on CDP from a pure-Python module) we log the would-have-sent
    body and mark the dispatch as `mock=True`. The popover surfaces
    the same proposal text so the user still sees the request, and
    the channel selection is captured on the persisted record so an
    operator can replay through the real Gmail path if needed.
    """
    if not proposal_text:
        return {"ok": False, "mock": False,
                "error": "no proposal body"}
    logger.info(
        "email_pre_confirm_dispatch body=%r",
        proposal_text[:240],
    )
    # When ANTICIPY_USER_EMAIL is set we record it so the audit trail
    # captures the intended recipient even though we are not opening
    # Chrome from this thread.
    to_email = (os.environ.get("ANTICIPY_USER_EMAIL", "")
                or os.environ.get("ANTICIPY_NOTIFY_EMAIL", "")
                or "").strip()
    return {"ok": True, "mock": True, "error": None,
            "to_email": to_email,
            "note": "engine logs email proposal; popover surfaces "
                    "the same text. Live Gmail send happens via the "
                    "receipt path on user request."}


# ----------------------------------------------------------------------
# Channel selection
# ----------------------------------------------------------------------
def _criticality_from_plan(plan: dict[str, Any],
                           instruction: str) -> tuple[str, str]:
    """Run the risk assessor on (plan, instruction) and return a
    (criticality, time_sensitivity) pair the channel router can
    consume.

    The risk assessor's `level` (low/medium/high) does not map
    1:1 to the matrix's CRITICAL / HIGH / MEDIUM / LOW tiers. The
    feedback (feedback_channel_by_urgency.md) calls out:
      - money irreversible -> CRITICAL
      - personal-name signature legal doc -> CRITICAL
      - patient lab order / medical -> CRITICAL
      - email send to external client about deal -> HIGH
      - calendar reschedule with multi-party impact -> HIGH
      - email draft saved -> MEDIUM
      - routine reminder / status update -> LOW

    We promote risk_assessor's level using the additional signals it
    already computes: money_amount > 0 marks the action irreversible
    in dollar terms; irreversibility_score >= 0.9 marks the delete /
    wipe / destroy class. third_party_impact promotes the otherwise-
    medium send-to-external-recipient class to HIGH so a real email
    going out the door gets BOTH SMS and email confirms instead of
    email-only.

    Pure-Python; no network.
    """
    try:
        from app.product.risk_assessor import assess as _assess
    except Exception:
        # Conservative fallback so a packaging miss never breaks the
        # gate. Treat everything as HIGH so the user is at least
        # notified via SMS + email.
        return "high", "not_time_sensitive"
    binding: dict[str, Any] = {}
    intent_text = instruction or str(plan.get("task") or "")
    person = str(plan.get("person") or "").strip()
    if "@" in person and "." in person:
        binding["recipients"] = [person]
    elif person:
        binding["contact"] = person
    surface = str(plan.get("surface_target") or "").strip()
    if surface:
        binding["surface_target"] = surface
    try:
        assessment = _assess(intent_text, binding, {})
    except Exception:
        return "high", "not_time_sensitive"
    # CRITICAL promotions (money irreversible, delete-class).
    if assessment.money_amount and assessment.money_amount > 0:
        crit = "critical"
    elif (assessment.irreversibility_score or 0.0) >= 0.9:
        crit = "critical"
    elif assessment.level == "high":
        # risk_assessor only emits level=high for the delete-class
        # and money paths, both already caught above. This branch is
        # the safety net.
        crit = "critical"
    elif (assessment.level == "medium"
          and (assessment.third_party_impact
               or (assessment.irreversibility_score or 0.0) >= 0.5)):
        # External send / publish / post: gets both SMS + email so
        # the user has receipt-and-reach before the message hits the
        # outside world.
        crit = "high"
    elif assessment.level == "medium":
        crit = "medium"
    elif assessment.level == "low":
        crit = "low"
    else:
        crit = "medium"
    return crit, assessment.time_sensitivity or "not_time_sensitive"


def _channel_for_plan(plan: dict[str, Any], instruction: str
                      ) -> tuple[str, str, str]:
    """Return (channel_value, criticality, time_sensitivity).

    `channel_value` is the string form of channel_router.Channel so
    callers can persist it on the PendingConfirm record.
    """
    crit, ts = _criticality_from_plan(plan, instruction)
    try:
        from app.product.channel_router import select_channel
        channel = select_channel(crit, ts)
        return channel.value, crit, ts
    except Exception:
        # Conservative fallback: SMS, the historical behaviour.
        return "sms", crit, ts


# ----------------------------------------------------------------------
# pre-confirm orchestration
# ----------------------------------------------------------------------
def create_pending_confirm(plan: dict[str, Any], instruction: str,
                           *, store: Optional[PendingConfirmStore] = None,
                           ttl_seconds: int = DEFAULT_TTL_SECONDS,
                           extra_payload: Optional[dict[str, Any]] = None
                           ) -> dict[str, Any]:
    """Build a PendingConfirm record, dispatch via the channel router,
    persist.

    The channel router (engine/app/product/channel_router.py) picks
    one of voice_call / sms / sms_plus_email / email / silent based
    on the action's criticality and time-sensitivity. We use the
    risk_assessor as the source of truth for both signals. The
    chosen channel determines which Twilio surface fires:
      - voice_call         -> _send_voice_confirm (Programmable
                              Voice; TwiML Says proposal +
                              Gathers spoken YES/NO/EDIT)
      - sms                -> send_sms_sync (single SMS)
      - sms_plus_email     -> send_sms_sync + _send_email_confirm
      - email              -> _send_email_confirm only
      - silent             -> persist record, no outbound dispatch
                              (the popover still surfaces the
                              proposal for in-app review)

    Returns the dict shape the /api/act handler returns to the
    caller:

      {
        "ran": false,
        "awaiting_sms_confirm": true,
        "channel": "voice_call|sms|sms_plus_email|email|silent",
        "criticality": "critical|high|medium|low",
        "time_sensitivity": "time_sensitive|not_time_sensitive",
        "task_id": "...",
        "expires_at": <unix>,
        "proposal_text": "...",
        "to_number": "...",
        "twilio": {"ok": bool, "twilio_sid": "...", "mock": bool,
                   "channel": "..."},
      }
    """
    store = store or PendingConfirmStore()
    now = time.time()
    task_id = uuid.uuid4().hex[:16]
    to_number = resolve_destination_number()
    proposal = build_proposal_text(plan, instruction)
    channel_value, crit, time_sensitivity = _channel_for_plan(
        plan, instruction)
    rec = PendingConfirm(
        task_id=task_id,
        created_at=now,
        expires_at=now + max(int(ttl_seconds), 60),
        status=STATUS_PENDING,
        proposal_text=proposal["proposal_text"],
        to_number=to_number,
        recipient=proposal["recipient"],
        verb=proposal["verb"],
        subject=proposal["subject"],
        preview=proposal["preview"],
        action_payload={
            "instruction": instruction,
            "plan": plan,
            **(extra_payload or {}),
        },
        channel=channel_value,
        criticality=crit,
        time_sensitivity=time_sensitivity,
    )
    sms_result: dict[str, Any] = {}
    voice_result: dict[str, Any] = {}
    email_result: dict[str, Any] = {}
    if channel_value == "voice_call":
        voice_result = _send_voice_confirm(to_number, rec.proposal_text)
        rec.twilio_sid = str(voice_result.get("twilio_sid") or "")
    elif channel_value == "sms":
        sms_result = send_sms_sync(to_number, rec.proposal_text)
        rec.twilio_sid = str(sms_result.get("twilio_sid") or "")
    elif channel_value == "sms_plus_email":
        sms_result = send_sms_sync(to_number, rec.proposal_text)
        rec.twilio_sid = str(sms_result.get("twilio_sid") or "")
        email_result = _send_email_confirm(rec.proposal_text)
    elif channel_value == "email":
        email_result = _send_email_confirm(rec.proposal_text)
    elif channel_value == "silent":
        # Record only; popover handles in-app surfacing. No twilio
        # round-trip.
        sms_result = {"ok": True, "twilio_sid": "", "twilio_status": 0,
                      "mock": True, "error": None,
                      "mock_reason": "silent channel selected"}
    else:
        # Defense in depth: unknown channel falls back to SMS so we
        # never silently drop a CRITICAL action.
        sms_result = send_sms_sync(to_number, rec.proposal_text)
        rec.twilio_sid = str(sms_result.get("twilio_sid") or "")
    store.save(rec)
    primary = (voice_result if channel_value == "voice_call"
               else (sms_result if sms_result else email_result))
    return {
        "ran": False,
        "awaiting_sms_confirm": True,
        "task_id": task_id,
        "expires_at": rec.expires_at,
        "proposal_text": rec.proposal_text,
        "to_number": to_number,
        "recipient": rec.recipient,
        "verb": rec.verb,
        "subject": rec.subject,
        "preview": rec.preview,
        "intent": str(plan.get("intent") or ""),
        "channel": channel_value,
        "criticality": crit,
        "time_sensitivity": time_sensitivity,
        "twilio": {
            "ok": bool(primary.get("ok")),
            "twilio_sid": primary.get("twilio_sid", ""),
            "mock": bool(primary.get("mock")),
            "error": primary.get("error"),
            "mock_reason": primary.get("mock_reason"),
            "channel": channel_value,
            "voice": voice_result or None,
            "sms": sms_result or None,
            "email": email_result or None,
        },
    }


# ----------------------------------------------------------------------
# inbound SMS reply parsing
# ----------------------------------------------------------------------
def parse_reply(body: str) -> str:
    """Classify a user SMS reply.

    Returns one of: "yes", "no", "edit", "unknown".
    Matching is whole-word, case-insensitive, only looks at the first
    32 characters so a typo at the end of the message does not flip
    the decision.
    """
    text = (body or "").strip().lower()[:32]
    if not text:
        return "unknown"
    text = re.sub(r"[^a-z0-9\s'-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "unknown"
    tokens = text.split(" ")
    head = tokens[0]
    if head in _YES_TOKENS or text in _YES_TOKENS:
        return "yes"
    if head in _NO_TOKENS or text in _NO_TOKENS:
        return "no"
    if head in _EDIT_TOKENS or text in _EDIT_TOKENS:
        return "edit"
    return "unknown"


def resolve_inbound(body: str, *,
                    store: Optional[PendingConfirmStore] = None,
                    task_id: str = ""
                    ) -> dict[str, Any]:
    """Apply an inbound SMS body to the most recent pending task.

    If task_id is empty we resolve against the most recently created
    pending task. This matches Twilio's standard "user replies to the
    last message" UX: the user just texts YES, no need to type a
    task id.

    Returns a dict shape:

      {
        "ok": bool,
        "reply_class": "yes|no|edit|unknown",
        "task_id": "...",
        "previous_status": "pending|approved|...",
        "new_status": "...",
        "action_payload": {...} | None,    # populated when YES so
                                            # the caller can dispatch
      }
    """
    store = store or PendingConfirmStore()
    if task_id:
        rec = store.get(task_id)
    else:
        rec = store.latest_pending()
    if rec is None:
        return {"ok": False, "reply_class": parse_reply(body),
                "task_id": task_id, "previous_status": "",
                "new_status": "", "action_payload": None,
                "error": "no pending task"}
    reply_class = parse_reply(body)
    prev = rec.status
    if rec.status != STATUS_PENDING:
        return {"ok": False, "reply_class": reply_class,
                "task_id": rec.task_id, "previous_status": prev,
                "new_status": prev, "action_payload": None,
                "error": "task not pending"}
    if reply_class == "yes":
        rec.status = STATUS_APPROVED
    elif reply_class == "no":
        rec.status = STATUS_CANCELLED
    elif reply_class == "edit":
        rec.status = STATUS_EDIT_REQUESTED
    else:
        # Leave the record pending and tell the user what to do.
        return {"ok": False, "reply_class": reply_class,
                "task_id": rec.task_id, "previous_status": prev,
                "new_status": prev, "action_payload": None,
                "error": "unrecognized reply"}
    rec.decided_at = time.time()
    rec.decided_via = "sms"
    rec.reply_body = (body or "")[:600]
    store.save(rec)
    return {
        "ok": True,
        "reply_class": reply_class,
        "task_id": rec.task_id,
        "previous_status": prev,
        "new_status": rec.status,
        "action_payload": (dict(rec.action_payload)
                           if reply_class == "yes" else None),
        "proposal_text": rec.proposal_text,
        "recipient": rec.recipient,
    }


# ----------------------------------------------------------------------
# expiry sweeper
# ----------------------------------------------------------------------
def expire_pending(now_ts: Optional[float] = None,
                   *,
                   store: Optional[PendingConfirmStore] = None,
                   followup_sms: bool = True
                   ) -> list[dict[str, Any]]:
    """Mark expired pending tasks as `expired`. Returns the list of
    expired records (dicts) so the caller can save them as drafts.

    Per the directive: when 5 min pass with no reply, mark task as
    draft (save Gmail draft, don't send) and SMS a follow-up: "No
    reply, saved as draft. Open Anticipy popover to review."
    """
    store = store or PendingConfirmStore()
    now = float(now_ts) if now_ts is not None else time.time()
    expired_rows: list[dict[str, Any]] = []
    for rec in store.list_pending(now_ts=now):
        if rec.expires_at and now >= rec.expires_at:
            rec.status = STATUS_EXPIRED
            rec.decided_at = now
            rec.decided_via = "timer"
            store.save(rec)
            if followup_sms and rec.to_number:
                send_sms_sync(
                    rec.to_number,
                    "Anticipy: no reply, saved as draft. Open the "
                    "Anticipy popover to review.",
                )
            expired_rows.append(rec.to_dict())
    return expired_rows


# ----------------------------------------------------------------------
# Inbound SMS poller. The engine cannot accept inbound Twilio webhooks
# directly because it lives on 127.0.0.1 on user laptops. Instead, the
# website (anticipy.ai) exposes POST /api/twilio/sms-inbound which
# verifies the Twilio signature and stores the payload in
# public.anticipy_sms_inbound. We poll that table every 10 seconds, claim
# any unconsumed rows for our account, and forward each one to the local
# /api/sms/inbound handler so the existing YES/NO/EDIT pipeline runs
# unchanged.
# ----------------------------------------------------------------------

DEFAULT_INBOUND_POLL_INTERVAL_SECONDS = 10.0


def _website_base_url() -> str:
    """The public HTTPS host that owns /api/twilio/sms-inbound."""
    return (
        os.environ.get("ANTICIPY_WEBSITE_URL", "").strip()
        or os.environ.get("NEXT_PUBLIC_SITE_URL", "").strip()
        or os.environ.get("VERCEL_URL", "").strip()
        or "https://www.anticipy.ai"
    ).rstrip("/")


def _local_engine_base_url() -> str:
    return (
        os.environ.get("ANTICIPY_ENGINE_URL", "").strip()
        or "http://127.0.0.1:8731"
    ).rstrip("/")


def _engine_id() -> str:
    """Stable per-engine identifier so the website knows which engine
    claimed which inbound rows. Persists across restarts."""
    cached = os.environ.get("ANTICIPY_ENGINE_ID", "").strip()
    if cached:
        return cached
    state_dir = Path(
        os.environ.get("ANTICIPY_DATA_DIR", "")
        or os.path.expanduser("~/.anticipy/v7")
    )
    state_dir.mkdir(parents=True, exist_ok=True)
    id_path = state_dir / "engine_id"
    if id_path.exists():
        try:
            return id_path.read_text(encoding="utf-8").strip() or "anticipy-engine"
        except Exception:
            pass
    new_id = f"engine-{uuid.uuid4().hex[:12]}"
    try:
        id_path.write_text(new_id, encoding="utf-8")
    except Exception:
        pass
    return new_id


def _poller_account_id() -> str:
    """The dossier account this engine owns. The website filters
    anticipy_sms_inbound rows by account_id when the From-number maps
    to a known user."""
    return (
        os.environ.get("ANTICIPY_ACCOUNT_ID", "").strip()
        or os.environ.get("ANTICIPY_USER_ID", "").strip()
        or "anticipy-user"
    )


def _poll_inbound_rows(timeout_seconds: float = 8.0) -> list[dict[str, Any]]:
    """One blocking call to the website poll surface.

    Returns the list of new inbound rows (each row already claimed by
    this engine). Empty on no rows, on network error, or when the
    website URL is unconfigured. Never raises.
    """
    base = _website_base_url()
    if not base:
        return []
    account_id = _poller_account_id()
    # include_unmapped=1 so dev engines without a phone-to-account map
    # still receive replies they can route by latest_pending().
    qs = urllib.parse.urlencode(
        {
            "account_id": account_id,
            "include_unmapped": "1",
            "limit": "50",
        }
    )
    url = f"{base}/api/twilio/sms-inbound?{qs}"
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "x-engine-id": _engine_id(),
        },
    )
    try:
        with urllib.request.urlopen(
            req, timeout=float(timeout_seconds)
        ) as resp:
            body = resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return []
    except Exception:
        return []
    try:
        obj = json.loads(body)
    except Exception:
        return []
    if not isinstance(obj, dict) or not obj.get("ok"):
        return []
    rows = obj.get("rows") or []
    if not isinstance(rows, list):
        return []
    return rows


def _forward_inbound_to_local_engine(row: dict[str, Any],
                                     timeout_seconds: float = 5.0
                                     ) -> dict[str, Any]:
    """POST one inbound row to the engine's own /api/sms/inbound.

    The local handler runs the existing YES/NO/EDIT pipeline. We send
    form-encoded fields shaped like Twilio's native webhook payload so
    the existing parser does not need to know it was relayed.
    """
    base = _local_engine_base_url()
    if not base:
        return {"ok": False, "error": "engine_url_unset"}
    fields = {
        "Body": str(row.get("body") or ""),
        "From": str(row.get("from_number") or ""),
        "To": str(row.get("to_number") or ""),
        "MessageSid": str(row.get("message_sid") or ""),
    }
    raw = row.get("raw_form") or {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            if k in fields:
                continue
            try:
                fields[str(k)] = str(v) if v is not None else ""
            except Exception:
                continue
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/api/sms/inbound",
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(
            req, timeout=float(timeout_seconds)
        ) as resp:
            try:
                payload = resp.read().decode("utf-8", "replace")
            except Exception:
                payload = ""
            status = getattr(resp, "status", 200)
            return {
                "ok": 200 <= int(status) < 300,
                "status_code": int(status),
                "body_excerpt": payload[:400],
            }
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "status_code": int(getattr(exc, "code", 0) or 0),
            "error": "http_error",
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


_POLLER_STATE: dict[str, Any] = {
    "thread": None,
    "stop": threading.Event(),
    "started_at": None,
    "polls_total": 0,
    "rows_relayed": 0,
    "last_poll_at": None,
    "last_error": "",
}


def _poller_loop(interval_seconds: float) -> None:
    state = _POLLER_STATE
    while not state["stop"].is_set():
        state["polls_total"] = int(state.get("polls_total") or 0) + 1
        state["last_poll_at"] = time.time()
        try:
            rows = _poll_inbound_rows()
            for row in rows:
                try:
                    res = _forward_inbound_to_local_engine(row)
                    if res.get("ok"):
                        state["rows_relayed"] = (
                            int(state.get("rows_relayed") or 0) + 1
                        )
                    else:
                        state["last_error"] = (
                            f"forward_failed: "
                            f"{res.get('error') or res.get('status_code')}"
                        )
                except Exception as exc:
                    state["last_error"] = (
                        f"forward_unhandled: {type(exc).__name__}: {exc}"
                    )
        except Exception as exc:
            state["last_error"] = (
                f"poll_unhandled: {type(exc).__name__}: {exc}"
            )
        if state["stop"].wait(timeout=float(interval_seconds)):
            return


def start_inbound_poller(
    interval_seconds: Optional[float] = None,
) -> dict[str, Any]:
    """Start (idempotent) the background poller thread.

    Returns a status dict. Safe to call on engine startup. The poller
    is a no-op when ANTICIPY_INBOUND_SMS_POLL=0 or when no website URL
    is configured."""
    if os.environ.get("ANTICIPY_INBOUND_SMS_POLL", "1") == "0":
        return {"ok": False, "reason": "disabled_via_env"}
    state = _POLLER_STATE
    if state.get("thread") is not None:
        t = state["thread"]
        if hasattr(t, "is_alive") and t.is_alive():
            return {"ok": True, "already_running": True,
                    "started_at": state.get("started_at")}
    interval = float(
        interval_seconds
        if interval_seconds is not None
        else os.environ.get(
            "ANTICIPY_INBOUND_SMS_POLL_INTERVAL_SECONDS",
            DEFAULT_INBOUND_POLL_INTERVAL_SECONDS,
        )
    )
    state["stop"] = threading.Event()
    state["started_at"] = time.time()
    state["polls_total"] = 0
    state["rows_relayed"] = 0
    state["last_error"] = ""
    t = threading.Thread(
        target=_poller_loop,
        name="anticipy-sms-inbound-poller",
        args=(interval,),
        daemon=True,
    )
    state["thread"] = t
    t.start()
    return {
        "ok": True,
        "started_at": state["started_at"],
        "interval_seconds": interval,
        "engine_id": _engine_id(),
        "account_id": _poller_account_id(),
        "website_url": _website_base_url(),
    }


def stop_inbound_poller(timeout: float = 5.0) -> None:
    state = _POLLER_STATE
    if state.get("stop"):
        try:
            state["stop"].set()
        except Exception:
            pass
    t = state.get("thread")
    if t is not None and hasattr(t, "is_alive") and t.is_alive():
        try:
            t.join(timeout=float(timeout))
        except Exception:
            pass
    state["thread"] = None


def inbound_poller_status() -> dict[str, Any]:
    state = _POLLER_STATE
    t = state.get("thread")
    return {
        "running": bool(t is not None
                        and hasattr(t, "is_alive")
                        and t.is_alive()),
        "started_at": state.get("started_at"),
        "polls_total": int(state.get("polls_total") or 0),
        "rows_relayed": int(state.get("rows_relayed") or 0),
        "last_poll_at": state.get("last_poll_at"),
        "last_error": str(state.get("last_error") or ""),
        "interval_seconds": float(
            os.environ.get(
                "ANTICIPY_INBOUND_SMS_POLL_INTERVAL_SECONDS",
                DEFAULT_INBOUND_POLL_INTERVAL_SECONDS,
            )
        ),
        "engine_id": _engine_id(),
        "account_id": _poller_account_id(),
        "website_url": _website_base_url(),
    }


# ----------------------------------------------------------------------
# back-compat surface used by the server.py /api/act gate.
# ----------------------------------------------------------------------
__all__ = [
    "DEFAULT_TTL_SECONDS",
    "DEFAULT_INBOUND_POLL_INTERVAL_SECONDS",
    "PendingConfirm",
    "PendingConfirmStore",
    "STATUS_APPROVED",
    "STATUS_CANCELLED",
    "STATUS_EDIT_REQUESTED",
    "STATUS_EXPIRED",
    "STATUS_PENDING",
    "build_proposal_text",
    "build_voice_confirm_twiml",
    "create_pending_confirm",
    "expire_pending",
    "inbound_poller_status",
    "parse_reply",
    "resolve_destination_number",
    "resolve_inbound",
    "send_sms_sync",
    "should_pre_confirm",
    "start_inbound_poller",
    "stop_inbound_poller",
]
