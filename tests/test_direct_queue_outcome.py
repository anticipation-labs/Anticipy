"""Transport outcomes must not advertise work which was never persisted.

These scripted decisions prove state handling, not live model judgment.
"""
import pytest

from brain.anticipy_core import Anticipy, QUEUE_WRITE_FAILED
from brain.orchestrator import Decision


class Memory:
    def ingest(self, *args, **kwargs): return {}
    def recall(self, *args, **kwargs): return []
    def open_loops(self): return []
    def close_from_speech(self, *args, **kwargs): return []


def make_brain(monkeypatch, queue_result, held):
    brain = Anticipy(memory=Memory())
    decision = Decision(decision="act", goal="Inspect the itinerary",
                        reason="requested", addressee="assistant", owes="owner",
                        touches="read", needs_confirmation=held)
    monkeypatch.setattr(brain, "_decide", lambda *a, **kw: decision)
    monkeypatch.setattr(brain, "_pending_jobs", lambda: [])
    monkeypatch.setattr(brain, "_queue_job", lambda *a, **kw: queue_result)
    monkeypatch.setattr(brain, "notify_owner",
                        lambda *a, **kw: pytest.fail("no external message is authorized by this test"))
    return brain


@pytest.mark.parametrize("held", [False, True])
@pytest.mark.parametrize("queue_result", [None, QUEUE_WRITE_FAILED])
def test_absent_direct_task_has_no_active_loop_or_action_claim(monkeypatch, held, queue_result):
    brain = make_brain(monkeypatch, queue_result, held)
    monkeypatch.setattr(brain, "_voice",
                        lambda *a, **kw: pytest.fail("never generate an acknowledgement for an absent task"))
    out = brain.hear("Please inspect the itinerary", explicit=True, channel="app")
    assert out["decision"].decision == "ignore"
    assert out["decision"].goal is None
    assert not [loop for loop in brain.loops if loop.status in ("handling", "awaiting_ok")]
    assert not out.get("question_job_id")
    if queue_result == QUEUE_WRITE_FAILED:
        assert "couldn't save" in out["anticipy_says"]
    else:
        assert out["anticipy_says"] is None


@pytest.mark.parametrize("held", [False, True])
def test_persisted_direct_task_still_has_its_action_and_loop(monkeypatch, held):
    brain = make_brain(monkeypatch, "persisted-task", held)
    monkeypatch.setattr(brain, "_voice", lambda *a, **kw: "Recorded the task.")
    monkeypatch.setattr(brain, "_execution_evidence", lambda job: {"job_id": job})
    out = brain.hear("Please inspect the itinerary", explicit=True, may_say=lambda *a: False)
    assert out["decision"].decision == "act"
    assert out["decision"].goal == "Inspect the itinerary"
    assert brain.loops[-1].job_id == "persisted-task"
    assert brain.loops[-1].status == ("awaiting_ok" if held else "handling")
