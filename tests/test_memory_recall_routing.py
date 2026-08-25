from __future__ import annotations

import pytest

from brain.anticipy_core import Anticipy, explicitly_for_memory


class MemoryWithCode:
    def __init__(self):
        self.ingested = []

    def ingest(self, text, **_kwargs):
        self.ingested.append(text)
        return {"commitment_id": None}

    # **kw so a new read-lane parameter on Memory.recall (RULING 2's
    # retired action/speech split) does not turn this stand-in into a
    # TypeError far from the thing under test.
    def recall(self, _question, limit=8, **kw):
        return [{"fact": "The pickup code is 668872.",
                 "quote": "the pickup code is 668872"}]

    def open_loops(self):
        return []

    def close_from_speech(self, *_args, **_kwargs):
        return []

    def briefing_facts(self, *_args, **_kwargs):
        return {"heard": [], "open_loops": []}


@pytest.mark.parametrize("question", [
    "What is the pickup code?",
    "Anticipy, what is the pickup code?",
    "hey Anticipy: what is the pickup code?",
])
def test_wake_word_memory_questions_are_answered_not_acted_on(question):
    memory = MemoryWithCode()
    result = Anticipy(memory=memory).hear(question, explicit=True)

    assert result["decision"].decision == "answer"
    assert result["decision"].goal is None
    assert "668872" in result["anticipy_says"]
    assert memory.ingested == [question]


def test_declarative_code_for_later_is_memory_not_a_browser_job():
    line = "For later, the pickup code for school is 340097."
    assert explicitly_for_memory(line)
    memory = MemoryWithCode()
    anticipy = Anticipy(memory=memory)
    anticipy._queue_job = lambda *_args, **_kwargs: pytest.fail(
        "a declarative memory fact reached the job queue")

    result = anticipy.hear(line, speaker="owner")

    assert result["decision"].decision == "ignore"
    assert result["decision"].goal == ""
    assert result["anticipy_says"] is None
    assert memory.ingested == [line]


def test_remember_to_is_not_misclassified_as_a_passive_fact():
    assert not explicitly_for_memory("Remember to call the dentist tomorrow.")
