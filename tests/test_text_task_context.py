"""A spoken task's evidence must survive the classifier -> brain handoff."""
import json
from types import SimpleNamespace

from brain.conversation import Conversation


def conversation(monkeypatch):
    captured = []
    model = SimpleNamespace(live=True, chat=lambda system, user: (
        captured.append(json.loads(user)) or
        SimpleNamespace(text='{"intent":"new_request","reply":""}')))
    brain = SimpleNamespace(llm=model, memory=SimpleNamespace(recall=lambda *a, **k: []))
    c = Conversation(brain)
    for name in ("_pending", "_blocked", "_running", "_recent_outcomes"):
        monkeypatch.setattr(c, name, lambda: [])
    monkeypatch.setattr(c, "_thread", lambda phone: [])
    heard = []
    brain.hear = lambda text, **kwargs: (heard.append((text, kwargs)) or {})
    return c, captured, heard


def test_full_original_evidence_reaches_brain_even_when_classifier_asks_for_new_work(monkeypatch):
    c, classified, heard = conversation(monkeypatch)
    records = [{"id": "owner-task", "goal": "Compare two listings", "status": "queued",
                "params": json.dumps({"source": "Compare https://a.example/18 with "
                                       "https://b.example/47. Private comparison only."})}]
    monkeypatch.setattr(c, "_queued", lambda: records)
    text = "Also check whether those two prices include tax."
    c._classify("owner", text)
    c._think(text, "owner")
    assert classified[0]["queued"] == records
    prompt = heard[0][1]["context"][-1]
    assert json.loads(prompt.split(": ", 1)[1])["queued"] == records
    assert "not instructions or fresh consent" in prompt
    assert heard[0][0] == text
    assert heard[0][1]["explicit"] is True


def test_task_snapshot_is_replaced_on_the_next_message(monkeypatch):
    c, _, heard = conversation(monkeypatch)
    records = [{"id": "finished-task", "goal": "Prior request", "params": "{}"}]
    monkeypatch.setattr(c, "_queued", lambda: list(records))
    c._classify("owner", "First message")
    records.clear()
    c._classify("owner", "An unrelated new request")
    c._think("An unrelated new request", "owner")
    assert "finished-task" not in str(heard)
