"""The pending queue reads its persisted effect class and never task prose."""

from brain.anticipy_core import Anticipy


def test_pending_class_uses_the_stored_consequence():
    assert Anticipy._pending_class({"consequence": "consequential"}) is True
    assert Anticipy._pending_class({"consequence": "read_only"}) is False


def test_missing_pending_consequence_fails_closed_without_reading_the_goal():
    # These goals used to take opposite branches through is_consequential().
    # Once the persisted field is absent, wording has no authority: both hold.
    assert Anticipy._pending_class({"goal": "look up public opening hours"}) is True
    assert Anticipy._pending_class({"goal": "send the signed contract"}) is True
