"""The link answer, and the wall around it.

Three states, and the whole safety of this change is the difference between
the last two:

    >=1   this line carries on from that numbered earlier line
     0    this line starts a new thread   <- a CLAIM
    None  no usable answer                <- fall back to today

Everything malformed collapses to None, never to 0. A model that is confused
has not claimed anything, and reading confusion as a claim is exactly how a
safety wall becomes decoration — which has already happened twice on this
project (a `_freshest_pending` that aged by a field nobody selects, an
`is_late` with no callers).
"""
import json
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.orchestrator import (Brain, TRIAGE_SYSTEM, _continues)  # noqa: E402


class Fake:
    live = True

    def __init__(self, payload):
        self.payload = payload

    def chat(self, system, user, **kw):
        text = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return types.SimpleNamespace(text=text)


BASE = {"decision": "act", "goal": "book a table", "addressee": "person",
        "owes": "owner", "reason": "plan agreed"}


def triage(payload, candidates):
    return Brain(llm=Fake(payload)).triage("some line", candidates=candidates)


# ------------------------------------------------------------ it works

def test_a_valid_index_is_kept():
    assert triage({**BASE, "continues": 3}, candidates=6).continues == 3


def test_zero_means_a_new_thread_and_is_kept():
    assert triage({**BASE, "continues": 0}, candidates=6).continues == 0


def test_the_boundaries_of_the_range_are_inclusive():
    assert _continues(1, 4) == 1
    assert _continues(4, 4) == 4


def test_a_numeric_string_is_accepted():
    assert triage({**BASE, "continues": "2"}, candidates=6).continues == 2
    assert _continues(" 3 ", 6) == 3


# ------------------------------------------------------- the honesty wall

def test_no_field_at_all_is_no_answer():
    assert triage(BASE, candidates=6).continues is None


def test_showing_no_candidates_discards_any_answer():
    """Nothing was shown, so there is nothing to point at. This is what every
    existing caller does, which is why this change cannot move production."""
    for answer in (0, 1, 5, "2", None):
        assert _continues(answer, 0) is None


def test_out_of_range_is_no_answer_not_a_new_thread():
    """A model naming line 9 of 4 has told us nothing. Reading that as 0
    would let a confused model confidently start threads."""
    assert _continues(9, 4) is None
    assert _continues(-1, 4) is None
    assert _continues(-0.0, 4) == 0        # still zero, just ugly


def test_booleans_are_refused():
    """True == 1 in Python, so an unguarded int check would silently read
    `"continues": true` as 'continues line 1'."""
    assert _continues(True, 4) is None
    assert _continues(False, 4) is None


def test_garbage_is_no_answer():
    for junk in (None, "", "  ", "null", "none", "new", "abc", [], {}, 1.5,
                 object()):
        assert _continues(junk, 4) is None, junk


def test_unparseable_model_output_does_not_raise():
    d = triage("not json at all", candidates=6)
    assert d.continues is None
    assert d.decision == "ignore"


def test_a_link_answer_never_disturbs_the_other_fields():
    """Adding a field to the contract must not cost us the ones that already
    decide her behaviour."""
    d = triage({**BASE, "continues": 2}, candidates=6)
    assert d.decision == "act"
    assert d.goal == "book a table"
    assert d.owes == "owner"
    assert d.addressee == "person"


def test_the_default_call_signature_is_unchanged():
    """Every existing caller passes one argument. It must keep working, and
    it must yield no link verdict."""
    assert Brain(llm=Fake({**BASE, "continues": 3})).triage("x").continues is None


def test_the_model_is_actually_asked_the_question():
    assert '"continues"' in TRIAGE_SYSTEM
    assert "CARRY ON FROM" in TRIAGE_SYSTEM


def _flat(text: str) -> str:
    """The prompt is hard-wrapped prose, so a phrase we care about can be
    split across a newline. Assert on meaning, not on where the wrap fell."""
    return " ".join(text.split()).lower()


def test_the_prompt_forbids_judging_by_time_or_length():
    """The two heuristics that produced Omar's twelve-row screenshot. If a
    future edit drops these the prompt silently reverts to a timer in prose."""
    flat = _flat(TRIAGE_SYSTEM)
    assert "not by how much time passed" in flat
    assert "not by how short the line is" in flat


def test_the_prompt_distinguishes_omitting_from_zero():
    assert "different from 0" in _flat(TRIAGE_SYSTEM)


def test_the_prompt_covers_the_case_that_started_this():
    """A cold caller: her opening line is new, and everything after it is the
    same conversation however long the gaps while she talks."""
    assert "cold caller" in _flat(TRIAGE_SYSTEM)
