#!/usr/bin/env python3
"""Regression tests for the SMS conversation defects found 2026-07-31.

Offline: no LLM, no network. Each test names the live failure it prevents.
Run:  PYTHONPATH=. python3 proof/test_sms_flows.py
"""
import sys

from brain.conversation import Conversation, MockTransport
from brain.worker import same_phone

PASS, FAIL = [], []


def check(name, cond):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name)


class FakeAnticipy:
    """Minimal stand-in: records what hear() was asked to swallow."""
    backend_url = "http://127.0.0.1:0"
    owner_id = "owner-1"
    owner_phone = "+16047245161"

    def __init__(self):
        self.heard = []
        self.llm = None

        class _Mem:
            def recall(self, *a, **k):
                return []
        self.memory = _Mem()

    def hear(self, line):
        self.heard.append(line)
        return {"memory": {}, "decision": None, "anticipy_says": None}


def convo_with(pending, flips):
    a = FakeAnticipy()
    c = Conversation(a, transport=MockTransport())
    c._pending = lambda: list(pending)
    c._fetch = lambda jid: next((p for p in pending if p["id"] == jid), None)
    c._flip = lambda jid, fields, verb: (flips.append((jid, fields, verb))
                                         or f"{verb}:{jid}")
    return a, c


JOB = {"id": "j1", "goal": "book a table at Cactus", "params": "{}",
       "status": "awaiting_confirm"}


def test_answer_amends_instead_of_dropping():
    """LIVE BUG: 'Sunday' answering her question was dropped by the fragment
    guard while the reply said 'Sunday it is', and longer answers minted
    duplicate jobs."""
    a, c = convo_with([JOB], flips := [])
    c._classify = lambda p, t: {"intent": "answer", "pending_id": "j1",
                                "changes": {"date": "2026-08-04"},
                                "reply": "August 4th it is."}
    out = c.on_reply("+16047245161", "the 4th")
    check("answer amends the pending job", out["acted"] == "amended:j1")
    check("answer is NOT re-heard as a new commitment", a.heard == [])
    check("the amendment actually wrote params", flips and "params" in flips[0][1])


def test_amend_never_claims_it_is_moving():
    """LIVE BUG: after an amendment the owner was told 'On it — X is moving'
    about a job still held, so he stopped replying and it waited forever."""
    _, c = convo_with([JOB], [])
    c._classify = lambda p, t: {"intent": "modify", "pending_id": "j1",
                                "changes": {"time": "8pm"},
                                "reply": "Sure, 8pm."}
    out = c.on_reply("+16047245161", "make it 8")
    check("amend reply says still waiting, not moving",
          "waiting" in out["reply"].lower() and "moving" not in out["reply"].lower())


def test_failed_write_is_never_reported_as_success():
    """LIVE BUG: a 4xx/5xx on the queue flip still told the owner 'On it'."""
    a = FakeAnticipy()
    c = Conversation(a, transport=MockTransport())
    c._pending = lambda: [JOB]
    c._fetch = lambda jid: JOB
    c._flip = lambda jid, fields, verb: f"failed:{jid}"
    c._classify = lambda p, t: {"intent": "confirm", "pending_id": "j1",
                                "changes": None, "reply": "On it."}
    out = c.on_reply("+16047245161", "yes send it")
    check("failed write yields an honest reply", "snag" in out["reply"].lower())


def test_keyword_fallback_uses_word_boundaries():
    """LIVE BUG: 'yes' matched inside 'yesterday' (released a held job) and
    'no' inside 'know'/'now' (cancelled one)."""
    a = FakeAnticipy()
    c = Conversation(a, transport=MockTransport())
    c._pending = lambda: [JOB]
    got_yesterday = c._classify("+1", "I sent it yesterday")
    got_know = c._classify("+1", "call me when you know")
    got_real_yes = c._classify("+1", "yes go ahead")
    check("'yesterday' is not a confirm", got_yesterday["intent"] == "chat")
    check("'know' is not a decline", got_know["intent"] == "chat")
    check("a real 'yes go ahead' still confirms", got_real_yes["intent"] == "confirm")


def test_fallback_with_nothing_pending_does_not_claim_action():
    a = FakeAnticipy()
    c = Conversation(a, transport=MockTransport())
    c._pending = lambda: []
    got = c._classify("+1", "yes")
    check("bare yes with empty queue does not claim action",
          got["intent"] == "chat")


def test_only_the_owner_can_steer():
    """LIVE BUG: any stranger texting the Twilio number could release or
    cancel the owner's held jobs and read his pending list."""
    check("owner matches across formatting",
          same_phone("+1 (604) 724-5161", "+16047245161"))
    check("a stranger does not match", not same_phone("+15551234567", "+16047245161"))
    check("unset owner authorizes nobody", not same_phone("+16047245161", "owner"))
    check("empty sender authorizes nobody", not same_phone("", "+16047245161"))


for fn in [test_answer_amends_instead_of_dropping,
           test_amend_never_claims_it_is_moving,
           test_failed_write_is_never_reported_as_success,
           test_keyword_fallback_uses_word_boundaries,
           test_fallback_with_nothing_pending_does_not_claim_action,
           test_only_the_owner_can_steer]:
    fn()

print(f"\nsms flows: {len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
