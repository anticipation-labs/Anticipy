"""Live 2026-08-17, the Vestor demo. She asked which Earls location. He said
"Just do West Bend I told you this" OUT LOUD, twice. Both lines were filed
`ignore`. She asked again. The booking died while he was answering it.

A TEXTED answer has always reached a parked job. A SPOKEN one never could:
hear() did not look at blocked work at all, so every spoken reply to her own
question went to triage, matched no goal, and was filed as ambient chatter.
On a product whose whole premise is a pendant, that was the worst gap in it.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import brain.anticipy_core as coremod  # noqa: E402
from brain.anticipy_core import Anticipy  # noqa: E402
from brain.memory import Memory  # noqa: E402


def _recent():
    return (datetime.now(timezone.utc) - timedelta(minutes=2)
            ).strftime("%Y-%m-%d %H:%M:%S")


class FakeConvo:
    """Only what the router touches, so the test pins the ROUTING."""

    def __init__(self, blocked):
        self._b = blocked
        self.amended = []

    def _blocked(self):
        return self._b

    def _remember_about_owner(self, text):
        return {"location": "West Van"} if "west" in text.lower() else {}

    @staticmethod
    def _answers_need(learned, need):
        return any(k in (need or "").lower() for k in learned)

    @staticmethod
    def _disputes_or_directs(text, need):
        from brain.conversation import Conversation
        return Conversation._disputes_or_directs(text, need)

    def _amend(self, job_id, changes, owner_text=""):
        self.amended.append((job_id, changes, owner_text))
        return f"resumed:{job_id}"


def _core(convo):
    a = Anticipy(memory=Memory(":memory:"), llm=None, owner_id="t")
    a.conversation = convo
    return a


PARKED = [{"id": "j-earls", "goal": "Book Earls for lunch tomorrow",
           "result": "which location works best for you?",
           "params": "{}", "updated": _recent()}]


def test_the_spoken_answer_reaches_the_job_that_asked():
    convo = FakeConvo(list(PARKED))
    out = _core(convo)._spoken_answer_to_parked_work(
        "Just do West Van I told you this")
    assert out is not None, "his spoken answer must land"
    assert out["decision"].decision == "answer"
    assert convo.amended and convo.amended[0][0] == "j-earls"
    assert "West Van" in convo.amended[0][2]


def test_ambient_chatter_still_goes_to_triage():
    convo = FakeConvo(list(PARKED))
    for line in ("Put the TV on", "Mom I'm in a meeting", "Good morning"):
        assert _core(convo)._spoken_answer_to_parked_work(line) is None, line
    assert not convo.amended


def test_two_parked_jobs_are_never_guessed_between():
    """Stamping his answer onto the wrong errand is its own harm."""
    two = PARKED + [{"id": "j-other", "goal": "Book a haircut",
                     "result": "which location works best for you?",
                     "params": "{}", "updated": _recent()}]
    convo = FakeConvo(two)
    assert _core(convo)._spoken_answer_to_parked_work("West Van") is None
    assert not convo.amended


def test_a_question_asked_hours_ago_is_not_answered_by_a_passing_remark():
    stale = [dict(PARKED[0],
                  updated=(datetime.now(timezone.utc) - timedelta(hours=3)
                           ).strftime("%Y-%m-%d %H:%M:%S"))]
    convo = FakeConvo(stale)
    assert _core(convo)._spoken_answer_to_parked_work(
        "Just do West Van") is None


def test_disputing_the_premise_also_lands():
    """The CAPTCHA lesson: "there's no captcha, press submit" is an answer."""
    parked = [dict(PARKED[0], result="solve the CAPTCHA on the screen")]
    convo = FakeConvo(parked)
    out = _core(convo)._spoken_answer_to_parked_work(
        "there's no captcha just press submit")
    assert out is not None and convo.amended


def test_nothing_happens_without_a_conversation_lane():
    a = Anticipy(memory=Memory(":memory:"), llm=None, owner_id="t")
    a.conversation = None
    assert a._spoken_answer_to_parked_work("West Van") is None


def test_hear_consults_parked_work_before_triage():
    src = (os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "brain", "anticipy_core.py"))
    body = open(src).read()
    hear = body[body.index("def hear("):]
    assert "_spoken_answer_to_parked_work" in hear[:9000], (
        "the check must run inside hear, before triage decides")
    # ...and never for dictation or a line he typed at her (the SMS lane
    # already delivers those itself).
    call = hear[hear.index("_spoken_answer_to_parked_work") - 200:
                hear.index("_spoken_answer_to_parked_work") + 80]
    assert "not explicit" in call and "not dictated" in call


# ------------------------------- a card he already knows about survives

def test_a_repeat_request_is_not_punished_by_cancelling_his_card():
    """Live 2026-08-17, the demo: every retry of the same Earls booking came
    back cancelled — "she was not allowed to raise this, so it was never his
    to approve". Ten out of ten, silently.

    The cancel exists for a card he was NEVER told about, which would be a
    trap. But the commonest reason she may not speak is that she ALREADY
    told him — and then he knows, so killing the card punishes him for
    asking twice.
    """
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "brain", "anticipy_core.py")).read()
    assert "def _told_him_before" in src
    branch = src.split("elif held and not explicit and self._told_him_before")[1][:1400]
    assert "keeping the" in branch and "staying quiet" in branch
    # the cancel still exists for the genuinely-untold case
    assert "so it was never his to approve" in src
    # and it may only be reached AFTER the already-told branch
    told = src.index("_told_him_before(decision.goal)")
    cancel = src.index("so it was never his to approve")
    assert told < cancel, "already-told must be checked before cancelling"


def test_only_a_delivered_message_counts_as_having_told_him():
    """A composed-but-unsent message must never buy silence — that mistake
    cost him ten hours on 2026-08-16."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "brain", "anticipy_core.py")).read()
    body = src.split("def _told_him_before", 1)[1][:1400]
    assert 'kind="anticipy_says"' in body, "read the durable record"
    assert "owner_ref" in body, "scoped to this account"
