"""One answer, one path, whichever channel it came in on.

docs ex 120 forbids a second path to a decision this one already owns, and the
2026-08-02 two-blocked-tasks bug is what that costs: an answer arrived, resolved
nothing, and both tasks stayed stuck while she kept saying "I'll finish the
booking now." Conversation._resume_stuck is the ONE resolution, so an in-app
answer box must reach it rather than reimplement it.

These drive brain.worker.handle_inbound directly -- the function main() calls --
so nothing here is a re-typed copy of the loop.
"""
from __future__ import annotations

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import worker as W  # noqa: E402

OWNER_PHONE = "+16047245161"
OWNER_REF = "ref_abc123"


class Recorder:
    """A stand-in Conversation that records rather than sends.

    reply_in_app() is the real contract copied honestly: it is a context manager
    that suppresses the outbound text for the duration of the turn.
    """

    def __init__(self, raises: BaseException | None = None):
        self.raises = raises
        self.keys: list[str] = []       # conversation key per on_reply
        self.texted: list[tuple[str, str]] = []
        self.suppressed = False
        self.suppressed_during: list[bool] = []

    def reply_in_app(self):
        import contextlib

        @contextlib.contextmanager
        def cm():
            prev = self.suppressed
            self.suppressed = True
            try:
                yield
            finally:
                self.suppressed = prev
        return cm()

    def on_reply(self, phone, text):
        self.keys.append(phone)
        self.suppressed_during.append(self.suppressed)
        if self.raises:
            raise self.raises
        return {"intent": "confirm", "reply": "On it."}

    def say(self, phone, body):
        # A real Conversation.say() skips the transport while suppressed; this
        # models the observable half -- what actually reached his phone.
        if not self.suppressed:
            self.texted.append((phone, body))


@pytest.fixture
def wired(monkeypatch):
    """Capture every side effect handle_inbound has on the world."""
    seen = {"marks": [], "events": [], "claims": []}

    monkeypatch.setattr(W, "mark_processed",
                        lambda eid, decision, **kw: seen["marks"].append((eid, decision)) or True)
    monkeypatch.setattr(W, "claim",
                        lambda eid: seen["claims"].append(eid) or True)
    monkeypatch.setattr(W, "post_event",
                        lambda kind, text, **kw: seen["events"].append((kind, text)))
    return seen


def anticipy(phone=OWNER_PHONE, ref=OWNER_REF):
    return types.SimpleNamespace(
        owner_phone=phone, owner_ref=ref, owner_id="legacy",
        _voice=lambda ctx: "That one got away from me — say it again?")


def app_row(text="7pm works", ref=OWNER_REF):
    # What the phone writes. No phone number: guard.pb.js pins owner_ref to the
    # signed-in account, which is the identity.
    return {"id": "e_app", "kind": "app_reply", "text": text, "goal": "",
            "owner_ref": ref}


def sms_row(text="7pm works", frm=OWNER_PHONE):
    return {"id": "e_sms", "kind": "sms_reply", "text": text, "goal": frm,
            "owner_ref": OWNER_REF}


# --------------------------------------------------------------- one path

def test_an_app_answer_reaches_the_same_on_reply(wired):
    convo = Recorder()
    assert W.handle_inbound(app_row(), convo, anticipy()) == "confirm"
    assert len(convo.keys) == 1, "the app answer never reached on_reply"


def test_both_channels_land_in_one_conversation(wired):
    # The heart of docs leg 2. If the app used its own key, answering in the app
    # would open a second thread and she would lose the thread of what was said.
    convo = Recorder()
    W.handle_inbound(sms_row(), convo, anticipy())
    W.handle_inbound(app_row(), convo, anticipy())
    assert convo.keys[0] == convo.keys[1] == OWNER_PHONE


def test_an_owner_with_no_phone_can_still_answer(wired):
    # The reason same_phone() cannot be the gate for the app: a fresh account
    # has no number, and refusing his answer would make the card unanswerable.
    convo = Recorder()
    assert W.handle_inbound(app_row(), convo, anticipy(phone="")) == "confirm"
    assert convo.keys == [f"app:{OWNER_REF}"]


# ------------------------------------------------- the reply goes back right

def test_an_app_answer_is_not_texted_back(wired):
    convo = Recorder()
    W.handle_inbound(app_row(), convo, anticipy())
    assert convo.texted == [], "typing in the app got him a text back"
    assert ("anticipy_text", "On it.") in wired["events"], \
        "the app has nothing to render as her reply"


def test_the_suppression_is_active_during_the_turn(wired):
    # Wrapping the call but suppressing nothing would still pass the assertion
    # above if on_reply happened not to speak. Pin the state at the moment it is
    # meant to hold.
    convo = Recorder()
    W.handle_inbound(app_row(), convo, anticipy())
    assert convo.suppressed_during == [True]
    assert convo.suppressed is False, "suppression leaked past the turn"


def test_a_texted_answer_is_still_texted_back(wired):
    convo = Recorder()
    W.handle_inbound(sms_row(), convo, anticipy())
    assert convo.suppressed_during == [False]


