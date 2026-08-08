"""She should not talk like a changelog — and TWO attempts to fix that were
measured, failed, and are recorded here so they are not tried a third time.

2026-08-07, Omar, on getting "I'm drafting a post for the listing. Nothing else
goes out until you approve it":

    "the fact that it says 'Nothing goes out until you approve it', that's
     developer stuff, my god"

He is right. The promise is real and worth keeping — she genuinely will not
send without him — but spelling it out is release-note voice, and ending on the
question ("want me to book it?") carries the same promise the way a person does.

WHAT SHIPPED: only the hardcoded fallback in say_handling. It is used solely
when there is no model, so it cannot affect live behaviour — which is exactly
why it is safe, and also why it does not solve the live problem.

WHAT DID NOT SHIP, both measured against second_scenario_proof on the
production model:

  1. Instructing the model in VOICE_SYSTEM to end on the question.
         baseline   6 green / 6
         with it    1 green / 6

  2. Cutting the trailing promise clause off her text mechanically, in _voice.
         scrub unhooked   4 green / 4
         scrub hooked     2 green / 10

  Combined baseline across the whole session: 14 green / 14. With either fix
  in: 2 / 10.

Both failures look identical: triage flips the addressee from "person" to
"self" on nearly every line, so the self-talk rule swallows every question and
no card is ever built — the proof reports "silent card — he was never asked".

I could not find the mechanism. The three prompts are byte-identical with and
without the change (sha256 checked on TRIAGE_SYSTEM, VOICE_SYSTEM and
TEXTING_STYLE), and _voice runs AFTER the addressee has been decided, so there
is no path I can point at. What is not in doubt is the measurement: it
reproduced across interleaved batches in the same minutes, and unhooking the
scrub alone restored 4/4.

So this stays broken on purpose. A cosmetic wording preference is not worth a
fivefold drop in the booking flow, and shipping something I cannot explain is
how the rest of today went wrong.

THE OPEN QUESTION worth someone's time: why does anything downstream of triage
change what triage decides? That coupling is a real defect in its own right and
is almost certainly behind other flakiness in this repo.
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
