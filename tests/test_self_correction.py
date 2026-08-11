"""A self-corrected text means the LAST version, never the retracted one.

Omar, 2026-08-11, live: he texted "Can I do two people tomorrow not tomorrow
in four days from now" — a dictated self-correction — and she answered "got
it, two people for tomorrow". The correction lost to the value it retracted,
and the job drove toward the WRONG DAY with authority to book (killed by the
operator before it could).

The rule is in the classifier's one prompt, stated as a hard reading rule
with the failure's own shape as an example, plus an echo requirement: the
reply must say the corrected value back, so a misread surfaces in the very
next text instead of inside a wrong booking. Measured on the live model with
the exact broken text: 3/3 now carries "four days" in changes and echoes it.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.conversation import REPLY_SYSTEM  # noqa: E402


def test_the_rule_is_in_the_classifier_prompt():
    low = " ".join(REPLY_SYSTEM.split()).lower()
    assert "self-correction" in low
    assert "the last version is the one they mean" in low
    assert "never the retracted one" in low


def test_the_reply_must_echo_the_corrected_value():
    low = " ".join(REPLY_SYSTEM.split()).lower()
    assert "say the corrected value back" in low


def test_the_live_failure_shape_is_the_example():
    """The rule teaches by the exact shape that burned him: a value stated,
    then negated and replaced inside the same message."""
    low = " ".join(REPLY_SYSTEM.split()).lower()
    assert "not tomorrow" in low
