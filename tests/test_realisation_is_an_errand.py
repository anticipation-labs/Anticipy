"""A realisation that something was dropped is the errand, not venting.

This is the register the whole product is sold on, and on 2026-08-20 it had no
test at all - which is exactly why it could break in silence. The owner's own
demonstration line went quiet:

    "Oh my goodness, I forgot to cook for my kids this afternoon."
    -> ignore, empty goal, reason "Exclamation of realization with no
       finishable task."

The model was not being stupid; it was obeying the prompt. TRIAGE_SYSTEM taught
the wish/to-do boundary with "I should get to the gym more" and "we should hang
out sometime" - aspirations with no deadline and nothing to complete - and the
model generalised "forgot to cook" into that family. It also listed bare
"venting" as a stay-quiet category, and dismay about a dropped obligation
reads as venting if you only listen to the tone.

Both halves matter, so both are asserted here:
  - a dropped obligation with a live window is work
  - dismay about something you could still fix is not venting

And the precision half is asserted too, because the fix must not turn her into
a nag: a realisation with nothing left to finish must still stay quiet. The MVP
targets 2 or fewer false pings a week, and a system that answers every sigh is
worse than one that misses a dinner.

These are contract assertions on the prompt, deterministic and offline. The
behavioural measurement lives in the ambient corpus, which grades against a
live model; this file exists so the teaching cannot be deleted by accident
between corpus runs.
"""
from brain.orchestrator import TRIAGE_SYSTEM


def _flat(text: str) -> str:
    """The prompt is hard-wrapped prose, so a phrase can be split across a
    newline. Assert on meaning, not on where the wrap fell."""
    return " ".join(text.split()).lower()


def test_a_forgotten_obligation_is_taught_as_an_errand():
    flat = _flat(TRIAGE_SYSTEM)
    assert "a realisation that something was forgotten is an errand" in flat
    # The owner's own line, kept verbatim in the prompt. If someone reworks the
    # examples, this is the one that must survive.
    assert "i forgot to cook for my kids this afternoon" in flat


def test_the_test_is_whether_the_need_is_still_live():
    """Not the tone, not the verb - whether anything remains to be done. This
    is what separates the dinner from "I should get to the gym more"."""
    flat = _flat(TRIAGE_SYSTEM)
    assert "does the need survive the sentence" in flat \
        or "is there something that still has to happen" in flat
    assert "inside a window you can still see" in flat


def test_a_realisation_with_nothing_left_to_finish_stays_quiet():
    """The precision half. Without this the fix becomes a nag."""
    flat = _flat(TRIAGE_SYSTEM)
    assert "if nothing is left to finish, stay quiet" in flat
    assert "birthday last month" in flat


def test_venting_is_qualified_rather_than_a_blanket_stay_quiet():
    """Bare "venting" in the ignore list is what swallowed the dinner. It must
    stay qualified: only venting with nothing to be done about it."""
    flat = _flat(TRIAGE_SYSTEM)
    assert "venting counts only when there is nothing to be done about it" in flat
    assert "frustration aimed at something you could still fix is not venting" in flat


def test_the_aspiration_examples_are_still_there():
    """The fix must not have been made by deleting the boundary it sits beside.
    Those examples are load-bearing: they are why she stays quiet all day."""
    flat = _flat(TRIAGE_SYSTEM)
    for wish in ("i should get to the gym more",
                 "we should hang out sometime",
                 "i need to be better about this"):
        assert wish in flat, wish
    assert "real, finishable act" in flat


def test_the_goal_is_help_rather_than_a_reminder_that_they_forgot():
    """A goal of "remind them they forgot to cook" is technically responsive
    and completely useless. The prompt says what help means here."""
    flat = _flat(TRIAGE_SYSTEM)
    assert "food that arrives in time, not a reminder that they forgot" in flat


# --- the same failure, one layer down: WHOSE job is it -----------------------
#
# The 320-utterance ambient corpus put a number on this. Even with the triage
# teaching above, half of all real errands were still dropped: misses 88/173 =
# 50.9%. Every one of 32 clean-room misses came back owes="nobody", with reasons
# like "Observation about approaching deadline without an actionable errand".
#
# The `owes` rubric defined "owner" as three SPEECH ACTS - he promised, someone
# asked him, he asked you. An overheard realisation performs none of them, so a
# real duty fell to "nobody" and nothing downstream could rescue it. The measured
# signature was grammatical, which is the giveaway that the rule was wrong rather
# than the model: lines containing I/my/me missed 38.9%, impersonal lines 63.9%.
# A 25-point gap on whether the sentence happened to have a subject.


def test_an_obligation_can_reach_her_without_a_speech_act():
    """The fourth route to "owner": a duty that already existed and was merely
    revealed. This is the entire premise of listening all day."""
    flat = _flat(TRIAGE_SYSTEM)
    assert "an obligation he already had" in flat
    assert "a speech act is one way an obligation reaches you" in flat


def test_the_owner_test_is_would_something_still_need_doing():
    """Stated as a test the model can apply, not a category to pattern-match."""
    flat = _flat(TRIAGE_SYSTEM)
    assert "if nobody had spoken at all, would something still need doing" in flat


def test_nobody_means_no_obligation_anywhere():
    """Not "no obligation created by this sentence" - which is what let an
    impersonal statement of a real deadline land in "nobody"."""
    flat = _flat(TRIAGE_SYSTEM)
    assert "no obligation exists anywhere" in flat
    assert "not merely no obligation created by this sentence" in flat


def test_a_fact_in_passing_can_still_name_an_unmet_duty():
    flat = _flat(TRIAGE_SYSTEM)
    assert "a \"fact in passing\" that names something of his still undone" in flat


def test_the_impersonal_examples_are_present():
    """These are the shapes that measured worst - no first-person subject, no
    request, a real duty. They are in the prompt so the rule is legible."""
    flat = _flat(TRIAGE_SYSTEM)
    for line in ("the vat return is due on the seventh",
                 "we're completely out of the good coffee"):
        assert line in flat, line
