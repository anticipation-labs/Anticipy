"""An answer must contain the thing it answers with.

Live, 2026-08-11 21:48: a booking was parked on "I need the verification
code sent to +1604...". He texted "There it is" (the pasted code never made
it into the thread) and she replied "got it, i'll use that to confirm the
booking" — then stored the literal string "There it is" as the
verification_code and resumed the job with it. A pointer to a value she
cannot see is not the value.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.conversation import REPLY_SYSTEM  # noqa: E402


def _low():
    return " ".join(REPLY_SYSTEM.split()).lower()


def test_the_rule_is_in_the_prompt():
    low = _low()
    assert "an answer must contain the thing" in low
    assert "there it is" in low


def test_no_placeholder_values_and_no_false_receipt():
    low = _low()
    assert "do not put a placeholder in changes" in low
    assert "never say you'll use a value you never received" in low
