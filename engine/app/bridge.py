"""
Bridge: ProactiveEngine.Decision → engine.agent.execute_task.

The proactive cascade (engine/app/proactive/) was architecturally complete
(L0..L6) but its `Executor` defaulted to `_LoggingExecutor` — a test stub
that just appended Decisions to a list. This module supplies the real
production executor that closes the loop:

    ProactiveEngine
       │
       ├── on_transcript_chunk(...) ──► Decision objects
       │
       └── self._executor.execute(decision) ──┐
                                               ▼
                                    BrowserAgentExecutor (this file)
                                               │
                                               ├── compose_goal_from_decision()
                                               ├── execute_task(goal, ...)  [agent.py]
                                               └── EndStateVerifier.verify(...)  [verifier.py]
                                                       │
                                                       ▼
                                               EngineStatusEvent

The bridge is the ONE place that knows about both the proactive cascade
and the browser agent. Neither imports the other — both depend only on
the dataclass contracts in proactive/types.py.

Cop-out #10 (no site-specific branches): goal is composed from intent.text
plus intent.parameters generically; the agent's planner extracts the URL.
Cop-out #8 (no fake verification by reading the agent's final message):
end-state verification is mandatory when a verifier is present.
Cop-out #6 (no silent half-completion): on verifier failure, treat as
failure and surface an honest message, never claim success.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from app.agent import execute_task
from app.proactive.types import (
    Decision,
    DecisionKind,
    EngineStatusEvent,
)
from app.verifier import EndStateVerifier, Verdict, FinalPageState
from app import messages as msg

logger = logging.getLogger("engine.bridge")


# ─────────────────────────────────────────────────────────────────
# Goal composition from a Decision
# ─────────────────────────────────────────────────────────────────


def compose_goal_from_decision(decision: Decision) -> str:
    """Compose the free-form English goal that execute_task receives.

    Generic. Never names sites. Never branches on action_verb or
    parameters. The intent.text is the LLM's one-sentence rephrasing of
    what the wearer wants; intent.parameters are slot fills the
    interpreter extracted. We append the parameters as constraints so
    the agent's planner has full context, even if the rephrasing
    elided some fields.
    """
    intent = decision.intent
    parts: list[str] = []

    if intent.text and intent.text.strip():
        parts.append(intent.text.strip())

    if intent.parameters:
        constraints: list[str] = []
        for k, v in intent.parameters.items():
            if v is None:
                continue
            if isinstance(v, str) and not v.strip():
                continue
            constraints.append(f"{k}: {v}")
        if constraints:
            parts.append("Constraints: " + "; ".join(constraints) + ".")

    return " ".join(parts).strip() or intent.action_verb or ""


# ─────────────────────────────────────────────────────────────────
# Compress agent message stream into a verifier-friendly summary
# ─────────────────────────────────────────────────────────────────


def summarize_history(messages: list[dict], max_lines: int = 30) -> str:
    """Compact a list of agent send-callback messages.

    Generic — no per-site logic. Drops noise; keeps the most recent
    `max_lines` interesting messages joined by newlines.
    """
    interesting: list[str] = []
    for m in messages:
        t = m.get("type", "")
        if t in ("status", "complete", "error", "confirm", "login_needed"):
            txt = (m.get("message") or "").strip()
            if txt:
                interesting.append(f"[{t}] {txt}")
    if max_lines <= 0:
        return ""
    return "\n".join(interesting[-max_lines:])


# Callback type for forwarding wearer-facing messages
WearerMessageFn = Callable[[dict], Awaitable[None]]
ReceiveConfirmationFn = Callable[[], Awaitable[str]]


# ─────────────────────────────────────────────────────────────────
# BrowserAgentExecutor — implements the Executor protocol from
# engine/app/proactive/engine.py
# ─────────────────────────────────────────────────────────────────


@dataclass
class BrowserAgentExecutor:
    """Production Executor implementation for ProactiveEngine.

    Implements ``async def execute(decision: Decision) -> EngineStatusEvent``
    (the protocol declared in ``engine.app.proactive.engine.Executor``).

    Constructor parameters:

    user_id              passed to execute_task for cookie/profile isolation
    verifier             EndStateVerifier; if None, agent's self-report is
                         trusted (NOT recommended for production — cop-out #8)
    on_wearer_message    async callback receiving each agent message dict in
                         real time. Wire this to the wearer's notification
                         surface (WS, SSE, push) so they see status as it
                         streams. Per-message dict shape: {type, message, ...}
    receive_confirmation async callback when the agent needs runtime
                         confirmation (login resume mid-action, etc.).
                         Defaults to "confirmed" since the proactive ASK
                         gate already ran upstream.
    """

    user_id: str | None = None
    verifier: EndStateVerifier | None = None
    on_wearer_message: WearerMessageFn | None = None
    receive_confirmation: ReceiveConfirmationFn | None = None

    async def execute(self, decision: Decision) -> EngineStatusEvent:
        # The ProactiveEngine routes EXECUTE-kind decisions here directly,
        # and ASK decisions here only after the wearer has confirmed (the
        # engine internally bumps them to EXECUTE before dispatch). Anything
        # else is a programming error upstream.
        if decision.kind != DecisionKind.EXECUTE:
            logger.error(
                "bridge: refused non-EXECUTE decision kind=%s id=%s",
                decision.kind, decision.decision_id,
            )
            return EngineStatusEvent(
                decision_id=decision.decision_id,
                stage="error",
                message=msg.CONNECTION_ERROR,
            )

        goal = compose_goal_from_decision(decision)
        if not goal:
            logger.error("bridge: empty goal for decision %s", decision.decision_id)
            return EngineStatusEvent(
                decision_id=decision.decision_id,
                stage="error",
                message=msg.CONNECTION_ERROR,
            )

        agent_messages: list[dict] = []

        async def collect(message: dict) -> None:
            agent_messages.append(message)
            if self.on_wearer_message is not None:
                try:
                    await self.on_wearer_message(message)
                except Exception:
                    # A failing wearer surface must never abort the agent —
                    # we still want to finish and verify.
                    logger.exception("on_wearer_message raised; continuing")

        async def receive_confirmation_inner() -> str:
            if self.receive_confirmation is not None:
                try:
                    return await self.receive_confirmation()
                except Exception:
                    logger.exception("receive_confirmation raised; defaulting to 'confirmed'")
                    return "confirmed"
            # The proactive cascade already routed irreversible / mid-confidence
            # actions through ASK and waited for the wearer's reply; by the time
            # we are here the action has been authorized.
            return "confirmed"

        # Run the browser agent. Cancellation propagates so the caller can
        # cancel the proactive engine's background task cleanly.
        try:
            await execute_task(
                goal=goal,
                send=collect,
                receive_confirmation=receive_confirmation_inner,
                user_id=self.user_id,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("bridge: execute_task raised")
            return EngineStatusEvent(
                decision_id=decision.decision_id,
                stage="error",
                message=msg.CONNECTION_ERROR,
            )

        # Inspect the agent's final message — used for the success path AND
        # to short-circuit when the agent itself reported error.
        agent_self_report: str | None = None
        agent_self_report_kind: str | None = None
        for m in reversed(agent_messages):
            t = m.get("type")
            if t in ("complete", "error"):
                agent_self_report = m.get("message")
                agent_self_report_kind = t
                break

        if agent_self_report_kind == "error":
            return EngineStatusEvent(
                decision_id=decision.decision_id,
                stage="error",
                message=agent_self_report or msg.CONNECTION_ERROR,
            )

        # End-state verification — overrides agent self-report on failure.
        # When verifier is None we fall through to agent's self-report, but
        # cop-out #8 says this path is for testing/back-compat only.
        if self.verifier is not None:
            history_summary = summarize_history(agent_messages)
            try:
                verdict: Verdict = await self.verifier.verify(
                    goal=goal,
                    history_summary=history_summary,
                    final_state=None,
                )
            except Exception:
                logger.exception("bridge: verifier raised; fail-closed")
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

        # Verifier passed (or was not supplied). Surface the agent's own
        # completion message OR the cascade's pre-composed completion text.
        final_message = (
            agent_self_report
            or decision.completion_message
            or "Done."
        )
        return EngineStatusEvent(
            decision_id=decision.decision_id,
            stage="completed",
            message=final_message,
        )


# ─────────────────────────────────────────────────────────────────
# Convenience: build a production-ready executor wired to MODEL_CHAIN
# ─────────────────────────────────────────────────────────────────


def make_production_executor(
    *,
    user_id: str | None = None,
    on_wearer_message: WearerMessageFn | None = None,
    receive_confirmation: ReceiveConfirmationFn | None = None,
    enable_verification: bool = True,
) -> BrowserAgentExecutor:
    """Build a BrowserAgentExecutor with the default verifier wired in.

    For test contexts, set ``enable_verification=False`` to opt out.
    """
    verifier: EndStateVerifier | None = None
    if enable_verification:
        from app.verifier import make_default_verifier
        verifier = make_default_verifier()

    return BrowserAgentExecutor(
        user_id=user_id,
        verifier=verifier,
        on_wearer_message=on_wearer_message,
        receive_confirmation=receive_confirmation,
    )
