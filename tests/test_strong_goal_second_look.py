"""Any extracted goal gets the configured strong second opinion.

`ignore + goal` is not silence: it is the quiet-research lane. The live
transcription/model invention about quantum work used that contradictory shape,
so testing only cheap `act`/`ask` verdicts left the hallucinated job untouched.
"""
import json
import types

from brain.orchestrator import Brain, TRIAGE_SYSTEM


class Model:
    live = True
    model = "fake"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, system, user, **kwargs):
        self.calls.append((system, user))
        reply = self.replies.pop(0)
        return types.SimpleNamespace(
            text=reply if isinstance(reply, str) else json.dumps(reply))


def test_strong_model_removes_invented_quiet_work():
    cheap = Model([{
        "decision": "ignore", "goal": "Research quantum computing",
        "reason": "quiet lookup", "owes": "nobody", "touches": "read",
    }])
    strong = Model([{
        "decision": "ignore", "goal": None,
        "reason": "the owner was testing transcription", "owes": "nobody",
        "touches": None,
    }])
    brain = Brain(cheap)
    brain.strong = strong
    result = brain.triage("I'm just checking how good this transcription is")
    assert result.decision == "ignore"
    assert result.goal is None
    assert len(strong.calls) == 1
    assert strong.calls[0][0] == TRIAGE_SYSTEM


def test_ordinary_ignore_without_a_goal_does_not_spend_the_strong_model():
    cheap = Model([{
        "decision": "ignore", "goal": None, "reason": "chatter",
        "owes": "nobody", "touches": None,
    }])
    strong = Model([{"decision": "act", "goal": "invented"}])
    brain = Brain(cheap)
    brain.strong = strong
    result = brain.triage("nice weather")
    assert result.decision == "ignore" and result.goal is None
    assert strong.calls == []


def test_unanswered_strong_model_leaves_the_cheap_candidate_for_existing_floors():
    cheap_payload = {
        "decision": "act", "goal": "Research the invoice",
        "reason": "requested", "owes": "owner", "touches": "read",
    }
    cheap = Model([cheap_payload])

    class Dead(Model):
        def chat(self, *args, **kwargs):
            self.calls.append(args)
            raise TimeoutError("strong model unavailable")

    strong = Dead([])
    brain = Brain(cheap)
    brain.strong = strong
    result = brain.triage("research the invoice")
    assert result.decision == "act"
    assert result.goal == "Research the invoice"
    assert len(strong.calls) == 1
