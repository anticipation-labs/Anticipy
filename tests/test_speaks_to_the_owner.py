"""She talked ABOUT her owner, TO her owner.

Live session, 2026-08-21, single-owner account whose profile first_name is
set. He said, disfluently, exactly this:

    "prescription. need to. the repeat one, it runs out"

and she texted HIM:

    i can get that repeat prescription going for Alex; which one is it, and
    what pharmacy does he use?

"for Alex", "does he use" — the person she was writing to, discussed in the
third person as if the errand were somebody else's. The same session, on an
errand with no name attached, was correct:

    i'm holding a draft email to the accountant for the receipts; which
    accountant is that, and which receipts should i attach?

So the NAME was the trigger, not the phrasing. Every prompt in the tree says
what he needs and none of them said he was the one READING it: the composer is
handed the line it heard, the goal and the missing details, and the owner's own
first name arrives inside that payload — in a goal like "renew Alex's repeat
prescription", built from the memory fact "Their name is Alex" — indis-
tinguishable from a third party's. Given a name and no addressee, the model
picks the reading that is wrong.

brain/llm.py:who_line() is the one sentence that closes it, in the same place
and for the same reason as where_line(): grounding belongs at the client so no
caller can forget it. It says nothing at all until a first name is known, so an
account without one sends byte-identical prompts to before.

THE CARVE-OUT IS HALF THE FIX. "send Priya the invoice" must still name Priya
and still call her "her" — a blanket ban on the third person would break the
errands this product exists for, which is what
test_a_real_third_party_is_still_named_and_still_a_she pins.
"""
import os
import re
import sys
from json import loads as _loads

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.anticipy_core import Anticipy  # noqa: E402
from brain.llm import LLM, now_line, where_line, who_line  # noqa: E402

OWNER = "Alex"

# Verbatim from the live session.
THE_LINE = "prescription. need to. the repeat one, it runs out"

# What the composer is actually handed. The name rides in on the GOAL, which is
# how it reached the text — the composer is never told whose name it is.
OWNER_ERRAND = {
    "situation": "one essential detail is missing before you can start",
    "heard": THE_LINE,
    "goal": f"renew {OWNER}'s repeat prescription",
    "missing": ["which prescription", "which pharmacy"],
}

THIRD_PARTY_ERRAND = {
    "situation": "held for approval",
    "heard": "i never sent Priya that invoice",
    "goal": "email Priya the August invoice",
}

# Third-person reference to a PERSON. "the" and "that" are fine; a bare pronoun
# standing in for the reader is not.
_THIRD_PERSON = re.compile(r"\b(he|him|his|she|her|hers)\b", re.IGNORECASE)


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+|\n", text) if s.strip()]


def _knows_who_it_is_writing_to(system: str, name: str) -> bool:
    """Does the prompt bind this name to the person reading the message?

    Not merely "does the name appear" — it has to appear in the same breath as
    the second person, which is the entire content of the fix.
    """
    return any(name in s and "you" in s.lower() for s in _sentences(system))


def _still_allows_naming_other_people(system: str) -> bool:
    """A third-person rule is only safe if it exempts actual third parties."""
    low = system.lower()
    forbids = "never as a third person" in low
    exempts = "anyone else" in low and "third party" in low
    return exempts or not forbids


class _Reply:
    def __init__(self, text: str):
        self._text = text

    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": self._text}}], "usage": {}}


