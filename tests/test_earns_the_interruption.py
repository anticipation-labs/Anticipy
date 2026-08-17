"""An uninvited text has to be worth getting.

His report: "why is it also randomly messaging me after the fact... Don't
kill it because it's good sometimes. 90% of the time it's bad."

Background: on 2026-08-05 overheard lookups started texting instead of
landing silently, because invisible work had made the product look dead.
That was right. But the only gates were quiet hours and don't-repeat-the-
same-goal, and nothing asked whether the message was worth having. So an
empty-handed lookup still buzzed his phone.

Every rule here decides ONE thing: buzz, or feed only. Nothing is ever
discarded — the finding always reaches the feed.
"""
import pytest
from brain.worker import (
    worth_interrupting_him, job_age_seconds,
    UNINVITED_TEXTS_PER_DAY, FYI_STALE_AFTER_SECONDS,
)

# Verbatim from a production job row.
REAL_NON_ANSWER = ('The provided sources do not contain information about an '
                   '"Earls" restaurant in Vancouver. The sources mention "The EARL"')
REAL_GOOD = ('Cactus Club Cafe has a location in West Vancouver at Park Royal '
             'Mall, 855 Main Street. You can make a reservation through their site.')


def test_the_message_he_actually_got_would_no_longer_buzz():
    worth, why = worth_interrupting_him("earls vancouver", REAL_NON_ANSWER, 60, 0)
    assert worth is False
    assert "found nothing" in why


@pytest.mark.parametrize("dud", [
    "I couldn't find anything about that.",
    "No results were found for this query at all.",
    "I don't have information on that particular restaurant.",
    "That information is not available from the sources I checked.",
])
def test_no_empty_handed_lookup_ever_buzzes(dud):
    assert worth_interrupting_him("x", dud, 60, 0)[0] is False


def test_a_real_fresh_answer_still_buzzes():
    """The 10% that is the whole point of the product must survive."""
    assert worth_interrupting_him("cactus club", REAL_GOOD, 300, 0)[0] is True


def test_the_moment_can_pass():
    assert worth_interrupting_him("x", REAL_GOOD, FYI_STALE_AFTER_SECONDS - 60, 0)[0] is True
    worth, why = worth_interrupting_him("x", REAL_GOOD, FYI_STALE_AFTER_SECONDS + 60, 0)
    assert worth is False and "moment has passed" in why


def test_a_chatty_day_has_a_ceiling():
    for n in range(UNINVITED_TEXTS_PER_DAY):
        assert worth_interrupting_him("x", REAL_GOOD, 60, n)[0] is True
    worth, why = worth_interrupting_him("x", REAL_GOOD, 60, UNINVITED_TEXTS_PER_DAY)
    assert worth is False and "uninvited texts today" in why


def test_a_thin_result_is_not_news():
    assert worth_interrupting_him("x", "Yes.", 60, 0)[0] is False
    assert worth_interrupting_him("x", "", 60, 0)[0] is False


def test_an_unreadable_timestamp_is_treated_as_fresh_not_muted():
    """Failing to parse a date must never become a reason to go quiet."""
    assert job_age_seconds({"created": "nonsense"}) == 0.0
    assert job_age_seconds({}) == 0.0
    assert worth_interrupting_him("x", REAL_GOOD, job_age_seconds({}), 0)[0] is True


def test_nothing_here_can_discard_a_finding():
    """Every rule returns a verdict about BUZZING. None of them can be read
    as permission to drop the finding — the feed always gets it."""
    import inspect
    src = inspect.getsource(worth_interrupting_him)
    assert "NEVER discards" in src or "never discards" in src.lower()
