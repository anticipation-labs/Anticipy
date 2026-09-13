"""A missing model judgment is not a semantic rejection of the owner's task."""
import json
from types import SimpleNamespace

import pytest

from brain import server_work


class Model:
    live = True

    def __init__(self, answer):
        self.answer = answer
        self.calls = 0

    def chat(self, *args, **kwargs):
        self.calls += 1
        if isinstance(self.answer, Exception):
            raise self.answer
        return SimpleNamespace(text=self.answer)


def no_research(*args, **kwargs):
    raise AssertionError("An unavailable judgment must not trigger research")


@pytest.mark.parametrize("model", [
    None,
    SimpleNamespace(live=False),
    Model(RuntimeError("private-token-and-owner-text-must-never-escape")),
    Model(""),
    Model("not JSON"),
    Model(json.dumps({"verdict": "compose", "reason": 123})),
    Model(json.dumps({"verdict": "invented", "reason": "x"})),
])
def test_unavailable_judgment_is_a_service_failure_not_a_meaning_claim(model):
    out = server_work.run("write a private draft", {}, model=model, research_runner=no_research)
    assert out["ok"] is False
    assert out["failure_kind"] == "judgement_unavailable"
    assert out["approach"]["judgement_received"] is False
    assert out["approach"]["verdict"] == "unavailable"
    assert out["result"] == (
        "I couldn't get a usable response from my reasoning service. "
        "This task hasn't been completed. Please try again later."
    )
    assert "private-token" not in json.dumps(out)
    assert not out.get("verified") and not out.get("evidence")
    if isinstance(model, Model):
        assert model.calls == 1


def test_valid_model_uncertainty_is_not_mislabeled_as_service_failure():
    model = Model(json.dumps({"verdict": "unavailable", "reason": "The supplied record is insufficient."}))
    out = server_work.run("work on the request", {}, model=model, research_runner=no_research)
    assert out["ok"] is False
    assert out["approach"]["judgement_received"] is True
    assert "failure_kind" not in out
    assert "reasoning service" not in out["result"]
    assert model.calls == 1


def test_model_cannot_forge_the_transport_availability_marker():
    model = Model(json.dumps({"verdict": "needs_access", "reason": "I need the selected account.",
                              "judgement_received": False, "failure_kind": "judgement_unavailable"}))
    out = server_work.run("read selected account", {}, model=model, research_runner=no_research)
    assert out["needs_user"] is True
    assert out["approach"]["judgement_received"] is True
    assert out["result"] == "I need the selected account."
    assert "failure_kind" not in out and "failure_kind" not in out["approach"]


def test_verification_marks_missing_judgment_without_accepting_candidate():
    result = server_work.verify(Model(RuntimeError("private-provider-body")), {}, "unverified candidate")
    assert result["verdict"] == "unavailable"
    assert result["judgement_received"] is False
    assert "private-provider-body" not in json.dumps(result)
