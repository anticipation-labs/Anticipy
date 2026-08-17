"""A spoken "yeah do it" must not pick a card for him.

The voice lane fetched perPage=1 sorted newest-first and released it. With
two cards open, saying "do it" out loud booked whichever happened to be
newer -- and that release does a real thing in the world. The identical
words sent by SMS correctly come back "which one, 1) or 2)?", because that
path refuses to guess. Two lanes to the same decision must not disagree
about whether guessing is allowed.
"""
import inspect, time, datetime
from brain.anticipy_core import Anticipy


def _row(seconds_ago):
    t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=seconds_ago)
    return {"created": t.strftime("%Y-%m-%d %H:%M:%S")}


def test_recently_asked_window():
    assert Anticipy._recently_asked(_row(60)) is True
    assert Anticipy._recently_asked(_row(300)) is True
    assert Anticipy._recently_asked(_row(1200)) is False


def test_an_unreadable_timestamp_still_counts():
    # Never silently drop a card because its date would not parse.
    assert Anticipy._recently_asked({"created": "nonsense"}) is True
    assert Anticipy._recently_asked({}) is True


def test_the_voice_lane_asks_for_more_than_one_candidate():
    src = inspect.getsource(Anticipy._release_freshest_held)
    assert '"perPage": 1' not in src, (
        "fetching a single row is what made a spoken yes pick a card for him")
    assert "_recently_asked" in src
    assert "return None" in src


def test_several_live_cards_make_a_spoken_yes_fall_through():
    """Two live cards and one unqualified 'do it' must reach triage, which
    can ask which -- not release one and find out afterwards."""
    src = inspect.getsource(Anticipy._release_freshest_held)
    flat = " ".join(src.split())
    assert "if len([j for j in items if self._recently_asked(j)]) > 1:" in flat
