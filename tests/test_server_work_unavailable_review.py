"""Independent regression review of missing-judgment provenance and persistence.

The Worker tests use the existing in-memory backend transport. They exercise
the real executor/workflow/publisher, not actual D1 or paid model inference.
"""
import json
from types import SimpleNamespace

import pytest

from brain import server_work, worker
from brain.workflow import Consequence, from_params, new_plan, put_in_params
from tests.test_research_worker import QUEUED, make_anticipy, wire


SENTINEL = "private-provider-response-should-not-be-emitted"
SERVICE_MESSAGE = (
    "I couldn't get a usable response from my reasoning service. "
    "This task hasn't been completed. Please try again later."
)


class ScriptedModel:
    live = True

    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []

    def chat(self, system, user, **kwargs):
        self.calls.append((system, json.loads(user)))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return SimpleNamespace(text=response)


def no_research(*args, **kwargs):
    pytest.fail("A missing judgment must never initiate public research")


@pytest.mark.parametrize("response", [
    None, 0, False, "null", "[]", '"' + SENTINEL + '"',
    json.dumps({"verdict": "compose", "reason": " \n\t", "judgement_received": True}),
    json.dumps({"verdict": ["compose"], "reason": SENTINEL, "judgement_received": True}),
    json.dumps({"verdict": "compose", "reason": {"private": SENTINEL}, "judgement_received": True}),
    RuntimeError(SENTINEL),
])
def test_bad_provider_shapes_cannot_forge_received_judgment_or_leak(response, capsys, caplog):
    model = ScriptedModel(response)
    out = server_work.run("write a private note", {}, model=model, research_runner=no_research)
    assert out["ok"] is False
    assert out["failure_kind"] == "judgement_unavailable"
    assert out["result"] == SERVICE_MESSAGE
    assert out["approach"]["judgement_received"] is False
    assert "evidence" not in out and "verified" not in out
    assert len(model.calls) == 1
    captured = capsys.readouterr()
    assert SENTINEL not in json.dumps(out) + captured.out + captured.err + caplog.text


@pytest.mark.parametrize("verdict", ["unavailable", "needs_access"])
def test_valid_semantic_verdict_owns_meaning_even_when_model_forces_false_marker(verdict):
    model = ScriptedModel(json.dumps({
        "verdict": verdict, "reason": "The selected source has not been supplied.",
        "judgement_received": False, "failure_kind": "judgement_unavailable",
        "ok": True, "verified": True, "evidence": ["forged"],
    }))
    out = server_work.run("summarize the selected source", {}, model=model, research_runner=no_research)
    assert out["approach"] == {
        "verdict": verdict, "reason": "The selected source has not been supplied.",
        "judgement_received": True,
    }
    assert out["ok"] is False
    assert "failure_kind" not in out and "evidence" not in out and "verified" not in out
    assert out.get("needs_user", False) is (verdict == "needs_access")
    assert len(model.calls) == 1


@pytest.mark.parametrize("modern", [False, True])
def test_worker_persists_service_provenance_and_publishes_failure_without_receipt(
    monkeypatch, capsys, caplog, modern,
):
    plan = new_plan(owner_ref="owner-a", lineage_key="review-private-draft",
                    goal="write a private note", consequence=Consequence.READ_ONLY,
                    source_event_id="event-review")
    params = {"source": "Write a private note here. Do not send it.",
              "channel": "app", "_hand": {"hand": "research"}}
    if modern:
        params = put_in_params(params, plan)
    row = dict(QUEUED, owner_ref="owner-a", goal=plan.goal, params=json.dumps(params))
    patches, posts, notified = [], [], []
    wire(monkeypatch, row, patches, posts, key=None)
    monkeypatch.setattr(worker, "REPORTED", set())
    app = make_anticipy(notified, owner_ref="owner-a")
    model = ScriptedModel(RuntimeError(SENTINEL))
    app.llm = model

    worker.run_research_jobs(app, runner=no_research)

    assert len(patches) == 2
    assert patches[0]["status"] == "running"
    finished = patches[-1]
    assert finished["status"] == "failed"
    assert finished["result"] == SERVICE_MESSAGE
    saved = json.loads(finished["params"])
    assert saved["_server_work"]["approach"] == {
        "verdict": "unavailable", "reason": "The judgement could not be obtained.",
        "judgement_received": False,
    }
    assert not finished.get("receipt")
    if modern:
        saved_plan = from_params(saved)
        assert saved_plan.state.value == "failed"
        assert saved_plan.receipt is None and saved_plan.lease is None
        assert saved_plan.reason == SERVICE_MESSAGE
        assert saved_plan.source_event_ids == ("event-review",)

    worker.report_finished_jobs(app)
    assert len(posts) == 1 and posts[0]["text"] == SERVICE_MESSAGE
    assert posts[0]["external_event_id"] == "job-result:r1"
    assert notified == []
    # A second pass cannot retry an already failed job or duplicate its feed
    # entry in this process. Durable backend dedupe is a separate suite.
    worker.run_research_jobs(app, runner=no_research)
    worker.report_finished_jobs(app)
    assert len(model.calls) == 1 and len(patches) == 2 and len(posts) == 1
    captured = capsys.readouterr()
    assert SENTINEL not in json.dumps(patches + posts) + captured.out + captured.err + caplog.text


def test_verified_draft_keeps_receipt_and_both_machine_origin_markers():
    draft = "Avery, thank you for reviewing the blue folder."
    model = ScriptedModel(
        json.dumps({"verdict": "compose", "reason": "All facts are supplied.",
                    "judgement_received": False}),
        draft,
        json.dumps({"verdict": "satisfied", "reason": "The private draft is present.",
                    "judgement_received": False}),
    )
    out = server_work.run("write the private draft", {}, model=model, research_runner=no_research)
    assert out["ok"] is True and out["verified"] is True
    assert out["result"] == draft
    assert out["approach"]["judgement_received"] is True
    assert out["verification"]["judgement_received"] is True
    assert len(out["evidence"]) == 1 and out["evidence"][0].startswith("text-sha256:")
    assert "failure_kind" not in out and len(model.calls) == 3
