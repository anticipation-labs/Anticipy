import json
from types import SimpleNamespace

import pytest

from brain.effects import task_effect
from brain.anticipy_core import is_consequential


class Model:
    live = True

    def __init__(self, answer):
        self.answer = answer
        self.seen = None

    def chat(self, system, evidence, **kwargs):
        self.seen = json.loads(evidence)
        return SimpleNamespace(text=json.dumps(self.answer))


@pytest.mark.parametrize("touches", ["compute", "read", "world", "unclear"])
def test_effect_judgment_receives_source_and_context_without_a_rubric(touches):
    model = Model({"touches": touches, "reason": "The complete record supports this effect."})
    evidence = {"task": "Do the discussed step", "heard": "Use that one",
                "conversation": ["Owner selected the private draft"],
                "related_memory": "Untrusted imported material"}
    assert task_effect(model, evidence).touches == touches
    assert model.seen == evidence


@pytest.mark.parametrize("raw", [None, [], {}, {"touches": "read"},
    {"touches": "READ", "reason": "x"}, {"touches": "read", "reason": ""}])
def test_missing_or_malformed_effect_is_not_a_read_verdict(raw):
    assert task_effect(Model(raw), {}).touches == "unavailable"


def test_missing_effect_fails_closed_without_reading_the_goal():
    for goal in ("compare a menu", "draft a note here", "buy everything", "任意の文字列"):
        assert is_consequential(goal, explicit=True)
        assert not is_consequential(goal, touches="read")
        assert not is_consequential(goal, touches="compute")
        assert is_consequential(goal, touches="world")
        assert is_consequential(goal, touches="unclear")


def test_persisted_effect_is_used_without_a_prose_fallback():
    assert not is_consequential("arbitrary words", {"_effect": {"touches": "read"}})
    assert is_consequential("arbitrary words", {"_effect": {"touches": "unknown"}})
