"""Failure recovery transparency for the action engine.

When the agent drives a real site and can't finish because Gmail is
logged out, MFA appeared, CAPTCHA blocked, the IP is rate-limited, or
the network dropped, today the engine returns a silent error. The user
has no way to know what to fix or when to expect a retry. This module
closes that gap.

Three responsibilities:

1. `classify_failure(error)` reads a raw exception or error string and
   returns one of six `FailureKind` values (login_required, mfa_challenge,
   captcha_blocked, rate_limited, network_error, unknown_error).
2. `format_recovery_sms(failure_kind, surface_url, ...)` builds a plain
   English SMS body the user actually wants to receive. No jargon. No
   stack traces. Names the recipient and the surface, tells the user
   what to fix, promises a retry. No em-dashes anywhere.
3. `route_recovery(task_id, failure_kind, surface_url, ...)` is the
   single entry point the action engine wrapper calls when it catches
   a failure. It sends the SMS via the existing
   `app.product.sms_pre_confirm.send_sms_sync` path (mock-friendly in
   dev) and parks the task in the persistent queue with
   `wait_for_recovery: true` in metadata so the dispatcher does not
   retry until the user has had a chance to fix it. On the next inject
   for the same task_id, the dispatcher picks it back up automatically.

Design constraints:
- Pure stdlib + the existing notifier helpers. No new dependencies.
- Never raises. A recovery failure cannot itself crash the action path.
- The SMS fires once per failure event. The persisted record carries
  `recovery_sms_sent_at` so a re-classification of the same task does
  not double-send.
- This module is a SIBLING of the frozen engine/app/action_engine tree.
  It MUST NOT import from action_engine at module load time.
- The friendly SMS is the surface; the queue park is the spine. Both
  are best-effort. If Twilio is mocked we still park the task; if the
  queue write fails we still send the SMS.

Layout for the persisted record fields (added to TaskRecord.metadata):

  {
    "wait_for_recovery": true,
    "recovery_failure_kind": "login_required",
    "recovery_surface_url": "https://mail.google.com/mail/u/0/#inbox",
    "recovery_sms_sent_at": 1748555200.0,
    "recovery_sms_body": "Anticipy couldn't ...",
    "recovery_sms_twilio_sid": "SM...",
    "recovery_sms_mock": false,
    "recovery_originating_instruction": "send Sarah the deck",
    "recovery_recipient_hint": "Sarah",
  }
"""

from __future__ import annotations

import logging
import re
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any, Optional


logger = logging.getLogger("engine.product.failure_recovery")


# ----------------------------------------------------------------------
# FailureKind taxonomy
# ----------------------------------------------------------------------

FAILURE_LOGIN_REQUIRED = "login_required"
FAILURE_MFA_CHALLENGE = "mfa_challenge"
FAILURE_CAPTCHA_BLOCKED = "captcha_blocked"
FAILURE_RATE_LIMITED = "rate_limited"
FAILURE_NETWORK_ERROR = "network_error"
FAILURE_UNKNOWN_ERROR = "unknown_error"


_VALID_FAILURE_KINDS = (
    FAILURE_LOGIN_REQUIRED,
    FAILURE_MFA_CHALLENGE,
    FAILURE_CAPTCHA_BLOCKED,
    FAILURE_RATE_LIMITED,
    FAILURE_NETWORK_ERROR,
    FAILURE_UNKNOWN_ERROR,
)


# Pattern tables. Order matters: the first match wins, so the more
# specific signals (MFA, CAPTCHA) sit above the general ones (login).
# We match against the lowercased error string AND the exception class
# name when an exception is supplied.
_MFA_PATTERNS = (
    "mfa",
    "two factor",
    "two-factor",
    "2fa",
    "2-factor",
    "two step",
    "two-step",
    "verification code",
    "verify it's you",
    "verify your identity",
    "security code",
    "authentication code",
    "one time password",
    "one-time password",
    "totp",
    "authenticator app",
    "approve sign in",
    "approve sign-in",
)

