import json
from types import SimpleNamespace

import pytest

from brain.anticipy_core import Anticipy
from brain.orchestrator import Decision
from brain.speech_request import information_request


class Model:
    live = True

    def __init__(self, answer):
        self.answer = answer
        self.inputs = []

    def chat(self, system, user, **kwargs):
        self.inputs.append(json.loads(user))
        if isinstance(self.answer, Exception):
            raise self.answer
        return SimpleNamespace(text=self.answer)


@pytest.mark.parametrize("answer", ["not JSON", "[]", '{}',
    '{"verdict":"requested","kind":"browser"}',
    '{"verdict":true,"kind":"memory"}', TimeoutError()])
def test_missing_or_invalid_request_verdict_never_authorizes_a_reply(answer):
    assert information_request(Model(answer), "Any words?").verdict == "unavailable"


def test_request_judge_receives_raw_conversation_and_measured_source():
    model = Model('{"verdict":"requested","kind":"status"}')
    reply = information_request(model, "And that one?", context=["How is my task going?"],
                                speaker="owner", explicit=False)
    assert (reply.verdict, reply.kind) == ("requested", "status")
    assert model.inputs == [{"utterance": "And that one?",
        "conversation": ["How is my task going?"], "measured_speaker": "owner",
        "explicit_message_to_assistant": False}]


class Memory:
    def ingest(self, *args, **kw): return {}
    def recall(self, *args, **kw): return []
    def open_loops(self): return []
    def close_from_speech(self, *args, **kw): return []


@pytest.mark.parametrize("has_phone", [True, False])
def test_question_is_saved_and_stays_in_app_without_an_inline_sms_attempt(monkeypatch, has_phone):
    anticipy = Anticipy(memory=Memory())
    anticipy.owner_phone = "+12025550100" if has_phone else ""
    decision = Decision(decision="ask", reason="one missing detail", goal="Prepare the visit", addressee="assistant",
                        owes="owner", touches="world", missing=["when it ends"])
    monkeypatch.setattr(anticipy, "_decide", lambda *a, **kw: decision)
    monkeypatch.setattr(anticipy, "_voice", lambda *a, **kw: "When does the visit end?")
    queued = []
    monkeypatch.setattr(anticipy, "_queue_job",
                        lambda *a, **kw: queued.append((a, kw)) or "task-one")
    monkeypatch.setattr(anticipy, "notify_owner",
                        lambda *a, **kw: pytest.fail("the durable question outbox owns sending"))
    out = anticipy.hear("Please prepare the visit", explicit=True, channel="app")
    assert len(queued) == 1
    assert queued[0][1] == {"hold": True, "explicit": True, "touches": "world"}
    assert queued[0][0][1]["source"] == "Please prepare the visit"
    assert out["decision"].decision == "ask"
    assert out["anticipy_says"] == "When does the visit end?"
    assert anticipy.loops[-1].job_id == "task-one"


def test_no_question_claim_when_its_persistence_fails(monkeypatch):
    from brain.anticipy_core import QUEUE_WRITE_FAILED
    anticipy = Anticipy(memory=Memory())
    monkeypatch.setattr(anticipy, "_decide", lambda *a, **kw: Decision(
        decision="ask", reason="one missing detail", goal="Prepare visit", addressee="assistant", touches="world"))
    monkeypatch.setattr(anticipy, "_queue_job", lambda *a, **kw: QUEUE_WRITE_FAILED)
    out = anticipy.hear("Prepare visit", explicit=True)
    assert "couldn't save" in out["anticipy_says"]
    assert anticipy.loops == []


@pytest.mark.parametrize("verdict", ["unsupported", "unclear", "unavailable"])
def test_ungrounded_task_neither_queues_nor_asks_the_owner_to_explain_inventions(monkeypatch, verdict):
    anticipy = Anticipy(memory=Memory(), llm=Model('{}'))
    monkeypatch.setattr(anticipy, "_decide", lambda *a, **kw: Decision(
        decision="act", reason="model proposal", goal="Meet Dr. Evans", touches="world",
        addressee="assistant", owes="owner"))
    monkeypatch.setattr(anticipy, "_same_pending", lambda *a, **kw: None)
    monkeypatch.setattr(anticipy, "_refines_pending", lambda *a, **kw: None)
    monkeypatch.setattr("brain.anticipy_core.grounding_verdict", lambda *a, **kw: verdict)
    monkeypatch.setattr("brain.anticipy_core.fill_gaps_from_memory",
                        lambda *a, **kw: pytest.fail("memory cannot ratify an invented task"))
    monkeypatch.setattr(anticipy, "_queue_job", lambda *a, **kw: pytest.fail("ungrounded work queued"))
    out = anticipy.hear("I have a hard stop at 5:15", speaker="owner")
    assert not out["decision"].goal
    assert out["anticipy_says"] is None


def test_clarification_preserves_effect_type_and_utterance_provenance(monkeypatch):
    anticipy = Anticipy(memory=Memory())
    decision = Decision(decision="act", reason="requested", goal="Create appointment",
                        addressee="assistant", owes="owner", touches="world", continues=2,
                        missing=["when it ends"])
    monkeypatch.setattr(anticipy, "_decide", lambda *a, **kw: decision)
    saved = []
    monkeypatch.setattr(anticipy, "_queue_job", lambda *a, **kw: saved.append((a, kw)) or "calendar-task")
    out = anticipy.hear("Create the appointment", explicit=True, source_event_id="utterance-a")
    assert out["decision"].decision == "ask"
    assert out["decision"].touches == "world"
    assert out["decision"].continues == 2
    assert out["question_job_id"] == "calendar-task"
    assert saved[0][1]["touches"] == "world"
    assert anticipy._source_event_id == "utterance-a"


def test_hand_discovered_missing_field_uses_the_same_invited_question_outbox(monkeypatch):
    anticipy = Anticipy(memory=Memory())
    monkeypatch.setattr(anticipy, "_decide", lambda *a, **kw: Decision(
        decision="act", reason="requested", goal="Create appointment",
        addressee="assistant", owes="owner", touches="world"))
    monkeypatch.setattr(anticipy, "_pending_jobs", lambda: [])
    queued = []
    monkeypatch.setattr(anticipy, "_queue_job", lambda *a, **kw: queued.append((a, kw)) or "calendar-one")
    monkeypatch.setattr(anticipy, "_execution_evidence", lambda _: {
        "status": "awaiting_confirm", "workflow_state": "draft", "question": "When does it end?"})
    monkeypatch.setattr(anticipy, "notify_owner", lambda *a, **kw: pytest.fail("inline send duplicates outbox"))
    out = anticipy.hear("Create appointment", explicit=True)
    assert out["decision"].decision == "ask"
    assert out["question_job_id"] == "calendar-one"
    assert queued[0][0][1]["_question_invited"] is True
    assert out["anticipy_says"] == "When does it end?"
