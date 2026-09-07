"""Result fulfilment, tool boundaries and failures of the real server executor."""
import hashlib
import json
from types import SimpleNamespace

import pytest

from brain import server_work as S


class Model:
    live = True

    def __init__(self, *answers):
        self.answers = iter(answers)
        self.calls = []

    def chat(self, system, user, **kwargs):
        self.calls.append((system, json.loads(user)))
        answer = next(self.answers)
        if isinstance(answer, Exception):
            raise answer
        return SimpleNamespace(text=json.dumps(answer) if isinstance(answer, dict) else answer)


def verdict(value, reason="Assessment from the supplied record."):
    return {"verdict": value, "reason": reason}


def no_search(*args):
    raise AssertionError("This request must not reach public search")


def test_private_draft_is_the_artifact_without_search_or_external_writes():
    draft = "Hi Avery, could you review the blue folder? Nothing has been sent."
    model = Model(verdict("compose"), draft, verdict("satisfied"))
    out = S.run("prepare a message draft", {"source": "Ask Avery to review the blue folder"},
                model=model, research_runner=no_search)
    assert out["ok"] and out["verified"]
    assert out["result"] == draft
    assert out["evidence"] == ["text-sha256:" + hashlib.sha256(draft.encode()).hexdigest()]
    assert [c[0] for c in model.calls] == [S.PLAN_SYSTEM, S.COMPOSE_SYSTEM, S.VERIFY_SYSTEM]


def test_how_to_answer_is_repaired_into_the_requested_draft():
    bad = "Open a document editor and create a private draft."
    good = "Hi Avery, could you review the blue folder when you have a moment?"
    model = Model(verdict("compose"), bad, verdict("incomplete", "Instructions are not a draft."),
                  good, verdict("satisfied"))
    out = S.run("write a private draft", {}, model=model, research_runner=no_search)
    assert out["result"] == good and out["verified"]
    assert model.calls[3][1]["prior_output"] == bad
    assert model.calls[3][1]["review"]["verdict"] == "incomplete"


def test_a_second_unfulfilled_draft_is_not_completed():
    model = Model(verdict("compose"), "Use an editor.", verdict("incomplete"),
                  "Follow the instructions.", verdict("incomplete"))
    out = S.run("write the draft", {}, model=model, research_runner=no_search)
    assert not out["ok"] and "verified" not in out
    assert len(model.calls) == 5
    assert "couldn't verify" in out["result"]


def test_private_source_requires_access_instead_of_searching_the_task():
    model = Model(verdict("needs_access", "I need access to your supplier quotes to compare them."))
    out = S.run("compare my supplier quotes", {}, model=model, research_runner=no_search)
    assert not out["ok"] and out["needs_user"]
    assert "supplier quotes" in out["result"]


@pytest.mark.parametrize("state", ["hold", "unasked", "unanswered"])
def test_an_unlicensed_hand_cannot_become_a_search(state):
    model = Model()
    out = S.run("do the task", {"_hand": {"hand": state}}, model=model, research_runner=no_search)
    assert not out["ok"] and not model.calls


def test_a_consequential_workflow_cannot_complete_as_server_text():
    model = Model()
    out = S.run("finish the task", {"_workflow": {"consequence": "consequential"}},
                model=model, research_runner=no_search)
    assert not out["ok"] and out["needs_user"] and not model.calls


def test_cited_research_still_needs_fulfilment_review():
    sources = [{"url": "https://example.test", "content": "Instructions for creating a draft."}]
    model = Model(verdict("research"), verdict("incomplete", "This does not produce the requested draft."))
    out = S.run("write a draft", {}, model=model, research_runner=lambda *a:
                {"ok": True, "result": "Use an editor. https://example.test", "sources": sources})
    assert not out["ok"]
    assert model.calls[-1][1]["retrieved_sources"] == sources


def test_the_verifier_receives_actual_source_content_and_original_authority():
    sources = [{"url": "https://example.test/hours", "content": "Open 9 to 5."}]
    model = Model(verdict("research"), verdict("satisfied"))
    out = S.run("find opening hours", {"source": "What are the opening hours?"},
                model=model, research_runner=lambda *a: {"ok": True, "result": "Open 9 to 5.", "sources": sources})
    assert out["ok"]
    assert model.calls[1][1]["task_record"]["source"] == "What are the opening hours?"
    assert out["evidence"][1] == sources[0]["url"]


def test_urls_in_prose_do_not_replace_actual_source_evidence():
    model = Model(verdict("research"))
    out = S.run("look it up", {}, model=model, research_runner=lambda *a:
                {"ok": True, "result": "Claim. https://example.test", "sources": []})
    assert not out["ok"] and len(model.calls) == 1


@pytest.mark.parametrize("review", ["unclear", "unavailable"])
def test_missing_verification_does_not_lift_completion(review):
    model = Model(verdict("compose"), "A plausible draft", verdict(review))
    assert not S.run("draft", {}, model=model, research_runner=no_search)["ok"]


def test_no_model_never_claims_completion_from_fallback_snippets():
    assert not S.run("lookup", {}, model=None, research_runner=no_search)["ok"]


def test_storage_bound_is_applied_before_verifying_and_hashing():
    model = Model(verdict("compose"), "x" * 7000, verdict("incomplete"),
                  "x" * 7000, verdict("incomplete"))
    out = S.run("write a long artifact", {}, model=model, research_runner=no_search)
    assert not out["ok"]
    assert len(model.calls[2][1]["candidate"]) == 6000


def test_invalid_judgement_shape_is_unavailable():
    model = Model({"verdict": "compose", "reason": 123})
    assert not S.run("draft", {}, model=model, research_runner=no_search)["ok"]
