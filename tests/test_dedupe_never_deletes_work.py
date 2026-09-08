"""A guess may delay her. It may never delete his work.

The cancel in `_hear` exists for a real trap: a held card the owner was never
told about, which he could later approve without ever having seen it. Silence
must mean stillness.

But the commonest reason she may not speak is a DEDUPE SCORE — `already_raised`
and `raised_and_ignored` compare the words of two model-phrased goals and
decide they are the same errand. That score cannot be right every time. A
brand-new dinner plan shares most of its words with last week's, and when the
score is wrong the card the owner spoke seconds ago is cancelled and he is
told nothing.

That shape was hit three times live in one day, and each repair exempted the
one kind that had just been bitten:

    ask + a sentence still arriving   -> "defer"   (SPEAK_ONCE)
    ambient_act + quiet hours         -> "defer"   (SPEAK_ONCE)
    ambient_act + no budget left      -> "defer"   (SPEAK_ONCE)
    act + already told him            -> a whole branch (_told_him_before)

Four patches, one rule underneath, and every kind not yet bitten still
exposed. This pins the rule instead of the cases: a refusal that means "she
already said this" is DEDUPED — falsy, so nobody speaks on it, and
identifiable, so the cancel branch can tell a guess from a genuine
never-told card.

The cancel itself is untouched. A card she truly never raised is still
cancelled, for the reason it always was.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.anticipy_core import DEDUPED, Anticipy  # noqa: E402

CORE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "brain", "anticipy_core.py")
WORKER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "brain", "worker.py")


# ------------------------------------------------ the verdict's two properties

def test_deduped_is_falsy_so_no_gate_speaks_on_it():
    """Every gate asks `if verdict:` or `if not verdict:`. DEDUPED must read
    as "do not speak" at every one of them without any of them being edited —
    that is what makes this a rule and not a fifth special case."""
    assert not DEDUPED
    assert bool(DEDUPED) is False
    assert not bool(DEDUPED)


def test_deduped_is_still_identifiable_after_the_bool():
    """Falsy is not enough. If it collapsed to a plain False the cancel
    branch could not tell a dedupe guess from a card he was never told
    about — which is the entire distinction."""
    assert DEDUPED is not False
    assert isinstance(DEDUPED, str)
    assert DEDUPED == "deduped"


# ------------------------------------------- _may_say must not flatten it away

def test_may_say_preserves_deduped_and_defer_and_still_bools_the_rest():
    """_may_say is the one funnel every unprompted line passes through. It
    used to return bool(got) for anything that was not exactly "defer", which
    would throw the sentinel away one call before the branch that needs it."""
    assert Anticipy._may_say(lambda *a: DEDUPED, "t", "g", "act") is DEDUPED
    assert Anticipy._may_say(lambda *a: "defer", "t", "g", "act") == "defer"
    assert Anticipy._may_say(lambda *a: True, "t", "g", "act") is True
    assert Anticipy._may_say(lambda *a: False, "t", "g", "act") is False
    # A guard that is absent means "no gate", which has always meant speak.
    assert Anticipy._may_say(None, "t", "g", "act") is True


def test_a_deduped_verdict_still_reads_as_do_not_speak():
    """The three call sites that only ever asked "may I?" must behave exactly
    as they did. This is the regression that would show up as her speaking
    MORE, which is the opposite of what this change is for."""
    verdict = Anticipy._may_say(lambda *a: DEDUPED, "t", "g", "clock")
    assert not verdict, "a dedupe refusal must never become permission"


# --------------------------------------------------- the branch, and its order

def test_the_dedupe_branch_keeps_the_card_and_precedes_the_cancel():
    src = open(CORE).read()
    assert "say_verdict is DEDUPED" in src, \
        "the cancel chain must be able to see a dedupe guess"
    keep = src.index("say_verdict is DEDUPED")
    cancel = src.index("so it was never his to approve")
    assert keep < cancel, \
        "a dedupe guess must be caught BEFORE the branch that cancels the card"
    branch = src[keep:cancel]
    assert "keeping the card" in branch, \
        "the dedupe branch must keep the card, not merely stay quiet"
    # and the genuine never-told cancel is still there, unweakened
    assert "SILENCE MUST MEAN STILLNESS" in src


def test_the_verdict_is_taken_once_so_the_budget_is_not_spent_twice():
    """_may_say reserves the day's outreach slot. Asking it twice in one pass
    would spend two slots for one message."""
    src = open(CORE).read()
    assert src.count('self._may_say(may_say, handled, decision.goal, "act")') == 1
    taken = src.index('say_verdict = (self._may_say')
    assert "not write_failed and held and not repeat" in src[taken:taken + 400], \
        "the verdict must be taken under exactly the old conditions"


def test_both_dedupe_refusals_return_the_sentinel():
    """Both word-overlap guards, not just the one that was reported."""
    src = open(WORKER).read()
    assert "from .anticipy_core import (DEDUPED" in src
    for guard in ("already_raised(goal, text, decision=",
                  "raised_and_ignored(goal, text)"):
        i = src.index(guard)
        assert "return DEDUPED" in src[i:i + 700], \
            f"the refusal after {guard!r} must be a dedupe verdict, not a bare False"
    # Nothing else changed shape: the budget refusal is still its own word.
    assert 'return True if _hold_uninvited_slot(kind, slot) else "defer"' in src
