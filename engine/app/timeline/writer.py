"""Unified timeline writer.

Append-only JSONL feed at ``~/.anticipy/v7/timeline.jsonl``. One row per
Anticipy action across every channel (SMS, voice, email, web, notes,
user replies). This module owns the write path; reads live in
``reader.py``.

==============================================================================
PLAN.md  (integration points; do NOT edit those files from this module)
==============================================================================

This module owns ``engine/app/timeline/``. Another agent owns server.py,
sms_pre_confirm.py, and notifier.py. The following call sites are where
``timeline.append(...)`` should be invoked from once those agents wire
the integration. File paths and line numbers are pinned to the state at
the time this module was created.

1. SMS outbound (Twilio / broker)
   - engine/app/product/server.py:9469
       ``result = _sms_pre.send_sms_sync(phone, body, "receipt")``
       After this call returns, emit:
         kind="sms_sent", channel="twilio_sms",
         status="done" if result.get("ok") else "failed",
         summary=f"SMS receipt to {phone}",
         payload={"to": phone, "body": body,
                  "twilio_sid": result.get("delivery", {}).get("twilio_sid"),
                  "source": "broker"}
   - engine/app/product/server.py:9524
       ``result = asyncio.run(_twilio_sms(phone, body))`` (direct path)
       Same emit, source="direct".
   - engine/app/product/server.py:12188 and 12250
       /api/notify endpoints. Same shape, kind="sms_sent" or "voice_call"
       depending on the channel variable.
   - engine/app/product/sms_pre_confirm.py:634 (``send_sms_sync``)
       Wrap the final return so every send funnels through one writer
       call. payload should include category ("receipt", "preconfirm",
       "fallback") for filtering in the popover.
   - engine/app/product/sms_pre_confirm.py:1148, 1151, 1165, 1326
       (SMS dispatched as part of the pre-confirm cascade). status
       starts "wait_user" when the SMS is asking for YES/NO, flips to
       "done" once handle_inbound resolves it.

2. Voice outbound (Twilio voice)
   - engine/app/product/server.py:12252
       ``result = await _twilio_voice(to_number, body=body or title)``
       Emit kind="voice_call", channel="twilio_voice",
       status="done" if ok else "failed".
   - engine/app/product/server.py:2272 (onboarding call)
       Emit kind="voice_call", channel="twilio_voice", payload includes
       "purpose": "onboarding".

3. Email outbound (Resend or Gmail CDP draft)
   - engine/app/product/server.py:9613
       ``result = create_gmail_draft(DraftRequest(...))``
       Emit kind="email_sent", channel="chrome", status="done" on draft
       creation success, payload includes message_id, sent_link,
       screenshot_path, draft-only flag.
   - engine/app/product/server.py:9934
       ``email_result = _send_receipt_email_via_cdp(...)``
       Same emit; the wrapper already gathers the metadata.
   - Future: when Resend broker lands at /api/email/receipt, emit
       channel="resend" and store the Resend message ID in payload.

4. Web actions (chrome.debugger via universal_surface_runtime)
   - engine/app/product/server.py:3459
       ``response = _run_action_engine(instruction, plan)``
       After the action returns, emit kind="web_action", channel="chrome",
       status from response (ran/completed -> "done", gated -> "wait_user",
       error -> "failed"), summary=instruction[:200],
       payload={"plan": plan, "result_url": ..., "screenshot_path": ...}.
   - engine/app/product/server.py:9089 (``_run_action_engine``)
       The same call site; one emit per dispatcher invocation, not per
       primitive step.

5. Notes (silent feed entries)
   - engine/app/proactive/notifier.py:447-459 (``_record_to_feed``)
       When ``decision.kind == DecisionKind.LOG`` or when channel is
       NOTED, emit kind="note", channel="popover", status="done",
       summary=_body_for(decision)[:200], payload={"decision_id": ...,
       "intent_id": decision.intent.intent_id, "urgency": ...}.

6. User replies (inbound SMS / popover input)
   - engine/app/product/server.py:10551 (``sms_inbound`` handler)
       After parsing ``body_text`` and ``from_number``, emit
       kind="user_reply", channel="twilio_sms", status="done",
       summary=body_text[:200],
       payload={"from": from_number, "message_sid": ...,
                "task_id_hint": task_id_hint, "speech": bool(speech_result)}
       BEFORE running resolve_inbound so the timeline shows the reply
       even when classification fails.
   - engine/app/product/sms_pre_confirm.py:1228 (``resolve_inbound``)
       No additional emit; the server.py handler is the canonical entry.

Ordering rule for callers: ``append`` the row AFTER the action completes
(or fails) but BEFORE any user-visible UI update, so the popover never
shows an action without a backing timeline entry. For long-running
actions (web action that takes 10+ seconds), emit a "pending" row at
start and a second row with the same goal_id at end.

==============================================================================
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

# Required top-level fields for every timeline row. Anything else can
# live in ``payload`` (free-form dict). ``goal_id`` and ``ts`` are
# auto-filled when omitted, so they're not in the validation list.
REQUIRED_FIELDS = ("kind", "status", "summary")

# Allowed values per ARCHITECTURE.md section 3. We accept anything for
# ``channel`` because new channels (push, email reply via reply.anticipy.ai,
# native Mac notification) may land before this list is updated; the
# popover treats unknown channels as a generic icon.
VALID_KINDS = {
    "email_sent",
    "sms_sent",
    "voice_call",
    "web_action",
    "note",
    "user_reply",
}

VALID_STATUSES = {"pending", "done", "failed", "wait_user"}

# Default JSONL path. Override via ``ANTICIPY_TIMELINE_PATH`` for tests
# or alternate installs.
DEFAULT_TIMELINE_PATH = Path.home() / ".anticipy" / "v7" / "timeline.jsonl"

# Rotate when the file grows past this many bytes. 100 MB per
# ARCHITECTURE.md section 3 ("max 100 MB"). Exposed so tests can monkey
# patch a smaller value.
MAX_BYTES_BEFORE_ROTATE = 100 * 1024 * 1024

# Lock guarding the append + rotation critical section. One process-wide
# lock is sufficient: every write is a single line, and the lock is held
# only for the duration of the syscall sequence. No external readers
# coordinate through this lock; readers use seek + read on a closed
# snapshot.
_WRITE_LOCK = threading.Lock()


def _resolve_path() -> Path:
    """Return the active timeline path, honoring the env override."""
    override = os.environ.get("ANTICIPY_TIMELINE_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return DEFAULT_TIMELINE_PATH


def new_goal_id() -> str:
    """Generate a short goal id of the form ``g-<12 hex>``.

    Matches the example shape in ARCHITECTURE.md ("g-abc123"). We use 12
    hex chars (48 bits) for a comfortable collision margin without
    making the popover labels unreadable.
    """
    return f"g-{uuid.uuid4().hex[:12]}"


def _validate(entry: dict[str, Any]) -> None:
    """Raise ``ValueError`` when a row is missing required fields or
    carries an invalid kind / status. ``ts`` and ``goal_id`` are
    auto-filled by ``append`` so they're not enforced here."""
    if not isinstance(entry, dict):
        raise ValueError("timeline.append: entry must be a dict")
    for field in REQUIRED_FIELDS:
        if field not in entry or entry[field] in (None, ""):
            raise ValueError(
                f"timeline.append: missing required field {field!r}"
            )
    kind = entry["kind"]
    if kind not in VALID_KINDS:
        raise ValueError(
            f"timeline.append: invalid kind {kind!r}; "
            f"expected one of {sorted(VALID_KINDS)}"
        )
    status = entry["status"]
    if status not in VALID_STATUSES:
        raise ValueError(
            f"timeline.append: invalid status {status!r}; "
            f"expected one of {sorted(VALID_STATUSES)}"
        )
    summary = entry["summary"]
    if not isinstance(summary, str):
        raise ValueError("timeline.append: summary must be a string")


