"""The 2026-08-11 21:11-21:21 disaster, stage by stage.

Live: "Do you wanna finish the girls [earls]" scrapped the parked booking;
"Let's do Earl's tomorrow at 2 PM" left a misheard "rose" plan alive beside
the earls one and "Sounds good" released the WRONG sibling; "I told you to
book Earl's dammit" scrapped rose but never started earls; and "Why are you
not booking" was answered "there are no active requests" while his earls run
had failed minutes earlier.

Each rule lives in the classifier's one prompt; the redo half-act and the
recent-outcomes visibility are code.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import brain.conversation as convmod  # noqa: E402
from brain.anticipy_core import Anticipy  # noqa: E402
from brain.conversation import Conversation, REPLY_SYSTEM  # noqa: E402
from brain.memory import Memory  # noqa: E402


def _low():
    return " ".join(REPLY_SYSTEM.split()).lower()


def test_finishing_language_is_never_a_decline():
    low = _low()
    assert "finishing is not cancelling" in low
    assert "never a decline" in low


def test_a_redirect_supersedes_the_pending_plan():
    low = _low()
    assert "one plan, not two" in low
    assert "never leave the old version alive" in low


def test_a_bare_go_ahead_binds_to_her_own_last_text():
    low = _low()
    assert "your own last text" in low


def test_wrong_thing_corrections_carry_a_redo():
    low = _low()
    assert "i told you to book x" in low
    assert '"redo"' in low


def test_never_claims_a_booking_exists():
    low = _low()
    assert "never claim a booking" in low
    assert "cancelled or failed task" in low


def test_recent_outcomes_rule_is_in_the_prompt():
    low = _low()
    assert "recent_outcomes" in low
    assert "no active requests" in low


def _conv():
    a = Anticipy(memory=Memory(":memory:"), llm=None, owner_id="t")
    return Conversation(a, llm=None)


def test_recent_outcomes_reach_the_classifier(monkeypatch):
    """The payload the model reads must include what just failed."""
    seen = {}

    class R:
        ok = True
        def __init__(self, payload): self._p = payload
        def json(self): return self._p

    def get(url, **kw):
        filt = (kw.get("params") or {}).get("filter", "")
        if 'status="failed"' in filt:
            return R({"items": [{"goal": "Book lunch at Earls",
                                 "status": "failed",
                                 "result": "max steps reached"}]})
        return R({"items": []})

    monkeypatch.setattr(convmod, "pb", type("PB", (), {
        "get": staticmethod(get)}))
    c = _conv()

    class FakeLLM:
        live = True
        def chat(self, system, payload, **kw):
            seen["payload"] = payload
            class T:
                text = json.dumps({"intent": "chat", "reply": "hey"})
            return T()

    c.llm = FakeLLM()
    c._classify("+1", "why are you not booking")
    data = json.loads(seen["payload"])
    assert data["recent_outcomes"][0]["goal"] == "Book lunch at Earls"
    assert data["recent_outcomes"][0]["status"] == "failed"


def test_a_redo_starts_the_errand_they_actually_wanted(monkeypatch):
    """decline + redo must kill the wrong item AND start the right one."""
    c = _conv()
    monkeypatch.setattr(c, "_classify", lambda phone, text: {
        "intent": "decline", "pending_id": "wrong1", "pending_ids": ["wrong1"],
        "changes": None,
        "redo": "Book Earls in West Vancouver tomorrow at 2 PM for 2",
        "reply": "my fault — scrapping that."})
    monkeypatch.setattr(c, "_cancel", lambda jid, owner_text=None: "cancelled:wrong1")
    monkeypatch.setattr(c, "_fetch", lambda jid: {"id": jid, "goal": "book rose"})
    thought = {}

    def think(text, phone=""):
        thought["goal"] = text
        return "on it — booking Earls tomorrow at 2 PM."

    monkeypatch.setattr(c, "_think", think)
    sent = []
    monkeypatch.setattr(c, "say", lambda phone, body: sent.append(body))
    out = c.on_reply("+1", "I told you to book Earl's dammit")
    assert out["acted"] == "cancelled:wrong1"
    assert thought["goal"].startswith("Book Earls")
    assert "Earls" in sent[0]


def test_no_redo_no_phantom_task(monkeypatch):
    """A plain decline must not invent a redo errand."""
    c = _conv()
    monkeypatch.setattr(c, "_classify", lambda phone, text: {
        "intent": "decline", "pending_id": "j1", "pending_ids": ["j1"],
        "changes": None, "redo": None, "reply": "scrapped."})
    monkeypatch.setattr(c, "_cancel", lambda jid, owner_text=None: "cancelled:j1")
    monkeypatch.setattr(c, "_fetch", lambda jid: {"id": jid, "goal": "book x"})
    called = []
    monkeypatch.setattr(c, "_think", lambda *a, **k: called.append(a) or None)
    monkeypatch.setattr(c, "say", lambda phone, body: None)
    c.on_reply("+1", "forget it")
    assert not called
