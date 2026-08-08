"""She should not talk like a changelog — two attempts, and a correction to
the measurement that condemned them.

2026-08-07, Omar, on getting "I'm drafting a post for the listing. Nothing else
goes out until you approve it":

    "the fact that it says 'Nothing goes out until you approve it', that's
     developer stuff, my god"

He is right. The promise is real — she genuinely will not send without him —
but spelling it out is release-note voice. Ending on the question carries the
same promise the way a person does.

WHAT SHIPPED: only the say_handling fallback, which runs when there is no
model. Safe, and for the same reason it does not fix the live phrasing.

WHAT DID NOT, AND WHY THE REASON CHANGED. Two attempts were measured against
second_scenario_proof on the production model:

  1. Telling the model in VOICE_SYSTEM to end on the question
         6 green / 6 without   ->   1 / 6 with
  2. Cutting the trailing promise clause off her text inside _voice
         4 green / 4 without   ->   2 / 10 with

Both "failures" look identical: triage flips the addressee to "self" on nearly
every line, every question is swallowed, and no card is built.

THEN, WITH NEITHER FIX PRESENT, the same proof failed the same way again —
7 self / 1 person, in batches that otherwise ran green. So the Earls proof has
an INTRINSIC all-self failure mode, roughly one run in four, and the failures
are BATCH-CORRELATED: a whole parallel batch goes red together, then a whole
batch goes green. That is upstream model or routing state moving over minutes,
not anything in this repo.

Which means the attribution above is probably WRONG. 6/6 against 1/6 reads as
decisive, but batch-correlated noise makes parallel runs a far smaller
effective sample than the count suggests, and the "baselines" were partly luck.

So, honestly: neither fix is proven harmful and neither is proven safe. They
stay out because a cosmetic preference does not justify re-litigating this
against a wall that cannot tell a 25% flake from a regression.

THE REAL WORK THIS EXPOSED, and it is worth more than the wording: make
second_scenario_proof trustworthy — best-of-N, or a fixed seed, or score a rate
instead of pass/fail. Until then small changes cannot be judged by it at all,
and every future fix runs the risk of being blamed or excused by a coin flip.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.anticipy_core import VOICE_SYSTEM, Anticipy  # noqa: E402
from brain.memory import Memory  # noqa: E402


class DeadMemory(Memory):
    def __init__(self):
        pass


def _her():
    return Anticipy(memory=DeadMemory(), owner_id="voice")


RELEASE_NOTE = (
    "nothing goes out until",
    "nothing else goes out",
    "until you approve",
    "until you give the word",
)


def test_the_no_model_fallback_does_not_read_like_a_release_note():
    said = _her().say_handling("draft email to Priya with deck attached", True)
    low = said.lower()
    for phrase in RELEASE_NOTE:
        assert phrase not in low, f"{phrase!r} is still in: {said!r}"


def test_the_fallback_still_asks_rather_than_announces():
    """Dropping the promise entirely would be worse than clumsy wording — he
    must still be the one who decides."""
    said = _her().say_handling("draft email to Priya with deck attached", True)
    assert "?" in said, f"a held plan must ASK: {said!r}"


def test_quiet_work_is_unchanged():
    said = _her().say_handling("look up flight times", False)
    assert said.startswith("On it:")
    assert "?" not in said, "quiet work does not need his permission"


def test_the_goal_survives_into_the_sentence():
    assert "book dinner at Cactus Club" in \
        _her().say_handling("book dinner at Cactus Club", True)


def test_junk_never_produces_a_broken_sentence():
    for goal in ("", "   ", "_", "a" * 400):
        said = _her().say_handling(goal, True)
        assert isinstance(said, str) and said.strip()


# ------------------------------------------- the two fixes that must not
# ------------------------------------------- be re-attempted blind

def test_the_prompt_was_deliberately_left_alone():
    """Measured at 1 green / 6 versus a 6 / 6 baseline. If someone re-adds it,
    this fails and points them at the numbers in this file's docstring."""
    low = " ".join(VOICE_SYSTEM.split()).lower()
    assert "end on the question" not in low, (
        "instructing the model here was measured at 1/6 green on the Earls "
        "proof against 6/6 without it — re-read this file before retrying")
    # The original instruction stays exactly as it was.
    assert "nothing goes out until they give the word" in low


def test_the_mechanical_scrub_is_not_wired_in():
    """Measured at 2 green / 10 versus 4 / 4 with it unhooked. Removed rather
    than left as dead code, so nothing can quietly re-enable it."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "brain", "anticipy_core.py")).read()
    assert "_strip_release_note" not in src, (
        "the scrub cost the Earls proof 8 of 10 runs — re-read this file's "
        "docstring before wiring it back in")