def _rotate_if_needed(path: Path) -> None:
    """Move the active jsonl to a dated .bak when it exceeds the
    rotation threshold. Caller must hold ``_WRITE_LOCK``.

    Rotated file lands at ``timeline.jsonl.YYYY-MM-DD.bak``. If a backup
    already exists for the same day (multiple rotations in one calendar
    day), append a numeric suffix so nothing is overwritten.
    """
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return
    if size < MAX_BYTES_BEFORE_ROTATE:
        return
    stamp = time.strftime("%Y-%m-%d", time.gmtime())
    candidate = path.with_suffix(path.suffix + f".{stamp}.bak")
    suffix = 1
    while candidate.exists():
        candidate = path.with_suffix(
            path.suffix + f".{stamp}.{suffix}.bak"
        )
        suffix += 1
    try:
        path.rename(candidate)
    except OSError:
        # If rotation fails (e.g. read-only mount mid-flight) we keep
        # writing to the active file. The rotation will retry on the
        # next append.
        return


def append(entry: dict[str, Any]) -> None:
    """Append one timeline row to ``~/.anticipy/v7/timeline.jsonl``.

    Validation:
      - ``kind``, ``status``, ``summary`` are required (ValueError if
        missing).
      - ``kind`` must be one of ``VALID_KINDS``.
      - ``status`` must be one of ``VALID_STATUSES``.
      - ``goal_id`` auto-filled with ``new_goal_id()`` when omitted.
      - ``ts`` auto-filled with ``time.time()`` when omitted.

    Concurrency:
      - One process-wide ``threading.Lock`` serializes writes.
      - Each call opens with ``O_APPEND | O_CREAT | O_WRONLY``, writes
        exactly one line ending in ``\\n``, flushes, and closes. The
        kernel guarantees atomic O_APPEND for writes <= PIPE_BUF on
        POSIX, and a single short JSON line easily fits.
      - Rotation happens inside the lock so no row can land in a file
        that just got renamed.

    Errors:
      - ``ValueError`` on validation failure.
      - ``OSError`` propagates from filesystem operations (caller can
        decide whether to swallow).
    """
    _validate(entry)
    row = dict(entry)
    if "goal_id" not in row or not row["goal_id"]:
        row["goal_id"] = new_goal_id()
    if "ts" not in row or row["ts"] is None:
        row["ts"] = time.time()
    # ``json.dumps`` with ``ensure_ascii=False`` keeps non-ASCII
    # summaries (names, emoji-free unicode punctuation) readable in the
    # popover without a decoding round-trip. ``separators=(",", ":")``
    # keeps the line compact so 100 MB holds many entries.
    line = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
    payload = (line + "\n").encode("utf-8")
    path = _resolve_path()
    with _WRITE_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        _rotate_if_needed(path)
        # Open with O_APPEND so multiple processes (engine + watchdog +
        # the integration test harness) can write concurrently without
        # stepping on each other. flock would be stricter but is
        # overkill for in-process serialization, which the lock above
        # already provides.
        fd = os.open(
            str(path),
            os.O_WRONLY | os.O_APPEND | os.O_CREAT,
            0o644,
        )
        try:
            os.write(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
