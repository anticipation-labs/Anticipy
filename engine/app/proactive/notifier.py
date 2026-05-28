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

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Protocol

from .types import Decision, DecisionKind, NoticedItem, NotificationChannel

logger = logging.getLogger("engine.proactive.notifier")


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
        item = NoticedItem(
            item_id=uuid.uuid4().hex,
            user_id=decision.intent.user_id,
            session_id="",  # populated by the engine facade if available
            body=_body_for(decision),
            decision=decision,
            created_at=time.time(),
        )
        try:
            await self._feed.append(item)
        except Exception:
            logger.exception("noticed_feed_append_failed")

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
