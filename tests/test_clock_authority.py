"""Time may surface an owner-authored task; it may never invent one.

WHAT CHANGED, AND WHY THIS FILE IS NOW ABOUT A MODEL VERDICT
------------------------------------------------------------
The fence used to be `_CLOCK_ACTION_SOURCE_RE`: nine verb stems deciding
whether a remembered sentence MEANT an obligation, on the path that mints
goals from stored facts. HARNESS-LAWS Law 1's canonical shape, and the
2026-08-24 audit's item 11 (severity H).

It was wrong in both directions at once, reproduced on this tree:

  * every sentence orchestrator's own `owes` prompt names as the reason
    ambient listening exists — "the VAT return is due on the seventh",
    "we're completely out of the good coffee", "that filling has been aching
    for a week" — got the goal DROPPED, along with every bare imperative
    ("Book Earls for Friday at 7"). The same mistake measured on 2026-08-20,
    where treating a speech act as the only route to an obligation sent HALF
    of all real errands to "nobody";
  * "Can you believe Tejas said that?", "Please, that is ridiculous", "I'll
    be honest…" and "I have to say…" PASSED, so chatter licensed a
    consequential held card.

The question now goes to a model that can read the quote, and this file pins
the behaviour on both sides of that call — including the part of the old line
that was never about words at all.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.anticipy_core import Anticipy                    # noqa: E402
from brain.orchestrator import (LICENCE_YES, LICENCE_NO,    # noqa: E402
                                LICENCE_UNASKED, LICENCE_UNANSWERED,
                                work_is_licensed)
from llm_fakes import licence_reply                         # noqa: E402


class Memory:
    def __init__(self, source):
        self.source = source

    def open_loops(self):
        return [{"id": 7, "what": "dentist appointment", "source": self.source,
                 "ts": 1000}]


class LLM:
    """A live model answering two different questions — the clock's, and the
    licence question clock_tick now asks before it prepares anything. A double
    that answered both with one canned reply would be answering the second
    with something unreadable, and unreadable refuses."""
    owner_zone = "America/Vancouver"
    live = True

    def __init__(self, licensed=True, loop_ids=(7,), goal="confirm appointment details"):
        self.licensed = licensed
        self.loop_ids = list(loop_ids)
        self.goal = goal
        self.asked = []

    def chat(self, system="", user="", **_kw):
        self.asked.append((system, user))
        reply = licence_reply(system, self.licensed)
        if reply is None:
            reply = json.dumps({
                "initiate": True,
                "say": "Your dentist appointment is Friday at 3 PM.",
                "goal": self.goal,
                "loop_ids": self.loop_ids,
            })

        class R:
            text = reply
        return R()

    def licence_calls(self):
        return [u for s, u in self.asked if "licenses_work" in s]


def _run(source, **kw):
    llm = LLM(**kw)
    a = Anticipy(memory=Memory(source), llm=llm, owner_phone=None)
    queued = []
    a._queue_job = lambda goal, params, hold=False, **_k: queued.append(
        (goal, params, hold)) or "job"
    return a.clock_tick(now=2000), queued, llm


# --------------------------------------------------------------------------
# THE TWO ORIGINAL SCENARIOS, now decided by the model instead of by verbs
# --------------------------------------------------------------------------
def test_a_remembered_fact_can_be_reminded_but_never_becomes_a_job():
    out, queued, _ = _run("Remember that my dentist appointment is Friday at 3 PM.",
                          licensed=False)
    assert out["say"] == "Your dentist appointment is Friday at 3 PM."
    assert out["goal"] is None
    assert queued == []


def test_an_owner_authored_obligation_can_still_be_prepared_safely():
    out, queued, _ = _run("I need to confirm my dentist appointment by Friday.")
    assert out["goal"] == "confirm appointment details"
    assert queued and queued[0][0] == "confirm appointment details"
    assert queued[0][2] is True, "consequential clock work remains approval-held"


# --------------------------------------------------------------------------
# THE REGRESSION THE VERB LIST WAS: an obligation nobody promised out loud
# --------------------------------------------------------------------------
@pytest.mark.parametrize("source", [
    # The four lines orchestrator's `owes` prompt names as the case ambient
    # listening exists for. The verb list matched NONE of them.
    "The VAT return is due on the seventh.",
    "We're completely out of the good coffee.",
    "That filling has been aching for a week.",
    "I forgot to cook for my kids this afternoon.",
    # And a bare imperative aimed straight at her, which it also missed.
    "Book Earls for Friday at 7.",
])
def test_a_revealed_obligation_is_prepared_even_though_nobody_promised_anything(source):
    """Every one of these had its goal dropped by the verb list. The duty
    existed before the sentence did; the sentence is only how she heard about
    it, and a wording test cannot see that."""
    out, queued, _ = _run(source)
    assert out["goal"] == "confirm appointment details", \
        f"a real errand was thrown away because of how it was worded: {source!r}"
    assert queued


@pytest.mark.parametrize("source", [
    # Every one of these MATCHED the old verb list and licensed a job.
    "Can you believe Tejas said that?",
    "Please, that is ridiculous.",
    "I'll be honest, that movie was terrible.",
    "I have to say, the coffee here is amazing.",
    "I promised to never watch that again, ha.",
])
def test_chatter_that_matched_the_old_verb_list_no_longer_licenses_work(source):
    out, queued, _ = _run(source, licensed=False)
    assert out["goal"] is None, \
        f"chatter licensed a consequential card because of its verbs: {source!r}"
    assert queued == []
    assert out["say"], "the fence takes the action, never her voice"


def test_the_words_do_not_decide_it_the_model_does():
    """THE MUTATION GUARD FOR A RELAPSE. The one sentence the old list was
    RIGHT about, with the model saying no: if anything in this path ever reads
    the wording again as a shortcut, this goes green on the words and red
    here."""
    out, queued, _ = _run("I need to confirm my dentist appointment by Friday.",
                          licensed=False)
    assert out["goal"] is None, "something is still reading the verbs"
    assert queued == []


# --------------------------------------------------------------------------
# THE HALF OF THE OLD LINE THAT WAS NEVER ABOUT WORDS
# --------------------------------------------------------------------------
def test_a_goal_built_on_a_loop_id_we_do_not_hold_is_dropped_without_asking(capsys):
    """`not any(regex.search(...) for loop in selected)` is True on an EMPTY
    `selected` whatever the regex says — so the check that caught a
    hallucinated loop id was carried by the arity of any(), inside a check
    about meaning. Nothing else catches it: the guest fence's unnamed branch
    is guarded by `bool(selected)` and does not fire either.

    TWO REFUSALS STAND HERE, and this leg pins BOTH, because pinning only the
    outcome is a test that cannot fail. work_is_licensed() also refuses an
    empty quote list (LICENCE_UNASKED), so deleting the explicit check leaves
    the goal dropped and the model unasked — mutation-run, and every leg in
    this file stayed green. The distinguishable thing is WHICH refusal fired,
    and it is not cosmetic: an operator reading "nothing he said licenses
    this" about a loop we never held would go looking at the wrong half of the
    system, and the day somebody makes work_is_licensed() tolerate an empty
    set the backstop is gone with no other check standing behind it.

    It is mechanism, not meaning: it reads ids, never English, and it costs no
    model call."""
    out, queued, llm = _run("I need to confirm my dentist appointment by Friday.",
                            loop_ids=(99,))
    assert out["goal"] is None, "a goal was prepared off a loop that does not exist"
    assert queued == []
    assert llm.licence_calls() == [], \
        "a loop we do not hold is a mechanism fact; no model should be asked"
    said = capsys.readouterr().out
    assert "not loops I hold" in said, \
        ("the goal was dropped by the licence backstop, not by the check that "
         "knows why — restore the explicit `if goal and not selected` guard")
    assert "licenses preparing" not in said


def test_naming_a_real_loop_beside_a_phantom_still_reaches_the_licence_question():
    """The narrow read of the check above: `selected` is empty only when NONE
    of the named ids are ours. One real id is enough to have something to
    judge, and then the model judges it."""
    out, queued, llm = _run("I need to confirm my dentist appointment by Friday.",
                            loop_ids=(7, 99))
    assert out["goal"] == "confirm appointment details"
    assert queued
    assert len(llm.licence_calls()) == 1


def test_exactly_one_licence_call_per_tick():
    """One call for the whole set, mirroring the any() the verb list stood in
    for. A per-loop call would put ten frontier calls on a timer nobody asked
    for."""
    _, _, llm = _run("I need to confirm my dentist appointment by Friday.")
    assert len(llm.licence_calls()) == 1


def test_the_clock_never_asks_when_the_model_proposed_no_goal():
    """No goal, nothing to license. The reminder still goes out."""
    out, queued, llm = _run("Remember that my dentist appointment is Friday at 3 PM.",
                            goal=None)
    assert out["goal"] is None
    assert queued == []
    assert llm.licence_calls() == []


# --------------------------------------------------------------------------
# THE FLOOR: anything that is not a positive licence refuses
# --------------------------------------------------------------------------
class _Dead:
    """A model with no credential. clock_tick's own first call would have come
    back as heuristic triage JSON and returned before this point in any real
    deployment — but the polarity is stated and pinned rather than assumed."""
    owner_zone = "America/Vancouver"
    live = False

    def chat(self, system="", user="", **_kw):
        class R:
            text = json.dumps({"initiate": True, "say": "a reminder",
                               "goal": "confirm appointment details",
                               "loop_ids": [7]})
        return R()


class _Unreadable:
    owner_zone = "America/Vancouver"
    live = True

    def __init__(self, text):
        self.text = text

    def chat(self, system="", user="", **_kw):
        body = self.text if "licenses_work" in system else json.dumps(
            {"initiate": True, "say": "a reminder",
             "goal": "confirm appointment details", "loop_ids": [7]})

        class R:
            text = body
        return R()


def _run_with(llm):
    a = Anticipy(memory=Memory("I need to confirm my dentist appointment."),
                 llm=llm, owner_phone=None)
    queued = []
    a._queue_job = lambda goal, params, hold=False, **_k: queued.append(goal) or "job"
    return a.clock_tick(now=2000), queued


def test_no_live_model_means_no_authority_and_the_goal_is_dropped():
    """This is a FLOOR — it asks whether anything licenses preparing work at
    all. A ceiling may treat absence as "no verdict, change nothing"; a floor
    may not, or it lifts itself. The say survives."""
    out, queued = _run_with(_Dead())
    assert out["goal"] is None
    assert queued == []
    assert out["say"]


@pytest.mark.parametrize("text", [
    "not json at all", "{}", '{"licenses_work": null}',
    '{"licenses_work": "yes"}', '{"other_key": true}', "[]",
])
def test_a_reply_we_cannot_read_is_not_a_licence(text):
    out, queued = _run_with(_Unreadable(text))
    assert out["goal"] is None, f"read a licence out of {text!r}"
    assert queued == []
    assert out["say"]


# --------------------------------------------------------------------------
# THE ROOT, TESTED AT THE ROOT — the legs above go through clock_tick, and a
# collapse of the four states inside work_is_licensed would leave them green.
# --------------------------------------------------------------------------
class _LicenceLLM:
    live = True

    def __init__(self, text=None, raises=None):
        self._text, self._raises = text, raises

    def chat(self, *_a, **_k):
        if self._raises:
            raise self._raises

        class R:
            text = self._text
        return R()


def _licence(**kw):
    return work_is_licensed(_LicenceLLM(**kw), ["the VAT return is due Friday"],
                            "prepare the VAT return")


def test_a_licence_call_that_raises_is_unanswered_not_a_no():
    for boom in (TimeoutError("gateway timeout"),
                 RuntimeError("429 rate limited"),
                 ValueError("500 from the provider")):
        assert _licence(raises=boom) == LICENCE_UNANSWERED, \
            f"{boom!r} was recorded as the model saying 'no, not his'"


def test_a_real_answer_is_still_a_real_answer():
    assert _licence(text='{"licenses_work": true}') == LICENCE_YES
    assert _licence(text='{"licenses_work": false}') == LICENCE_NO


def test_nothing_to_ask_is_its_own_state():
    assert work_is_licensed(None, ["a quote"], "a goal") == LICENCE_UNASKED
    assert work_is_licensed(_LicenceLLM(text="{}"), ["a quote"], "") == LICENCE_UNASKED
    assert work_is_licensed(_LicenceLLM(text="{}"), [], "a goal") == LICENCE_UNASKED
    assert work_is_licensed(_LicenceLLM(text="{}"), ["", "   ", None],
                            "a goal") == LICENCE_UNASKED

    class _NeverCalled:
        live = False

        def chat(self, *_a, **_k):
            raise AssertionError("a dead model must never be called")
    assert work_is_licensed(_NeverCalled(), ["a quote"], "g") == LICENCE_UNASKED


def test_the_four_licence_states_are_four_distinct_values():
    """Cheap, and it catches the one-character edit that makes every leg above
    pass while meaning nothing."""
    assert len({LICENCE_YES, LICENCE_NO, LICENCE_UNASKED, LICENCE_UNANSWERED}) == 4


def test_every_quote_reaches_the_model_not_just_the_first():
    """One call, but the whole set in it. Sending only `selected[0]` would
    silently restore "the first loop decides", which is the failure the
    guest-promise wave spent a night on from the other direction."""
    seen = {}

    class _Capture:
        live = True

        def chat(self, system="", user="", **_kw):
            seen["user"] = user

            class R:
                text = '{"licenses_work": true}'
            return R()

    work_is_licensed(_Capture(), ["quote one", "quote two", "quote three"],
                     "some work")
    for quote in ("quote one", "quote two", "quote three"):
        assert quote in seen["user"], f"{quote!r} never reached the model"
    assert "some work" in seen["user"], "the model judged the quotes with no goal"


def test_the_verb_list_is_gone_from_the_tree():
    """Law 2's other half: a violation that was replaced does not get to leave
    a copy behind for the next agent to reach for."""
    import brain.anticipy_core as core
    assert not hasattr(core, "_CLOCK_ACTION_SOURCE_RE")
    src = open(core.__file__, encoding="utf-8").read()
    assert "_CLOCK_ACTION_SOURCE_RE = re.compile" not in src


def test_the_prompt_still_carries_the_key_every_test_double_routes_on():
    """tests/llm_fakes.licence_reply routes on "licenses_work" appearing in the
    system prompt, and every clock double in the suite depends on it. Rewording
    the prompt's reply shape without that substring un-routes all of them at
    once — they would answer the licence question with their canned clock JSON,
    which is unreadable, which refuses, and a dozen legs would go red at a
    distance with nothing pointing here. Cheap to pin, so pin it."""
    from brain.orchestrator import LICENCE_SYSTEM
    assert "licenses_work" in LICENCE_SYSTEM
    assert licence_reply(LICENCE_SYSTEM) == '{"licenses_work": true}'
    assert licence_reply(LICENCE_SYSTEM, False) == '{"licenses_work": false}'
    assert licence_reply("some other prompt entirely") is None


def test_clock_tick_calls_the_real_helper_and_not_a_stale_alias():
    """Every leg above would go green against a shadowed copy."""
    import brain.anticipy_core as core
    import brain.orchestrator as orch
    assert core.work_is_licensed is orch.work_is_licensed
    assert core.LICENCE_YES == orch.LICENCE_YES
