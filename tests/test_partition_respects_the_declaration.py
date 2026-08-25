"""A world-declared plan must never be deduped into a lookup.

_same_pending's own docstring carries the scar: on 2026-08-04 "research Cactus
Club availability" and "book Cactus Club" shared almost every word, word
overlap called them one job, and the booking was silently dropped in favour of
the lookup already queued. "A job that changes his world can never be deduped
against one that only reads."

The partition that enforces that asked `is_consequential(goal)` with no
`touches`, so it re-derived the class from PROSE — the exact question the
effect-channel declaration exists to stop anyone asking. When the model says
"world" about a goal whose wording reads read-only, the prose answer is False,
the classes match, and the plan disappears into the research job. The scar
reopens through the one door the declaration was built to close.

Measured on this tree before the fix:

    pending : 'research the Vienna trip for the team in March'  -> read-only
    incoming: 'plan the Vienna trip for the team in March'      -> declared WORLD
    token overlap 0.80, both sides derive False, so they dedupe.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.anticipy_core import Anticipy, is_consequential  # noqa: E402
from brain.memory import Memory  # noqa: E402

PENDING_LOOKUP = "research the Vienna trip for the team in March"
INCOMING_PLAN = "plan the Vienna trip for the team in March"


def _brain(pending):
    a = Anticipy(memory=Memory(":memory:"), llm=None, owner_id="t")
    a._pending_jobs = lambda: pending
    return a


def test_the_precondition_still_holds():
    """If either half stops being true the tests below prove nothing."""
    assert not is_consequential(PENDING_LOOKUP), "pending must read read-only"
    assert not is_consequential(INCOMING_PLAN), \
        "the incoming goal must READ read-only, or prose already parts them"
    assert is_consequential(INCOMING_PLAN, touches="world"), \
        "and the declaration must be what makes it world-changing"


def test_a_world_plan_is_not_swallowed_by_a_pending_lookup():
    a = _brain([{"id": "research-1", "goal": PENDING_LOOKUP,
                 "consequence": "read_only"}])
    assert a._same_pending(INCOMING_PLAN, touches="world") is None, \
        "the booking was deduped into the lookup — 2026-08-04, again"


def test_the_same_plan_still_dedupes_within_its_own_class():
    """The fix must not stop dedupe working, or every re-mention breeds a
    card — the failure this partition was built between."""
    a = _brain([{"id": "plan-1", "goal": INCOMING_PLAN,
                 "consequence": "consequential"}])
    assert a._same_pending(INCOMING_PLAN, touches="world") == "plan-1"


def test_refines_pending_parts_the_classes_too():
    # The richer-wording path has the identical partition and the identical
    # hole; fixing only one leaves the plan a longer sentence away from
    # vanishing.
    richer = "plan the Vienna trip for the team in March for 4 people"
    a = _brain([{"id": "research-1", "goal": PENDING_LOOKUP,
                 "consequence": "read_only"}])
    assert a._refines_pending(richer, touches="world") is None


def test_the_pending_side_believes_the_stored_class_over_its_wording():
    """The other half of the same mistake. A card minted from a declaration
    carries `consequence` on the row; re-deriving it from the goal text asks
    the prose question again about work already classified. Here the stored
    class is the only thing that parts them."""
    a = _brain([{"id": "held-1", "goal": INCOMING_PLAN,
                 "consequence": "consequential"}])
    assert a._same_pending(PENDING_LOOKUP) is None, \
        "a read-only lookup matched a card the workflow calls consequential"


def test_the_declaration_reaches_the_partition_through_queue_job():
    """The wiring half. The partitions can take `touches` and still never see
    it: unit tests that call them directly stay green while hear() -> the
    queue drops it on the way. Drive the real path."""
    from brain.orchestrator import Decision

    a = _brain([{"id": "research-1", "goal": PENDING_LOOKUP,
                 "consequence": "read_only"}])
    seen = {}
    real_same = a._same_pending

    def spy(goal, touches=None):
        seen["touches"] = touches
        return real_same(goal, touches=touches)

    a._same_pending = spy
    a._refines_pending = lambda *_a, **_k: None
    a.notify_owner = lambda *_a, **_k: {"ok": True}
    a._decide = lambda *_a, **_k: Decision(
        decision="act", goal=INCOMING_PLAN, reason="a plan",
        addressee="assistant", owes="owner", touches="world",
        needs_confirmation=False)

    a.hear("plan the vienna trip", explicit=True, channel="app")

    assert seen.get("touches") == "world", \
        f"the queue partitioned without the declaration: {seen!r}"
