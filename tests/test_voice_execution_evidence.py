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
