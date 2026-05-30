"""Recovery dispatcher for the Ralph loop (Phase 4-2).

Given a failure class produced by classifier.classify(), choose the
right next action: retry now, retry later (with backoff), notify the
user, cancel the goal, or escalate to a stronger model (vision).

Recovery is data, not control flow. recover() returns a RecoveryPlan
describing what the caller (loop.py) should do; this module never
calls the bridge / LLM / SMS directly. That keeps recovery testable
without network and lets the loop apply store.update_goal_status atomically
once it knows what action was chosen.

Mapping per RALPH_LOOP.md §"Failure classes":

  login_wall        notify_user (SMS with the tab URL)
  captcha           retry_now using NopeCHA (once). If we've already
                    tried captcha solve on this step (captcha_tried
                    flag in extras), notify_user.
  network           retry_later, exponential backoff per
                    consecutive_failures: 60s, 300s, 1800s, 10800s,
                    86400s. After 5 misses, notify_user.
  rate_limit        retry_later, honor Retry-After if present, else
                    5min / 30min / 6h backoff.
  element_missing   escalate_model (try with vision). If vision_tried
                    in extras, notify_user.
  payment_required  notify_user. NEVER autopay.
  account_locked    notify_user + cancel future retries.
  ambiguous_dom     escalate_model (vision picks). If vision_tried,
                    notify_user.
  cost_cap          notify_user "Spent $X, continue?".
  model_error       escalate_model (swap to fallback). Max 2 swaps
                    per step (model_swaps in extras).
  unknown           notify_user with full trace.

Recovery actions:
  retry_now         loop should retry the step immediately.
  retry_later       loop should call store.schedule_retry(goal_id,
                    plan.next_attempt_at) and yield.
  notify_user       loop should send SMS / push and mark the goal
                    wait_user. plan.notify carries the body.
  cancel            loop should mark the goal cancelled (no retry).
  escalate_model    loop should retry with vision / fallback model
                    set, then re-run the classifier on the next
                    failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from app.ralph.classifier import VALID_CLASSES
from app.ralph.store import Goal


# Action enum (string-keyed to keep JSON-serializable for logs).
ACTION_RETRY_NOW = "retry_now"
ACTION_RETRY_LATER = "retry_later"
ACTION_NOTIFY_USER = "notify_user"
ACTION_CANCEL = "cancel"
ACTION_ESCALATE_MODEL = "escalate_model"

VALID_ACTIONS: frozenset[str] = frozenset(
    {
        ACTION_RETRY_NOW,
        ACTION_RETRY_LATER,
        ACTION_NOTIFY_USER,
        ACTION_CANCEL,
        ACTION_ESCALATE_MODEL,
    }
)

# Network backoff schedule (seconds). Index = consecutive_failures.
# After we exceed the length, we notify the user.
_NETWORK_BACKOFF_S: tuple[int, ...] = (60, 300, 1_800, 10_800, 86_400)

# Rate-limit fallback backoff (used when no Retry-After header).
_RATE_LIMIT_BACKOFF_S: tuple[int, ...] = (300, 1_800, 21_600)

# Max consecutive vision escalations on the same step.
_MAX_VISION_RETRIES = 1

# Max consecutive model swaps per step (DeepSeek -> Gemini Flash, etc).
_MAX_MODEL_SWAPS = 2


@dataclass
class RecoveryPlan:
    """The dispatcher's answer to a failure.

    Always carries:
      action          one of VALID_ACTIONS
      reason          short human-readable string for logs / receipts
      failure_class   echo of the input class

    Optional fields:
      next_attempt_at unix-ts to schedule next try (retry_later only)
      notify          dict shaped for the SMS / push channel
                      {channel, body, deep_link, urgency}
      use_vision      True when escalating to the vision verifier
      swap_model      True when escalating to a fallback model
    """

    action: str
    reason: str
    failure_class: str
    next_attempt_at: Optional[int] = None
    notify: Optional[dict[str, Any]] = None
    use_vision: bool = False
    swap_model: bool = False
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "failure_class": self.failure_class,
            "next_attempt_at": self.next_attempt_at,
            "notify": self.notify,
            "use_vision": self.use_vision,
            "swap_model": self.swap_model,
            "extras": self.extras,
        }


def _network_backoff(consecutive_failures: int) -> Optional[int]:
    """Return seconds to wait or None if we've exhausted backoff."""
    idx = max(0, consecutive_failures)
    if idx >= len(_NETWORK_BACKOFF_S):
        return None
    return _NETWORK_BACKOFF_S[idx]