_CAPTCHA_PATTERNS = (
    "captcha",
    "recaptcha",
    "re-captcha",
    "hcaptcha",
    "h-captcha",
    "turnstile",
    "challenge page",
    "press and hold",
    "i am not a robot",
    "i'm not a robot",
    "are you a human",
    "are you human",
    "verify you are human",
)

_LOGIN_PATTERNS = (
    "sign in",
    "sign-in",
    "signin",
    "log in",
    "log-in",
    "login",
    "authenticate",
    "authentication required",
    "session expired",
    "logged out",
    "log out",
    "not signed in",
    "please log in",
    "please sign in",
    "accounts.google.com",
    "login.microsoftonline.com",
    "id.atlassian.com",
    "auth required",
    "401 unauthorized",
    "403 forbidden",
)

_RATE_LIMIT_PATTERNS = (
    "rate limit",
    "rate-limit",
    "rate_limit",
    "too many requests",
    "429",
    "throttl",  # throttled / throttling
    "slow down",
    "try again later",
    "quota exceeded",
    "usage limit",
    "blocked: ip",
    "datadome",
    "akamai bot",
    "cloudflare blocked",
)

_NETWORK_PATTERNS = (
    "network error",
    "connection refused",
    "connection reset",
    "connection aborted",
    "connection timeout",
    "connection timed out",
    "timed out",
    "timeout",
    "no route to host",
    "name or service not known",
    "name resolution",
    "dns",
    "ssl: ",
    "ssl error",
    "tls error",
    "certificate verify failed",
    "econnreset",
    "econnrefused",
    "etimedout",
    "enetunreach",
    "remote disconnected",
    "broken pipe",
)


def _normalize_error_text(error: Any) -> tuple[str, str]:
    """Return (lowercased_message, exception_class_name) tuple. Both
    sides are safe to grep against the pattern tables above.
    """
    if error is None:
        return "", ""
    if isinstance(error, BaseException):
        cls = type(error).__name__
        try:
            msg = str(error)
        except Exception:
            msg = repr(error)
        return msg.lower(), cls
    try:
        return str(error).lower(), ""
    except Exception:
        return repr(error).lower(), ""


def classify_failure(error: Any) -> str:
    """Map an exception or error string to one of the six FailureKind
    values. Never raises. Returns FAILURE_UNKNOWN_ERROR when nothing
    matches so the caller can still notify the user.

    Pattern matching order is deliberate: MFA / CAPTCHA / login are
    more specific than rate-limit / network, so they win when both
    signals appear in the same error string.
    """
    msg, cls = _normalize_error_text(error)
    if not msg and not cls:
        return FAILURE_UNKNOWN_ERROR
    haystack = f"{msg} {cls.lower()}"
    for pat in _MFA_PATTERNS:
        if pat in haystack:
            return FAILURE_MFA_CHALLENGE
    for pat in _CAPTCHA_PATTERNS:
        if pat in haystack:
            return FAILURE_CAPTCHA_BLOCKED
    for pat in _LOGIN_PATTERNS:
        if pat in haystack:
            return FAILURE_LOGIN_REQUIRED
    for pat in _RATE_LIMIT_PATTERNS:
        if pat in haystack:
            return FAILURE_RATE_LIMITED
    for pat in _NETWORK_PATTERNS:
        if pat in haystack:
            return FAILURE_NETWORK_ERROR
    return FAILURE_UNKNOWN_ERROR


# ----------------------------------------------------------------------
# SMS body composer
# ----------------------------------------------------------------------

