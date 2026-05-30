"""
Multi-channel notifier.

Selects an escalating channel based on urgency:

    NOTED   → silent, just appears in the "things I noticed" feed
    IN_APP  → in-app notification (badge / inbox row)
    PUSH    → OS push notification on the phone
    SMS     → text message
    VOICE   → outbound voice call

The notifier is a routing/dispatch layer. The actual delivery for each
channel is supplied at construction time as a callable, so:

  - Server-side reference impl: the callables hit Twilio (SMS/voice) and
    APNs/FCM (push); in-app delivery is via a Supabase Realtime broadcast
    on the user's private channel.
  - Phone-side native port: each callable maps to the OS notification API
    (UNUserNotificationCenter on iOS, NotificationManager on Android)
    plus telephony for SMS/voice.

The notifier never hardcodes recipient addresses — it asks an injected
ContactBook for the user's preferred email/phone. That keeps the test
double simple and keeps prod safe (no TEST_USER_PHONE leaking through).

The notifier also writes a NoticedItem to the "things I noticed" feed for
*every* decision regardless of kind, so the user always has a complete
record of what the agent considered.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Protocol

from .types import Decision, DecisionKind, NoticedItem, NotificationChannel

logger = logging.getLogger("engine.proactive.notifier")

# Unified timeline writer. Every "Things I noticed" feed entry also
# lands in ~/.anticipy/v7/timeline.jsonl so the popover can render one
# unified stream. Defensive import so a timeline-module failure cannot
# break notifier delivery.
try:
    from app.timeline import append as _timeline_append
except Exception:  # pragma: no cover - defensive
    def _timeline_append(_entry):  # type: ignore[no-redef]
        return None


# --- Contact book ---------------------------------------------------------------


class ContactBook(Protocol):
    """How the notifier finds the user's preferred destinations."""

    async def email_for(self, user_id: str) -> str | None: ...
    async def phone_for(self, user_id: str) -> str | None: ...
    async def push_token_for(self, user_id: str) -> str | None: ...


@dataclass
class _StubContactBook:
    """For tests and local dev. Returns nothing → notifier no-ops gracefully."""

    async def email_for(self, user_id: str) -> str | None:
        return None

    async def phone_for(self, user_id: str) -> str | None:
        return None

    async def push_token_for(self, user_id: str) -> str | None:
        return None


# --- Delivery callables ---------------------------------------------------------


# Each Deliver* takes (user_id, body) and returns when delivered (or fails).
# Failures should raise, NOT return False — the notifier escalates on raise.
DeliverFn = Callable[[str, str], Awaitable[None]]


@dataclass
class DeliveryRoutes:
    """Pluggable delivery implementations per channel.

    All optional. Missing channels fall through to the next-cheapest channel
    that has an implementation (e.g., no SMS configured → push).
    """

    in_app: DeliverFn | None = None
    push: DeliverFn | None = None
    sms: DeliverFn | None = None
    voice: DeliverFn | None = None


# --- Real delivery implementations ---------------------------------------------
#
# Three concrete deliveries the cascade hands off to. These plug into the
# empty `DeliveryRoutes` slots above via `build_default_routes()` below. The
# cascade picks the channel; these functions actually fire the notification.


_TWILIO_BASE = "https://api.twilio.com/2010-04-01"


def _osascript_available() -> bool:
    """True if macOS `osascript` is on PATH. False on non-mac hosts."""
    return sys.platform == "darwin" and shutil.which("osascript") is not None


def _applescript_quote(value: str) -> str:
    """Escape a string for safe use inside an AppleScript literal."""
    # AppleScript strings are double-quoted; only backslash and double-quote
    # need escaping. Newlines are not allowed inside a string literal, so
    # collapse them to spaces.
    cleaned = (value or "").replace("\r", " ").replace("\n", " ")
    return cleaned.replace("\\", "\\\\").replace("\"", "\\\"")


async def local_notify(title: str, body: str) -> dict:
    """Fire a native macOS notification banner via `osascript`.

    The production default for IN_APP and PUSH decisions when the user
    is on their Mac. Returns a dict with `ok` plus diagnostics so the
    test endpoint and callers can introspect what happened. Raises on
    non-macOS hosts so the notifier escalates down the ladder.
    """
    if not _osascript_available():
        raise RuntimeError(
            "local_notify requires macOS osascript (not available on this host)"
        )
    safe_title = _applescript_quote(title or "Anticipy")
    safe_body = _applescript_quote(body or "")
    script = (
        f'display notification "{safe_body}" with title "{safe_title}"'
    )

    def _run() -> tuple[int, str, str]:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""

    rc, stdout, stderr = await asyncio.to_thread(_run)
    if rc != 0:
        raise RuntimeError(
            f"osascript display notification failed: rc={rc} stderr={stderr.strip()[:200]}"
        )
    return {
        "ok": True,
        "channel": "local",
        "title": title,
        "body": body,
        "stdout": stdout.strip(),
        "stderr": stderr.strip(),
    }


