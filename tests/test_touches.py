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


# --------------------------------------------------------------------------
# THE DECLARATION HAS TO REACH THE GATE, NOT JUST EXIST.
#
# is_consequential takes `touches`, and the ambient lane passes it
# (anticipy_core.py ~1631). The DIRECT lane — everything he types or says
# straight to her — called it as is_consequential(goal, params,
# explicit=explicit) and dropped the declaration on the floor.
#
# That combination is the confirmation gate opening. Read the order inside
# is_consequential: the deny-list, then touches=="world", then `if explicit:
# return False`. With the declaration missing, an explicit ask is released the
# moment its verb is not on the deny-list — and the deny-list is a word list,
# so it only knows the verbs somebody thought of. "grab us a table", "put us
# down for a table": no match, released unheld, no card, no tap.
#
# The model had already judged these correctly. Triage said touches="world";
# the answer was computed, then discarded one function call before it was
# used. This is the trust spine of the product, and a stranger TYPES on day
# one.
# --------------------------------------------------------------------------

def test_a_typed_world_goal_is_held_even_when_no_verb_list_knows_it():
    # The model's verdict must survive the explicit shortcut.
    for goal in ("grab us a table at Earls at 7",
                 "put us down for a table at Earls at 7",
                 "get us on the list for Saturday"):
        assert not is_consequential(goal, explicit=True), \
            f"precondition: {goal!r} must be invisible to the deny-list, " \
            "or this test is not exercising the bypass"
        assert is_consequential(goal, explicit=True, touches="world"), \
            f"a declared world goal must hold even when typed: {goal!r}"


def test_the_explicit_shortcut_still_works_for_declared_read_and_compute():
    # The fix must not turn every typed errand into a card. An explicit ask
    # the model called read-only or arithmetic still runs unattended —
    # making him confirm "open wikipedia" is how people learn to tap through
    # prompts without reading.
    assert not is_consequential("look up the Earls menu", explicit=True,
                                touches="read")
    assert not is_consequential("what's 5 PM CST out west", explicit=True,
                                touches="compute")


def test_the_direct_lane_passes_the_declaration_to_the_gate():
    """The behavioural half: hear() a typed line whose goal the deny-list
    cannot see, with the model declaring world, and the job must be HELD.

    Unit-testing is_consequential alone would have stayed green through the
    entire bug — the declaration was correct and simply never arrived.
    """
    from brain.anticipy_core import Anticipy
    from brain.memory import Memory
    from brain.orchestrator import Decision

    a = Anticipy(memory=Memory(":memory:"), llm=None, owner_id="t")
    queued = {}

    def fake_queue(goal, params, hold=False, **kw):
        queued["goal"], queued["hold"] = goal, hold
        return "job-1"

    a._queue_job = fake_queue
    a.notify_owner = lambda *_a, **_k: {"ok": True}
    a._decide = lambda *_a, **_k: Decision(
        decision="act", goal="grab us a table at Earls at 7",
        reason="clear ask", addressee="assistant", owes="owner",
        touches="world", needs_confirmation=False)

    a.hear("grab us a table at earls at 7", explicit=True, channel="app")

    assert queued.get("goal") == "grab us a table at Earls at 7", \
        f"the errand never reached the queue at all: {queued!r}"
    assert queued.get("hold") is True, \
        "a world-declared errand was queued UNHELD — the confirmation gate " \
        "was bypassed by a verb the deny-list happens not to know"
