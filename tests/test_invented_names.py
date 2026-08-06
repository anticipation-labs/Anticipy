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


def test_names_are_bounded_and_safe_on_junk():
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


# ------------------------------------------------ invented head counts

from brain.orchestrator import unsupported_counts  # noqa: E402


def test_the_parker_lunch_invented_a_party_size():
    """He said: "For lunch tomorrow at four how's cactus in Parker". No number
    of people anywhere. The goal came back "Book lunch for TWO", the venue
    only takes parties of six to eight, and the invented two is the reason the
    whole booking failed."""
    assert unsupported_counts(
        "Book lunch for two at Cactus in Parker tomorrow at 4 PM",
        "For lunch tomorrow at four how's cactus in Parker that looks great OK",
    ) == ["how many people — you did not say two"]


def test_for_two_is_her_default_and_it_is_usually_wrong():
    """Measured across every real job carrying a head count: SEVEN OF TEN
    invented it."""
    assert unsupported_counts("Book a table at Earl's in West Vancouver for two people",
                              "Yes please book and in West Vancouver")
    assert unsupported_counts("Draft dinner reservation for Cactus Club for 2", "For dinner")


def test_a_count_he_actually_gave_is_never_flagged():
    for goal, heard in [
        ("Book dinner for two at Cactus Club Park Royal tomorrow at 7 PM",
         "let's do dinner tomorrow, just the two of us, seven at Cactus Club Park Royal"),
        ("Book a table for 4 at Earls Brooklyn for Saturday at 1 PM",
         "it'll be us four right the whole crew, Saturday at one"),
        ("Book a table for 6 on Friday", "book us in for 6 on friday"),
    ]:
        assert unsupported_counts(goal, heard) == [], goal


def test_words_and_digits_are_the_same_fact():
    """Without this, "at 4 PM" built from him saying "at four" would read as
    invented, and the check would block work that was entirely correct —
    worse than the bug it exists to stop."""
    assert unsupported_counts("Book a table for 4 tomorrow", "there'll be four of us") == []
    assert unsupported_counts("Book a table for four tomorrow", "there'll be 4 of us") == []
    assert unsupported_counts("Book Earls for Saturday at 1pm", "Saturday at one works") == []


def test_numbers_that_are_not_head_counts_are_left_alone():
    """A price, a time, a street number is not a party size."""
    for goal in ("Research noise cancelling headphones under 400 dollars",
                 "Book a table at 7 PM",
                 "Email Priya about invoice 1042"):
        assert unsupported_counts(goal, "whatever he said") == [], goal


def test_counts_are_bounded_and_safe_on_junk():
    assert unsupported_counts("", "x") == []
    assert unsupported_counts(None, "x") == []
    assert len(unsupported_counts("for two and for three and for four and for five", "")) <= 2


def test_both_checks_feed_the_same_gate():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "brain", "anticipy_core.py")).read()
    i = src.index("made_up = (unsupported_names")
    block = src[i:i + 300]
    assert "unsupported_counts(decision.goal" in block, \
        "an invented head count must become a question too"
    gate = src.index('if decision.decision == "act" and decision.missing:')
    assert i < gate
