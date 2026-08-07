"""Text read INTO a device is nobody's work.

2026-08-04. Omar was dictating into his laptop. The pendant overheard it. Three
lines became three real jobs on his desk:

    Pill 491 kill 492 kill 493 of your list
    Carson Michael and RV.help23 add that to the KTHAI list
    4546 4748 reply my inbox drive to Toby's email

MEASURED 2026-08-06 against google/gemini-2.5-flash — the model production
actually runs, confirmed with `railway variables --service worker`. Eight runs
per line: all three fired EIGHT TIMES OUT OF EIGHT. On the local deepseek
default they fired 3/8 and 2/8, which is exactly why this survived so long:
every local proof had been run against a more cautious model than his phone
uses.

`looks_like_dictation` misses all three. It wants forty-plus words of fluent
instruction-prose — Wispr Flow into another assistant. These are the opposite
shape: short, garbled, number-dense fragments.

Two things were tried and measured and are NOT what shipped:

  * Asking the model on its own — 11 of 18 silenced, and the KTHAI line 0 of 6,
    because "add that to the list" IS a request. It is just aimed at a machine
    that is already carrying it out.
  * Deciding mechanically — silences "the flight is AC123 landing at 6am" and
    "I need 2x4s and a 10mm bolt", which are real things people say out loud.

What shipped is mechanical evidence handed to the model AS evidence, with the
model still making the call: 24/24 garbage silenced, 119/120 real speech left
alone. These tests pin the wall around that judgement — the judgement itself is
measured live, not here.
"""
import json
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.orchestrator import (READ_ALOUD_SYSTEM, not_speech_evidence,  # noqa: E402
                                read_into_a_machine)

# Verbatim from the events table.
THE_THREE = [
    "Pill 491 kill 492 kill 493 of your list",
    "Carson Michael and RV.help23 add that to the KTHAI list",
    "4546 4748 reply my inbox drive to Toby's email",
]

# Real speech. If any of these is ever silenced the fix is worse than the bug.
REAL_SPEECH = [
    "can you book us dinner at 7 tomorrow at Cactus Club",
    "we should go for dinner tomorrow how's cactus",
    "honestly let's just do Earls, the Brooklyn one for sure, Saturday at one",
    "I have to email Priya the invoice later today",
    "text Priya on 604 555 1234 about the invoice",
    "book a table for 4 at Earls Brooklyn Saturday at 1pm",
    "remind me to renew the car insurance before the twelfth",
    "Hey we should go out for dinner you haven't really shit let's do it but",
    "For lunch tomorrow at four how's cactus in Parker",
    "oh I gotta open that budget spreadsheet and add the August",
    "let's meet at 7pm at the 5th street place",
    "if you don't mind putting that word in with Sakib",
    "put the link to today's recording into the doc and email it to the team",
]


class Fake:
    live = True

    def __init__(self, payload):
        self.payload = payload
        self.asked = []

    def chat(self, system, user, **kw):
        self.asked.append((system, user))
        text = self.payload if isinstance(self.payload, str) \
            else json.dumps(self.payload)
        return types.SimpleNamespace(text=text)


# ------------------------------------------------------- the evidence, pure

def test_all_three_carry_evidence():
    """The whole design rests on this. If a line carries no evidence the model
    is never asked, so a line that fires with no evidence can never be caught.
    All three of the real ones must be visible to the mechanical pass."""
    for line in THE_THREE:
        assert not_speech_evidence(line), line


def test_what_each_of_the_three_is_caught_by():
    a, b, c = (not_speech_evidence(x) for x in THE_THREE)
    assert any("counting upward" in n for n in a), a      # 491, 492, 493
    assert any("not pronounceable" in n for n in b), b    # RV.help23
    assert any("runs of bare numbers" in n for n in c), c  # 4546 4748


def test_ordinary_speech_carries_no_evidence_at_all():
    """Not just 'is judged speech' — never even reaches the model. This is what
    makes the check free on the overwhelming majority of what he says, and what
    makes a model outage a no-op rather than a behaviour change."""
    quiet = [s for s in REAL_SPEECH if not not_speech_evidence(s)]
    assert len(quiet) >= len(REAL_SPEECH) - 2, \
        [(s, not_speech_evidence(s)) for s in REAL_SPEECH if not_speech_evidence(s)]


def test_a_phone_number_read_aloud_is_speech_not_data():
    """Seven, ten or eleven digits is somebody's phone number. Without this,
    'text Priya on 604 555 1234 about the invoice' reads as reference numbers
    being typed into a form — measured, it cost 2 runs in 8."""
    assert not_speech_evidence("text Priya on 604 555 1234 about the invoice") == []
    assert not_speech_evidence("call me on 6047245161") == []
    assert not_speech_evidence("my number is 555 0199") == []
    # Eight digits in two groups is not a phone number anywhere.
    assert not_speech_evidence("4546 4748 reply my inbox")


def test_the_ordinary_ways_speech_fuses_a_number_to_letters():
    for said in ("let's meet at 7pm", "the 5th street place", "give it 20mins",
                 "about 30s of it", "a 10mm bolt", "roughly 5kg", "2 for 1",
                 "the 3rd of August", "it's 40C out there", "100% sure"):
        assert not_speech_evidence(said) == [], said


def test_a_real_identifier_in_real_speech_is_evidence_not_a_verdict():
    """These two DO reach the model — and the model must keep them. Deciding
    mechanically would silence a flight and a trip to the hardware store."""
    for said in ("the flight is AC123 landing at 6am can you check it in",
                 "I need 2x4s and a 10mm bolt can you order them"):
        assert not_speech_evidence(said), said          # evidence exists
        assert not read_into_a_machine(Fake({"speech": True}), said)