def _twilio_credentials() -> tuple[str, str, str]:
    """Read Twilio creds from env. Raises if any are missing.

    Returns (account_sid, auth_token, from_number). The from_number is
    only required for SMS/voice; callers that don't need it can ignore.
    """
    sid = (os.environ.get("TWILIO_ACCOUNT_SID") or "").strip()
    tok = (os.environ.get("TWILIO_AUTH_TOKEN") or "").strip()
    src = (os.environ.get("TWILIO_PHONE_NUMBER") or "").strip()
    if not sid or not tok:
        raise RuntimeError(
            "twilio creds missing: set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN"
        )
    return sid, tok, src


def _twilio_basic_auth(sid: str, tok: str) -> str:
    token = base64.b64encode(f"{sid}:{tok}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _twilio_post_form(path: str, fields: list[tuple[str, str]],
                      timeout: float = 20.0) -> dict:
    """Blocking POST to a Twilio REST endpoint. Returns parsed JSON or
    raises RuntimeError with the Twilio error body on a non-2xx status.
    """
    sid, tok, _ = _twilio_credentials()
    url = f"{_TWILIO_BASE}/Accounts/{sid}/{path}"
    body = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": _twilio_basic_auth(sid, tok),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read() if exc.fp is not None else b""
        status = exc.code
        try:
            parsed = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            parsed = {"raw": raw.decode("utf-8", "replace")[:400]}
        raise RuntimeError(
            f"twilio POST {path} failed: status={status} body={parsed}"
        )
    except Exception as exc:
        raise RuntimeError(f"twilio POST {path} transport error: {exc}")
    try:
        data = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        data = {"raw": raw.decode("utf-8", "replace")[:400]}
    if status >= 300:
        raise RuntimeError(
            f"twilio POST {path} non-2xx: status={status} body={data}"
        )
    return {"status": status, "response": data}


async def twilio_sms(to: str, body: str) -> dict:
    """Send a real SMS via Twilio.

    `to` and `from` are E.164 phone numbers; `from` is read from the
    TWILIO_PHONE_NUMBER env var. Returns the Twilio response dict on
    success; raises RuntimeError on failure so the cascade can fall
    down the ladder.
    """
    sid, tok, src = _twilio_credentials()
    if not src:
        raise RuntimeError(
            "TWILIO_PHONE_NUMBER missing; required for outbound SMS"
        )
    to_clean = (to or "").strip()
    if not to_clean:
        raise RuntimeError("twilio_sms: 'to' phone number is required")
    fields = [
        ("To", to_clean),
        ("From", src),
        ("Body", (body or "")[:1600]),  # Twilio SMS hard cap
    ]
    out = await asyncio.to_thread(_twilio_post_form, "Messages.json", fields)
    sid_msg = (out.get("response") or {}).get("sid", "")
    return {
        "ok": True,
        "channel": "sms",
        "to": to_clean,
        "from": src,
        "twilio_sid": sid_msg,
        "twilio_status": out.get("status"),
        "twilio_response": out.get("response"),
    }


def _twiml_for_body(body: str) -> str:
    """Build a Twilio-fetchable URL whose response is minimal TwiML that
    speaks the body with the `alice` voice and hangs up. Used as the
    call URL when no externally hosted TwiML endpoint is configured so
    the demo path still places a real call without needing a webhook.
    """
    safe = (body or "Anticipy calling.").replace("\r", " ").replace("\n", " ")
    safe = (
        safe.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\"", "&quot;")
    )
    twiml = (
        "<Response>"
        f"<Say voice=\"alice\">{safe}</Say>"
        "<Hangup/>"
        "</Response>"
    )
    return (
        "http://twimlets.com/echo?Twiml="
        + urllib.parse.quote(twiml, safe="")
    )


