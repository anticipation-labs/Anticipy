"""On a call she hears one side, and half of it is him agreeing with someone.

2026-08-06, a nineteen-minute investor call on AirPods. She heard only Omar.
He said, to the man on the phone:

    "...if you don't mind putting that word in with Sakib"

He was asking THEM to put in a good word for him. She made the task
"Remind Sakib about the word" — the obligation inverted, and the sentence
mangled on the way through. Measured against the live model on that exact
line with that exact context: act / owes=owner, three runs out of three.

The "you" trap is already named in the triage prompt, and it still lost,
because on a one-sided call there is no evidence anyone else exists. Every
line is his voice. A request he makes OF someone reads identically to a
request he makes OF her.

The tell is back-channel — "yeah", "ok", "exactly", "of course", "right".
Nobody talks that way to an assistant or to themselves. It is what listening
sounds like. Measured on his own logs, that call against the rest of the same
day: 28% of lines almost pure acknowledgement, versus 4% outside it. Seven
times, with nothing in between.

Deliberately not "is a phone call in progress" — she cannot know that today,
and this covers the same ground from the speech itself. A person across a
table whose voice the pendant misses reads exactly like a person on the phone.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.anticipy_core import (BACKCHANNEL_LINE, CONVERSATION_SHARE,  # noqa: E402
                                 CALL_WINDOW_LINES, _is_backchannel,
                                 in_conversation)

# Verbatim from the events table, 19:09–19:19.
THE_CALL = [
    "Yeah yeah",
    "Yeah OK and then",
    "Of course yeah",
    "Yeah yeah yeah yeah yeah of course",
    "OK that's good",
    "exactly how many how big is your network",
    "Yeah yeah",
    "Yeah yeah yeah yeah yeah",
    "No like I have it it's in the bank account",
    "Yeah OK yeah",
]


def test_the_real_call_is_recognised():
    assert in_conversation(THE_CALL) is True


def test_real_planning_is_not_a_one_sided_call():
    """The dinner conversation is also talking WITH someone — but he is
    saying things, not just agreeing. Suppressing this would delete the
    product."""
    assert in_conversation([
        "we should go for dinner tomorrow",
        "how's Cactus Park Royal",
        "seven works for me",
        "yeah let's do it",
        "just the two of us",
        "book it for seven",
    ]) is False


def test_a_run_of_his_own_to_dos_is_not_a_call():
    assert in_conversation([
        "I have to email Priya the invoice",
        "and send Marcus the quarterly numbers",
        "then update the budget spreadsheet",
        "remind me about the deposit",
    ]) is False


def test_too_little_to_tell_claims_nothing():
    """Four lines is the floor. Below it a single "yeah" would be enough to
    call an entire day a phone call."""
    assert in_conversation([]) is False
    assert in_conversation(None) is False
    assert in_conversation(["yeah"]) is False
    assert in_conversation(["yeah", "ok", "sure"]) is False


def test_blank_and_junk_lines_do_not_count():
    assert in_conversation(["", "   ", None, "yeah", "ok"]) is False


def test_only_the_recent_window_is_read():
    """A call an hour ago must not make everything since read as a call."""
    old_call = THE_CALL + [
        "I need to email Priya the invoice today",
        "and get the Q3 numbers into the budget sheet",
        "then send the deck to Marcus before Friday",
        "book the flights for the twelfth",
        "renew the insurance before it lapses",
        "call the dentist back about that appointment",
        "put the recording link in the project doc",
        "update the pricing page with the new tiers",
        "draft the investor update for this month",
        "chase the outstanding invoice from June",
    ]
    assert len(old_call) > CALL_WINDOW_LINES
    assert in_conversation(old_call) is False


def test_what_counts_as_back_channel():
    for yes in ("yeah", "Yeah yeah yeah yeah yeah", "Of course yeah",
                "OK yeah okay", "exactly", "Yeah OK and then", "mm hmm"):
        assert _is_backchannel(yes) is True, yes
    for no in ("book a table for two at seven",
               "we're based in Vancouver",
               "no like I have it it's in the bank account",
               "exactly how many how big is your network"):
        assert _is_backchannel(no) is False, no


def test_my_window_constant_is_not_shadowed():
    """A name collision that would have shipped. An unrelated
    CONVERSATION_WINDOW = 120 lives further down the same file and silently
    overrode this one, so the detector read 120 lines instead of 10 — and a
    call from an hour ago would have marked everything after it as a call."""
    assert CALL_WINDOW_LINES == 10
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "brain", "anticipy_core.py")).read()
    assert "[-CALL_WINDOW_LINES:]" in src


def test_the_thresholds_sit_inside_the_measured_gap():
    """28% inside the call, 4% outside. The threshold must live between them,
    not at either edge, or it is tuned to nothing."""
    assert 0.04 < CONVERSATION_SHARE < 0.28
    assert BACKCHANNEL_LINE >= 0.7, "a line half made of content is not a grunt"


def test_the_rider_actually_reaches_the_model():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "brain", "anticipy_core.py")).read()
    assert "mid_conversation=in_conversation(context)" in src, \
        "the detector must be wired to the real conversation context"
    i = src.index("if mid_conversation:")
    # The rider is a concatenated f-string, so phrases break across source
    # lines AND each fragment carries an f" prefix. Rebuild the sentence the
    # model will actually see before asserting on meaning — grepping raw
    # source made "repeating back" read as missing when it was plainly there,
    # because the source says: repeating " / f"back.
    block = re.sub(r'"\s*\+?\s*f?"', "", src[i:i + 1200])
    block = " ".join(block.replace('f"', " ").replace('"', " ").split())
    assert "CANNOT hear" in block
    assert "request OF" in block and "theirs" in block, \
        "the rider must flip the obligation, not merely mention a call"
    assert "repeating back" in block, \
        "echoing what they just said is the other half of the failure"
