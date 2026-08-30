"""A bare acknowledgment is never a new errand.

Live 2026-08-12 22:28: he texted "Sounds good" right after her own "got it,
booking earls at 4 pm". The classifier called it chat, the chat lane
re-triaged the thread while the booking job was RUNNING, and a duplicate held
card appeared whose text — "I'll hold off on booking ... until you give me
the word" — contradicted the work in motion.

Rules tested here:
  1. A bare ack with a held card waiting releases that card.
  2. A bare ack with nothing waiting and a plan running earns a nod —
     never a trip through triage, never a second card.
  3. A real message still reaches the brain unchanged.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.anticipy_core import Anticipy  # noqa: E402
from brain.conversation import Conversation  # noqa: E402
from brain.memory import Memory  # noqa: E402


def _conv():
    a = Anticipy(memory=Memory(":memory:"), llm=None, owner_id="t")
    return Conversation(a, llm=None)


def _classified_chat(c, monkeypatch, reply="nice!"):
    monkeypatch.setattr(c, "_classify", lambda phone, text: {
        "intent": "chat", "pending_id": None, "pending_ids": [],
        "changes": None, "redo": None, "reply": reply})


def test_an_ack_with_a_plan_running_never_reaches_triage(monkeypatch):
    c = _conv()
    _classified_chat(c, monkeypatch)
    monkeypatch.setattr(c, "_pending", lambda: [])
    monkeypatch.setattr(c, "_running", lambda: [
        {"id": "j1", "status": "running",
         "goal": "Book dinner for two at Earls West Vancouver tomorrow"}])
    thought = []
    monkeypatch.setattr(c, "_think", lambda *a, **k: thought.append(a) or None)
    sent = []
    monkeypatch.setattr(c, "say", lambda phone, body: sent.append(body))
    out = c.on_reply("+1", "Sounds good")
    assert not thought, "a bare ack was re-triaged"
    assert out["intent"] == "chat"
    assert "moving" in sent[0] and "Earls" in sent[0], sent
    assert "hold off" not in sent[0].lower()


def test_an_ack_with_a_card_waiting_releases_it(monkeypatch):
    c = _conv()
    _classified_chat(c, monkeypatch)
    monkeypatch.setattr(c, "_pending", lambda: [
        {"id": "j2", "status": "awaiting_confirm", "goal": "book earls"}])
    monkeypatch.setattr(c, "_asked_to_cancel", lambda: False)
    monkeypatch.setattr(c, "_freshest_pending", lambda: "j2")
    released = []
    monkeypatch.setattr(
        c, "_release",
        lambda jid, changes, owner_text=None: released.append(jid)
        or "released:j2")
    monkeypatch.setattr(c, "_fetch", lambda jid: {"id": jid,
                                                  "goal": "book earls"})
    monkeypatch.setattr(c, "_think", lambda *a, **k: None)
    monkeypatch.setattr(c, "say", lambda phone, body: None)
    out = c.on_reply("+1", "sounds great!")
    assert released == ["j2"]
    assert out["intent"] == "confirm"


def test_a_real_message_still_reaches_the_brain(monkeypatch):
    c = _conv()
    _classified_chat(c, monkeypatch)
    monkeypatch.setattr(c, "_pending", lambda: [])
    monkeypatch.setattr(c, "_running", lambda: [])
    monkeypatch.setattr(c, "_recent_outcomes", lambda: [])
    thought = []

    def think(text, phone=""):
        thought.append(text)
        return "on it."

    monkeypatch.setattr(c, "_think", think)
    monkeypatch.setattr(c, "say", lambda phone, body: None)
    c.on_reply("+1", "can you also grab a cake for saturday")
    assert thought == ["can you also grab a cake for saturday"]


def test_an_ack_after_a_cancel_question_is_not_a_release(monkeypatch):
    c = _conv()
    _classified_chat(c, monkeypatch)
    monkeypatch.setattr(c, "_pending", lambda: [
        {"id": "j3", "status": "awaiting_confirm", "goal": "book earls"}])
    monkeypatch.setattr(c, "_asked_to_cancel", lambda: True)
    monkeypatch.setattr(c, "_running", lambda: [])
    released = []
    monkeypatch.setattr(
        c, "_release",
        lambda jid, changes, owner_text=None: released.append(jid))
    monkeypatch.setattr(c, "_think", lambda *a, **k: None)
    monkeypatch.setattr(c, "say", lambda phone, body: None)
    c.on_reply("+1", "ok")
    assert not released, "an ack to 'want me to scrap it?' released the job"
