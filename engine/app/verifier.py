"""
End-state verifier for browser actions.

After Browser Use says "done", the verifier checks whether the goal was
actually achieved. Browser Use's self-report is unreliable — it routinely
says done on failure (page loaded ≠ task completed). The verifier:

  1. Sees the original goal, a compressed history of agent actions, and the
     final page state (URL, title, visible text).
  2. Asks an LLM, generically: "what evidence on this page proves the goal
     was achieved? Quote it verbatim."
  3. Returns a Verdict with passed=True/False, the evidence (or what's
     missing), and a wearer-honest message.

No site-specific evidence types. No regex on page content. The model
handles ambiguity. Cop-out #8: never trust the agent's self-report alone.
Cop-out #6: when verification can't run, fail closed and tell the wearer.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable

LlmCall = Callable[[str, str], Awaitable[str]]

logger = logging.getLogger("engine.verifier")


@dataclass
class FinalPageState:
    """What the verifier sees about the post-agent state."""

    url: str = ""
    title: str = ""
    visible_text: str = ""           # extracted page text, will be truncated
    history_summary: str = ""        # compressed agent action log


@dataclass
class Verdict:
    """Outcome of end-state verification."""

    passed: bool
    evidence: str = ""              # exact quote from the page proving completion
    missing: list[str] = field(default_factory=list)  # expected evidence not present
    confidence: float = 0.0         # verifier's self-rated confidence 0..1
    honest_message_for_wearer: str = ""  # plain-English message if !passed
    reasoning: str = ""             # one-sentence why


_VERIFIER_SYSTEM = """\
You verify whether a browser-automation goal was actually achieved.

You see:
  - The original GOAL (one English sentence).
  - A short summary of what the agent DID (its action history).
  - The FINAL page state: URL, title, and visible text on the page after the
    agent stopped.

Your ONE job: decide whether there is concrete, page-visible evidence that
the goal was completed.

Output STRICT JSON only:
{
  "passed": <true|false>,
  "evidence": "<exact short quote from the page proving completion, or empty>",
  "missing": ["<expected piece of evidence absent from the page>", ...],
  "confidence": <0.0..1.0>,
  "honest_message_for_wearer": "<one-sentence plain-English message; only set when passed=false>",
  "reasoning": "<one short sentence on why>"
}

Rules:
  - PASSED only when the visible page text contains direct evidence the
    goal was achieved (a confirmation number, a "thank you, your reservation
    is confirmed" sentence, an explicit "order placed" message with concrete
    detail, an answer to a fact-finding question quoted from the page).
  - The agent claiming "done" is NOT evidence. Only the page text counts.
  - For fact-finding goals, evidence is the answer quoted from the page.
  - A generic search-results page, an empty page, an error page, or a login
    page is NOT evidence of completion. passed=false.
  - When passed=false, the honest_message_for_wearer must be specific about
    what didn't finish. "I started the booking but couldn't see a
    confirmation. Want me to retry, or check your email?" is good.
    "Failed" is bad.
  - In doubt: passed=false. False positives ship the wrong outcome to the
    wearer; false negatives just ask them to double-check.

