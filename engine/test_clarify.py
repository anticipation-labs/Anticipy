"""
Unit tests for `app.clarify.needs_clarification` — the deterministic UX
gate that asks one targeted question before launching a 30-second browser
session for an under-specified action.

This module exists because router.py is enforced LLM-only by
`test_router.test_no_keyword_or_regex_used`. The clarify rules ARE
regex-driven; they live here so router.py can stay free of pattern
tables. These tests cover that the rules fire on vague inputs and stay
quiet on specific ones — the exact failure mode of "browser fires for
'book a flight', burns 30s, asks the user mid-flow what dates."

Tests are pure-function, no I/O. Each one corresponds to one row of the
intent matrix the gate decides on.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Required env BEFORE importing app.clarify (transitive: app.config validates
# PROFILE_ENCRYPTION_KEY at import).
os.environ.setdefault("JWT_SECRET", "x" * 48)
os.environ.setdefault(
    "PROFILE_ENCRYPTION_KEY",
    "RoUzc1lJ3gkPkHrxoYQzv1trmEJSQbgo6mNhlQYgfJk=",
)

from app.clarify import needs_clarification  # noqa: E402


# --- vague-action triggers ---------------------------------------------------


def test_book_a_flight_short_asks_for_route_and_dates():
    """Bare "book a flight" without route/dates should clarify, not act."""
    out = needs_clarification("book a flight")
    assert out is not None
    assert "fly" in out.lower() or "fro" in out.lower() or "date" in out.lower()


def test_book_a_flight_with_dates_passes_through():
    """Once the user specifies a concrete date number, the gate must NOT
    clarify — the digit signal alone is enough to skip the bespoke
    flight-route question. Bare airport codes without a digit are still
    treated as ambiguous (40-char floor) — that's the conservative side
    of the gate, traded for keeping the prompt short."""
    assert (
        needs_clarification("book a flight from SFO to JFK on August 12")
        is None
    )


def test_send_email_short_asks_recipient_and_body():
    out = needs_clarification("send an email")
    assert out is not None
    assert "who" in out.lower() or "send" in out.lower()


def test_send_email_with_recipient_passes_through():
    """Email + at-sign address means the user has supplied the slot."""
    assert needs_clarification("send email to alice@example.com about Q3") is None


def test_order_dog_food_short_asks_brand_and_store():
    out = needs_clarification("order dog food")
    assert out is not None
    assert (
        "brand" in out.lower()
        or "size" in out.lower()
        or "where" in out.lower()
    )


def test_order_dog_food_long_with_brand_passes():
    """If the user gives ≥40 chars + brand, no clarification needed."""
    assert needs_clarification(
        "order Wellness Core puppy chow 12lb bag from chewy.com"
    ) is None


def test_book_restaurant_short_asks_when_who():
    out = needs_clarification("book a restaurant")
    assert out is not None


def test_book_hotel_short_asks_when_where():
    out = needs_clarification("book a hotel")
    assert out is not None


def test_schedule_meeting_short_asks_when_who():
    out = needs_clarification("schedule a meeting")
    assert out is not None


def test_send_text_short_asks_who_and_what():
    out = needs_clarification("send a text")
    assert out is not None


# --- generic short-vague catch-all -------------------------------------------


def test_one_word_buy_asks_generic_clarification():
    """Single word `buy` is too vague even outside the bespoke patterns."""
    out = needs_clarification("buy")
    assert out is not None


def test_one_word_cancel_asks_what():
    out = needs_clarification("cancel")
    assert out is not None
    assert "cancel" in out.lower() or "what" in out.lower()


def test_two_word_action_with_subject_does_not_clarify():
    """Two words with a specific noun (e.g. "buy milk") is concrete enough
    that the gate stays quiet — the agent will figure out the rest."""
    assert needs_clarification("buy milk from amazon") is None


# --- non-vague inputs --------------------------------------------------------


def test_specific_search_does_not_clarify():
    assert needs_clarification("search for Python tutorials on YouTube") is None


def test_long_command_does_not_clarify():
    assert (
        needs_clarification(
            "navigate to wikipedia and find the article about quantum entanglement"
        )
        is None
    )


def test_command_with_url_does_not_clarify():
    """A URL is a strong signal of specificity; never ask for clarification."""
    assert (
        needs_clarification("open chewy.com and reorder my dog food")
        is None
    )


def test_command_with_number_passes_through():
    """A digit is a slot-fill signal (date/time/quantity); skip clarification."""
    # 3 words + digit → bypasses the very-short gate
    assert needs_clarification("book table for 4") is None


# --- empty / whitespace ------------------------------------------------------


def test_empty_input_does_not_clarify():
    assert needs_clarification("") is None
    assert needs_clarification("   ") is None
    assert needs_clarification("\n\t  ") is None


# --- chat / question shouldn't reach this code ------------------------------


def test_chat_does_not_clarify():
    """`needs_clarification` only runs after `classify` returns "action", but
    being defensive: chat/question text shouldn't trip the gate either."""
    assert needs_clarification("hi") is None
    assert needs_clarification("what's the weather like") is None
    assert needs_clarification("thanks") is None


# --- runner ------------------------------------------------------------------

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
