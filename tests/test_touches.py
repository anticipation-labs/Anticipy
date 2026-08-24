"""The effect channel is DECLARED by the model and ENFORCED by the gate.

History this locks in place: the gate first judged goals with a verb list
(held a timezone conversion for approval, 2026-08-23), then with a
calculator-sniff run on every goal — both pattern-matching wearing
different coats. Meaning belongs to the model: triage names what a goal
touches (compute | read | world) and is_consequential merely enforces it,
with one deterministic deny-list that outranks even the declaration.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.anticipy_core import is_consequential


def test_world_declaration_holds_even_in_read_only_clothing():
    # "plan" reads read-only to the old regex; the model saw a dinner that
    # ends in a reservation and said so. The declaration wins.
    assert is_consequential("plan dinner with the team Thursday",
                            touches="world")


def test_compute_declaration_runs_unattended_whatever_the_wording():
    # No word list recognises this phrasing; the brain called it math.
    assert not is_consequential("work out what 5 PM CST is out west",
                                touches="compute")


def test_the_deny_list_outranks_the_declaration():
    # A model talked into declaring "compute" on a SEND changes nothing —
    # enforcement lives below the model.
    assert is_consequential("send the 5 PM CST conversion to Tejas",
                            touches="compute")
    assert is_consequential("email Priya the summary", touches="read")


def test_no_declaration_behaves_exactly_as_before():
    assert not is_consequential("Convert 5 PM CST to PST")      # calc fallback
    assert not is_consequential("research standing desks")      # read-only re
    assert is_consequential("convert the garage into a studio") # held default
    assert is_consequential("book the 8:40 flight to Boston")   # deny-list


def test_garbage_declaration_is_no_declaration():
    # Decision parsing nulls invalid channels, but defend in depth here too.
    assert is_consequential("convert the garage into a studio",
                            touches="banana")
