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
