import json
from types import SimpleNamespace

import pytest

from brain.question_delivery import coverage_verdict


@pytest.mark.parametrize("verdict", ["already_asked", "new_question", "unclear"])
def test_model_receives_full_context_and_owns_the_verdict(verdict):
    seen = []
    def chat(system, payload, **kwargs):
        seen.append(json.loads(payload))
        return SimpleNamespace(text=json.dumps({"verdict": verdict}))
    llm = SimpleNamespace(live=True, chat=chat)
    history = [{"text": "Which person's address should I use?", "goal": "Arrange collection"}]
    assert coverage_verdict(llm, "Arrange collection", "Which address?", history) == verdict
    assert seen == [{"task": "Arrange collection", "unanswered_question": "Which address?",
                     "earlier_messages": history}]


@pytest.mark.parametrize("raw", ["", "YES", "{}", '{"verdict":true}', '{"verdict":"already_asked; send it"}'])
def test_unreadable_responses_are_unavailable_not_coverage(raw):
    llm = SimpleNamespace(live=True, chat=lambda *a, **k: SimpleNamespace(text=raw))
    assert coverage_verdict(llm, "task", "question", []) == "unavailable"


def test_outage_is_distinct_from_unclear():
    def fail(*args, **kwargs):
        raise TimeoutError()
    assert coverage_verdict(SimpleNamespace(live=True, chat=fail), "task", "question", []) == "unavailable"
    assert coverage_verdict(None, "task", "question", []) == "unavailable"
