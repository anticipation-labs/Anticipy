"""Runner wiring only, without real model or provider calls."""
import json
import sys
from types import SimpleNamespace

import pytest

from proof.audit import run_server_work as runner


def configure(tmp_path, monkeypatch, token="local-token"):
    (tmp_path / "gateway-token").write_text(token)
    monkeypatch.setattr(sys, "argv", ["runner", "--label", "fixture", "--state-dir", str(tmp_path),
                                    "--gateway-url", "http://127.0.0.1:8794/api/v1/chat/completions"])
    monkeypatch.setattr(runner, "CASES", [{"id": "draft", "goal": "draft", "source": "fixture", "want": "compose"}])
    monkeypatch.setattr(runner, "REVIEWS", [("review", "draft", "draft text", [], "satisfied")])


def test_paid_provider_override_cannot_bypass_gateway(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    models = []
    def make_model(**kwargs):
        model = SimpleNamespace(gemini_api_key="must-be-disabled", **kwargs)
        models.append(model)
        return model
    monkeypatch.setattr(runner.llm, "LLM", make_model)
    monkeypatch.setattr(runner.server_work, "run", lambda *a, **k: {
        "approach": {"verdict": "compose"}, "ok": True, "verified": True})
    monkeypatch.setattr(runner.server_work, "verify", lambda *a, **k: {"verdict": "satisfied"})
    runner.main()
    assert all(model.gemini_api_key is None for model in models)
    report = json.loads((tmp_path / "fixture.json").read_text())
    assert report["passed"] and report["attempted"] == report["completed"] == report["passed_count"] == 2


def test_case_exception_preserves_failed_evidence_without_private_body(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    monkeypatch.setattr(runner.llm, "LLM", lambda **kw: SimpleNamespace())
    def unavailable(*args, **kwargs):
        raise RuntimeError("PRIVATE PROVIDER BODY")
    monkeypatch.setattr(runner.server_work, "run", unavailable)
    monkeypatch.setattr(runner.server_work, "verify", unavailable)
    with pytest.raises(SystemExit) as outcome:
        runner.main()
    assert outcome.value.code == 1
    raw = (tmp_path / "fixture.json").read_text()
    assert "PRIVATE" not in raw
    report = json.loads(raw)
    assert report["failed_count"] == report["completed"] == 2 and not report["passed"]


@pytest.mark.parametrize("token", ["", "secret\nsecond-line", "x" * 4097])
def test_bad_local_token_rejected_before_model(tmp_path, monkeypatch, token):
    configure(tmp_path, monkeypatch, token)
    monkeypatch.setattr(runner.llm, "LLM", lambda **kw: pytest.fail("model reached"))
    with pytest.raises(SystemExit) as outcome:
        runner.main()
    assert outcome.value.code == 2 and not (tmp_path / "fixture.json").exists()


def test_empty_selection_cannot_pass(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    monkeypatch.setattr(runner, "CASES", [])
    with pytest.raises(SystemExit) as outcome:
        runner.main()
    assert outcome.value.code == 2
