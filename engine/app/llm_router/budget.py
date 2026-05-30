"""
Per-call, per-day, and per-month budget enforcement for the LLM router.

The router calls ``check_budget`` BEFORE dispatching to a provider. If the
estimated cost would push the user past any cap, ``BudgetExceeded`` is raised
and the caller decides what to do (escalate to user via SMS, pause the goal,
fall through to a free model, etc.).

Limits per spec (planning/00-handoff/ARCHITECTURE.md §9):
  - Per-call hard cap: $0.005
  - Per-day per-user: $0.30
  - Per-month per-user: $6.00

The router calls ``record_cost`` AFTER a successful call to write to the
budget log table (shared SQLite DB with the cache, per B477 lesson).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.llm_router.cache import budget_log_insert, budget_log_sum


logger = logging.getLogger("engine.llm_router.budget")


# Spec values. Tests can override via set_caps_for_tests.
CAP_PER_CALL_USD: float = 0.005
CAP_DAILY_USD: float = 0.30
CAP_MONTHLY_USD: float = 6.00

# Per-spec, trivia_lookup via Perplexity Sonar has a per-request search fee
# (~$0.005) that pushes a single call above the $0.005 per-call cap. The spec
# explicitly accounts for ~$0.0075/trivia-call. Without this exemption the
# router would always block trivia. We keep escalation under the regular cap
# (escalation IS supposed to be rare and gated by upstream confidence checks).
TASK_PER_CALL_CAP_OVERRIDES: dict[str, float] = {
    "trivia_lookup": 0.01,
    "escalation": 0.02,  # gemini-2.5-pro is expensive but rare; same envelope
}


# Seconds in a day / month (approx, ~30d).
_SECONDS_IN_DAY = 24 * 60 * 60
_SECONDS_IN_MONTH = 30 * _SECONDS_IN_DAY


_CAPS_OVERRIDE: dict[str, float] = {}


def set_caps_for_tests(
    per_call: float | None = None,
    daily: float | None = None,
    monthly: float | None = None,
) -> None:
    """Override caps (test only). Pass None to leave unchanged."""
    global _CAPS_OVERRIDE
    if per_call is not None:
        _CAPS_OVERRIDE["per_call"] = float(per_call)
    if daily is not None:
        _CAPS_OVERRIDE["daily"] = float(daily)
    if monthly is not None:
        _CAPS_OVERRIDE["monthly"] = float(monthly)


def clear_caps_override() -> None:
    """Wipe cap overrides so spec defaults apply again."""
    global _CAPS_OVERRIDE
    _CAPS_OVERRIDE = {}


def _per_call_cap(task_type: str | None = None) -> float:
    """Per-call cap, with optional task_type override.

    Test override (set_caps_for_tests) wins absolutely. Otherwise, certain
    task types (trivia_lookup, escalation) get a higher per-call cap per
    spec section 5; everything else uses CAP_PER_CALL_USD.
    """
    if "per_call" in _CAPS_OVERRIDE:
        return _CAPS_OVERRIDE["per_call"]
    if task_type and task_type in TASK_PER_CALL_CAP_OVERRIDES:
        return TASK_PER_CALL_CAP_OVERRIDES[task_type]
    return CAP_PER_CALL_USD


def _daily_cap() -> float:
    return _CAPS_OVERRIDE.get("daily", CAP_DAILY_USD)


def _monthly_cap() -> float:
    return _CAPS_OVERRIDE.get("monthly", CAP_MONTHLY_USD)


class BudgetExceeded(Exception):
    """Raised when an LLM call would push the user past a budget cap.

    Attributes:
        scope: one of "per_call", "daily", or "monthly"
        spent_usd: current cumulative spend in this scope (already-charged)
        cap_usd: the cap that was hit
        estimated_usd: the proposed call's estimated cost
        user_id: who tripped the cap
    """

    def __init__(
        self,
        scope: str,
        spent_usd: float,
        cap_usd: float,
        estimated_usd: float,
        user_id: str,
    ):
        self.scope = scope
        self.spent_usd = float(spent_usd)
        self.cap_usd = float(cap_usd)
        self.estimated_usd = float(estimated_usd)
        self.user_id = user_id
        super().__init__(
            f"BudgetExceeded[{scope}] user={user_id} "
            f"spent=${spent_usd:.4f} + estimated=${estimated_usd:.4f} "
            f"> cap=${cap_usd:.4f}"
        )


def check_budget(
    task_type: str,
    estimated_cost: float,
    user_id: str = "_anon",
) -> bool:
    """Return True if the call is allowed. Raise BudgetExceeded otherwise.

    Estimated cost MUST be the upper bound the router thinks the call will
    consume. ``user_id`` defaults to ``_anon`` so engine internal calls
    (no logged-in user) still get tracked under one bucket.
    """
    estimated_cost = float(estimated_cost or 0.0)
    user_id = str(user_id or "_anon")

    # Per-call cap is the strictest and easiest to evaluate.
    per_call_cap = _per_call_cap(task_type)
    if estimated_cost > per_call_cap:
        raise BudgetExceeded(
            scope="per_call",
            spent_usd=0.0,
            cap_usd=per_call_cap,
            estimated_usd=estimated_cost,
            user_id=user_id,
        )

    # Daily.
    daily_spent = budget_log_sum(user_id, _SECONDS_IN_DAY)
    daily_cap = _daily_cap()
    if daily_spent + estimated_cost > daily_cap:
        raise BudgetExceeded(
            scope="daily",
            spent_usd=daily_spent,
            cap_usd=daily_cap,
            estimated_usd=estimated_cost,
            user_id=user_id,
        )

    # Monthly.
    monthly_spent = budget_log_sum(user_id, _SECONDS_IN_MONTH)
    monthly_cap = _monthly_cap()
    if monthly_spent + estimated_cost > monthly_cap:
        raise BudgetExceeded(
            scope="monthly",
            spent_usd=monthly_spent,
            cap_usd=monthly_cap,
            estimated_usd=estimated_cost,
            user_id=user_id,
        )

    return True


def record_cost(
    task_type: str,
    model: str,
    cost_usd: float,
    user_id: str = "_anon",
) -> None:
    """Append the actual cost to the budget log AFTER a successful call."""
    budget_log_insert(
        user_id=str(user_id or "_anon"),
        task_type=task_type,
        model=model,
        cost_usd=float(cost_usd or 0.0),
    )


def budget_snapshot(user_id: str = "_anon") -> dict:
    """Return current daily and monthly spend for ``user_id``."""
    return {
        "user_id": user_id,
        "daily_spent_usd": round(budget_log_sum(user_id, _SECONDS_IN_DAY), 6),
        "monthly_spent_usd": round(budget_log_sum(user_id, _SECONDS_IN_MONTH), 6),
        "daily_cap_usd": _daily_cap(),
        "monthly_cap_usd": _monthly_cap(),
        "per_call_cap_usd": _per_call_cap(None),
    }


__all__ = [
    "BudgetExceeded",
    "check_budget",
    "record_cost",
    "budget_snapshot",
    "set_caps_for_tests",
    "clear_caps_override",
    "CAP_PER_CALL_USD",
    "CAP_DAILY_USD",
    "CAP_MONTHLY_USD",
]
