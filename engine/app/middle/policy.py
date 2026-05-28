"""Policy engine — fire / confirm-via-aevoy / refuse.

Takes an Intent + ResolvedSlots + SkillRouteResult, decides what to do
next. The decision is purely rule-based — NO LLM calls here.

Rules (in order of precedence):
  1. Irreversible action OR financial commitment above safety floor →
     ALWAYS Aevoy confirm (the wearer must approve).
  2. Slots still unresolved + no skill hit → REFUSE with reason
     "missing_required_slot" (router would just guess; better to
     ask via Aevoy or wait for the wearer's followup).
  3. STORE_AS_LATENT decisions → store but never dispatch (Pod A
     already wrote the latent intent row).
  4. Otherwise → fire.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.middle.skill_router import SkillRouteResult
from app.middle.slot_resolver import ResolvedSlots
from app.proactive.intent_extraction import TypedIntent

_logger = logging.getLogger("anticipy.middle.policy")


# Action categories that mutate state irreversibly OR commit financial
# resources. Exhaustive — if a new category lands without being added
# here, default policy is "treat as irreversible" (safest).
IRREVERSIBLE_CATEGORIES = frozenset(
    {
        "post_message",       # public post, can edit but not delete from feeds
        "send_email",         # Gmail Undo Send is 30s only
        "log_expense",        # writes to ledger / accounting
        "file_expense",       # same
    }
)
FINANCIAL_CATEGORIES = frozenset(
    {
        "reorder",
        "book_reservation",   # most don't charge, some do
    }
)
# Hard floor below which financial commitments don't require a confirm
# (sub-$5 reorder of consumables Omar buys monthly, e.g.).
FINANCIAL_SAFETY_FLOOR_USD = 5.0


class PolicyDispatchAction(str, Enum):
    FIRE = "fire"
    AEVOY_CONFIRM = "aevoy_confirm"
    REFUSE = "refuse"


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    action: PolicyDispatchAction
    rehearsal_required: bool
    irreversible: bool
    aevoy_confirmation_required: bool
    reason: str


class PolicyEngine:
    """Pure-Python policy engine. No LLM calls."""

    def __init__(
        self,
        financial_safety_floor_usd: float = FINANCIAL_SAFETY_FLOOR_USD,
    ) -> None:
        self.financial_safety_floor_usd = financial_safety_floor_usd

    def decide(
        self,
        intent: TypedIntent,
        slots: ResolvedSlots,
        route: SkillRouteResult,
    ) -> PolicyDecision:
        # STORE_AS_LATENT is never dispatched — Pod A already wrote the
        # latent intent row; the middle layer's job is only to wait for
        # the followup that promotes it to COMMIT.
        if intent.hedge_filter_decision == "STORE_AS_LATENT":
            return PolicyDecision(
                action=PolicyDispatchAction.REFUSE,
                rehearsal_required=False,
                irreversible=False,
                aevoy_confirmation_required=False,
                reason="store_as_latent_only",
            )

        category = intent.action_category or "fact_lookup"
        is_irreversible = category in IRREVERSIBLE_CATEGORIES
        is_financial = category in FINANCIAL_CATEGORIES
        amount_usd = self._extract_amount(slots)
        # Skill-router miss means "unfamiliar territory" → rehearsal first.
        rehearsal_required = not route.hit

        # Rule 1: irreversible OR significant financial → Aevoy confirm
        if is_irreversible:
            return PolicyDecision(
                action=PolicyDispatchAction.AEVOY_CONFIRM,
                rehearsal_required=rehearsal_required,
                irreversible=True,
                aevoy_confirmation_required=True,
                reason=f"irreversible_category:{category}",
            )
        if is_financial and amount_usd is not None and amount_usd > self.financial_safety_floor_usd:
            return PolicyDecision(
                action=PolicyDispatchAction.AEVOY_CONFIRM,
                rehearsal_required=rehearsal_required,
                irreversible=False,
                aevoy_confirmation_required=True,
                reason=f"financial_above_floor:${amount_usd:.2f}",
            )

        # Rule 2: still-unresolved slots + no skill hit → refuse with
        # missing_required_slot. The wearer's followup will resolve.
        if slots.still_unresolved and not route.hit:
            return PolicyDecision(
                action=PolicyDispatchAction.REFUSE,
                rehearsal_required=False,
                irreversible=False,
                aevoy_confirmation_required=False,
                reason=f"missing_required_slot:{','.join(slots.still_unresolved)}",
            )

        # Rule 3: low proactivity_score → Aevoy confirm even if reversible.
        if intent.proactivity_score is not None and intent.proactivity_score < 0.5:
            return PolicyDecision(
                action=PolicyDispatchAction.AEVOY_CONFIRM,
                rehearsal_required=rehearsal_required,
                irreversible=False,
                aevoy_confirmation_required=True,
                reason=f"low_proactivity:{intent.proactivity_score:.2f}",
            )

        # Default: fire.
        return PolicyDecision(
            action=PolicyDispatchAction.FIRE,
            rehearsal_required=rehearsal_required,
            irreversible=is_irreversible,
            aevoy_confirmation_required=False,
            reason="fire",
        )

    @staticmethod
    def _extract_amount(slots: ResolvedSlots) -> Optional[float]:
        """Best-effort: pull an `amount_usd` / `total_usd` slot if filled."""
        merged = slots.merged()
        for k in ("amount_usd", "total_usd", "price_usd"):
            v = merged.get(k)
            if v is None:
                continue
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
        return None
