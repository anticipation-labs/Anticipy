"""She must not act on a name she never heard.

2026-08-06. He said, garbled:

    "Hey we should go out for dinner you haven't really shit let's do it but"

The goal came back:

    "Book a table at EARL'S for dinner THE DAY AFTER TOMORROW"

The first appearance of the word Earl's anywhere in the system — his speech,
the conversation, the segment entities, memory — was that goal. She invented a
restaurant. Then she texted him "a table for two at earl's on saturday at 7pm",
inventing a day, a time and a party size as well, and spent 58 browser steps
failing to book it at a branch in Winnipeg.

Measured across the last fourteen real jobs: SIX carried a proper noun that
appears nowhere in what he said. It is the same disease as inventing
omar@x.com and a 555 phone number — filling a blank rather than admitting one.

Names are checked as PHRASES, never word by word. Completing a name she
half-heard is legitimate and must stay legitimate: "cactus" becoming "Cactus
Club Cafe Park Royal" is her knowing the world, which is the job. Producing
"Earl's" out of a sentence containing no venue at all is not knowledge, it is
invention.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.orchestrator import unsupported_names  # noqa: E402


def test_the_earls_invention():
    assert unsupported_names(
        "Book a table at Earl's for dinner the day after tomorrow",
        "Hey we should go out for dinner you haven't really shit let's do it but",
    ) == ["Earl's"]


def test_a_clock_initiative_with_no_source_at_all():
    """The Paris flight he never mentioned. Its whole source was the string
    'clock initiative'."""
    assert unsupported_names(
        "book a flight to Paris from Vancouver", "clock initiative"
    ) == ["Paris", "Vancouver"]


def test_completing_a_half_heard_name_is_allowed():
    """The most important non-catch. Flagging this would block a booking that
    was entirely correct — an earlier word-by-word version did exactly that,
    calling "Club" and "Cafe" inventions."""
    assert unsupported_names(
        "Book dinner for two at Cactus Club Cafe Park Royal tomorrow at 7 PM",
        "Yeah let's go for dinner tomorrow yeah how's cactus cactus and pork "
        "sounds good yeah Park Royal OK let's do it",
    ) == []


def test_names_he_did_say_are_never_flagged():
    for goal, heard in [
        ("Email Priya about the invoice", "I have to email Priya the invoice later today"),
        ("Remind Sakib about the word", "if you don't mind putting that word in with Sakib"),
        ("Add August data to budget spreadsheet",
         "Oh I gotta open that budget spreadsheet and add the August"),
        ("Book dinner for two at Earls Brooklyn Saturday at 1pm",
         "honestly let's just do Earls, the Brooklyn one for sure, Saturday at one"),
        ("Send Marcus the quarterly numbers", "i need to send marcus the quarterly numbers"),
    ]:
        assert unsupported_names(goal, heard) == [], goal


def test_the_name_may_come_from_anywhere_she_was_given():
    """Conversation and the previous line count as heard, not just the line."""
    assert unsupported_names(
        "Book dinner at Earls tomorrow",
        "let's do it tomorrow",                       # the line
        "how about Earls | yeah that place is good",  # the conversation
    ) == []


def test_her_own_verbs_are_not_names():
    for goal in ("Book a table", "Research the best options", "Email the invoice",
                 "Prepare the deck", "Reschedule the meeting", "Confirm dinner plans"):
        assert unsupported_names(goal, "whatever he said") == [], goal


def test_it_is_bounded_and_safe_on_junk():
    assert unsupported_names("", "anything") == []
    assert unsupported_names(None, "anything") == []
    assert unsupported_names("Book at Alpha Beta Gamma Delta Epsilon Zeta Eta", "") <= [
        "Alpha Beta Gamma Delta Epsilon Zeta Eta"]
    many = " ".join(f"At Place{n}" for n in range(20))
    assert len(unsupported_names(many, "")) <= 4


def test_it_feeds_the_gate_that_turns_act_into_ask():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "brain", "anticipy_core.py")).read()
    call = src.index("unsupported_names(")
    gate = src.index('if decision.decision == "act" and decision.missing:')
    assert call < gate, "an invented name must become a question, not a booking"
    block = src[call - 200:call + 500]
    assert "line" in block and "context" in block, \
        "it must check against everything she was given, not just the bare line"
