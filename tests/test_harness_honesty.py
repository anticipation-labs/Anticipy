"""Harness regressions: fixtures only; no legacy main, credentials or network."""
import ast
import inspect
import json
import warnings
from pathlib import Path
from types import SimpleNamespace

import pytest

from proof.audit import run_reply_wire as wire
with warnings.catch_warnings():
    # The contract suite registers these markers in its own conftest, not ours.
    warnings.simplefilter("ignore", pytest.PytestUnknownMarkWarning)
    from migration.spec import contract_tests as contract

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("selector", ["", " ", ",", "yes_one,", "missing-case", "yes_one,missing-case", "yes_one,yes_one"])
def test_invalid_selector_stops_before_secret_or_network(monkeypatch, tmp_path, selector):
    monkeypatch.setattr(wire, "STATE", tmp_path)
    monkeypatch.setattr("sys.argv", ["reply-wire", "--label", "offline", "--cases", selector])
    def forbidden(*args, **kwargs):
        pytest.fail("invalid selection touched a secret or the network")
    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(wire, "request", forbidden)
    with pytest.raises(SystemExit) as stopped:
        wire.main()
    assert stopped.value.code == 2
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("args", [["--label", "../escape"], ["--label", "ok", "--parallel", "0"]])
def test_invalid_cli_controls_stop_before_secret(monkeypatch, tmp_path, args):
    monkeypatch.setattr(wire, "STATE", tmp_path)
    monkeypatch.setattr("sys.argv", ["reply-wire", *args])
    monkeypatch.setattr(Path, "read_text", lambda *a, **k: pytest.fail("secret read"))
    with pytest.raises(SystemExit) as stopped:
        wire.main()
    assert stopped.value.code == 2


@pytest.mark.parametrize("url", ["https://openrouter.ai/api/v1/chat/completions", "http://user:secret@127.0.0.1:8790/api/v1/chat/completions",
                               "http://127.0.0.1:8790/api/v1/chat/completions?key=secret", "http://127.0.0.1:8790/other"])
def test_gateway_must_be_explicit_loopback_before_secret(monkeypatch, url):
    monkeypatch.setattr("sys.argv", ["reply-wire", "--label", "offline", "--gateway-url", url])
    monkeypatch.setattr(Path, "read_text", lambda *a, **k: pytest.fail("secret read"))
    with pytest.raises(SystemExit) as stopped:
        wire.main()
    assert stopped.value.code == 2


@pytest.mark.parametrize("token", [None, "  \n", "fixture\nprivate", "fixture\x00private", "\u2603"])
def test_missing_or_empty_token_stops_before_fixture_creation(monkeypatch, tmp_path, token):
    if token is not None:
        (tmp_path / "gateway-token").write_text(token)
    monkeypatch.setattr("sys.argv", ["reply-wire", "--label", "offline", "--state-dir", str(tmp_path)])
    monkeypatch.setattr(wire, "request", lambda *a, **k: pytest.fail("fixture creation"))
    with pytest.raises(SystemExit) as stopped:
        wire.main()
    assert stopped.value.code == 2
    assert not (tmp_path / "offline.json").exists()


def test_explicit_state_gateway_and_summary_plumbing(monkeypatch, tmp_path):
    (tmp_path / "gateway-token").write_text("fixture-only")
    monkeypatch.setattr("sys.argv", ["reply-wire", "--label", "offline", "--cases", "social",
                                    "--state-dir", str(tmp_path), "--gateway-url", "http://127.0.0.1:9991/api/v1/chat/completions"])
    monkeypatch.setattr(wire.llm, "OPENROUTER_URL", wire.llm.OPENROUTER_URL)
    monkeypatch.setenv("ANTICIPY_SERVICE_TOKEN", "fixture-original")
    class Pool:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def map(self, run, selected):
            return [{"case": case[0], "passed": True} for case in selected]
    monkeypatch.setattr(wire, "ThreadPoolExecutor", Pool)
    monkeypatch.setattr(wire, "request", lambda *a, **k: pytest.fail("network"))
    with pytest.raises(SystemExit) as stopped:
        wire.main()
    assert stopped.value.code == 0
    assert wire.llm.OPENROUTER_URL == "http://127.0.0.1:9991/api/v1/chat/completions?audit_run=offline"
    evidence = json.loads((tmp_path / "offline.json").read_text())
    assert evidence["summary"]["selected_count"] == evidence["summary"]["completed_count"] == 1
    assert evidence["summary"]["passed"] is True


def test_model_failure_does_not_print_raw_provider_payload(monkeypatch, capsys):
    class ToxicResponse:
        status_code = object()
        @property
        def text(self):
            pytest.fail("raw provider body accessed")
    failure = RuntimeError("private-provider-payload")
    failure.response = ToxicResponse()
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr(wire.llm.LLM, "chat", fail)
    with pytest.raises(RuntimeError, match="^model_unavailable$"):
        wire.AuditLLM.chat(object())
    assert json.loads(capsys.readouterr().out) == {"category": "model_unavailable", "http_status": None}


