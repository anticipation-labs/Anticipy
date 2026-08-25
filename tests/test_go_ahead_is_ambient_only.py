"""A contentless "okay let's do it" releases a held card with no second ask.

That shortcut exists for one shape: he is alone, she just asked him about a
plan, and his bare yes has nowhere else to land. Two shapes look identical to
the regex and are not that:

  - Mid-conversation. On a call she hears one side, and half of it is him
    agreeing with the other person. "Okay let's do it" said to the man on the
    phone is the purest back-channel there is — the exact class
    in_conversation() was built to catch — and the release ran two lines
    before that evidence was ever consulted. speaker is no help: measured on
    200 tagged lines, 97% carry no verdict at all.

  - Over SMS. conversation.py judges a text against the item it actually
    asked about, and only hands a line to the brain once it has decided the
    text is a new request or chat. A "sounds good" the SMS lane has already
    declined to treat as a confirmation must not come back through the
    ambient door and release the newest card instead.
"""
from brain.anticipy_core import Anticipy
from brain.memory import Memory

# Verbatim from the events table, the 2026-08-06 investor call.
THE_CALL = [
    "Yeah yeah",
    "Yeah OK and then",
    "Of course yeah",
    "Yeah yeah yeah yeah yeah of course",
    "OK that's good",
    "exactly how many how big is your network",
    "Yeah yeah",
    "Yeah yeah yeah yeah yeah",
]

# Him planning something out loud with someone. Also a conversation, but he is
# SAYING things, not just agreeing — suppressing this would delete the product.
THE_DINNER = [
    "we should go for dinner tomorrow",
    "how's Cactus Park Royal",
    "seven works for me",
    "just the two of us",
]

GO_AHEAD = "okay let's do it"


def _brain(monkeypatch):
    a = Anticipy(memory=Memory(":memory:"), llm=None, owner_id="t")
    released = []

    def release(line):
        released.append(line)
        return "Book dinner at Earls tomorrow at 7 PM"

    monkeypatch.setattr(a, "_release_freshest_held", release)
    monkeypatch.setattr(a, "_spoken_answer_to_parked_work", lambda _l: None)
    monkeypatch.setattr(a, "_decide", lambda *_a, **_k: __import__(
        "brain.orchestrator", fromlist=["Decision"]).Decision(
            decision="ignore", goal=None, reason="nothing actionable",
            addressee="self", owes="nobody"))
    return a, released


def test_a_yes_said_into_a_phone_call_releases_nothing(monkeypatch):
    a, released = _brain(monkeypatch)
    out = a.hear(GO_AHEAD, context=THE_CALL)
    assert released == [], \
        "his agreement with the caller must not book the dinner"
    assert out["decision"].decision != "act"


def test_a_yes_texted_back_is_the_sms_lane_s_to_judge(monkeypatch):
    a, released = _brain(monkeypatch)
    out = a.hear("sounds good", channel="sms", explicit=True)
    assert released == [], \
        "conversation.py owns confirm semantics for texts"
    assert out["decision"].decision != "act"


def test_a_yes_alone_in_the_room_still_releases_the_held_card(monkeypatch):
    """The shortcut has to keep working, or a bare spoken yes goes to triage
    and mints a brand-new goal out of injected context — which is how
    "extract memory into compact JSON" once became an errand."""
    a, released = _brain(monkeypatch)
    out = a.hear(GO_AHEAD, context=THE_DINNER)
    assert released == [GO_AHEAD]
    assert out["decision"].decision == "act"
    assert out["decision"].goal == "Book dinner at Earls tomorrow at 7 PM"


# --------------------------------------------------------------------------
# THE THIRD SHAPE: an armed meeting.
#
# in_conversation() is a BACK-CHANNEL density heuristic — it needs a fifth of
# the recent lines to be almost entirely "yeah/right/of course". The 2026-08-23
# Google Meet ran at 13% against its 20% threshold and never tripped it, which
# is the whole reason the meeting posture exists (worker.py's meeting_heard:
# ten lines inside 180s arms it, and it needs no speaker attribution because
# there is none). A substantive two-way meeting is therefore INVISIBLE to the
# guard above while being the exact room where "okay let's do it" is most
# likely to be the other person's sentence, or his answer to them.
#
# The posture already holds fresh consequential CARDS for the after-call
# digest. It did not hold the one path that needs no card at all: the bare
# spoken go-ahead, which releases work that is already sitting at the gate. A
# yes belonging to the man across the table could send an email.
#
# Nothing is lost by refusing: the line falls through to triage with the
# meeting pre-check riding along, and anything it mints mid-meeting is held
# for the digest anyway. The cost of being wrong is one tap; the cost of
# releasing is an action nobody authorised.
# --------------------------------------------------------------------------

# Substantive meeting talk — nobody is just agreeing, so the back-channel
# heuristic stays silent exactly as it did on the recorded call.
THE_MEETING = [
    "so the pricing tier we discussed last quarter",
    "right and that assumes the enterprise seats close",
    "we could move the deadline to the fifteenth",
    "what does that do to the engineering timeline",
]


def test_a_yes_inside_an_armed_meeting_releases_nothing(monkeypatch):
    a, released = _brain(monkeypatch)
    out = a.hear(GO_AHEAD, context=THE_MEETING, in_meeting=True)
    assert released == [], \
        "a go-ahead in a two-way meeting must not release a held card"
    assert out["decision"].decision != "act"


def test_the_meeting_guard_is_not_just_in_conversation_wearing_a_hat(monkeypatch):
    """If in_conversation() already caught this context the test above would
    prove nothing. Pin that it does NOT: same lines, posture disarmed, and the
    shortcut still fires."""
    a, released = _brain(monkeypatch)
    out = a.hear(GO_AHEAD, context=THE_MEETING, in_meeting=False)
    assert released == [GO_AHEAD], \
        "outside a meeting this context must still release, or the new " \
        "condition is redundant and the product just went deaf"
    assert out["decision"].decision == "act"