def _service_label_from_url(url: str) -> str:
    """Best-effort friendly name for the surface. Falls back to the
    bare hostname, then to a generic 'the site' so the SMS always
    reads as a complete sentence.
    """
    if not url:
        return "the site"
    try:
        netloc = urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return "the site"
    if not netloc:
        return "the site"
    # Strip leading www. so 'mail.google.com' beats 'www.mail.google.com'
    if netloc.startswith("www."):
        netloc = netloc[4:]
    friendly_map = {
        "mail.google.com": "Gmail",
        "calendar.google.com": "Google Calendar",
        "drive.google.com": "Google Drive",
        "docs.google.com": "Google Docs",
        "sheets.google.com": "Google Sheets",
        "accounts.google.com": "your Google account",
        "login.microsoftonline.com": "your Microsoft account",
        "login.live.com": "your Microsoft account",
        "outlook.office.com": "Outlook",
        "outlook.live.com": "Outlook",
        "app.slack.com": "Slack",
        "slack.com": "Slack",
        "trello.com": "Trello",
        "linear.app": "Linear",
        "notion.so": "Notion",
        "github.com": "GitHub",
        "twitter.com": "X (Twitter)",
        "x.com": "X (Twitter)",
        "linkedin.com": "LinkedIn",
        "stripe.com": "Stripe",
        "dashboard.stripe.com": "Stripe",
        "amazon.com": "Amazon",
        "appleid.apple.com": "your Apple ID",
        "dropbox.com": "Dropbox",
        "calendly.com": "Calendly",
    }
    if netloc in friendly_map:
        return friendly_map[netloc]
    # Pop one subdomain at a time looking for a known root.
    parts = netloc.split(".")
    for i in range(1, len(parts) - 1):
        candidate = ".".join(parts[i:])
        if candidate in friendly_map:
            return friendly_map[candidate]
    return netloc


def _action_summary(instruction: str, recipient_hint: str = "") -> str:
    """Build the 'because Anticipy was trying to ...' fragment of the
    SMS. Keeps the body grounded so the user understands which task
    paused, not just that something paused.
    """
    instr = (instruction or "").strip()
    rec = (recipient_hint or "").strip()
    if rec and instr:
        return f"sending the email to {rec}"
    if rec:
        return f"the task for {rec}"
    if instr:
        # Trim to a manageable phrase. The full instruction can be a
        # paragraph; the SMS keeps it short.
        snippet = re.sub(r"\s+", " ", instr)
        if len(snippet) > 80:
            snippet = snippet[:77].rstrip() + "..."
        return snippet
    return "the task"


def _action_link(failure_kind: str, surface_url: str) -> str:
    """Return the URL we tell the user to tap. For Gmail / Google
    login walls we prefer the canonical mail.google.com so the user
    lands in their inbox, not a buried OAuth redirect.
    """
    url = (surface_url or "").strip()
    if not url:
        return ""
    if failure_kind == FAILURE_LOGIN_REQUIRED:
        try:
            netloc = urllib.parse.urlparse(url).netloc.lower()
        except Exception:
            netloc = ""
        if "accounts.google.com" in netloc:
            return "https://mail.google.com/"
    return url