async def twilio_voice(to: str, twiml_url: str | None = None,
                       body: str | None = None) -> dict:
    """Place a real outbound Twilio voice call.

    `twiml_url` is a URL Twilio will GET for call instructions. When
    omitted, we fall back to an inline `<Say>{body}</Say>` TwiML hosted
    via twimlets.com so the call still completes for the demo path.
    Raises RuntimeError on failure.
    """
    sid, tok, src = _twilio_credentials()
    if not src:
        raise RuntimeError(
            "TWILIO_PHONE_NUMBER missing; required for outbound voice"
        )
    to_clean = (to or "").strip()
    if not to_clean:
        raise RuntimeError("twilio_voice: 'to' phone number is required")
    url = (twiml_url or "").strip() or _twiml_for_body(body or "")
    fields = [
        ("To", to_clean),
        ("From", src),
        ("Url", url),
    ]
    out = await asyncio.to_thread(_twilio_post_form, "Calls.json", fields)
    call_sid = (out.get("response") or {}).get("sid", "")
    return {
        "ok": True,
        "channel": "voice",
        "to": to_clean,
        "from": src,
        "twiml_url": url,
        "twilio_sid": call_sid,
        "twilio_status": out.get("status"),
        "twilio_response": out.get("response"),
    }


# --- Default wiring -------------------------------------------------------------


def _default_local_notify_title(decision_kind: DecisionKind | None) -> str:
    """Brand-consistent title for the macOS banner. Decisions don't
    carry a title field so synthesize one from the kind.
    """
    if decision_kind == DecisionKind.EXECUTE:
        return "Anticipy: done"
    if decision_kind == DecisionKind.ASK:
        return "Anticipy: needs you"
    if decision_kind == DecisionKind.REFUSE:
        return "Anticipy: held off"
    return "Anticipy"


def build_default_routes(
    *,
    enable_local: bool = True,
    enable_twilio_sms: bool = True,
    enable_twilio_voice: bool = True,
    contact_phone: str | None = None,
) -> DeliveryRoutes:
    """Wire the default production delivery routes.

    - IN_APP and PUSH both bind to `local_notify` so the cascade's
      IN_APP/PUSH decisions fire as macOS notification banners when
      the user is on their Mac.
    - SMS and VOICE bind to Twilio when credentials are present in env
      AND `contact_phone` is supplied. Otherwise those slots are left
      unwired and the notifier ladder falls down to PUSH.
    """
    local: DeliverFn | None = None
    if enable_local and _osascript_available():
        async def _local(user_id: str, body: str) -> None:
            await local_notify(_default_local_notify_title(None), body)
        local = _local

    sms_fn: DeliverFn | None = None
    voice_fn: DeliverFn | None = None
    if (enable_twilio_sms or enable_twilio_voice) and contact_phone:
        try:
            _twilio_credentials()
            creds_ok = True
        except Exception as exc:
            logger.info("twilio_creds_missing", extra={"error": str(exc)})
            creds_ok = False
        if creds_ok and enable_twilio_sms:
            async def _sms(user_id: str, body: str) -> None:
                await twilio_sms(contact_phone, body)
            sms_fn = _sms
        if creds_ok and enable_twilio_voice:
            async def _voice(user_id: str, body: str) -> None:
                await twilio_voice(contact_phone, body=body)
            voice_fn = _voice

    return DeliveryRoutes(
        in_app=local,
        push=local,
        sms=sms_fn,
        voice=voice_fn,
    )


# --- "Things I noticed" feed sink -----------------------------------------------


class NoticedFeed(Protocol):
    """Persists items to the user-visible feed."""

    async def append(self, item: NoticedItem) -> None: ...


@dataclass
class _MemoryNoticedFeed:
    """Default in-memory implementation. Production swaps in Supabase."""

    items: list[NoticedItem] = field(default_factory=list)

    async def append(self, item: NoticedItem) -> None:
        self.items.append(item)


# --- The notifier ---------------------------------------------------------------


