"""Legacy name-boundary regression; content destination now has a model judge.

The name matcher remains a separate legacy path, not evidence that an entire
recording is dictation. Contextual destination contrasts live in
test_read_into_a_machine.py and the real-model content-context proof.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.anticipy_core import NAME, addressed_by_name  # noqa: E402

# Verbatim from the worker log.
THE_WISPR_LINE = (
    "Please go please go on anticipY.ai kindly good picture to use then pull "
    "that in with ChatGPT GEN two and using all that I need you to generate an "
    "image if you need but no generate anything stupid but make sure the "
    "wording is correct to make one perfect picture that I can share around "
    "that's like the job listing essentially")






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




def test_junk_never_raises():
    for junk in (None, "", "   ", "@", "://", "....", "a" * 3000, "😀"):
        assert addressed_by_name(junk) in (True, False)


def test_the_name_is_matched_as_a_whole_word_not_a_substring():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "brain", "anticipy_core.py")).read()
    i = src.index("def addressed_by_name")
    # To the end of the function, not a fixed window — the docstring alone is
    # longer than 900 characters, so a fixed slice never reached the code and
    # the assertion below failed for the wrong reason.
    body = src[i:src.index("def explicitly_for_memory")]
    assert "NAME.lower() in text" not in body, \
        "a substring test is what caused this"
    assert r"\b" in body, "the name must be matched on word boundaries"
    assert "_ADDRESSES_RE.sub" in body, \
        "addresses must be removed before looking for her name"




def test_the_name_constant_is_what_is_being_matched():
    """If NAME is ever rebranded, this must follow it rather than hard-coding
    the word Anticipy in the matcher."""
    assert NAME == "Anticipy"
    assert addressed_by_name(f"{NAME} do the thing") is True