The honest_message_for_wearer must contain no technical jargon (no model
names, no JSON, no IDs, no "DOM", no "selector", no "session", no URLs).
"""


class EndStateVerifier:
    """Asks an LLM whether the goal was actually completed based on page state."""

    def __init__(self, llm_call: LlmCall) -> None:
        self._llm_call = llm_call

    async def verify(
        self,
        goal: str,
        final_state: FinalPageState | None = None,
        history_summary: str = "",
    ) -> Verdict:
        # If we have no signal at all, fail-closed (cop-out #6).
        if final_state is None and not (history_summary or "").strip():
            return Verdict(
                passed=False,
                confidence=1.0,
                honest_message_for_wearer="I couldn't tell whether that finished. Want me to retry?",
                reasoning="no final state and no history captured",
            )

        state = final_state or FinalPageState(history_summary=history_summary)
        history = state.history_summary or history_summary or "(no history captured)"

        user_prompt = (
            f"GOAL: {goal}\n\n"
            f"AGENT ACTION HISTORY:\n{history}\n\n"
            f"FINAL PAGE STATE:\n"
            f"  url: {state.url or '(unknown)'}\n"
            f"  title: {state.title or '(unknown)'}\n"
            f"  visible text (truncated):\n"
            f"\"\"\"\n{(state.visible_text or '(empty)')[:4000]}\n\"\"\"\n\n"
            "Output the JSON."
        )

        try:
            raw = await self._llm_call(_VERIFIER_SYSTEM, user_prompt)
        except Exception:
            logger.exception("verifier llm_call raised")
            return Verdict(
                passed=False,
                honest_message_for_wearer="I couldn't confirm that finished. Want me to retry?",
                reasoning="verifier llm error",
            )

        if not raw or not raw.strip():
            return Verdict(
                passed=False,
                honest_message_for_wearer="I couldn't confirm that finished. Want me to retry?",
                reasoning="verifier returned empty",
            )

        try:
            data = json.loads(raw.strip())
        except (ValueError, TypeError):
            logger.warning("verifier non-JSON: %r", raw[:200])
            return Verdict(
                passed=False,
                honest_message_for_wearer="I couldn't confirm that finished. Want me to retry?",
                reasoning="verifier malformed JSON",
            )

        if not isinstance(data, dict):
            return Verdict(
                passed=False,
                honest_message_for_wearer="I couldn't confirm that finished. Want me to retry?",
                reasoning="verifier non-dict JSON",
            )

        passed = bool(data.get("passed", False))
        evidence = str(data.get("evidence") or "").strip()

        missing_raw = data.get("missing", [])
        if isinstance(missing_raw, list):
            missing = [str(m).strip() for m in missing_raw if str(m).strip()]
        else:
            missing = []

        try:
            confidence = float(data.get("confidence") or 0.0)
        except (ValueError, TypeError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        honest = str(data.get("honest_message_for_wearer") or "").strip()
        reasoning = str(data.get("reasoning") or "").strip()

        # Sanity floor on honest message — never leave the wearer with no signal.
        if not passed and not honest:
            honest = "I started but couldn't fully confirm it finished. Want me to retry?"

        return Verdict(
            passed=passed,
            evidence=evidence,
            missing=missing,
            confidence=confidence,
            honest_message_for_wearer=honest,
            reasoning=reasoning,
        )


def make_default_verifier() -> EndStateVerifier:
    """Build a verifier wired to the engine's MODEL_CHAIN via the proactive llm adapter."""
    from app.proactive.llm_adapter import make_json_llm_call
    return EndStateVerifier(llm_call=make_json_llm_call(max_tokens=512))


# ─────────────────────────────────────────────────────────────────────────
# Multi-agent role wrapper — always runs the deterministic end-state
# verifier from app.end_state_verifier on the agent's done() claim.
#
# The LLM-based EndStateVerifier above is a fallback/judge-of-last-resort
# kept for the proactive bridge. The deterministic per-kind library is the
# +25-40 quality lever: it re-fetches the effect surface (Sent folder,
# calendar, cart, etc.) and asserts generic, observable properties without
# trusting the agent's self-report (cop-out #8).
# ─────────────────────────────────────────────────────────────────────────


@dataclass
class DoneVerification:
    """Outcome of the role-keyed verifier wrapping ``end_state_verifier``.

    A thin re-shape of ``end_state_verifier.VerificationResult`` so the
    agent's main loop can pattern-match a stable contract independently of
    the underlying engine. ``passed`` mirrors ``ok``; ``honest_message`` is
    pre-rendered for direct surfacing to the wearer.
    """

    passed: bool
    missing: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    honest_message: str = ""
    task_kind: str = "generic"


