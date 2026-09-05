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


# The shape _blocked ACTUALLY returns. Inventing this is what let the
# router ship dead: it read a "result" key nobody produces, and these tests
# passed 9/9 against the invention.
PARKED = [{"id": "j-earls", "goal": "Book Earls for lunch tomorrow",
           "needs": "which location works best for you?",
           "remembered_need": "", "updated": _recent()}]


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
    parked = [dict(PARKED[0], needs="solve the CAPTCHA on the screen")]
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
    # hear() is the budget wrapper since Omi port 06 (2026-09-05); the hearing
    # body — where this check must sit, before triage — is _hear().
    hear = body[body.index("def _hear("):]
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


# ----------------------------------------- the contract, not a fake of it

def test_the_router_reads_the_keys_blocked_actually_returns():
    """This is the test that was missing, and its absence cost a demo.

    _spoken_answer_to_parked_work read job["result"]. _blocked() has never
    produced that key — it returns id/goal/needs/remembered_need/updated —
    so the router bailed before looking at his words, every time, while the
    suite above passed 9/9 against a fake whose shape had been invented.

    Compare the producer and the consumer directly. A rename on either side
    fails here instead of going quiet in production.
    """
    import inspect
    from brain.conversation import Conversation
    from brain.anticipy_core import Anticipy

    produced = inspect.getsource(Conversation._blocked)
    consumed = inspect.getsource(Anticipy._spoken_answer_to_parked_work)

    for key in ("needs", "updated"):
        assert f'"{key}"' in produced, f"_blocked must still return {key}"
        assert f'job.get("{key}")' in consumed, f"the router must read {key}"
    assert 'job.get("result")' not in consumed, (
        "result is the runner's scratch field and is not in this contract")


def test_a_real_blocked_row_flows_through_untouched(monkeypatch):
    """End to end on the REAL _blocked output, built from a real job row."""
    import brain.conversation as convmod
    from brain.conversation import Conversation
    from brain.anticipy_core import Anticipy
    from brain.memory import Memory

    row = {"id": "j-real", "goal": "Book Earls for lunch tomorrow",
           "result": "which location works best for you?",
           "params": json.dumps({}), "status": "needs_user",
           "updated": _recent()}

    class R:
        ok = True
        def json(self): return {"items": [row]}

    monkeypatch.setattr(convmod, "pb", type("PB", (), {
        "get": staticmethod(lambda *a, **k: R()),
        "patch": staticmethod(lambda *a, **k: R())}))

    a = Anticipy(memory=Memory(":memory:"), llm=None, owner_id="t")
    convo = Conversation(a, llm=None)
    a.conversation = convo
    blocked = convo._blocked()
    assert blocked and blocked[0]["needs"], "the real row must carry a need"
    assert blocked[0]["updated"], "and a timestamp"

    monkeypatch.setattr(Conversation, "_remember_about_owner",
                        lambda self, tx: {"location": "West Van"})
    monkeypatch.setattr(Conversation, "_amend",
                        lambda self, jid, ch, owner_text="": f"resumed:{jid}")
    out = a._spoken_answer_to_parked_work("Just do West Van I told you this")
    assert out is not None, "his spoken answer must reach a REAL parked row"
    assert out["decision"].decision == "answer"
