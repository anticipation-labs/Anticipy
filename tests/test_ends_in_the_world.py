"""`ends_in_the_world` had no test at all. Not a thin one — none.

    $ grep -rn ends_in_the_world tests/
    (nothing)

It is `party_verdict`'s twin: same signature, same `except: return False`,
the same "only an explicit true escalates" docstring, and it decides whether a
read-only-WORDED goal is actually consequential — whether the owner is asked
before a plan goes ahead, or whether it runs as quiet research and he never
hears about it. `party_verdict` has thirteen legs in
tests/test_memory_knows_who_spoke.py; this one had none, so every property its
docstring claims was an assertion nobody had ever checked.

WHAT MAKES THE ABSENCE EXPENSIVE is the collapse direction. This is one of the
four meaning questions HARNESS-LAW 1 names, and Law 1 is explicit that "whether
the missing state refuses or waves through is decided by which way the check
points". This one collapses QUIET: a timeout, a malformed reply or a dead model
all return False, the plan stays read-only, and the owner never gets the one
text. That is the 2026-08-09 failure its own docstring cites — "the whole plan
went silent" — reachable again through the mechanism built to stop it.

The collapse is deliberate for now: escalating on every transient fault would
interrupt him about prep work, which is the failure the quiet lane exists to
prevent. Whether it SHOULD escalate is an owner ruling
(research/2026-08-24-supersession-fixes.md). What these legs do is make it a
decision somebody made rather than a default nobody could see: every state is
pinned, and each one goes red if it moves.
"""
from __future__ import annotations

import json
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from brain.orchestrator import (WORLD_SYSTEM,  # noqa: E402
                                ends_in_the_world)

LINE = "yeah let's do Cactus Club Thursday, eight-ish, I'll sort it"
GOAL = "plan dinner at Cactus Club on Thursday"


class _LLM:
    """A model that answers the consequence question with `reply`, and every
    other prompt with "{}". Routed on the system prompt, the way llm_fakes
    already does, so a double cannot answer a question it was never asked."""

    def __init__(self, reply, live=True, raises=None):
        self.reply = reply
        self.live = live
        self.raises = raises
        self.asked: list[tuple[str, str]] = []

    def chat(self, system, user, **kw):
        self.asked.append((system, user))
        if self.raises:
            raise self.raises
        return types.SimpleNamespace(text=self.reply)


# ------------------------------------------------------------ the question


def test_the_question_is_asked_on_its_own_with_both_halves():
    """Law 1's shape: ONE question, asked alone, never a ninth key in an
    existing reply. The model needs the line AND the goal — the goal alone is
    the wording that already misled the verb regex, and the line alone says
    nothing about what was extracted from it."""
    llm = _LLM(json.dumps({"ends_in_the_world": True}))
    ends_in_the_world(llm, LINE, GOAL)
    assert len(llm.asked) == 1, llm.asked
    system, user = llm.asked[0]
    assert system == WORLD_SYSTEM
    assert LINE in user and GOAL in user, user


def test_the_prompt_judges_substance_and_says_so():
    """The whole point of taking this off the verb list: a sealed dinner plan
    ends in a reservation whether the task says "book", "plan" or "arrange"
    it. If the prompt ever starts naming verbs, this goes red."""
    flat = " ".join(WORLD_SYSTEM.split())
    assert "never on the verb" in flat, flat
    assert "SUBSTANCE" in flat, flat


# ------------------------------------------------------------ the four states


def test_an_explicit_true_escalates():
    assert ends_in_the_world(
        _LLM(json.dumps({"ends_in_the_world": True})), LINE, GOAL) is True


def test_an_explicit_false_does_not():
    assert ends_in_the_world(
        _LLM(json.dumps({"ends_in_the_world": False})), LINE, GOAL) is False


def test_a_dead_model_is_never_asked_and_never_escalates():
    """UNASKED. `live` is False, so there is nothing to read and no call to
    pay for. Asserted on the call count too: a question asked of a model that
    cannot answer is a bill with no verdict attached."""
    llm = _LLM(json.dumps({"ends_in_the_world": True}), live=False)
    assert ends_in_the_world(llm, LINE, GOAL) is False
    assert llm.asked == []


def test_no_goal_is_nothing_to_ask_about():
    llm = _LLM(json.dumps({"ends_in_the_world": True}))
    assert ends_in_the_world(llm, LINE, "") is False
    assert llm.asked == []