_FAILURE_MESSAGE_BY_KIND: dict[str, str] = {
    "read_extract": (
        "I couldn't find the answer on the page. Want me to try again, or "
        "do you want a different source?"
    ),
    "email_send": (
        "I couldn't confirm the email actually sent. Check your Sent folder, "
        "or want me to retry?"
    ),
    "calendar_create": (
        "I couldn't see the event in your calendar yet. Want me to retry, "
        "or check it manually?"
    ),
    "comment_post": (
        "I couldn't see the comment on the page. Want me to retry, or do "
        "you want to post it manually?"
    ),
    "cart_add": (
        "I couldn't see the item in your cart. Want me to retry?"
    ),
    "form_submit": (
        "I couldn't see a confirmation. Want me to retry, or check the "
        "site directly?"
    ),
    "generic": (
        "I started but couldn't fully confirm it finished. Want me to retry?"
    ),
}


def _honest_message_for(task_kind: str, missing: list[str]) -> str:
    """Pick a wearer-friendly failure message based on what was missing."""
    base = _FAILURE_MESSAGE_BY_KIND.get(task_kind, _FAILURE_MESSAGE_BY_KIND["generic"])
    return base


async def verify_at_done(
    task_kind: str,
    task_text: str,
    agent_done_payload: dict,
    bridge,
    *,
    user_id: str | None = None,
) -> DoneVerification:
    """Always-runs verifier called when the agent claims ``done``.

    Delegates to ``app.end_state_verifier.verify_end_state`` — the
    deterministic per-task-kind assertion library. Re-shapes the result
    so the agent loop has a single stable contract:

      passed:        bool — same as VerificationResult.ok
      missing:       list[str] of expected facts/effects not found
      evidence:      list[str] of supporting quotes/URLs
      honest_message: pre-composed wearer-facing message on failure
      task_kind:     normalised kind ("generic" if unknown)

    Args:
        task_kind: planner-supplied task kind. See end_state_verifier for
            the supported set. Unknown kinds fall through to ``generic``.
        task_text: the wearer's original task phrase.
        agent_done_payload: the dict the agent passed to ``done(...)``. Often
            includes ``message``/``answer`` plus task-specific fields like
            ``subject``, ``title``, ``cart_url``.
        bridge: any object implementing the BridgeProtocol from
            end_state_verifier (``navigate``, ``get_text``, ``get_url``).
        user_id: forwarded for telemetry; the deterministic verifier itself
            does not call any LLM and so does not log paid calls.

    Returns:
        DoneVerification. ``passed=False`` MUST block the success message and
        force the wearer-honest message.

    WIRE-ME: ``app/agent.py`` should call this once when the agent claims
    done(), and:
      - on ``passed=True`` → emit the agent's success message;
      - on ``passed=False`` → emit ``DoneVerification.honest_message`` and
        log ``DoneVerification.missing`` for telemetry.
    """
    from app.end_state_verifier import (
        VerificationResult,
        verify_end_state,
    )

    kind = (task_kind or "").strip().lower() or "generic"
    if not isinstance(agent_done_payload, dict):
        agent_done_payload = {}

    try:
        result: VerificationResult = await verify_end_state(
            task_kind=kind,
            task_text=task_text or "",
            agent_done_payload=agent_done_payload,
            bridge=bridge,
        )
    except Exception:
        logger.exception("verify_at_done: end_state_verifier raised; fail closed")
        return DoneVerification(
            passed=False,
            missing=["verifier_raised"],
            evidence=[],
            honest_message=_FAILURE_MESSAGE_BY_KIND["generic"],
            task_kind=kind,
        )

    if not isinstance(result, VerificationResult):
        return DoneVerification(
            passed=False,
            missing=["verifier_misbehaved"],
            evidence=[],
            honest_message=_FAILURE_MESSAGE_BY_KIND["generic"],
            task_kind=kind,
        )

    honest = "" if result.ok else _honest_message_for(kind, list(result.missing))

    return DoneVerification(
        passed=bool(result.ok),
        missing=list(result.missing),
        evidence=list(result.evidence),
        honest_message=honest,
        task_kind=kind,
    )


__all__ = [
    "EndStateVerifier",
    "FinalPageState",
    "Verdict",
    "DoneVerification",
    "make_default_verifier",
    "verify_at_done",
]
