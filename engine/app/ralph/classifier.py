"""Failure classifier for the Ralph loop (Phase 4-2).

Maps a (error_msg, url, dom_snapshot, http_status) tuple to one of the
11 failure classes defined in planning/00-handoff/RALPH_LOOP.md.

The classifier is intentionally rule-based and deterministic. No LLM
calls. The recovery dispatcher (recovery.py) consumes the class label
to choose a strategy.

Detection rules per RALPH_LOOP.md "Failure classes" table:

  login_wall        URL contains /login or /signin, OR an auth form
                    selector is present in the dom snapshot.
  captcha           reCAPTCHA / hCaptcha / Cloudflare Turnstile
                    selectors appear in dom or error_msg.
  network           HTTP status in {502, 503, 504}, OR error mentions
                    "timeout", "ECONNREFUSED", DNS errors.
  rate_limit        HTTP status == 429, OR text contains
                    "Too Many Requests" / "rate limit".
  element_missing   Error mentions "not found within timeout" /
                    "selector ... not found".
  payment_required  URL contains /checkout, /billing, or text
                    contains "payment required" / "402".
  account_locked    Text contains "locked", "suspended", or
                    "2fa required".
  ambiguous_dom     Error contains "multiple matches" or similar
                    disambiguation failure language.
  cost_cap          Error is CostCapExceeded (or message says
                    "cost cap").
  model_error       Error contains "json", "malformed", "refused"
                    (model-side problems).
  unknown           Fallthrough; the dispatcher will SMS the user
                    with full trace.

Order of precedence matters when multiple rules would match (a 429 on
/login is rate_limit, NOT login_wall). The function returns the FIRST
class that matches in the priority order below; we encode that order in
the body of classify().
"""

from __future__ import annotations

import re
from typing import Optional

from app.ralph.store import CostCapExceeded

# Public list of valid class labels. The recovery dispatcher must
# accept every value in this set.
VALID_CLASSES: tuple[str, ...] = (
    "login_wall",
    "captcha",
    "network",
    "rate_limit",
    "element_missing",
    "payment_required",
    "account_locked",
    "ambiguous_dom",
    "cost_cap",
    "model_error",
    "unknown",
)

# --- detection regex / token tables ---------------------------------

# URL substrings (case-insensitive) indicating an auth / login wall.
_LOGIN_URL_TOKENS = (
    "/login",
    "/signin",
    "/sign-in",
    "/log-in",
    "/auth/login",
    "/accounts/login",
    "/users/sign_in",
    "/oauth/authorize",
)

# DOM substrings (case-insensitive) for login form recognition.
_LOGIN_DOM_TOKENS = (
    'name="password"',
    "id=\"password\"",
    "type=\"password\"",
    'autocomplete="current-password"',
    'aria-label="password"',
    "sign in to continue",
    "log in to continue",
)

# Captcha widget signatures in DOM or error text.
_CAPTCHA_TOKENS = (
    "g-recaptcha",
    "recaptcha/api.js",
    "data-sitekey",
    "hcaptcha",
    "h-captcha",
    "cf-turnstile",
    "challenges.cloudflare.com",
    "captcha challenge",
    "are you human",
    "i'm not a robot",
)

# Generic timeout / connection failure markers in error_msg.
_NETWORK_TOKENS = (
    "timeout",
    "timed out",
    "econnrefused",
    "econnreset",
    "etimedout",
    "enotfound",
    "dns",
    "name resolution failed",
    "connection refused",
    "connection reset",
    "network error",
    "net::err_",
)

# Rate-limit signatures.
_RATE_LIMIT_TOKENS = (
    "too many requests",
    "rate limit",
    "rate-limit",
    "rate_limited",
    "throttled",
    "retry-after",
)

# Element-missing / selector-not-found signatures.
_ELEMENT_MISSING_TOKENS = (
    "not found within timeout",
    "no element found",
    "selector not found",
    "no nodes found",
    "element is not visible",
    "waiting for selector",
    "wait_for_selector",
    "timeout exceeded while waiting for element",
)

# Payment / checkout signatures (URL OR text).
_PAYMENT_URL_TOKENS = (
    "/checkout",
    "/billing",
    "/payments",
    "/pay",
    "/subscribe",
    "/upgrade",
)
_PAYMENT_TEXT_TOKENS = (
    "payment required",
    "402 payment required",
    "subscription required",
    "upgrade your plan",
    "your card was declined",
    "billing required",
)

# Account-locked signatures.
_ACCOUNT_LOCKED_TOKENS = (
    "account locked",
    "account is locked",
    "account suspended",
    "account has been suspended",
    "your account has been disabled",
    "2fa required",
    "two-factor authentication required",
    "verify your identity",
    "additional verification required",
)