def _rate_limit_backoff(consecutive_failures: int, retry_after_s: Optional[int]) -> int:
    """Return seconds to wait. Honors Retry-After if positive."""
    if retry_after_s is not None and retry_after_s > 0:
        return int(retry_after_s)
    idx = min(max(0, consecutive_failures), len(_RATE_LIMIT_BACKOFF_S) - 1)
    return _RATE_LIMIT_BACKOFF_S[idx]


def _now_ts() -> int:
    import time
    return int(time.time())


def _build_notify(
    channel: str,
    body: str,
    *,
    goal_id: Optional[str] = None,
    urgency: str = "medium",
    deep_link: Optional[str] = None,
) -> dict[str, Any]:
    """Standard notify dict shape used by the loop / comms bus."""
    out: dict[str, Any] = {
        "channel": channel,
        "body": body,
        "urgency": urgency,
    }
    if goal_id is not None:
        out["goal_id"] = goal_id
        out["deep_link"] = deep_link or f"anticipy://goal/{goal_id}/continue"
    elif deep_link is not None:
        out["deep_link"] = deep_link
    return out


def recover(
    failure_class: str,
    goal: Goal,
    *,
    now_ts: Optional[int] = None,
    extras: Optional[dict[str, Any]] = None,
) -> RecoveryPlan:
    """Dispatch a recovery plan for the given failure class + goal state.

    Args:
        failure_class: one of classifier.VALID_CLASSES.
        goal: the current goal row (provides consecutive_failures,
              cost_usd, goal_text, etc.).
        now_ts: unix seconds for "now"; defaults to time.time().
        extras: optional dict carrying step-level state the loop
                tracks across retries on the same step:
                  retry_after_s   int seconds from a 429 Retry-After
                                  header (rate_limit only)
                  captcha_tried   bool — already tried NopeCHA
                  vision_tried    bool — already escalated to vision
                  model_swaps     int — how many fallback models tried
                  tab_url         str — the URL of the open tab
                                  (login_wall notify body)
                  trace           str — full error trace for unknown
    """
    if failure_class not in VALID_CLASSES:
        raise ValueError(f"unknown failure class {failure_class!r}")

    now_ts = now_ts if now_ts is not None else _now_ts()
    extras = dict(extras or {})

    if failure_class == "login_wall":
        tab_url = extras.get("tab_url") or "(no tab URL provided)"
        body = (
            f"Anticipy needs you to sign in to continue: {tab_url}. "
            f"Goal: {goal.goal_text[:120]}"
        )
        return RecoveryPlan(
            action=ACTION_NOTIFY_USER,
            reason="login required; user must sign in before retry",
            failure_class=failure_class,
            notify=_build_notify(
                "sms",
                body,
                goal_id=goal.goal_id,
                urgency="high",
            ),
            extras=extras,
        )

    if failure_class == "captcha":
        if extras.get("captcha_tried"):
            body = (
                f"Captcha is blocking '{goal.goal_text[:100]}'. "
                f"Solver failed; please solve in the open tab."
            )
            return RecoveryPlan(
                action=ACTION_NOTIFY_USER,
                reason="captcha solver already tried; needs user",
                failure_class=failure_class,
                notify=_build_notify(
                    "sms", body, goal_id=goal.goal_id, urgency="high"
                ),
                extras=extras,
            )
        extras["captcha_tried"] = True
        return RecoveryPlan(
            action=ACTION_RETRY_NOW,
            reason="attempt NopeCHA captcha solve",
            failure_class=failure_class,
            extras=extras,
        )

    if failure_class == "network":
        wait_s = _network_backoff(goal.consecutive_failures)
        if wait_s is None:
            body = (
                f"Anticipy hit repeated network errors trying '{goal.goal_text[:100]}'. "
                f"Will not retry without your OK."
            )
            return RecoveryPlan(
                action=ACTION_NOTIFY_USER,
                reason=(
                    f"network backoff exhausted "
                    f"({goal.consecutive_failures} failures)"
                ),
                failure_class=failure_class,
                notify=_build_notify(
                    "sms", body, goal_id=goal.goal_id, urgency="medium"
                ),
                extras=extras,
            )
        return RecoveryPlan(
            action=ACTION_RETRY_LATER,
            reason=f"network retry in {wait_s}s",
            failure_class=failure_class,
            next_attempt_at=now_ts + wait_s,
            extras=extras,
        )

    if failure_class == "rate_limit":
        wait_s = _rate_limit_backoff(
            goal.consecutive_failures, extras.get("retry_after_s")
        )
        return RecoveryPlan(
            action=ACTION_RETRY_LATER,
            reason=f"rate-limited; retry in {wait_s}s",
            failure_class=failure_class,
            next_attempt_at=now_ts + wait_s,
            extras=extras,
        )

    if failure_class == "element_missing":
        if extras.get("vision_tried"):
            body = (
                f"Anticipy can't find an expected element for '{goal.goal_text[:100]}'. "
                f"Vision fallback didn't help. Site layout likely changed."
            )
            return RecoveryPlan(
                action=ACTION_NOTIFY_USER,
                reason="element missing; vision fallback already tried",
                failure_class=failure_class,
                notify=_build_notify(
                    "sms", body, goal_id=goal.goal_id, urgency="medium"
                ),
                extras=extras,
            )
        extras["vision_tried"] = True
        return RecoveryPlan(
            action=ACTION_ESCALATE_MODEL,
            reason="element missing; retry with vision DOM map",
            failure_class=failure_class,
            use_vision=True,
            extras=extras,
        )

    if failure_class == "payment_required":
        body = (
            f"Anticipy hit a payment wall while doing '{goal.goal_text[:100]}'. "
            f"Won't autopay. Reply CONFIRM to allow, or another instruction."
        )
        return RecoveryPlan(
            action=ACTION_NOTIFY_USER,
            reason="payment required; never autopay",
            failure_class=failure_class,
            notify=_build_notify(
                "sms", body, goal_id=goal.goal_id, urgency="high"
            ),
            extras=extras,
        )

    if failure_class == "account_locked":
        body = (
            f"Your account looks locked / suspended for '{goal.goal_text[:100]}'. "
            f"Anticipy is cancelling this goal. Unlock it and ask again."
        )
        return RecoveryPlan(
            action=ACTION_CANCEL,
            reason="account locked; no retries",
            failure_class=failure_class,
            notify=_build_notify(
                "sms", body, goal_id=goal.goal_id, urgency="high"
            ),
            extras=extras,
        )

    if failure_class == "ambiguous_dom":
        if extras.get("vision_tried"):
            body = (
                f"Anticipy is unsure which element to use for "
                f"'{goal.goal_text[:100]}'. Need your direction."
            )
            return RecoveryPlan(
                action=ACTION_NOTIFY_USER,
                reason="ambiguous selector; vision didn't disambiguate",
                failure_class=failure_class,
                notify=_build_notify(
                    "sms", body, goal_id=goal.goal_id, urgency="medium"
                ),
                extras=extras,
            )
        extras["vision_tried"] = True
        return RecoveryPlan(
            action=ACTION_ESCALATE_MODEL,
            reason="ambiguous DOM; let vision pick",
            failure_class=failure_class,
            use_vision=True,
            extras=extras,
        )

    if failure_class == "cost_cap":
        body = (
            f"Spent ${goal.cost_usd:.4f} on '{goal.goal_text[:100]}'. "
            f"Reply CONTINUE to lift the cap or STOP to cancel."
        )
        return RecoveryPlan(
            action=ACTION_NOTIFY_USER,
            reason=f"cost cap ${goal.cost_cap_usd:.4f} reached",
            failure_class=failure_class,
            notify=_build_notify(
                "sms", body, goal_id=goal.goal_id, urgency="medium"
            ),
            extras=extras,
        )

    if failure_class == "model_error":
        swaps = int(extras.get("model_swaps") or 0)
        if swaps >= _MAX_MODEL_SWAPS:
            body = (
                f"Anticipy's reasoning model kept failing on "
                f"'{goal.goal_text[:100]}'. Pausing for your input."
            )
            return RecoveryPlan(
                action=ACTION_NOTIFY_USER,
                reason=f"model swaps exhausted ({swaps})",
                failure_class=failure_class,
                notify=_build_notify(
                    "sms", body, goal_id=goal.goal_id, urgency="low"
                ),
                extras=extras,
            )
        extras["model_swaps"] = swaps + 1
        return RecoveryPlan(
            action=ACTION_ESCALATE_MODEL,
            reason=f"swap fallback model (swap {swaps + 1}/{_MAX_MODEL_SWAPS})",
            failure_class=failure_class,
            swap_model=True,
            extras=extras,
        )

    # unknown: snapshot everything and notify.
    trace = (extras.get("trace") or "(no trace)")[:300]
    body = (
        f"Anticipy hit an unknown failure on '{goal.goal_text[:100]}'. "
        f"Last error: {trace}"
    )
    return RecoveryPlan(
        action=ACTION_NOTIFY_USER,
        reason="unknown failure; full trace attached",
        failure_class=failure_class,
        notify=_build_notify(
            "sms", body, goal_id=goal.goal_id, urgency="medium"
        ),
        extras=extras,
    )


__all__ = [
    "ACTION_CANCEL",
    "ACTION_ESCALATE_MODEL",
    "ACTION_NOTIFY_USER",
    "ACTION_RETRY_LATER",
    "ACTION_RETRY_NOW",
    "RecoveryPlan",
    "VALID_ACTIONS",
    "recover",
]
