import json
from types import SimpleNamespace

import pytest

from brain.anticipy_core import Anticipy
from brain.orchestrator import Decision
from brain.readiness import task_readiness


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


@pytest.mark.parametrize("answer", ["[]", "null", "{}", "garbage", TimeoutError(),
    '{"verdict":"ready","missing":["who"]}',
    '{"verdict":"needs_owner","missing":[]}',
    '{"verdict":"needs_owner","missing":[null]}'])
def test_no_verdict_does_not_silently_answer_owner_questions(answer):
    assert task_readiness(Model(answer), {"task": "Prepare a visit"}).verdict == "unavailable"


class Memory:
    def recall(self, *args, **kwargs):
        return [{"fact": "Ren runs Project Orion; their email is ren@contacts.audit.invalid", "source": "import"}]
    def ingest(self, *args, **kwargs): return {}
    def open_loops(self): return []
    def close_from_speech(self, *args, **kwargs): return []


def test_question_review_sees_conversation_memory_and_real_access_without_promoting_import(monkeypatch):
    from brain.hands import HandContext, ConnectedApp
    monkeypatch.setattr("brain.hands.gather_context", lambda **kw: HandContext(
        connections=(ConnectedApp("documents", status="disconnected"),), browser_online=False))
    model = Model('{"verdict":"ready","missing":[]}')
    app = Anticipy(memory=Memory(), llm=model)
    decision = Decision(decision="ask", reason="fixture missing detail", goal="Draft an Orion update for Ren", touches="world",
                        missing=["Ren's email", "the Orion brief"], addressee="assistant")
    reviewed = app._review_readiness(decision, "Use the Orion brief and let me review it",
                                     ["Ren is the project lead"], "Draft a short note")
    assert reviewed.decision == "act" and reviewed.missing == []
    assert reviewed.touches == "world"
    assert app._memory_filled == {}, "quoted imported context is not an approved action value"
    evidence = model.inputs[-1]
    assert evidence["conversation"] == ["Ren is the project lead"]
    assert evidence["previous_line"] == "Draft a short note"
    assert "ren@contacts.audit.invalid" in evidence["related_memory"]
    assert "untrusted" in evidence["related_memory"].lower()
    assert evidence["access"]["connections"][0]["status"] == "disconnected"
    assert evidence["access"]["browser_online"] is False


@pytest.mark.parametrize("verdict", ["unclear", "unavailable"])
def test_unanswered_review_preserves_the_existing_question(monkeypatch, verdict):
    model = Model(json.dumps({"verdict": verdict, "missing": []}))
    app = Anticipy(memory=Memory(), llm=model)
    monkeypatch.setattr("brain.hands.gather_context", lambda **kw: (_ for _ in ()).throw(TimeoutError()))
    decision = Decision(decision="ask", reason="fixture missing detail", goal="Prepare visit", missing=["When does it end?"])
    assert app._review_readiness(decision, "Prepare visit", [], None) == decision


def test_initial_ask_uses_the_same_review_before_composing_or_queuing(monkeypatch):
    app = Anticipy(memory=Memory())
    monkeypatch.setattr(app, "_decide", lambda *a, **kw: Decision(
        decision="ask", reason="fixture missing detail", goal="Draft an update for review", missing=["Email address"],
        addressee="assistant", touches="world", owes="owner"))
    reviewed = []
    def review(decision, *args):
        from dataclasses import replace
        reviewed.append(decision)
        return replace(decision, decision="act", missing=[])
    monkeypatch.setattr(app, "_review_readiness", review)
    queued = []
    monkeypatch.setattr(app, "_queue_job", lambda *a, **kw: queued.append((a, kw)) or "job-one")
    monkeypatch.setattr(app, "_execution_evidence", lambda job: {"status":"awaiting_confirm"})
    monkeypatch.setattr(app, "_voice", lambda context: "The draft task is ready for your approval.")
    app.hear("Draft the note and hold it for review", explicit=True, may_say=lambda *a, **kw: False)
    assert len(reviewed) == 1 and len(queued) == 1
    assert "missing" not in queued[0][0][1]
    assert queued[0][1]["touches"] == "world"


def test_partial_memory_answer_stays_with_its_question_and_not_the_next_task(monkeypatch):
    app = Anticipy(memory=Memory())
    decisions = iter([
        Decision(decision="ask", reason="two details", goal="Prepare a visit", touches="world",
                 missing=["location", "end time"], addressee="assistant", owes="owner"),
        Decision(decision="act", reason="another task", goal="Prepare another note", touches="world",
                 addressee="assistant", owes="owner"),
    ])
    monkeypatch.setattr(app, "_decide", lambda *a, **kw: next(decisions))
    monkeypatch.setattr(app, "_review_readiness", lambda decision, *a: decision)
    monkeypatch.setattr("brain.anticipy_core.fill_gaps_from_memory",
                        lambda *a, **kw: ({"location": "Harbor office"}, ["end time"]))
    queued = []
    monkeypatch.setattr(app, "_queue_job", lambda *a, **kw: queued.append(a[1]) or "job-one")
    monkeypatch.setattr(app, "_execution_evidence", lambda job: {"status":"awaiting_confirm"})
    monkeypatch.setattr(app, "_voice", lambda context: "When does it end?")
    app.hear("Prepare the visit", explicit=True, may_say=lambda *a, **kw: False)
    assert queued[0]["location"] == "Harbor office"
    assert queued[0]["missing"] == ["end time"]
    app.hear("Prepare another note", explicit=True, may_say=lambda *a, **kw: False)
    assert "location" not in queued[1]
