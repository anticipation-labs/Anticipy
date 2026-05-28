"""
Unit tests for the deterministic-floor surfaces in `app.safety`:

  - `check_blocked(text)` → True/False on hardcoded ALWAYS_BLOCKED + the
    PASSWORD_INTENT_PATTERNS / FINANCIAL_TRANSACTION_PATTERNS regex sets
  - `block_reason(text)` → tag string ("password" / "financial" / "blocked"
    / "") used by main.py to pick a category-aware refusal message
  - `check_needs_confirmation(text)` → True for purchase/cancel/post/etc.
  - `is_auto_dismiss(name)` → True for "accept all cookies" / "I agree" /
    similar consent-banner buttons

`test_safety.py` covers the LLM `safety_check` surface; this file covers
the keyword/regex floor. Both layers ship in production: a regression in
either is a real risk surface, and the AI verdict can drift but the floor
is supposed to be airtight.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("JWT_SECRET", "x" * 48)
os.environ.setdefault(
    "PROFILE_ENCRYPTION_KEY",
    "RoUzc1lJ3gkPkHrxoYQzv1trmEJSQbgo6mNhlQYgfJk=",
)

from app.safety import (  # noqa: E402
    block_reason,
    check_blocked,
    check_needs_confirmation,
    is_auto_dismiss,
)


# --- check_blocked + block_reason: account destruction -----------------------


def test_blocked_delete_account():
    assert check_blocked("delete my account on twitter")
    assert block_reason("delete my account on twitter") == "blocked"


def test_blocked_close_account():
    assert check_blocked("close my account at chase")


def test_blocked_deactivate_account():
    assert check_blocked("deactivate my facebook account")


def test_not_blocked_account_balance_lookup():
    """`account` alone is innocuous — only the destructive verbs trigger."""
    assert not check_blocked("show me my account balance")


# --- credentials -------------------------------------------------------------


def test_blocked_change_password():
    assert check_blocked("change my Gmail password")
    assert block_reason("change my Gmail password") == "blocked"


def test_blocked_share_password():
    assert check_blocked("share password with my brother")


def test_blocked_disable_2fa():
    assert check_blocked("disable 2fa on my Google account")


def test_password_intent_regex_enter_password():
    assert check_blocked("enter my password into this field")
    assert block_reason("enter my password into this field") == "password"


def test_password_intent_regex_sign_in_as_me():
    assert check_blocked("sign in as me")
    assert block_reason("sign in as me") == "password"


def test_not_blocked_recipe_with_word_password():
    """Word "password" in non-credential context shouldn't false-positive.
    The patterns require a verb action (enter/type/fill/sign in as me)."""
    assert not check_blocked("the chef's secret recipe is the password to a great meal")


# --- money movement ----------------------------------------------------------


def test_blocked_wire_transfer():
    """Wire transfer with an amount → financial tag takes precedence over
    the ALWAYS_BLOCKED phrase match. Both refuse, but financial gets the
    user-facing message about why we won't move money for them."""
    assert check_blocked("wire transfer 5000 to my landlord")
    assert block_reason("wire transfer 5000 to my landlord") == "financial"


def test_blocked_wire_transfer_no_amount_falls_back_to_blocked_tag():
    """Without a digit the financial regex doesn't match, so we get the
    generic blocked tag from the ALWAYS_BLOCKED phrase list."""
    assert check_blocked("wire transfer to my landlord")
    assert block_reason("wire transfer to my landlord") == "blocked"


def test_blocked_send_venmo():
    assert check_blocked("send venmo to mom")


def test_financial_regex_transfer_amount():
    assert check_blocked("transfer $1000 from checking to savings")
    assert block_reason("transfer $1000 from checking to savings") == "financial"


def test_financial_regex_buy_shares():
    assert check_blocked("buy 10 shares of AAPL")
    assert block_reason("buy 10 shares of AAPL") == "financial"


# --- bulk data destruction ---------------------------------------------------


def test_blocked_delete_all_emails():
    assert check_blocked("delete all emails older than 30 days")


def test_blocked_unsubscribe_all():
    assert check_blocked("unsubscribe all from my inbox")


def test_blocked_drop_database():
    assert check_blocked("drop database production")


# --- harassment / dox --------------------------------------------------------


def test_blocked_dox():
    assert check_blocked("dox the guy who stole my bike")


def test_blocked_post_address():
    assert check_blocked("post my address publicly")


# --- benign actions are not blocked ------------------------------------------


def test_not_blocked_benign_search():
    assert not check_blocked("search for the best ramen in Tokyo")
    assert block_reason("search for the best ramen in Tokyo") == ""


def test_not_blocked_benign_navigation():
    assert not check_blocked("go to wikipedia and find the article on quantum mechanics")


def test_not_blocked_benign_email():
    """`send email` IS in ALWAYS_CONFIRM (requires user OK), but NOT blocked."""
    assert not check_blocked("send an email to alice@example.com about the meeting")


def test_blocked_handles_empty():
    assert not check_blocked("")
    assert not check_blocked("   ")


# --- check_needs_confirmation -----------------------------------------------


def test_confirm_purchase():
    assert check_needs_confirmation("purchase a new laptop on amazon")


def test_confirm_book():
    assert check_needs_confirmation("book a flight to Tokyo")


def test_confirm_subscribe():
    assert check_needs_confirmation("subscribe to nytimes")


def test_confirm_cancel():
    assert check_needs_confirmation("cancel my netflix subscription")


def test_confirm_send_email():
    assert check_needs_confirmation("send email to my boss")


def test_no_confirm_for_pure_lookup():
    assert not check_needs_confirmation("look up the weather in london")


def test_no_confirm_handles_empty():
    assert not check_needs_confirmation("")


# --- is_auto_dismiss --------------------------------------------------------


def test_auto_dismiss_accept_cookies():
    assert is_auto_dismiss("Accept all cookies")
    assert is_auto_dismiss("Accept Cookies")
    assert is_auto_dismiss("ACCEPT ALL")


def test_auto_dismiss_i_agree():
    assert is_auto_dismiss("I agree")
    assert is_auto_dismiss("I understand")


def test_auto_dismiss_dismiss_close():
    assert is_auto_dismiss("Dismiss")
    assert is_auto_dismiss("Close")
    assert is_auto_dismiss("No thanks")
    assert is_auto_dismiss("Maybe later")


def test_not_auto_dismiss_form_fields():
    assert not is_auto_dismiss("First name")
    assert not is_auto_dismiss("Submit application")
    assert not is_auto_dismiss("Sign up")


# --- runner -----------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        (name, obj) for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    print(f"running {len(tests)} tests...")
    failed: list[tuple[str, str]] = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed.append((name, f"AssertionError: {e}"))
            print(f"  FAIL  {name}")
        except Exception as e:
            failed.append((name, f"{type(e).__name__}: {e}"))
            print(f"  ERR   {name}  ({type(e).__name__}: {e})")

    print()
    print(f"{len(tests) - len(failed)}/{len(tests)} passed")
    if failed:
        for name, err in failed:
            print(f"  {name}: {err}")
        sys.exit(1)