# ------------------------------------------------------------ the gate holds

def test_a_stranger_texting_yes_is_still_refused(wired):
    # The check that stops a wrong number releasing a held job into his browser.
    convo = Recorder()
    got = W.handle_inbound(sms_row(frm="+15550009999"), convo, anticipy())
    assert got == "ignored_nonowner"
    assert convo.keys == [], "a stranger's text reached her reasoning"
    assert wired["claims"] == [], "a stranger's text was claimed"


def test_the_app_lane_does_not_become_a_way_around_the_phone_check(wired):
    # An sms_reply row must not be able to claim in-app trust by carrying the
    # app's shape; the kind is what selects the gate, and it is set by the hook.
    convo = Recorder()
    row = sms_row(frm="+15550009999")
    row["goal"] = ""          # looks phone-less, like an app row
    assert W.handle_inbound(row, convo, anticipy()) == "confirm"
    # goal="" falls back to the owner's own number, so this is the owner's own
    # lane -- NOT a stranger admitted. Pin that it did not use the app key.
    assert convo.keys == [OWNER_PHONE]


def test_an_empty_answer_is_dropped_not_reasoned_about(wired):
    convo = Recorder()
    assert W.handle_inbound(app_row(text="   "), convo, anticipy()) == "ignore"
    assert convo.keys == []


def test_an_unclaimable_event_is_left_for_the_next_pass(wired, monkeypatch):
    # Two workers, one row. Losing the claim must not mean answering twice.
    monkeypatch.setattr(W, "claim", lambda eid: False)
    convo = Recorder()
    assert W.handle_inbound(app_row(), convo, anticipy()) == "unclaimed"
    assert convo.keys == []


# ------------------------------------------------------- never silent, in app

def test_a_crash_still_answers_him_in_the_app(wired):
    # 2026-08-01: two messages hit an exception and vanished permanently,
    # because the event is marked processed and never retried. The app path must
    # not reintroduce that silence in a new place.
    convo = Recorder(raises=AttributeError("'list' object has no attribute 'transport'"))
    assert W.handle_inbound(app_row(), convo, anticipy()) == "error"
    replies = [t for k, t in wired["events"] if k == "anticipy_text"]
    assert replies and "again" in replies[0].lower(), \
        f"the app was left with nothing after a crash: {wired['events']}"


def test_a_crash_on_the_text_lane_still_texts_him(wired):
    convo = Recorder(raises=RuntimeError("boom"))
    assert W.handle_inbound(sms_row(), convo, anticipy()) == "error"
    assert convo.texted, "a crash on the SMS lane went silent"


# ------------------------------- the REAL say(), not a stand-in
# Everything above drives handle_inbound with a faithful stub. These drive the
# actual Conversation, because the suppression contract lives there: two
# mutations of it survived the stubbed tests, which means the stub was carrying
# the assertion instead of the code.

def real_conversation():
    from brain.conversation import Conversation, MockTransport
    transport = MockTransport()
    owner = types.SimpleNamespace(llm=None, owner_ref=OWNER_REF, owner_id="",
                                  memory=None)
    return Conversation(owner, transport=transport, llm=None), transport


def test_the_real_say_does_not_text_inside_an_app_turn():
    convo, transport = real_conversation()
    with convo.reply_in_app():
        out = convo.say(OWNER_PHONE, "answering in the app")
    assert transport.sent == [], "an in-app answer was texted back after all"
    assert out.get("via") == "in-app"


def test_the_real_say_still_texts_outside_an_app_turn():
    convo, transport = real_conversation()
    convo.say(OWNER_PHONE, "an ordinary text")
    assert len(transport.sent) == 1


def test_suppression_does_not_leak_past_the_turn():
    # If the flag stayed set, every later message she tried to send -- proactive
    # nudges, the next question, an apology -- would be silently dropped, and
    # nothing would look broken from the inside.
    convo, transport = real_conversation()
    with convo.reply_in_app():
        convo.say(OWNER_PHONE, "in-app reply")
    convo.say(OWNER_PHONE, "a text that must still go out")
    assert [b for _, b in [(s["to"], s["body"]) for s in transport.sent]] == \
        ["a text that must still go out"]


def test_nesting_restores_the_previous_state_not_a_guess():
    convo, transport = real_conversation()
    with convo.reply_in_app():
        with convo.reply_in_app():
            pass
        convo.say(OWNER_PHONE, "still inside the outer app turn")
    assert transport.sent == [], "the inner block re-enabled texting"


def test_a_suppressed_reply_is_still_part_of_the_conversation():
    # The turn must be recorded even though it was not texted: the thread is
    # what the dedupe reads (the same sentence must not go out twice within
    # minutes) and what she is shown as context next turn. Dropping it makes an
    # in-app exchange invisible to her own history -- two conversations again.
    convo, _ = real_conversation()
    with convo.reply_in_app():
        convo.say(OWNER_PHONE, "her in-app reply")
    assert [t.text for t in convo.threads[OWNER_PHONE]] == ["her in-app reply"]