def format_recovery_sms(
    failure_kind: str,
    surface_url: str,
    *,
    instruction: str = "",
    recipient_hint: str = "",
) -> str:
    """Build the SMS body the user will see when a real action fails.

    Style rules (from the project guide):
      - Plain English. No jargon. No HTTP codes. No stack traces.
      - No em-dashes. Use periods, commas, parens.
      - One short paragraph. Hard cap 320 chars so a single SMS
        segment lands on every carrier.
      - End with a clear promise: "I will retry once you do."

    The format is deliberately friendly so the user does not feel
    like they got an error log on their phone.
    """
    kind = (failure_kind or "").strip() or FAILURE_UNKNOWN_ERROR
    service = _service_label_from_url(surface_url)
    summary = _action_summary(instruction, recipient_hint)
    link = _action_link(kind, surface_url)
    tap_clause = f" Tap to fix: {link}." if link else ""

    if kind == FAILURE_LOGIN_REQUIRED:
        body = (
            f"Anticipy couldn't finish {summary} because {service} "
            f"is logged out."
            f"{tap_clause}"
            f" I will retry once you sign in."
        )
    elif kind == FAILURE_MFA_CHALLENGE:
        body = (
            f"Anticipy couldn't finish {summary} because {service} "
            f"asked you to verify your identity."
            f"{tap_clause}"
            f" I will retry once you do."
        )
    elif kind == FAILURE_CAPTCHA_BLOCKED:
        body = (
            f"Anticipy couldn't finish {summary} because {service} "
            f"is showing a CAPTCHA."
            f"{tap_clause}"
            f" I will retry once you solve it."
        )
    elif kind == FAILURE_RATE_LIMITED:
        body = (
            f"Anticipy couldn't finish {summary} because {service} "
            f"asked us to slow down. I will retry in a few minutes."
            f"{tap_clause}"
        )
    elif kind == FAILURE_NETWORK_ERROR:
        body = (
            f"Anticipy couldn't finish {summary} because of a "
            f"network blip on {service}. I will retry shortly."
            f"{tap_clause}"
        )
    else:
        body = (
            f"Anticipy paused {summary} on {service} and needs a "
            f"hand."
            f"{tap_clause}"
            f" I will retry once you take a look."
        )

    body = re.sub(r"\s+", " ", body).strip()
    # Twilio single-segment SMS is 160 ASCII chars but most modern
    # carriers concatenate up to 1600. Cap at 320 to keep the
    # message readable and avoid surprise multi-part charges.
    return body[:320]


# ----------------------------------------------------------------------
# Persistent queue + SMS dispatch
# ----------------------------------------------------------------------

@dataclass
class RecoveryRouteResult:
    """Return shape for route_recovery, structured so the caller can
    inspect what happened without re-parsing strings.
    """
    ok: bool
    task_id: str
    failure_kind: str
    sms_body: str
    sms_sent: bool
    sms_mock: bool
    sms_twilio_sid: str
    sms_error: str
    queue_parked: bool
    queue_error: str
    duplicate_skip: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "task_id": self.task_id,
            "failure_kind": self.failure_kind,
            "sms_body": self.sms_body,
            "sms_sent": self.sms_sent,
            "sms_mock": self.sms_mock,
            "sms_twilio_sid": self.sms_twilio_sid,
            "sms_error": self.sms_error,
            "queue_parked": self.queue_parked,
            "queue_error": self.queue_error,
            "duplicate_skip": self.duplicate_skip,
        }


def _resolve_destination_phone(override: str = "") -> str:
    """Reuse the same destination resolution the SMS pre-confirm path
    uses so the recovery SMS lands at the same number as the
    confirmation SMS the user already trusts. Falls back to the env
    vars directly so this module still works if sms_pre_confirm cannot
    be imported (defense in depth).
    """
    if (override or "").strip():
        return override.strip()
    try:
        from app.product import sms_pre_confirm as _sms_pre
        resolved = _sms_pre.resolve_destination_number()
        if resolved:
            return resolved
    except Exception:
        pass
    import os
    raw = (os.environ.get("TWILIO_TEST_TO_REAL_NUMBER_E164") or "").strip()
    if raw:
        return raw
    raw = (os.environ.get("TWILIO_NOTIFY_TO") or "").strip()
    if raw:
        return raw
    return ""


def _send_recovery_sms(body: str, to_number: str) -> dict[str, Any]:
    """Wrap sms_pre_confirm.send_sms_sync so the recovery SMS path
    benefits from the same mock-friendly behavior the pre-confirm
    gate already has.
    """
    if not to_number:
        return {
            "ok": False,
            "twilio_sid": "",
            "mock": False,
            "error": "no destination phone",
        }
    try:
        from app.product import sms_pre_confirm as _sms_pre
    except Exception as exc:
        return {
            "ok": False,
            "twilio_sid": "",
            "mock": False,
            "error": f"sms_pre_confirm import failed: "
                     f"{type(exc).__name__}: {exc}",
        }
    try:
        return _sms_pre.send_sms_sync(to_number, body)
    except Exception as exc:
        return {
            "ok": False,
            "twilio_sid": "",
            "mock": False,
            "error": f"send_sms_sync raised: "
                     f"{type(exc).__name__}: {exc}",
        }


