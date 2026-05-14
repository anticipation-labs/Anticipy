"""Stage 2 — typed-Intent extraction.

Only runs on utterances Stage 1.5 returned COMMIT (or STORE_AS_LATENT
when the wearer's followup arrives). Produces an Intent object that
mirrors `src/lib/contracts-v2.ts:Intent` exactly so the website / Mac
app TS subscribers can `isIntent(payload)` without translation.

5-way parallel RAG injection per the master prompt:
  - workspace transcript (last 10 min)
  - user memory (sqlite-vec)
  - fleet skill library (matched intents)
  - prior trajectories on the same site
  - global knowledge (relationship facts, recurrences)

The first cut here implements the contract + the LLM extraction. RAG
sources are wired in via the optional `context_*` kwargs — when None,
the cascade still works (just with less context). Pod A1+A5 fill in
the RAG sources progressively.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from app.proactive.hedge_filter import HedgeResult
from app.proactive.llm_adapter import make_json_llm_call

_logger = logging.getLogger("anticipy.proactive.intent_extraction")

_SYSTEM_PROMPT = """\
You are Stage 2 of an ambient AI wearable's intent cascade. Stage 1.5
has already decided this utterance is a COMMIT (or a multi-turn
follow-up to a prior STORE_AS_LATENT). Your job: emit a typed Intent.

Output STRICT JSON only:

{
  "action_category": "<category>",
  "proposed_skill_hint": "<skill_id from library, or null>",
  "slots": {
    "filled":           { "<slot_name>": "<value>", ... },
    "needs_memory":     [ "<slot_name>", ... ],
    "needs_inference":  [ "<slot_name>", ... ],
    "ambiguous":        [ "<slot_name>", ... ]
  },
  "proactivity_score": 0.0..1.0
}

action_category enum (pick one):
  book_reservation | send_email | schedule_event | reorder |
  post_message    | draft_proposal | set_reminder | navigate_to |
  log_expense     | queue_song | create_issue | update_contact |
  file_expense    | fact_lookup

slots.filled  — every slot the utterance pins down verbatim.
slots.needs_memory — slots the executor must look up in the wearer's
                     memory (e.g. "wearer_phone", "preferred_restaurant").
slots.needs_inference — slots derivable from filled+memory ("date"
                        from "next Tuesday", "duration_min" default).
slots.ambiguous — slots that are present but underspecified and would
                  need a clarification.

proactivity_score:
  1.0 — the wearer literally said "book it / send it / order it now"
  0.7 — the wearer named the action but a sensible default of one slot
  0.5 — the wearer named the action but multiple slots ambiguous
  0.3 — STORE_AS_LATENT follow-ups where the action is now clear but
        wasn't in the original turn

NEVER halucinate slot values. If the utterance does not specify a date,
DO NOT fill `slots.filled.date` — put `"date"` in `slots.needs_inference`.
"""


@dataclass(frozen=True, slots=True)
class IntentSlots:
    filled: dict[str, Any] = field(default_factory=dict)
    needs_memory: list[str] = field(default_factory=list)
    needs_inference: list[str] = field(default_factory=list)
    ambiguous: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "filled": self.filled,
            "needs_memory": self.needs_memory,
            "needs_inference": self.needs_inference,
            "ambiguous": self.ambiguous,
        }


@dataclass(frozen=True, slots=True)
class TypedIntent:
    """Mirrors `src/lib/contracts-v2.ts:Intent` exactly."""

    intent_id: str
    user_id: str
    utterance_window: dict  # {transcript_segments, start_ts, end_ts}
    action_category: Optional[str]
    proposed_skill_hint: Optional[str]
    slots: IntentSlots
    detection_confidence: Optional[float]
    hedge_filter_decision: str
    hedge_filter_reason: Optional[str]
    proactivity_score: Optional[float]
    source: str  # "pendant" | "mac_mic" | "typed"
    timestamp: str  # ISO-8601

    def to_db_row(self) -> dict:
        return {
            "intent_id": self.intent_id,
            "user_id": self.user_id,
            "utterance_window": self.utterance_window,
            "action_category": self.action_category,
            "proposed_skill_hint": self.proposed_skill_hint,
            "slots": self.slots.to_dict(),
            "detection_confidence": self.detection_confidence,
            "hedge_filter_decision": self.hedge_filter_decision,
            "hedge_filter_reason": self.hedge_filter_reason,
            "proactivity_score": self.proactivity_score,
            "source": self.source,
        }


class IntentExtractor:
    """Stage 2 extractor. One LLM call per COMMIT utterance."""

    def __init__(self, max_tokens: int = 800) -> None:
        self._llm = make_json_llm_call(max_tokens=max_tokens)

    async def extract(
        self,
        utterance: str,
        user_id: str,
        utterance_window: dict,
        hedge_result: HedgeResult,
        source: str = "mac_mic",
        context_transcript: Optional[str] = None,
        context_memory: Optional[str] = None,
        context_skills: Optional[str] = None,
        context_trajectories: Optional[str] = None,
        detection_confidence: Optional[float] = None,
    ) -> TypedIntent:
        user_parts = []
        if context_transcript:
            user_parts.append(f"WORKSPACE TRANSCRIPT (last 10 min):\n{context_transcript}")
        if context_memory:
            user_parts.append(f"WEARER LONG-TERM MEMORY:\n{context_memory}")
        if context_skills:
            user_parts.append(f"MATCHED SKILLS IN LIBRARY:\n{context_skills}")
        if context_trajectories:
            user_parts.append(f"PRIOR TRAJECTORIES ON RELATED SITES:\n{context_trajectories}")
        user_parts.append(f"WEARER'S COMMIT UTTERANCE:\n{utterance}")
        user_parts.append("Return the JSON object now. No prose. No fences.")
        user_msg = "\n\n".join(user_parts)

        raw = await self._llm(_SYSTEM_PROMPT, user_msg)

        parsed: dict = {}
        if raw:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as e:
                _logger.warning("intent_extraction JSON parse failed: %s; raw=%s", e, raw[:200])

        slots_raw = parsed.get("slots") or {}
        slots = IntentSlots(
            filled=dict(slots_raw.get("filled") or {}),
            needs_memory=list(slots_raw.get("needs_memory") or []),
            needs_inference=list(slots_raw.get("needs_inference") or []),
            ambiguous=list(slots_raw.get("ambiguous") or []),
        )

        from datetime import datetime, timezone

        return TypedIntent(
            intent_id=str(uuid.uuid4()),
            user_id=user_id,
            utterance_window=utterance_window,
            action_category=parsed.get("action_category"),
            proposed_skill_hint=parsed.get("proposed_skill_hint"),
            slots=slots,
            detection_confidence=detection_confidence,
            hedge_filter_decision=hedge_result.decision,
            hedge_filter_reason=hedge_result.reason,
            proactivity_score=float(parsed.get("proactivity_score", 0.5))
            if parsed.get("proactivity_score") is not None
            else None,
            source=source,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
