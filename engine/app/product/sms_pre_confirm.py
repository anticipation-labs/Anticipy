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
# pre-confirm orchestration
# ----------------------------------------------------------------------
def create_pending_confirm(plan: dict[str, Any], instruction: str,
                           *, store: Optional[PendingConfirmStore] = None,
                           ttl_seconds: int = DEFAULT_TTL_SECONDS,
                           extra_payload: Optional[dict[str, Any]] = None
                           ) -> dict[str, Any]:
    """Build a PendingConfirm record, send the SMS, persist.

    Returns the dict shape the /api/act handler returns to the caller:

      {
        "ran": false,
        "awaiting_sms_confirm": true,
        "task_id": "...",
        "expires_at": <unix>,
        "proposal_text": "...",
        "to_number": "...",
        "twilio": {"ok": bool, "twilio_sid": "...", "mock": bool},
      }
    """
    store = store or PendingConfirmStore()
    now = time.time()
    task_id = uuid.uuid4().hex[:16]
    to_number = resolve_destination_number()
    proposal = build_proposal_text(plan, instruction)
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
    )
    sms_result = send_sms_sync(to_number, rec.proposal_text)
    rec.twilio_sid = str(sms_result.get("twilio_sid") or "")
    store.save(rec)
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
        "twilio": {
            "ok": bool(sms_result.get("ok")),
            "twilio_sid": sms_result.get("twilio_sid", ""),
            "mock": bool(sms_result.get("mock")),
            "error": sms_result.get("error"),
            "mock_reason": sms_result.get("mock_reason"),
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
# back-compat surface used by the server.py /api/act gate.
# ----------------------------------------------------------------------
__all__ = [
    "DEFAULT_TTL_SECONDS",
    "PendingConfirm",
    "PendingConfirmStore",
    "STATUS_APPROVED",
    "STATUS_CANCELLED",
    "STATUS_EDIT_REQUESTED",
    "STATUS_EXPIRED",
    "STATUS_PENDING",
    "build_proposal_text",
    "create_pending_confirm",
    "expire_pending",
    "parse_reply",
    "resolve_destination_number",
    "resolve_inbound",
    "send_sms_sync",
    "should_pre_confirm",
]
