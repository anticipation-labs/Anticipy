"""Unit tests for the Ralph failure classifier (Phase 4-2).

Covers all 11 classes plus precedence ordering between rules that
could plausibly both match. No external services; pure rule-based
classification.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ralph.classifier import VALID_CLASSES, classify  # noqa: E402
from app.ralph.store import CostCapExceeded  # noqa: E402


def test_login_wall_detected_from_url() -> None:
    assert classify(url="https://accounts.google.com/login?continue=x") == "login_wall"
    assert classify(url="https://example.com/signin") == "login_wall"
    assert classify(url="https://x.com/oauth/authorize") == "login_wall"


def test_login_wall_detected_from_dom() -> None:
    dom = '<form action="/auth"><input name="password" type="password"></form>'
    assert classify(url="https://example.com/", dom_snapshot=dom) == "login_wall"


def test_captcha_detected_from_dom() -> None:
    dom = '<div class="g-recaptcha" data-sitekey="abc"></div>'
    assert classify(dom_snapshot=dom) == "captcha"
    dom2 = '<div class="cf-turnstile"></div>'
    assert classify(dom_snapshot=dom2) == "captcha"


def test_captcha_takes_precedence_over_login_wall() -> None:
    # A captcha widget shown on /login must still classify as captcha,
    # not login_wall: NopeCHA must run before SMS-the-user.
    dom = '<div class="h-captcha"></div>'
    assert classify(url="https://x.com/login", dom_snapshot=dom) == "captcha"


def test_network_detected_from_5xx_status() -> None:
    assert classify(http_status=502) == "network"
    assert classify(http_status=503) == "network"
    assert classify(http_status=504) == "network"


def test_network_detected_from_error_text() -> None:
    assert classify(error_msg="connect ECONNREFUSED 1.2.3.4:443") == "network"
    assert classify(error_msg="navigation timeout of 30000ms exceeded") == "network"
    assert classify(error_msg="getaddrinfo ENOTFOUND foo.com") == "network"


def test_rate_limit_detected_from_429() -> None:
    assert classify(http_status=429) == "rate_limit"


def test_rate_limit_detected_from_text() -> None:
    assert classify(error_msg="HTTP 429 Too Many Requests") == "rate_limit"
    assert classify(error_msg="you are being throttled") == "rate_limit"


def test_rate_limit_wins_over_network_when_429() -> None:
    # 429 must NOT be misclassified as network just because the
    # message also says "timeout".
    assert (
        classify(error_msg="request timed out", http_status=429) == "rate_limit"
    )


def test_element_missing_detected() -> None:
    assert (
        classify(error_msg="locator.click: selector not found within timeout 30000")
        == "element_missing"
    )
    assert (
        classify(error_msg="Waiting for selector div[gh=cm] failed: not found")
        == "element_missing"
    )


def test_payment_required_detected_from_url() -> None:
    assert classify(url="https://example.com/checkout/cart") == "payment_required"
    assert classify(url="https://example.com/billing/upgrade") == "payment_required"


def test_payment_required_detected_from_402() -> None:
    assert classify(http_status=402) == "payment_required"


def test_payment_required_detected_from_text() -> None:
    assert classify(error_msg="Payment required to access this feature") == "payment_required"
    assert classify(dom_snapshot="Your card was declined") == "payment_required"


def test_account_locked_detected() -> None:
    assert classify(error_msg="Your account has been suspended") == "account_locked"
    assert classify(dom_snapshot="2FA required to continue") == "account_locked"
    assert classify(error_msg="Account locked due to suspicious activity") == "account_locked"


def test_ambiguous_dom_detected() -> None:
    assert (
        classify(error_msg="strict mode violation: 3 elements matched")
        == "ambiguous_dom"
    )
    assert (
        classify(error_msg="selector resolved to multiple elements")
        == "ambiguous_dom"
    )


def test_cost_cap_via_exception() -> None:
    exc = CostCapExceeded("g_abc", 0.06, 0.05)
    assert classify(error_msg=str(exc), exception=exc) == "cost_cap"


def test_cost_cap_via_text() -> None:
    assert classify(error_msg="cost cap exceeded for goal") == "cost_cap"


def test_model_error_detected() -> None:
    assert classify(error_msg="LLM returned malformed JSON") == "model_error"
    assert classify(error_msg="model refused to answer") == "model_error"
    assert classify(error_msg="context_length_exceeded: 32000 tokens") == "model_error"


def test_unknown_fallthrough() -> None:
    # Nothing matches => unknown.
    assert classify(error_msg="some weird thing happened") == "unknown"
    assert classify() == "unknown"
    assert classify(error_msg="", url="", dom_snapshot="", http_status=None) == "unknown"


def test_every_returned_class_is_valid() -> None:
    """Smoke: every input produces a class label in VALID_CLASSES."""
    inputs = [
        {"http_status": 500},
        {"http_status": 429},
        {"http_status": 502},
        {"http_status": 402},
        {"url": "https://example.com/login"},
        {"dom_snapshot": "<div class='g-recaptcha'></div>"},
        {"error_msg": "selector not found within timeout"},
        {"error_msg": "Account suspended"},
        {"error_msg": "multiple matches found"},
        {"error_msg": "malformed json"},
        {"error_msg": "absolutely nothing"},
    ]
    for case in inputs:
        cls = classify(**case)
        assert cls in VALID_CLASSES, f"got {cls!r} for {case!r}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