def test_local_d1_uses_explicit_scratch_state_and_offline_settings(monkeypatch):
    seen = []
    monkeypatch.setattr(contract, "LOCAL_WRANGLER_CONFIG", "/fixture/wrangler.jsonc")
    monkeypatch.setenv("ANTICIPY_LOCAL_WRANGLER_PERSIST_TO", "/fixture/scratch-state")
    def run(command, **kwargs):
        seen.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout='[{"results":[]}]')
    monkeypatch.setattr(contract.subprocess, "run", run)
    assert contract.local_d1("SELECT 1") == []
    command, kwargs = seen[0]
    assert "--local" in command and "--remote" not in command
    assert command[command.index("--persist-to") + 1] == "/fixture/scratch-state"
    for name, value in [("CLOUDFLARE_LOAD_DEV_VARS_FROM_DOT_ENV", "false"), ("WRANGLER_SEND_METRICS", "false"), ("npm_config_offline", "true")]:
        assert kwargs["env"][name] == value


def test_selection_is_explicit_and_summary_cannot_pass_empty_or_partial():
    all_cases = wire.select_cases(None)
    selected = wire.select_cases("social, yes_one")
    assert [case[0] for case in all_cases] == [case[0] for case in wire.CASES]
    assert [case[0] for case in selected] == ["social", "yes_one"]
    results = [{"case": case[0], "passed": True} for case in selected]
    summary = wire.summarize_results(selected, results)
    assert summary == {"selected_cases": ["social", "yes_one"], "completed_cases": ["social", "yes_one"],
                       "selected_count": 2, "completed_count": 2, "passed_count": 2,
                       "failed_count": 0, "passed": True}
    for chosen, observed in [([], []), (selected, []), (selected, results[:1]),
                              (selected, [results[0], results[0]]),
                              (selected, [{"case": "social", "passed": 1}, results[1]]),
                              (selected, [{"case": "social", "passed": False}, results[1]])]:
        assert wire.summarize_results(chosen, observed)["passed"] is False


def legacy_queue(path):
    """Compile the one override; never import legacy dotenv/bootstrap/main."""
    tree = ast.parse((ROOT / path).read_text())
    method = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_queue_job")
    posted = []
    def post(*args, **kwargs):
        posted.append(kwargs["json"])
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"id": "fixture-job"})
    namespace = {"json": json, "requests": SimpleNamespace(post=post), "IRREVERSIBLE": set(),
                 "is_consequential": lambda *a: False, "BASE": "http://127.0.0.1:8090",
                 "CURRENT_START_URL": "https://example.invalid", "START_URL": "https://example.invalid"}
    exec(compile(ast.Module(body=[method], type_ignores=[]), path, "exec"), namespace)
    return namespace["_queue_job"], posted


@pytest.mark.parametrize("path", ["proof/run_conversational.py", "proof/run_e2e_scenarios.py"])
def test_legacy_queue_accepts_current_effect_contract_and_holds_world(path):
    queue, posted = legacy_queue(path)
    owner = SimpleNamespace(owner_id="fixture", backend_url="http://127.0.0.1:8090")
    inspect.signature(queue).bind(owner, "fixture task", {}, touches="read", act=None)
    for effect, status in [("read", "queued"), ("compute", "queued"), ("world", "awaiting_confirm")]:
        assert queue(owner, "fixture task", {}, touches=effect) == "fixture-job"
        assert posted[-1]["status"] == status
        assert json.loads(posted[-1]["params"])["_effect"]["touches"] == effect
    count = len(posted)
    with pytest.raises(ValueError):
        queue(owner, "fixture task", {}, touches="invalid")
    with pytest.raises(ValueError):
        queue(owner, "fixture task", {}, act=object())
    assert len(posted) == count


@pytest.mark.parametrize("method", [name for name in vars(contract.TestSmsInbound) if name.startswith("test_")])
def test_retired_carrier_contract_accepts_only_410_and_checks_no_row(monkeypatch, method):
    calls, reads = [], []
    monkeypatch.setattr(contract, "LOCAL_WRANGLER_CONFIG", "fixture-config")
    monkeypatch.setattr(contract, "SMS_OWNER_PHONE", "+15550100001")
    monkeypatch.setattr(contract, "SMS_OWNER_REF", "fixture-owner")
    monkeypatch.setattr(contract, "TWILIO_TEST_AUTH_TOKEN", "")
    def call(*args, **kwargs):
        calls.append((args, kwargs))
        return contract.Response(410, {"Content-Type": "application/json"},
                                 b'{"error":"messaging_endpoint_retired"}', "http://127.0.0.1/sms/inbound")
    monkeypatch.setattr(contract, "call", call)
    monkeypatch.setattr(contract, "sms_rows", lambda key: reads.append(key) or [])
    getattr(contract.TestSmsInbound(), method)()
    assert calls and reads
    assert all(args[:2] == ("POST", "/sms/inbound") for args, _ in calls)
    monkeypatch.setattr(contract, "call", lambda *a, **k: contract.Response(200, {}, b'{}', "fixture"))
    with pytest.raises(AssertionError):
        getattr(contract.TestSmsInbound(), method)()