def test_a_call_that_raises_does_not_escalate_and_says_so(capsys):
    """UNANSWERED, and THE ONE THAT COSTS SOMETHING. A live model was asked
    and nothing readable came back: nothing about the world was learned, and
    the plan stays quiet — the owner never gets the text. That is the recorded
    2026-08-09 shape arriving through the mechanism built to stop it, so it
    must at least be VISIBLE. It was swallowed silently, which made a model
    that timed out every night look exactly like one answering "no"."""
    llm = _LLM("", raises=TimeoutError("read timed out"))
    assert ends_in_the_world(llm, LINE, GOAL) is False
    assert llm.asked, "the question was never actually put"
    out = capsys.readouterr().out
    assert "unanswered" in out, out
    assert GOAL in out, out


def test_a_reply_that_is_not_json_does_not_escalate_and_says_so(capsys):
    llm = _LLM("I think so, yes!")
    assert ends_in_the_world(llm, LINE, GOAL) is False
    assert "unanswered" in capsys.readouterr().out


def test_a_live_model_that_answered_a_different_question_says_so(capsys):
    """A reply without the key is not a "no" — it is a model that answered
    something else, which is what a prompt revision nobody here has seen looks
    like. Same treatment as the timeout, and it says which one it was."""
    llm = _LLM(json.dumps({"consequential": True}))
    assert ends_in_the_world(llm, LINE, GOAL) is False
    out = capsys.readouterr().out
    assert "unreadable" in out, out


def test_only_a_real_boolean_true_counts():
    """"true", 1 and "yes" are a model improvising a shape this code does not
    know. `is True`, not truthiness — the same wall _fact_kind and
    _speaker_verdict hold."""
    for value in ("true", 1, "yes", [True], {"ok": True}):
        assert ends_in_the_world(
            _LLM(json.dumps({"ends_in_the_world": value})),
            LINE, GOAL) is False, value


def test_a_null_answer_is_a_no_not_a_crash():
    assert ends_in_the_world(
        _LLM(json.dumps({"ends_in_the_world": None})), LINE, GOAL) is False


# ------------------------------------------------------------- the call site


def test_the_ambient_lane_calls_the_real_question_not_a_stale_alias():
    """The legs below script `core.ends_in_the_world`. If the ambient lane
    ever called something else — a stale import, a renamed sibling — every one
    of them would go green while testing nothing at all."""
    import brain.anticipy_core as core
    import brain.orchestrator as orch
    assert core.ends_in_the_world is orch.ends_in_the_world


def _ambient_run(monkeypatch, verdict):
    """The real ambient path, with triage's answer scripted: a plan made out
    loud with another person, worded read-only ("plan"), declared read-only by
    the model. Everything upstream of the consequence question is fixed, so
    the only variable is what the question answers."""
    import brain.anticipy_core as core
    from brain.memory import Memory
    from brain.orchestrator import Decision

    asked = []

    def _spy(llm, line, goal):
        asked.append((line, goal))
        return verdict

    monkeypatch.setattr(core, "ends_in_the_world", _spy)
    a = core.Anticipy(memory=Memory(":memory:"), llm=None, owner_id="t")
    queued = {}

    def fake_queue(goal, params, hold=False, **kw):
        queued["goal"], queued["hold"] = goal, hold
        return "job-1"

    a._queue_job = fake_queue
    a._backed_by_a_card = lambda *_a, **_k: True
    a.notify_owner = lambda *_a, **_k: {"ok": True}
    a._decide = lambda *_a, **_k: Decision(
        decision="act", goal=GOAL, reason="a sealed plan",
        addressee="person", owes="owner", touches="read",
        needs_confirmation=False)
    a.hear(LINE)
    return asked, queued


def test_the_verdict_reaches_the_decision_that_spends_it(monkeypatch):
    """The value being correct and simply never arriving is this repo's
    recorded failure shape (8849df15), so the verdict is followed to where it
    is spent. `consequential` decides whether the work is HELD for his yes
    with one text asking for the go-ahead, or queued unheld as quiet research
    he never hears about — which is the 2026-08-09 failure exactly."""
    asked, queued = _ambient_run(monkeypatch, True)
    assert asked == [(LINE, GOAL)], asked
    assert queued.get("goal") == GOAL, \
        f"the plan never reached the queue at all: {queued!r}"
    assert queued.get("hold") is True, \
        ("a plan the model called consequential was queued UNHELD — it runs "
         "as quiet research and the owner never gets the text")


def test_a_no_leaves_genuine_research_quiet(monkeypatch):
    """The other half, and the reason the question exists rather than a
    blanket escalation: research that only ever reads stays quiet, exactly as
    it did before this question existed. She never interrupts his conversation
    to ask about prep work."""
    asked, queued = _ambient_run(monkeypatch, False)
    assert asked == [(LINE, GOAL)], asked
    assert queued.get("hold") is False, queued