class _Composer:
    """The model at the compose step, standing in offline.

    Not a language model: it reads the system message for the two things this
    fix is about — whether the prompt says who is reading the text, and whether
    it still permits naming other people — and returns whichever sentence that
    prompt licenses. The owner-errand miss is the live text, verbatim.
    """

    def __init__(self):
        self.systems: list[str] = []
        self.users: list[str] = []

    # Stands in for the httpx.Client CLASS: called, then used as a context
    # manager, exactly as brain/llm.py does it.
    def __call__(self, *_a, **_kw):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def post(self, _url, headers=None, json=None):  # noqa: A002 - OpenRouter's kwarg
        payload = json
        system = payload["messages"][0]["content"]
        if not isinstance(system, str):
            system = "\n".join(block["text"] for block in system)
        self.systems.append(system)
        self.users.append(payload["messages"][1]["content"])
        return _Reply(self._say(system, _loads(self.users[-1])))

    def _say(self, system: str, context: dict) -> str:
        if "Priya" in (context.get("goal") or ""):
            if _still_allows_naming_other_people(system):
                return ("i've got the email to Priya ready with the August "
                        "invoice — want me to send it to her?")
            # A prompt that banned the third person outright leaves her
            # unnameable, which is a different bug of the same size.
            return "i've got that invoice email ready — want me to send it?"
        if _knows_who_it_is_writing_to(system, OWNER):
            return ("i can get that repeat prescription going — which one is "
                    "it, and what pharmacy do you use?")
        return (f"i can get that repeat prescription going for {OWNER}; "
                f"which one is it, and what pharmacy does he use?")


def _compose(monkeypatch, context: dict, first_name):
    """What she actually texts, through the real client and the real prompt."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    composer = _Composer()
    monkeypatch.setattr("brain.llm.httpx.Client", composer)
    llm = LLM(owner_zone="America/Vancouver", owner_name=first_name)
    return Anticipy(llm=llm)._voice(context), composer


def test_the_owners_own_errand_is_addressed_to_him(monkeypatch):
    """The live defect. His prescription is HIS, and he is the reader."""
    said, _ = _compose(monkeypatch, OWNER_ERRAND, OWNER)
    assert said
    assert not _THIRD_PERSON.search(said), \
        f"talking about the owner in the third person, to the owner: {said!r}"
    assert f"for {OWNER}" not in said, \
        f"his own errand handed to him as somebody else's: {said!r}"
    # Greeting him by name stays fine and normal; using the name as the
    # BENEFICIARY of his own task is the defect, so the assertions are on the
    # shape rather than on the name appearing at all.
    assert "you" in said.lower(), f"nobody is being spoken to: {said!r}"


def test_a_real_third_party_is_still_named_and_still_a_she(monkeypatch):
    """The errand this product exists for. Priya is not the reader."""
    said, _ = _compose(monkeypatch, THIRD_PARTY_ERRAND, OWNER)
    assert said
    assert "Priya" in said, f"the person the errand is FOR went missing: {said!r}"
    assert _THIRD_PERSON.search(said), \
        f"a real third party must still be referred to normally: {said!r}"


def test_the_sentence_reaches_the_compose_prompt(monkeypatch):
    _, composer = _compose(monkeypatch, OWNER_ERRAND, OWNER)
    system = composer.systems[-1]
    assert who_line(OWNER) in system
    # And it does not displace the grounding that was already there.
    assert where_line("America/Vancouver") in system
    assert "Right now it is" in system


def test_the_composer_is_shown_the_errand(monkeypatch):
    """Guarding the guard: a passing third-person assertion must not be an
    artifact of a prompt with nothing in it."""
    said, composer = _compose(monkeypatch, OWNER_ERRAND, OWNER)
    assert THE_LINE in composer.users[-1]
    assert "prescription" in said


def test_an_account_with_no_name_is_untouched(monkeypatch):
    """Byte-identical prompts for anyone who has not told her their name — the
    fix must not cost the accounts it cannot help."""
    assert who_line(None) == ""
    assert who_line("   ") == ""
    _, composer = _compose(monkeypatch, OWNER_ERRAND, None)
    assert composer.systems[-1].startswith(
        f"{where_line('America/Vancouver')}\n{now_line('America/Vancouver')}")


def test_the_line_is_one_short_sentence():
    """It rides on every call, including the cheap mechanical ones."""
    line = who_line(OWNER)
    assert line.count(".") == 1, line
    assert len(line) < 260, len(line)


def test_it_binds_the_name_to_the_second_person_and_spares_everyone_else():
    line = who_line("Jose")
    assert _knows_who_it_is_writing_to(line, "Jose"), line
    assert _still_allows_naming_other_people(line), line


def test_only_the_first_name_is_used():
    """The profile column carries whatever onboarding typed into the box."""
    assert who_line("Alex Rivera") == who_line(OWNER)
    assert who_line(" Alex ") == who_line(OWNER)