# Ambiguous DOM signatures.
_AMBIGUOUS_DOM_TOKENS = (
    "multiple matches",
    "strict mode violation",
    "more than one element",
    "ambiguous selector",
    "n matches found",
    "resolved to multiple elements",
)

# Model-side errors (cascade swap territory).
_MODEL_ERROR_TOKENS = (
    "malformed json",
    "malformed response",
    "invalid json",
    "could not parse json",
    "model refused",
    "refused to answer",
    "content policy",
    "safety filter",
    "context length",
    "context_length_exceeded",
    "max tokens",
    "out of memory",
    "oom",
)

# Cost-cap signatures (for plain string callers that didn't pass the
# exception object).
_COST_CAP_TOKENS = (
    "cost cap",
    "costcap",
    "cost_cap_exceeded",
    "cost cap exceeded",
    "budget exhausted",
    "budget exceeded",
)


def _has_any(needles: tuple[str, ...], hay_lower: str) -> bool:
    """True if any case-insensitive needle appears in hay_lower."""
    for n in needles:
        if n in hay_lower:
            return True
    return False


def classify(
    error_msg: Optional[str] = None,
    url: Optional[str] = None,
    dom_snapshot: Optional[str] = None,
    http_status: Optional[int] = None,
    *,
    exception: Optional[BaseException] = None,
) -> str:
    """Return one of VALID_CLASSES for the given failure context.

    All inputs are optional; the function tolerates None / empty. The
    classifier is order-sensitive: higher-priority rules win when
    multiple would match.

    Priority order (highest first):
      1. cost_cap      (caller-supplied CostCapExceeded exception wins)
      2. captcha       (UI block; takes precedence over auth wall)
      3. rate_limit    (429 -> never confuse with network 5xx)
      4. element_missing (Playwright "selector not found within timeout"
                          mentions 'timeout', so it MUST be checked
                          before the generic network 'timeout' rule)
      5. ambiguous_dom (also runs before network so "strict mode
                        violation" doesn't lose to a stray substring)
      6. network       (5xx, timeouts, DNS)
      7. account_locked
      8. payment_required
      9. login_wall
     10. model_error
     11. unknown
    """
    err = (error_msg or "").strip()
    err_low = err.lower()
    url_low = (url or "").lower()
    dom_low = (dom_snapshot or "").lower()

    # 1. cost_cap — explicit exception type is the ground truth.
    if isinstance(exception, CostCapExceeded):
        return "cost_cap"
    if _has_any(_COST_CAP_TOKENS, err_low):
        return "cost_cap"

    # 2. captcha (check before login_wall: a captcha on a /login page
    # should still route to captcha).
    if _has_any(_CAPTCHA_TOKENS, dom_low) or _has_any(_CAPTCHA_TOKENS, err_low):
        return "captcha"

    # 3. rate_limit (HTTP 429 always wins; tokens secondary).
    if http_status == 429:
        return "rate_limit"
    if _has_any(_RATE_LIMIT_TOKENS, err_low):
        return "rate_limit"

    # 4. element_missing (must run before network: Playwright wraps
    # selector-not-found errors with the word "timeout" which would
    # otherwise route to network).
    if _has_any(_ELEMENT_MISSING_TOKENS, err_low):
        return "element_missing"

    # 5. ambiguous_dom (also before network for safety).
    if _has_any(_AMBIGUOUS_DOM_TOKENS, err_low):
        return "ambiguous_dom"
    # Pattern like "3 matches found" / "5 elements matched".
    if re.search(r"\b\d+\s+(matches|elements?)\s+(found|matched)\b", err_low):
        return "ambiguous_dom"

    # 6. network (5xx, connection / timeout / DNS).
    if http_status in (502, 503, 504):
        return "network"
    if _has_any(_NETWORK_TOKENS, err_low):
        return "network"

    # 7. account_locked.
    if _has_any(_ACCOUNT_LOCKED_TOKENS, err_low) or _has_any(
        _ACCOUNT_LOCKED_TOKENS, dom_low
    ):
        return "account_locked"

    # 8. payment_required.
    if http_status == 402:
        return "payment_required"
    if any(tok in url_low for tok in _PAYMENT_URL_TOKENS):
        return "payment_required"
    if _has_any(_PAYMENT_TEXT_TOKENS, err_low) or _has_any(
        _PAYMENT_TEXT_TOKENS, dom_low
    ):
        return "payment_required"

    # 9. login_wall.
    if any(tok in url_low for tok in _LOGIN_URL_TOKENS):
        return "login_wall"
    if _has_any(_LOGIN_DOM_TOKENS, dom_low):
        return "login_wall"

    # 10. model_error.
    if _has_any(_MODEL_ERROR_TOKENS, err_low):
        return "model_error"

    return "unknown"


__all__ = ["classify", "VALID_CLASSES"]
