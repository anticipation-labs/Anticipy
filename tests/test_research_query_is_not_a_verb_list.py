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


def test_the_stripped_label_never_changes_the_QUESTION_THAT_GETS_ANSWERED():
    """The residual half of the same defect, found reviewing the repair.

    The separator makes the verb list safe to run over SEARCH TERMS — deciding
    what string a search engine is handed is plumbing, and Law 1's carve-out
    for senses covers it. It does not make the list safe to run over the
    QUESTION, and `run_research` was handing the stripped string to both:

        "compare: the two quotes from the movers"
            -> Brave gets "the two quotes from the movers"     (fine)
            -> the answering model is ASKED "the two quotes from the movers"

    which is the original failure exactly — comparing IS the task, and the
    answer comes back describing two quotes instead of comparing them. It just
    needed a colon to reach it. So the model is asked what the owner asked, and
    the word list is left doing only the one thing it can legitimately do.
    """
    import types
    import brain.research as r

    class Brave:
        def __init__(self):
            self.queries = []

        def search(self, query, count=5):
            self.queries.append(query)
            return [{"title": "Movers", "url": "https://example.com/movers",
                     "description": "Two quotes."}]

    class LLM:
        live = True

        def __init__(self):
            self.asked = []

        def chat(self, system, user, **kw):
            self.asked.append(user)
            return types.SimpleNamespace(text="Quote A is cheaper [1].")

    brave, llm = Brave(), LLM()
    r.run_research("compare: the two quotes from the movers", {}, llm=llm,
                   brave=brave, fetcher=lambda url: "Quote A $900, quote B $1200.")
    assert brave.queries == ["the two quotes from the movers"], \
        "the search string is plumbing and the label still comes off it"
    assert "compare" in llm.asked[0].lower(), \
        "the answering model was asked a question the word list had rewritten"


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
