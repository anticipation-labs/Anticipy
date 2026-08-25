"""The search query was built by a verb list, and it ate the request.

`_QUERY_PREFIX` (brain/research.py) strips a leading "instruction verb" so Brave
sees "opening hours of the aquarium" rather than "research: opening hours of the
aquarium". That intent is fine. Deciding WHICH WORDS of a person's sentence are
instruction and which are subject is not — it is a judgement about meaning, and
HARNESS-LAWS Law 1 puts those with a model, never a word list.

Measured against the list as it stood:

    "Compare the two quotes from the movers" -> "the two quotes from the movers"
    "Price check the Sony a7 IV"             -> "check the Sony a7 IV"
    "check on my passport application"       -> "on my passport application"
    "Find me a dentist open Saturdays"       -> "me a dentist open Saturdays"

The first loses the entire request — comparing IS the task. The last is the
Brief's own moment 29, and the query it sent began with the word "me".

The fix keeps the useful half and drops the judgement: a LABEL is stripped only
when an explicit separator marks it as one. A colon is punctuation, not meaning.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from brain.research import query_from_goal  # noqa: E402


def test_a_labelled_prefix_is_still_stripped():
    """The case the stripping was written for, and it keeps working."""
    assert query_from_goal("research: opening hours of the Vancouver aquarium") \
        == "opening hours of the Vancouver aquarium"
    assert query_from_goal("look up - the ferry timetable") == "the ferry timetable"


def test_the_verb_that_carries_the_request_survives():
    """Comparing IS the task. A query without it asks a different question."""
    assert query_from_goal("Compare the two quotes from the movers") \
        == "Compare the two quotes from the movers"


def test_the_briefs_own_moment_29_is_not_mangled():
    """Moment 29: 'Find me a dentist that's open Saturdays near work'. The old
    list left a query beginning with the word 'me'."""
    q = query_from_goal("Find me a dentist open Saturdays near work")
    assert not q.lower().startswith("me ")
    assert "dentist" in q


def test_a_verb_mid_sentence_is_never_touched():
    assert query_from_goal("check on my passport application") \
        == "check on my passport application"
    assert query_from_goal("Price check the Sony a7 IV") == "Price check the Sony a7 IV"


def test_an_empty_or_bare_goal_never_becomes_empty():
    """A query of "" searches for nothing and returns nothing, silently — which
    reads downstream as "the sources did not contain the answer", a lie about
    work that never happened.

    HONEST NOTE: `or g` is currently UNREACHABLE — the leading .strip() plus the
    pattern's trailing `\s+` mean the regex can never consume the whole string,
    and a mutation removing the guard survives this test. That is recorded in
    brain/research.py rather than papered over with a contrived input. The
    assertions below are still the right ones: they pin the OUTCOME (nothing
    empty ever leaves) rather than the mechanism, so they keep their value if a
    later edit makes the guard reachable."""
    assert query_from_goal("research: ") == "research:"   # strips to "", falls back
    assert query_from_goal("look up — ") == "look up —"
    assert query_from_goal("research:") == "research:"
    assert query_from_goal("") == ""
    assert query_from_goal("   ") == ""


def test_only_the_first_label_is_stripped():
    """count=1. Two labels means the second is part of what he asked for —
    "research: look up: the ferry" is asking about a thing called "look up:"
    far less often than it is one label and a sentence, and stripping both
    silently rewrites the question."""
    assert query_from_goal("research: look up: the ferry") == "look up: the ferry"


def test_the_separator_is_mandatory_not_optional():
    """Law 1, pinned at the exact character that decides it.

    The verb alternation may stay — gated behind a required separator it only
    ever strips an explicit label. What must never come back is the `?` that
    made the separator OPTIONAL, because that single character is what turned a
    punctuation rule back into a verb list reading a sentence."""
    import brain.research as r
    assert r._QUERY_LABEL.pattern.count("[:\\-—]?") == 0, \
        "the separator is optional again — the verb list is reading meaning"
    assert "[:\\-—]" in r._QUERY_LABEL.pattern

    # And the behaviour that character controls, so the pin is not the only proof.
    assert query_from_goal("compare the movers") == "compare the movers"
    assert query_from_goal("compare: the movers") == "the movers"
