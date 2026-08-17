"""One corrupt plan row must not silence him for the rest of the day.

Consequence() and PlanState() raise ValueError on an empty or unknown value,
and the blob is parsed inside hear(). A single malformed row therefore threw
out of _queue_job and hear(); the worker marked the already-claimed event
"error" and never retried it. Every later line touching that lineage died the
same way, in silence.
"""
import pytest
from brain.workflow import (
    Plan, Consequence, PlanState, _consequence_or_safe, _state_or_safe,
)


def test_unknown_consequence_is_treated_as_world_changing():
    assert _consequence_or_safe("") is Consequence.CONSEQUENTIAL
    assert _consequence_or_safe("bogus") is Consequence.CONSEQUENTIAL
    assert _consequence_or_safe(None) is Consequence.CONSEQUENTIAL
    # a readable value is still honoured
    assert _consequence_or_safe("read_only") is Consequence.READ_ONLY


def test_unknown_state_parks_for_the_owner():
    for bad in ("", "weird", None, 17):
        assert _state_or_safe(bad) is PlanState.NEEDS_USER, bad
    assert _state_or_safe("queued") is PlanState.QUEUED
    # never silently terminal: a corrupt row must stay recoverable
    assert _state_or_safe("nonsense") not in {
        PlanState.SUCCEEDED, PlanState.FAILED, PlanState.CANCELLED}


ID = {"plan_id": "p1", "owner_ref": "acct1", "lineage_key": "lin1", "version": 1,
      "goal": "book a table at Earls"}


@pytest.mark.parametrize("bad", [
    {"consequence": "", "state": "queued"},
    {"consequence": "consequential", "state": ""},
    {"consequence": "junk", "state": "junk"},
    {},                                   # both fields missing entirely
])
def test_a_corrupt_row_parses_instead_of_throwing(bad):
    plan = Plan.from_dict({**ID, **bad})
    assert plan.consequence in tuple(Consequence)
    assert plan.state in tuple(PlanState)
    # unreadable is treated as the cautious reading, never as free to act
    if bad.get("consequence") not in ("read_only", "consequential"):
        assert plan.consequence is Consequence.CONSEQUENTIAL
    if bad.get("state") not in {s.value for s in PlanState}:
        assert plan.state is PlanState.NEEDS_USER
    # An unreadable consequence must PARK the work too: gating it while
    # leaving it queued builds an illegal plan (consequential + unapproved)
    # and throws the very exception this fix exists to prevent.
    if bad.get("consequence") not in ("read_only", "consequential"):
        assert plan.state is PlanState.NEEDS_USER


def test_a_plan_with_no_identity_is_still_refused():
    """Not everything gets a safe default. There is no honest guess for
    WHOSE plan this is, and inventing one would attribute work to the wrong
    person — worse than the crash. The caller must skip such a row."""
    from brain.workflow import WorkflowViolation
    with pytest.raises(WorkflowViolation):
        Plan.from_dict({"consequence": "read_only", "state": "queued", "goal": "x"})