def _park_task_in_queue(
    task_id: str,
    failure_kind: str,
    surface_url: str,
    sms_body: str,
    sms_result: dict[str, Any],
    instruction: str,
    recipient_hint: str,
) -> tuple[bool, str, bool]:
    """Move the persisted task into waiting status with the recovery
    metadata stamped on it. Returns (parked, error, duplicate_skip).

    Duplicate guard: if the existing record already has
    `wait_for_recovery: true` AND the same failure_kind, we skip the
    SMS to avoid double-notifying. The caller decides whether to
    still re-send (currently we do not).
    """
    try:
        from app import task_queue as _tq
    except Exception as exc:
        return False, f"task_queue import failed: " \
                      f"{type(exc).__name__}: {exc}", False
    try:
        rec = _tq.get(task_id) if task_id else None
    except Exception as exc:
        return False, f"task_queue.get failed: " \
                      f"{type(exc).__name__}: {exc}", False
    if rec is None:
        # No queue record (this can happen if the action was driven
        # directly via /api/act without the listen pipeline). Enqueue
        # a fresh entry so the recovery sticks across restarts.
        try:
            rec = _tq.enqueue(
                instruction or f"recovery: {failure_kind}",
                metadata={
                    "source": "failure_recovery_route",
                    "wait_for_recovery": True,
                    "recovery_failure_kind": failure_kind,
                    "recovery_surface_url": surface_url,
                    "recovery_sms_sent_at": time.time()
                                            if sms_result.get("ok") else 0.0,
                    "recovery_sms_body": sms_body,
                    "recovery_sms_twilio_sid": str(
                        sms_result.get("twilio_sid") or ""),
                    "recovery_sms_mock": bool(sms_result.get("mock")),
                    "recovery_originating_instruction": instruction or "",
                    "recovery_recipient_hint": recipient_hint or "",
                },
            )
        except Exception as exc:
            return False, f"task_queue.enqueue failed: " \
                          f"{type(exc).__name__}: {exc}", False
        try:
            _tq.wait_for(rec.task_id, f"recovery:{failure_kind}")
        except Exception:
            # Best-effort: enqueue alone is enough to keep the task
            # alive. The wait_for guarantees the dispatcher will not
            # immediately re-fire.
            pass
        return True, "", False

    # Existing record. Check the duplicate guard.
    md = dict(rec.metadata or {})
    if (md.get("wait_for_recovery") is True
            and md.get("recovery_failure_kind") == failure_kind):
        return True, "", True

    md["wait_for_recovery"] = True
    md["recovery_failure_kind"] = failure_kind
    md["recovery_surface_url"] = surface_url
    md["recovery_sms_sent_at"] = (time.time() if sms_result.get("ok")
                                   else 0.0)
    md["recovery_sms_body"] = sms_body
    md["recovery_sms_twilio_sid"] = str(sms_result.get("twilio_sid") or "")
    md["recovery_sms_mock"] = bool(sms_result.get("mock"))
    if instruction:
        md.setdefault("recovery_originating_instruction", instruction)
    if recipient_hint:
        md.setdefault("recovery_recipient_hint", recipient_hint)
    rec.metadata = md
    try:
        _tq.wait_for(task_id, f"recovery:{failure_kind}")
        # wait_for re-writes the record. We need to stamp metadata
        # after the wait_for call because store.wait_for only mutates
        # status / waiting_reason / updated_at; metadata stays whatever
        # we set above on the in-memory rec object, but the journal
        # entry written by wait_for re-serializes asdict(rec) so the
        # metadata we just mutated IS persisted.
    except Exception as exc:
        return False, f"task_queue.wait_for failed: " \
                      f"{type(exc).__name__}: {exc}", False
    return True, "", False


