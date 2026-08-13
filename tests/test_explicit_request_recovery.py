"""A direct owner request gets one semantic second look, never a promotion."""

import json
from types import SimpleNamespace

from brain.orchestrator import Brain


class SequenceLLM:
    live = True

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, system, user, **kwargs):
        self.calls.append((system, user, kwargs))
        return SimpleNamespace(text=json.dumps(self.replies.pop(0)))


IGNORE = {
    "decision": "ignore", "goal": None, "addressee": "assistant",
    "owes": "machine", "missing": [], "assumption": None,
    "reason": "misread as dictation",
}


def test_direct_request_gets_one_channel_grounded_second_look():
    goal = ("Give permission for Theo Kim to attend the Science Centre trip "
            "on Friday; emergency contact Jordan Kim at +1 604 555 7532")
    llm = SequenceLLM(IGNORE, {
        "decision": "act", "goal": goal, "addressee": "assistant",
        "owes": "owner", "missing": [], "assumption": None,
        "reason": "direct finishable request",
    })

    decision = Brain(llm=llm).triage(f"Please {goal}", explicit=True)

    assert decision.decision == "act"
    assert decision.goal == goal
    assert len(llm.calls) == 2
    assert "deliberately sent" in llm.calls[1][1]


def test_ambient_ignore_never_gets_direct_channel_recovery():
    llm = SequenceLLM(IGNORE)
    decision = Brain(llm=llm).triage("Please give permission", explicit=False)

    assert decision.decision == "ignore"
    assert len(llm.calls) == 1


def test_direct_small_talk_stays_ignored_after_the_second_look():
    llm = SequenceLLM(IGNORE, {**IGNORE, "reason": "small talk"})
    decision = Brain(llm=llm).triage("Thanks, that is all", explicit=True)

    assert decision.decision == "ignore"
    assert decision.goal is None
    assert len(llm.calls) == 2