def test_counting_is_counting_and_a_few_numbers_are_not():
    assert not_speech_evidence("491 492 493")
    assert not_speech_evidence("items 10 12 14 on the sheet")
    # Real speech with several numbers that are not a sequence.
    assert not any("counting" in n for n in
                   not_speech_evidence("book 4 people at 7 for the 12th"))


def test_evidence_is_bounded_on_a_pathological_line():
    line = " ".join(f"ref{n}" for n in range(200)) + " " + \
           " ".join(str(n) for n in range(300))
    notes = not_speech_evidence(line)
    assert len(notes) <= 3
    assert sum(len(n) for n in notes) < 400


def test_evidence_never_raises():
    for junk in ("", None, "   ", "\n\n", "...", "!!!", "😀😀", "a" * 5000):
        assert isinstance(not_speech_evidence(junk), list)


# ----------------------------------------------------------- the judgement

def test_only_an_explicit_false_ever_silences():
    """Absent, null, the string "false", a number, a wrong type — none of these
    are the model saying "this is data". Treating any of them as a verdict
    would silence real speech whenever a reply came back malformed."""
    line = THE_THREE[0]
    for payload in ({}, {"speech": None}, {"speech": "false"}, {"speech": 0},
                    {"speech": []}, {"why": "no field at all"},
                    {"speech": True}):
        assert read_into_a_machine(Fake(payload), line) is False, payload
    assert read_into_a_machine(Fake({"speech": False}), line) is True


def test_every_failure_leaves_her_exactly_as_she_was():
    """THE HONESTY WALL. A broken check must never take work away. It must
    vanish and behave precisely as she did before this existed."""
    line = THE_THREE[0]
    assert read_into_a_machine(Fake("not json at all"), line) is False
    assert read_into_a_machine(Fake("{ broken "), line) is False
    assert read_into_a_machine(None, line) is False
    assert read_into_a_machine(Fake({"speech": False}), "") is False
    assert read_into_a_machine(Fake({"speech": False}), None) is False

    class Dead:
        live = False

        def chat(self, *a, **k):
            raise AssertionError("must not be called when the model is offline")
    assert read_into_a_machine(Dead(), line) is False

    class Boom:
        live = True

        def chat(self, *a, **k):
            raise RuntimeError("network")
    assert read_into_a_machine(Boom(), line) is False


def test_no_evidence_means_no_model_call_at_all():
    """The cost guarantee AND the safety guarantee in one. An ordinary spoken
    sentence must not pay for a model call, and must not be at the mercy of
    one either."""
    # Counted, NOT raised. An earlier version of this test raised inside chat()
    # — and the honesty wall catches every exception and returns False, so the
    # assertion was swallowed and the test could not fail. A mutation that
    # called the model on every single line sailed straight through it.
    llm = Fake({"speech": False})
    for said in ("can you book us dinner at 7 tomorrow at Cactus Club",
                 "we should go for dinner tomorrow how's cactus",
                 "I have to email Priya the invoice later today",
                 "text Priya on 604 555 1234 about the invoice",
                 "let's meet at 7pm at the 5th street place"):
        assert read_into_a_machine(llm, said) is False, said
    assert llm.asked == [], \
        f"paid for {len(llm.asked)} model calls on plain sentences"


def test_the_evidence_actually_reaches_the_model():
    """The evidence is the entire reason this works — the KTHAI line scored
    0 of 6 without it. If it stops being sent, the check quietly degrades to
    the version that was measured and rejected."""
    llm = Fake({"speech": True})
    read_into_a_machine(llm, THE_THREE[1])
    system, user = llm.asked[0]
    assert system is READ_ALOUD_SYSTEM
    assert "RV.help23" in user
    assert "OBSERVATIONS" in user
    assert THE_THREE[1] in user


def test_it_is_asked_on_its_own_not_bolted_onto_triage():
    """The finding that keeps being re-learned here: a rule buried among eight
    other fields loses every time. This is one question with one job."""
    llm = Fake({"speech": True})
    read_into_a_machine(llm, THE_THREE[0])
    system, _ = llm.asked[0]
    assert '"decision"' not in system, "this must not be the triage prompt"
    assert '"owes"' not in system
    assert '"speech"' in system


def test_the_question_names_both_traps():
    low = " ".join(READ_ALOUD_SYSTEM.split()).lower()
    # The trap that made the KTHAI line score zero.
    assert "aimed at the machine already carrying it out" in low
    # The trap that mechanical-only fell into.
    assert "ac123" in low and "2x4s" in low
    # And which way to fail.
    assert "if you cannot tell, it is speech" in low


# ------------------------------------------------------------- the wiring

def test_it_is_wired_into_the_dictation_gate():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "brain", "anticipy_core.py")).read()
    i = src.index("dictated = not explicit and")
    block = src[i:i + 200]
    assert "looks_like_dictation(line)" in block, \
        "the long-fluent-prose filter must stay — it catches the other shape"
    assert "read_into_a_machine(self.llm, line)" in block, \
        "the short garbled-fragment filter must run too"
    assert " or " in block, "both, not one instead of the other"


def test_an_explicit_line_is_never_treated_as_dictation():
    """When he types or texts it AT her he is plainly talking to her, whatever
    it looks like. `not explicit` must gate both filters, not just the old one."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "brain", "anticipy_core.py")).read()
    i = src.index("dictated = not explicit and")
    block = src[i:i + 200]
    assert block.index("not explicit") < block.index("read_into_a_machine")