def route_recovery(
    task_id: str,
    failure_kind: str,
    surface_url: str,
    *,
    instruction: str = "",
    recipient_hint: str = "",
    to_phone: str = "",
) -> dict[str, Any]:
    """Single entry point for the action engine wrapper. Sends a
    friendly SMS and parks the task in the queue with
    `wait_for_recovery: true`. Never raises; always returns a dict
    the caller can log.

    Idempotency: if the persisted task already has the same
    `recovery_failure_kind`, we skip the SMS (duplicate_skip=True)
    but still report ok=True so the caller does not see this as a
    failure.

    The SMS goes out via the same Twilio path the pre-confirm uses,
    so the mock-friendly behavior in dev is identical: no real
    network call without TWILIO_TEST_TO_REAL_NUMBER=1, but the queue
    parking + persisted metadata still land so tests can verify the
    full handoff.
    """
    kind = (failure_kind or "").strip()
    if kind not in _VALID_FAILURE_KINDS:
        kind = FAILURE_UNKNOWN_ERROR
    body = format_recovery_sms(
        kind, surface_url,
        instruction=instruction,
        recipient_hint=recipient_hint,
    )
    to_number = _resolve_destination_phone(to_phone)

    # Pre-flight duplicate check so we do not send the SMS when the
    # task is already parked under the same recovery kind.
    duplicate = False
    try:
        from app import task_queue as _tq
        existing = _tq.get(task_id) if task_id else None
        if existing is not None:
            md = dict(existing.metadata or {})
            if (md.get("wait_for_recovery") is True
                    and md.get("recovery_failure_kind") == kind):
                duplicate = True
    except Exception:
        # Pre-flight failure: treat as not-duplicate and fall through
        # to the regular send path. The park step will surface any
        # real queue error in the result.
        pass

    if duplicate:
        logger.info(
            "failure_recovery_duplicate_skip task_id=%s kind=%s",
            task_id, kind,
        )
        parked_ok, parked_err, _ = _park_task_in_queue(
            task_id, kind, surface_url, body,
            {"ok": False, "twilio_sid": "", "mock": False,
             "error": "duplicate_skip"},
            instruction, recipient_hint,
        )
        return RecoveryRouteResult(
            ok=True,
            task_id=task_id,
            failure_kind=kind,
            sms_body=body,
            sms_sent=False,
            sms_mock=False,
            sms_twilio_sid="",
            sms_error="",
            queue_parked=parked_ok,
            queue_error=parked_err,
            duplicate_skip=True,
        ).to_dict()

    sms_result = _send_recovery_sms(body, to_number)
    parked_ok, parked_err, was_dup = _park_task_in_queue(
        task_id, kind, surface_url, body, sms_result,
        instruction, recipient_hint,
    )
    sms_ok = bool(sms_result.get("ok"))
    sms_mock = bool(sms_result.get("mock"))
    return RecoveryRouteResult(
        ok=(sms_ok or sms_mock or parked_ok),
        task_id=task_id,
        failure_kind=kind,
        sms_body=body,
        sms_sent=sms_ok and not sms_mock,
        sms_mock=sms_mock,
        sms_twilio_sid=str(sms_result.get("twilio_sid") or ""),
        sms_error=str(sms_result.get("error") or ""),
        queue_parked=parked_ok,
        queue_error=parked_err,
        duplicate_skip=was_dup,
    ).to_dict()


# ----------------------------------------------------------------------
# Public surface
# ----------------------------------------------------------------------

__all__ = [
    "FAILURE_CAPTCHA_BLOCKED",
    "FAILURE_LOGIN_REQUIRED",
    "FAILURE_MFA_CHALLENGE",
    "FAILURE_NETWORK_ERROR",
    "FAILURE_RATE_LIMITED",
    "FAILURE_UNKNOWN_ERROR",
    "RecoveryRouteResult",
    "classify_failure",
    "format_recovery_sms",
    "route_recovery",
]
