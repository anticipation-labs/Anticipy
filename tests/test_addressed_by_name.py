"""His own website turned off the filter that protects him.

Her name is Anticipy. His company's site is anticipy.ai.

`looks_like_dictation` stands down when she has been addressed by name — right
rule, since somebody saying "Anticipy, book me a table" is plainly talking to
her. It tested that with a plain substring, so EVERY sentence mentioning
anticipy.ai counted as being addressed by name, and the filter switched off for
exactly the lines it exists to catch.

Seen live 2026-08-07. Sixty-one words dictated at Wispr Flow:

    "Please go please go on anticipY.ai kindly good picture to use then pull
     that in with ChatGPT GEN two and using all that I need you to generate an
     image ... make sure the wording is correct to make one perfect picture
     that I can share around that's like the job listing essentially"

Measured, on that exact line:

    with anticipY.ai in it          looks_like_dictation -> False
    same sentence, domain removed   looks_like_dictation -> True

So triage read it as work. Then a truncated follow-on fragment, "Tell people to
contact omar@aNt", became a real job — "Draft a social media post for a job
listing, including contact information for omar@ant.ai" — inventing an address
out of a cut-off word. He got told she was drafting a public post about a job
he never offered.

One substring test. A web address, an email address and a bare domain are
things being NAMED, not people being spoken to.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.anticipy_core import (DICTATION_MIN_WORDS, NAME,  # noqa: E402
                                 addressed_by_name, looks_like_dictation)

# Verbatim from the worker log.
THE_WISPR_LINE = (
    "Please go please go on anticipY.ai kindly good picture to use then pull "
    "that in with ChatGPT GEN two and using all that I need you to generate an "
    "image if you need but no generate anything stupid but make sure the "
    "wording is correct to make one perfect picture that I can share around "
    "that's like the job listing essentially")


def test_the_line_that_caused_it_is_now_caught():
    assert len(THE_WISPR_LINE.split()) >= DICTATION_MIN_WORDS
    assert addressed_by_name(THE_WISPR_LINE) is False, \
        "his own website still reads as her being spoken to"
    assert looks_like_dictation(THE_WISPR_LINE) is True, \
        "this is the Wispr Flow dictation that became a public job post"


def test_removing_the_domain_changes_nothing_now():
    """The measurement that proved the cause: the ONLY difference between
    caught and not-caught used to be whether his website was mentioned."""
    without = THE_WISPR_LINE.replace("anticipY.ai", "the website")
    assert looks_like_dictation(THE_WISPR_LINE) == looks_like_dictation(without)


def test_a_web_address_is_not_someone_being_spoken_to():
    for line in ("go to anticipy.ai and grab the logo",
                 "check https://anticipy.ai/careers for the wording",
                 "it's on www.anticipy.ai somewhere",
                 "email hello@anticipy.ai about it",
                 "the deck is at anticipy.ai/deck",
                 "look at ANTICIPY.AI",
                 "try anticipy.co.uk as well"):
        assert addressed_by_name(line) is False, line


def test_saying_her_name_to_her_still_counts():
    for line in ("Anticipy, book me a table",
                 "hey anticipy can you check that",
                 "ask Anticipy to do it",
                 "ANTICIPY stop",
                 "so, Anticipy — what's on today?",
                 "thanks Anticipy!"):
        assert addressed_by_name(line) is True, line


def test_her_name_next_to_a_web_address_still_counts():
    """Both in one sentence: the domain is stripped, the real address remains."""
    assert addressed_by_name("Anticipy, pull the logo off anticipy.ai") is True


def test_a_word_that_merely_contains_her_name_is_not_her_name():
    for line in ("the anticipyation was unbearable",
                 "we run anticipylabs internally",
                 "unanticipy is not a word but it should not match either"):
        assert addressed_by_name(line) is False, line


def test_being_addressed_still_stops_the_dictation_filter():
    """The rule this protects. A long instruction spoken TO her is not
    dictation to some other machine, and must not be silenced."""
    spoken_to_her = (
        "Anticipy I need you to go ahead and put together the whole thing for "
        "me please make sure the wording is correct and you should use the "
        "same layout as before so that it matches what we already have and "
        "then send it over to me when you are done with all of that thanks")
    assert len(spoken_to_her.split()) >= DICTATION_MIN_WORDS
    assert addressed_by_name(spoken_to_her) is True
    assert looks_like_dictation(spoken_to_her) is False


def test_junk_never_raises():
    for junk in (None, "", "   ", "@", "://", "....", "a" * 3000, "😀"):
        assert addressed_by_name(junk) in (True, False)
        assert looks_like_dictation(junk) in (True, False)


def test_the_name_is_matched_as_a_whole_word_not_a_substring():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "brain", "anticipy_core.py")).read()
    i = src.index("def addressed_by_name")
    # To the end of the function, not a fixed window — the docstring alone is
    # longer than 900 characters, so a fixed slice never reached the code and
    # the assertion below failed for the wrong reason.
    body = src[i:src.index("def looks_like_dictation")]
    assert "NAME.lower() in text" not in body, \
        "a substring test is what caused this"
    assert r"\b" in body, "the name must be matched on word boundaries"
    assert "_ADDRESSES_RE.sub" in body, \
        "addresses must be removed before looking for her name"


def test_the_dictation_filter_actually_uses_it():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "brain", "anticipy_core.py")).read()
    i = src.index("def looks_like_dictation")
    body = src[i:i + 600]
    assert "addressed_by_name(text)" in body
    assert "NAME.lower() in text" not in body


def test_the_name_constant_is_what_is_being_matched():
    """If NAME is ever rebranded, this must follow it rather than hard-coding
    the word Anticipy in the matcher."""
    assert NAME == "Anticipy"
    assert addressed_by_name(f"{NAME} do the thing") is True
