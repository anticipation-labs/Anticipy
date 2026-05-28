"""
Bridge that drives the **wearer's actual Chrome** through the existing
Anticipy Chrome extension — never spawns a separate Chromium/Patchright.

Architecture:

  ProactiveEngine emits Decision (in this codespace, on the wearer's Mac,
  wherever the brain runs)
        │
        ▼
  RealtimePublishExecutor (this file)
        │
        ├── upsert into anticipy_intents (Supabase table)
        │       row: user_id, action_type, summary_for_user, status='confirmed'
        │
        ├── broadcast 'confirmed_intent' to channel 'anticipy-intents'
        │       The Chrome extension's background.js subscribes to this
        │       channel and filters by user_id. When it sees a confirmed_intent
        │       for its user, the extension's own BrowserAgent runs the action
        │       in the wearer's actual Chrome — real cookies, real profile,
        │       real residential IP.
        │
        ├── poll anticipy_intents.status until extension reports
        │       'executed' or 'failed'
        │
        └── run EndStateVerifier on the extension's reported result
              cop-out #8: never trust the extension's self-report alone

Cop-out #25 (added this round): **No spawning a separate browser binary in
production.** The wearer's browser is the wearer's actual Chrome. No Patchright
or headless_shell subprocess in the production action path. Patchright is
acceptable only for test fixtures.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

import httpx

from app import messages as msg
from app import supabase_client
from app.config import SUPABASE_ANON_KEY, SUPABASE_URL
from app.proactive.types import Decision, DecisionKind, EngineStatusEvent
from app.verifier import EndStateVerifier, Verdict

logger = logging.getLogger("engine.bridge_extension")


SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

REALTIME_TOPIC = "anticipy-intents"
REALTIME_EVENT_CONFIRMED = "confirmed_intent"
REALTIME_EVENT_NEW = "new_intent"


# ─────────────────────────────────────────────────────────────────
# Supabase Realtime broadcast (server → channel) over REST
# ─────────────────────────────────────────────────────────────────


def _service_headers() -> dict:
    """Headers using the service role key (required for Realtime broadcast
    + bypassing RLS on writes)."""
    key = SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


async def broadcast_to_realtime(
    topic: str,
    event: str,
    payload: dict,
    *,
    timeout: float = 10.0,
) -> bool:
    """POST to Supabase Realtime broadcast endpoint.

    Returns True on 2xx, False otherwise. Never raises — broadcast failure
    is surfaced via the executor's EngineStatusEvent so the wearer gets an
    honest message, not a stack trace.
    """
    if not SUPABASE_URL:
        logger.warning("broadcast skipped: SUPABASE_URL unset")
        return False
    url = f"{SUPABASE_URL.rstrip('/')}/realtime/v1/api/broadcast"
    body = {"messages": [{"topic": topic, "event": event, "payload": payload}]}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, headers=_service_headers(), json=body)
        if 200 <= resp.status_code < 300:
            return True
        logger.warning(
            "realtime broadcast %s/%s failed: %s %s",
            topic, event, resp.status_code, resp.text[:200],
        )
        return False
    except Exception:
        logger.exception("realtime broadcast raised")
        return False


# ─────────────────────────────────────────────────────────────────
# Decision → anticipy_intents row mapping
# ─────────────────────────────────────────────────────────────────


def _urgency_to_importance(level: int) -> str:
    """Map cascade Urgency.level (1..5) → anticipy_intents.importance."""
    if level >= 5:
        return "critical"
    if level >= 3:
        return "important"
    if level >= 2:
        return "standard"
    return "low"


def decision_to_intent_row(decision: Decision, user_id: str) -> dict:
    """Map a cascade Decision to the schema the Chrome extension expects.

    The schema mirrors what `/api/engine/analyze` (Next.js) produces, so the
    extension does not need to change to consume Python-cascade-produced
    intents.
    """
    intent = decision.intent
    created_iso = time.strftime(
        "%Y-%m-%dT%H:%M:%S.000Z",
        time.gmtime(decision.created_at),
    )
    return {
        "id": decision.decision_id,
        "user_id": user_id,
        "action_type": intent.action_verb or "general_action",
        "summary_for_user": (intent.text or "").strip(),
        "evidence_quote": "",
        "importance": _urgency_to_importance(decision.urgency.level),
        "confidence": float(decision.confidence.score),
        "parameters": intent.parameters or {},
        "status": "confirmed" if decision.kind == DecisionKind.EXECUTE else "pending",
        "created_at": created_iso,
    }


# ─────────────────────────────────────────────────────────────────
# RealtimePublishExecutor — implements the Executor protocol
# ─────────────────────────────────────────────────────────────────


WearerMessageFn = Callable[[dict], Awaitable[None]]


@dataclass
class RealtimePublishExecutor:
    """Executor that drives the wearer's Chrome via the existing extension.

    Constructor parameters:

    user_id              wearer's id (extension filters Realtime broadcasts on this)
    verifier             EndStateVerifier; if None, the extension's self-report
                         is trusted (NOT recommended — cop-out #8)
    on_wearer_message    optional callback called when intermediate status is
                         worth surfacing to the wearer (e.g., "Sent to your
                         browser, running...")
    poll_timeout_s       how long to wait for the extension to report back
                         before declaring a timeout; default 4 minutes (a real
                         OpenTable booking can take that long)
    poll_interval_s      cadence on the result-row poll
    """

    user_id: str
    verifier: EndStateVerifier | None = None
    on_wearer_message: WearerMessageFn | None = None
    poll_timeout_s: float = 240.0
    poll_interval_s: float = 2.0

    async def _emit(self, message: dict) -> None:
        if self.on_wearer_message is None:
            return
        try:
            await self.on_wearer_message(message)
        except Exception:
            logger.exception("on_wearer_message raised")

    async def execute(self, decision: Decision) -> EngineStatusEvent:
        # Same defensive guard as bridge.py: only EXECUTE decisions.
        # ASK decisions should already be confirmed → become EXECUTE upstream.
        if decision.kind != DecisionKind.EXECUTE:
            logger.error(
                "bridge_extension: refused non-EXECUTE decision kind=%s id=%s",
                decision.kind, decision.decision_id,
            )
            return EngineStatusEvent(
                decision_id=decision.decision_id,
                stage="error",
                message=msg.CONNECTION_ERROR,
            )

        intent_row = decision_to_intent_row(decision, self.user_id)

        # ── 1. Upsert the intent so the extension can find it by id
        try:
            inserted = await supabase_client.upsert_row("anticipy_intents", intent_row)
        except Exception:
            logger.exception("anticipy_intents upsert raised")
            inserted = None
        if inserted is None:
            logger.warning(
                "anticipy_intents upsert returned None for %s — broadcast will still fire",
                decision.decision_id,
            )

        # ── 2. Broadcast to the channel the extension subscribes to
        ok = await broadcast_to_realtime(
            topic=REALTIME_TOPIC,
            event=REALTIME_EVENT_CONFIRMED,
            payload={
                "intent": intent_row,
                "user_id": self.user_id,
            },
        )
        if not ok:
            return EngineStatusEvent(
                decision_id=decision.decision_id,
                stage="error",
                message="I couldn't reach your browser. Make sure the Anticipy extension is running and try again.",
            )

        await self._emit({
            "type": "status",
            "message": "Sent to your browser — running on your tab.",
        })

        # ── 3. Poll for the extension to report back
        deadline = time.time() + self.poll_timeout_s
        final_status = ""
        execution_result = ""
        last_status_emitted = ""
        while time.time() < deadline:
            try:
                rows = await supabase_client.select_rows(
                    "anticipy_intents",
                    filters={"id": decision.decision_id},
                    limit=1,
                )
            except Exception:
                logger.exception("poll raised")
                rows = []

            if rows:
                row = rows[0]
                cur_status = row.get("status", "")
                execution_result = (row.get("execution_result") or "")
                if cur_status in ("executed", "failed"):
                    final_status = cur_status
                    break
                # Surface intermediate progress without spamming
                if cur_status and cur_status != last_status_emitted:
                    last_status_emitted = cur_status
                    if cur_status not in ("confirmed", "pending"):
                        await self._emit({
                            "type": "status",
                            "message": f"Browser update: {cur_status}",
                        })

            await asyncio.sleep(self.poll_interval_s)

        if final_status not in ("executed", "failed"):
            return EngineStatusEvent(
                decision_id=decision.decision_id,
                stage="error",
                message="My browser didn't get back to me in time. Want me to try again?",
            )

        if final_status == "failed":
            return EngineStatusEvent(
                decision_id=decision.decision_id,
                stage="error",
                message=execution_result or "I started but couldn't finish that one. Want me to retry?",
            )

        # ── 4. Verify (cop-out #8: extension's "executed" is its self-report)
        if self.verifier is not None:
            try:
                verdict: Verdict = await self.verifier.verify(
                    goal=intent_row.get("summary_for_user") or decision.intent.text,
                    history_summary=execution_result,
                )
            except Exception:
                logger.exception("bridge_extension: verifier raised; fail-closed")
                return EngineStatusEvent(
                    decision_id=decision.decision_id,
                    stage="error",
                    message="I couldn't confirm that finished. Want me to retry?",
                )
            if not verdict.passed:
                return EngineStatusEvent(
                    decision_id=decision.decision_id,
                    stage="error",
                    message=(
                        verdict.honest_message_for_wearer
                        or "I started but couldn't fully confirm it finished. Want me to retry?"
                    ),
                )

        # Extension says executed AND verifier says passed (or no verifier).
        return EngineStatusEvent(
            decision_id=decision.decision_id,
            stage="completed",
            message=execution_result or decision.completion_message or "Done.",
        )


def make_production_executor(
    *,
    user_id: str,
    on_wearer_message: WearerMessageFn | None = None,
    enable_verification: bool = True,
) -> RealtimePublishExecutor:
    """Build a RealtimePublishExecutor with the default verifier wired in."""
    verifier: EndStateVerifier | None = None
    if enable_verification:
        from app.verifier import make_default_verifier
        verifier = make_default_verifier()
    return RealtimePublishExecutor(
        user_id=user_id,
        verifier=verifier,
        on_wearer_message=on_wearer_message,
    )
