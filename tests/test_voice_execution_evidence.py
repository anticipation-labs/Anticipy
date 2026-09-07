"""A plan and a queue acknowledgement are not receipts for completed work."""
import json
from types import SimpleNamespace

import pytest

from brain import backend
from brain.anticipy_core import Anticipy


@pytest.mark.parametrize("status", ["awaiting_confirm", "queued", "running", "done"])
def test_voice_gets_persisted_state_without_inventing_step_receipts(monkeypatch, status):
    a = Anticipy.__new__(Anticipy)
    a.backend_url = "http://fixture.invalid"
    monkeypatch.setattr(backend, "get", lambda *args, **kwargs: SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"id": "job-one", "status": status}))
    evidence = a._execution_evidence("job-one")
    assert evidence == {"job_id": "job-one", "status": status,
                        "verified_results": []}


def test_unreadable_queue_is_unknown_not_started(monkeypatch):
    a = Anticipy.__new__(Anticipy)
    a.backend_url = "http://fixture.invalid"
    def unavailable(*args, **kwargs):
        raise ConnectionError("offline")
    monkeypatch.setattr(backend, "get", unavailable)
    assert a._execution_evidence("job-one")["status"] == "unverified"
    assert a._execution_evidence(None)["status"] == "not_created"


def test_held_fallback_describes_a_proposal_not_a_ready_artifact():
    a = Anticipy.__new__(Anticipy)
    assert a.say_handling("prepare the renewal summary", True) == (
        "I can take this on: prepare the renewal summary. Want me to start?")


def test_voice_uses_stronger_model_and_keeps_assistant_identity_separate():
    from brain.memory import Memory
    captured = []
    class Strong:
        def chat(self, system, user, **kwargs):
            captured.append(json.loads(user))
            return SimpleNamespace(text="the comparison is queued", truncated=False)
    a = Anticipy.__new__(Anticipy)
    a.llm = SimpleNamespace(owner_name="Amira", owner_email="amira@example.invalid", owner_zone="UTC")
    a.brain = SimpleNamespace(strong=Strong())
    a.memory = Memory()
    assert a._voice({"goal": "compare the proposals", "execution": {"status": "queued"}}) == "the comparison is queued"
    assert captured[0]["assistant_identity"] == {"name": "Anticipy", "role": "assistant"}
    assert a.brain.strong.owner_name == "Amira"
