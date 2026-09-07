from __future__ import annotations

import pytest

from brain.anticipy_core import Anticipy
from brain.speech_request import InformationRequest


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
def test_model_identified_memory_request_is_answered_without_a_job(question, monkeypatch):
    # This proves routing, not language understanding. The real-model speech
    # audit measures whether these are requests using the complete conversation.
    monkeypatch.setattr("brain.anticipy_core.information_request",
                        lambda *a, **kw: InformationRequest("requested", "memory"))
    memory = MemoryWithCode()
    result = Anticipy(memory=memory).hear(question, explicit=True)

    assert result["decision"].decision == "answer"
    assert result["decision"].goal is None
    assert "668872" in result["anticipy_says"]
    assert memory.ingested == [question]


def test_declarative_code_for_later_is_memory_not_a_browser_job():
    line = "For later, the pickup code for school is 340097."
    memory = MemoryWithCode()
    anticipy = Anticipy(memory=memory)
    anticipy._queue_job = lambda *_args, **_kwargs: pytest.fail(
        "a declarative memory fact reached the job queue")

    result = anticipy.hear(line, speaker="owner")

    assert result["decision"].decision == "ignore"
    assert not result["decision"].goal
    assert result["anticipy_says"] is None
    assert memory.ingested == [line]


@pytest.mark.parametrize("verdict", ["not_requested", "unclear", "unavailable"])
def test_no_request_verdict_never_reads_memory_as_an_answer(verdict, monkeypatch):
    monkeypatch.setattr("brain.anticipy_core.information_request",
                        lambda *a, **kw: InformationRequest(verdict))
    anticipy = Anticipy(memory=MemoryWithCode())
    anticipy._answer_from_memory = lambda *_: pytest.fail("answered without a request")
    out = anticipy.hear("Did you send those figures? Yes, yesterday.", speaker="owner")
    assert out["anticipy_says"] is None


def test_without_a_model_even_a_question_mark_cannot_authorize_an_answer():
    out = Anticipy(memory=MemoryWithCode()).hear("What is the pickup code?", explicit=True)
    assert out["anticipy_says"] is None