class Notifier:
    """Routes a decision to the right channel(s) and records to the feed."""

    def __init__(
        self,
        routes: DeliveryRoutes | None = None,
        contacts: ContactBook | None = None,
        feed: NoticedFeed | None = None,
    ) -> None:
        self._routes = routes or DeliveryRoutes()
        self._contacts = contacts or _StubContactBook()
        self._feed = feed or _MemoryNoticedFeed()

    async def announce(self, decision: Decision) -> None:
        """Deliver per the decision kind + urgency. Always also writes to feed."""
        await self._record_to_feed(decision)

        if decision.kind == DecisionKind.LOG:
            return  # only the feed entry; no channel delivery

        body = _body_for(decision)
        channel = decision.urgency.channel

        # If this is a fyi for an already-executed action, don't escalate
        # past PUSH — we don't wake the user with a voice call to tell
        # them their search got run.
        if decision.kind == DecisionKind.EXECUTE:
            channel = _cap_channel(channel, NotificationChannel.PUSH)

        await self._deliver(decision.intent.user_id, channel, body)

    # --- Internals -------------------------------------------------------------

    async def _record_to_feed(self, decision: Decision) -> None:
        body_text = _body_for(decision)
        item = NoticedItem(
            item_id=uuid.uuid4().hex,
            user_id=decision.intent.user_id,
            session_id="",  # populated by the engine facade if available
            body=body_text,
            decision=decision,
            created_at=time.time(),
        )
        try:
            await self._feed.append(item)
        except Exception:
            logger.exception("noticed_feed_append_failed")
        # Mirror every silent/log entry to the unified timeline so the
        # popover shows a single feed across SMS, voice, email, web
        # actions, AND notes. Only LOG decisions (or any decision
        # routed to the NOTED channel) land here; channel-delivered
        # decisions get their own timeline rows from the delivery path.
        try:
            urgency_channel = decision.urgency.channel
        except Exception:
            urgency_channel = None
        if (decision.kind == DecisionKind.LOG
                or urgency_channel == NotificationChannel.NOTED):
            try:
                _timeline_append({
                    "kind": "note",
                    "channel": "popover",
                    "status": "done",
                    "summary": (body_text or "")[:200],
                    "payload": {
                        "decision_id": decision.decision_id,
                        "intent_id": decision.intent.intent_id,
                        "urgency": int(
                            getattr(decision.urgency, "level", 0) or 0
                        ),
                        "kind": str(decision.kind.value),
                    },
                })
            except Exception:
                pass

    async def _deliver(self, user_id: str, channel: NotificationChannel, body: str) -> None:
        # Walk the channel ladder downward until one succeeds. Each lower
        # rung is less intrusive; we never escalate UP automatically — that
        # would surprise the user.
        ladder = _ladder_from(channel)
        last_err: Exception | None = None
        for c in ladder:
            fn = self._fn_for(c)
            if fn is None:
                continue
            try:
                await fn(user_id, body)
                logger.info("notifier_delivered", extra={
                    "user_id": user_id,
                    "channel": c.value,
                })
                return
            except Exception as exc:
                last_err = exc
                logger.warning("notifier_channel_failed", extra={
                    "user_id": user_id,
                    "channel": c.value,
                    "error": str(exc),
                })
        if last_err is not None:
            logger.error("notifier_all_channels_failed", extra={"user_id": user_id})

    def _fn_for(self, channel: NotificationChannel) -> DeliverFn | None:
        return {
            NotificationChannel.IN_APP: self._routes.in_app,
            NotificationChannel.PUSH: self._routes.push,
            NotificationChannel.SMS: self._routes.sms,
            NotificationChannel.VOICE: self._routes.voice,
            NotificationChannel.NOTED: None,
        }.get(channel)


# --- Helpers --------------------------------------------------------------------


def _body_for(decision: Decision) -> str:
    """The user-visible string for this decision."""
    if decision.kind == DecisionKind.EXECUTE and decision.completion_message:
        return decision.completion_message
    if decision.kind == DecisionKind.ASK and decision.user_facing_question:
        return decision.user_facing_question
    if decision.kind == DecisionKind.REFUSE and decision.refusal_reason:
        return decision.refusal_reason
    # LOG fallback
    return decision.intent.text


def _cap_channel(channel: NotificationChannel, ceiling: NotificationChannel) -> NotificationChannel:
    """Don't deliver above the ceiling. Used to keep fyi-after-execute non-disruptive."""
    order = [
        NotificationChannel.NOTED,
        NotificationChannel.IN_APP,
        NotificationChannel.PUSH,
        NotificationChannel.SMS,
        NotificationChannel.VOICE,
    ]
    if order.index(channel) > order.index(ceiling):
        return ceiling
    return channel


def _ladder_from(channel: NotificationChannel) -> list[NotificationChannel]:
    """Channels to try, in order. Starts at requested channel, falls down on failure."""
    if channel == NotificationChannel.NOTED:
        return []
    order = [
        NotificationChannel.VOICE,
        NotificationChannel.SMS,
        NotificationChannel.PUSH,
        NotificationChannel.IN_APP,
    ]
    if channel not in order:
        return []
    start = order.index(channel)
    return order[start:]
