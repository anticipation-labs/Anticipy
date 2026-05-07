"""
Dispatcher: AI-driven dedup gate at the moment of dispatch.

The cascade extracts intents per chunk; the settling buffer collapses
intents within the same buffer window; consolidate_pending merges across
the buffer at flush time. None of these layers see decisions that have
ALREADY been announced to the user — so when the user circles back to a
goal three minutes later, the engine re-extracts, re-decides, and fires
a new notification for what is, semantically, a re-mention.

Dispatcher closes that gap. Before each settled decision is announced,
it asks the model: against the last N decisions we've already fired in
this session, is this new candidate a distinct goal, or a re-mention?

  - distinct  → admit, fire normally, record into recent buffer
  - re-mention → drop silently (the user already got the notification)

No keywords. No verb-string matching. The dispatcher carries no rules
about content; it is a pure "have we already told the user about this?"
gate driven by an LLM that sees both sides.

Fail-open by design: any error / timeout admits the decision. Better to
occasionally double-fire than to silently drop a real new intent.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Awaitable, Callable, Deque

from .types import Decision

logger = logging.getLogger("engine.proactive.dispatcher")


LlmCall = Callable[[str, str], Awaitable[str]]


# Default memory window: 10 minutes of dispatched-decision history. Past this,
# a re-mention probably IS a fresh goal (the user circled back after enough
# time that a reminder is warranted). Tunable via constructor.
DEFAULT_WINDOW_SECONDS = 600.0
DEFAULT_HISTORY_SIZE = 30
DEFAULT_TIMEOUT_SECONDS = 8.0


@dataclass
class _RecentDispatch:
    decision_id: str
    intent_id: str
    verb: str
    text: str
    parameters: dict
    timestamp: float


@dataclass
class AdmitVerdict:
    admit: bool
    duplicate_of: str | None  # decision_id of the prior dispatch that subsumes this one
    reasoning: str


_SYS = (
    "You are checking whether a new candidate intent is a re-mention or duplicate "
    "of any intent already dispatched to the user earlier in this same conversation. "
    "The user is wearing an AI assistant that hears their continuous speech, and they "
    "naturally circle back to topics — re-stating, refining, or reinforcing goals "
    "they've already mentioned. The model that extracted this candidate had no "
    "knowledge of what was already dispatched.\n\n"
    "Output STRICT JSON only:\n"
    '{ "duplicate_of": <integer id from the existing list, or null>, '
    '"reasoning": "<one short sentence>" }\n\n'
    "Set duplicate_of to the id of an existing intent if they share the SAME "
    "underlying real-world goal:\n"
    "  - same task, same person, same item, same destination — even if the verbs "
    "are different (\"book appointment\" / \"set reminder for appointment\" / "
    "\"schedule physical with Dr Chen\" all dispatch the same goal).\n"
    "  - one is a refinement that adds detail to a previously-dispatched goal.\n"
    "  - one is a sub-task that exists only to fulfill a previously-dispatched goal.\n\n"
    "Set duplicate_of to null ONLY when the new candidate is a genuinely distinct "
    "goal — different person, different task, different concrete subject — that the "
    "user would benefit from seeing as its own notification.\n\n"
    "Bias toward duplicate when uncertain: a missed real-new-goal becomes a notification "
    "later when the user re-mentions; a wrongly-fired duplicate is the spammy failure "
    "mode we are eliminating."
)


class Dispatcher:
    """AI-driven dispatch dedup. One model call per candidate dispatch."""

    def __init__(
        self,
        llm_call: LlmCall | None = None,
        *,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        history_size: int = DEFAULT_HISTORY_SIZE,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._llm_call = llm_call
        self._window = window_seconds
        self._timeout = timeout_seconds
        self._recent: Deque[_RecentDispatch] = deque(maxlen=max(1, history_size))

    def record(self, decision: Decision) -> None:
        """Stamp a decision as having been announced. Future admit() calls
        in the same session will see it as a possible duplicate target."""
        self._recent.append(_RecentDispatch(
            decision_id=decision.decision_id,
            intent_id=decision.intent.intent_id,
            verb=decision.intent.action_verb,
            text=decision.intent.text,
            parameters=dict(decision.intent.parameters or {}),
            timestamp=time.time(),
        ))

    async def admit(self, decision: Decision) -> AdmitVerdict:
        """Decide whether this candidate dispatch should fire.

        Returns admit=True if distinct or if the dispatcher fails to reach
        the model (fail-open). Returns admit=False with duplicate_of set if
        the model recognizes a prior dispatch that subsumes this one.
        """
        cutoff = time.time() - self._window
        recent = [r for r in self._recent if r.timestamp >= cutoff]
        if not recent or self._llm_call is None:
            return AdmitVerdict(admit=True, duplicate_of=None, reasoning="no_recent_or_no_llm")

        candidates = [
            {
                "id": i,
                "verb": r.verb,
                "text": r.text,
                "parameters": r.parameters,
            }
            for i, r in enumerate(recent)
        ]
        user_prompt = (
            f"New candidate intent (NOT yet announced):\n"
            f"  verb: {decision.intent.action_verb}\n"
            f"  text: {decision.intent.text}\n"
            f"  parameters: {json.dumps(decision.intent.parameters or {}, default=str)}\n\n"
            f"Already-announced intents from this conversation (oldest first):\n"
            f"{json.dumps(candidates, indent=2, default=str)}\n\n"
            f"Output the JSON."
        )
        try:
            raw = await asyncio.wait_for(
                self._llm_call(_SYS, user_prompt),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("dispatcher_admit_timeout", extra={
                "decision_id": decision.decision_id,
                "verb": decision.intent.action_verb,
            })
            return AdmitVerdict(admit=True, duplicate_of=None, reasoning="timeout_fail_open")
        except Exception:
            logger.exception("dispatcher_admit_error")
            return AdmitVerdict(admit=True, duplicate_of=None, reasoning="error_fail_open")

        try:
            data = json.loads((raw or "").strip() or "{}")
        except (ValueError, TypeError):
            return AdmitVerdict(admit=True, duplicate_of=None, reasoning="bad_json_fail_open")
        if not isinstance(data, dict):
            return AdmitVerdict(admit=True, duplicate_of=None, reasoning="not_object_fail_open")
        dup = data.get("duplicate_of")
        reason = str(data.get("reasoning", "")).strip()[:160]
        if dup is None:
            return AdmitVerdict(admit=True, duplicate_of=None, reasoning=reason or "distinct")
        try:
            dup_idx = int(dup)
        except (TypeError, ValueError):
            return AdmitVerdict(admit=True, duplicate_of=None, reasoning="bad_dup_id_fail_open")
        if 0 <= dup_idx < len(recent):
            return AdmitVerdict(
                admit=False,
                duplicate_of=recent[dup_idx].decision_id,
                reasoning=reason or "duplicate",
            )
        return AdmitVerdict(admit=True, duplicate_of=None, reasoning="dup_id_out_of_range")
