"""Isolated-runner controls only: no paid model, provider, or Worker calls."""
import json
import subprocess
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from proof.audit import run_isolated_task_flow as flow


def test_main_captures_launch_environment_before_scrubbing(monkeypatch, tmp_path):
    from brain import llm
    monkeypatch.setattr(llm, "OPENROUTER_URL", llm.OPENROUTER_URL)
    run_dir = tmp_path / "evidence"
    run_dir.mkdir()
    monkeypatch.setattr(flow.tempfile, "mkdtemp", lambda **kwargs: str(run_dir))
    monkeypatch.setattr(flow.os, "environ", {"PATH": "/fixture/node/bin:/usr/bin:/bin",
        "HOME": "/fixture/home", "OPENROUTER_API_KEY": "must-not-inherit",
        "HTTP_PROXY": "must-not-inherit"})
    monkeypatch.setattr("sys.argv", ["flow", "--smoke", "--cases", "private-draft"])
    seen = []
    class API:
        base = "http://127.0.0.1:18555"
        network = []
        def __init__(self, directory): pass
        def __enter__(self): seen.append(dict(flow.os.environ)); return self
        def __exit__(self, *args): pass
    monkeypatch.setattr(flow, "LocalAPI", API)
    monkeypatch.setattr(flow, "run_case", lambda *args, **kwargs: {"passed": True, "fixture_deleted": True})
    with pytest.raises(SystemExit) as stopped:
        flow.main()
    assert stopped.value.code == 0
    assert seen[0]["PATH"] == "/fixture/node/bin:/usr/bin:/bin"
    assert seen[0]["OPENROUTER_API_KEY"] == ""
    assert "HTTP_PROXY" not in seen[0]
    assert json.loads((run_dir / "result.json").read_text())["full_product_verified"] is False


@pytest.mark.parametrize("phase", ["schema", "spawn"])
def test_failed_enter_closes_log_and_never_leaves_process(monkeypatch, tmp_path, phase):
    calls = []
    def spawn(command, **kwargs):
        calls.append(command)
        if len(calls) == 2: raise OSError("fixture")
        return SimpleNamespace(pid=99999999, wait=lambda **kwargs: 1 if phase == "schema" else 0)
    monkeypatch.setattr(flow.subprocess, "Popen", spawn)
    monkeypatch.setattr(flow.os, "killpg", lambda *args: None)
    api = flow.LocalAPI(tmp_path, port=18601)
    with pytest.raises((RuntimeError, OSError)):
        with api: pytest.fail("failed startup entered the body")
    assert api.process is None
    assert api.log is not None and api.log.closed
    assert (tmp_path / "workerd.log").exists(), "startup evidence must survive"


def test_child_env_and_worker_options_disable_credential_autoload(monkeypatch, tmp_path):
    monkeypatch.setenv("SENDBLUE_API_KEY", "must-not-inherit")
    calls = []
    process = SimpleNamespace(pid=99999999, poll=lambda: None, wait=lambda **kw: 0)
    monkeypatch.setattr(flow.subprocess, "Popen", lambda command, **kw: calls.append((command, kw)) or process)
    monkeypatch.setattr(flow.os, "killpg", lambda *args: None)
    monkeypatch.setattr(flow.httpx, "get", lambda *args, **kw: SimpleNamespace(status_code=200))
    with flow.LocalAPI(tmp_path, port=18601): pass
    for command, kwargs in calls:
        assert "--local" in command and "--remote" not in command
        assert "SENDBLUE_API_KEY" not in kwargs["env"]
        assert kwargs["env"]["CLOUDFLARE_LOAD_DEV_VARS_FROM_DOT_ENV"] == "false"
        assert kwargs["env"]["CLOUDFLARE_INCLUDE_PROCESS_ENV"] == "false"
    command, kwargs = calls[-1]
    assert command[command.index("--env-file") + 1] == "/dev/null"
    assert kwargs["start_new_session"] is True


def test_schema_timeout_kills_own_group_and_preserves_log(monkeypatch, tmp_path):
    waits, killed = [], []
    def wait(timeout):
        waits.append(timeout)
        if len(waits) == 1: raise subprocess.TimeoutExpired("fixture", timeout)
        return 0
    monkeypatch.setattr(flow.subprocess, "Popen", lambda *args, **kwargs:
        SimpleNamespace(pid=99999999, wait=wait))
    monkeypatch.setattr(flow.os, "killpg", lambda *args: killed.append(args))
    api = flow.LocalAPI(tmp_path, port=18601)
    with pytest.raises(subprocess.TimeoutExpired): api.__enter__()
    assert killed == [(99999999, flow.signal.SIGTERM)]
    assert waits == [40, 8]
    assert api.process is None and api.log.closed
    assert (tmp_path / "workerd.log").exists()


def test_worker_readiness_failure_also_stops_child_and_closes_log(monkeypatch, tmp_path):
    spawned, killed = [], []
    def spawn(*args, **kwargs):
        pid = 99999990 + len(spawned)
        process = SimpleNamespace(pid=pid, wait=lambda **kwargs: 0, poll=lambda: None)
        spawned.append(process)
        return process
    clock = iter([0, 100])
    monkeypatch.setattr(flow.subprocess, "Popen", spawn)
    monkeypatch.setattr(flow.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(flow.os, "killpg", lambda *args: killed.append(args))
    api = flow.LocalAPI(tmp_path, port=18601)
    with pytest.raises(RuntimeError, match="Local Worker did not become ready"): api.__enter__()
    assert [pid for pid, _ in killed] == [process.pid for process in spawned]
    assert api.process is None and api.log.closed


def test_shutdown_escalates_only_its_own_unresponsive_process_group(monkeypatch, tmp_path):
    waits, killed = [], []
    def wait(timeout):
        waits.append(timeout)
        if len(waits) == 1: raise subprocess.TimeoutExpired("fixture", timeout)
        return 0
    api = flow.LocalAPI(tmp_path)
    api.process = SimpleNamespace(pid=99999999, wait=wait)
    monkeypatch.setattr(flow.os, "killpg", lambda *args: killed.append(args))
    api.__exit__(None, None, None)
    assert killed == [(99999999, flow.signal.SIGTERM), (99999999, flow.signal.SIGKILL)]
    assert waits == [8, 5]
    assert api.process is None


def test_api_request_rejects_cross_host_path_before_client(monkeypatch, tmp_path):
    monkeypatch.setattr(flow.httpx, "Client", lambda **kwargs: pytest.fail("request client created"))
    api = flow.LocalAPI(tmp_path)
    for path in ["https://example.invalid/", "//example.invalid/"]:
        with pytest.raises(ValueError): api.request("GET", path)


@pytest.mark.parametrize("value", ["https://api.example/api/v1/chat/completions",
    "http://127.0.0.1:8794/api/v1/chat/completions?key=x", "http://x@127.0.0.1:8794/api/v1/chat/completions",
    "http://127.0.0.1:8794/elsewhere"])
def test_nonlocal_or_secret_bearing_gateway_refused(value):
    with pytest.raises(ValueError): flow.local_gateway(value)


def test_safe_gateway_control():
    assert flow.local_gateway("http://127.0.0.1:8794/api/v1/chat/completions") == "http://127.0.0.1:8794/api/v1/chat/completions"


@pytest.mark.parametrize("collection", ["jobs", "events"])
def test_fixture_list_uses_exact_owner_filter_and_account_not_service(monkeypatch, tmp_path, collection):
    api = flow.LocalAPI(tmp_path)
    calls = []
    row = {"id": "fixture-row", "owner_ref": "fixture-owner"}
    def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"items": [row], "page": 1, "totalPages": 1, "totalItems": 1}
    monkeypatch.setattr(api, "request", request)
    assert api.owned_records(collection, "fixture-owner", "fixture-account-token") == [row]
    method, path, kwargs = calls[0]
    assert method == "GET" and urlsplit(path).path == f"/api/collections/{collection}/records"
    assert parse_qs(urlsplit(path).query) == {"filter": ['owner_ref="fixture-owner"'], "perPage": ["100"]}
    assert kwargs == {"token": "fixture-account-token"}


@pytest.mark.parametrize("response", [
    {"items": [{"owner_ref": "someone-else"}], "page": 1, "totalPages": 1, "totalItems": 1},
    {"items": [], "page": 1, "totalPages": 2, "totalItems": 101},
    {"items": [], "page": 2, "totalPages": 2, "totalItems": 0},
    {"items": "not-a-list", "page": 1, "totalPages": 1, "totalItems": 0},
    {"items": [], "page": 1, "totalPages": 0, "totalItems": 1},
])
def test_fixture_list_rejects_foreign_or_incomplete_observation(monkeypatch, tmp_path, response):
    api = flow.LocalAPI(tmp_path)
    monkeypatch.setattr(api, "request", lambda *args, **kwargs: response)
    with pytest.raises(AssertionError):
        api.owned_records("jobs", "fixture-owner", "fixture-account-token")


def test_fixture_list_accepts_an_explicit_complete_empty_page(monkeypatch, tmp_path):
    api = flow.LocalAPI(tmp_path)
    monkeypatch.setattr(api, "request", lambda *args, **kwargs:
        {"items": [], "page": 1, "totalPages": 0, "totalItems": 0})
    assert api.owned_records("jobs", "fixture-owner", "fixture-account-token") == []


@pytest.mark.parametrize("collection,owner", [("owners", "fixture"), ("../jobs", "fixture"), ("jobs", ""), ("jobs", None)])
def test_fixture_list_refuses_other_collections_or_missing_owner(monkeypatch, tmp_path, collection, owner):
    api = flow.LocalAPI(tmp_path)
    monkeypatch.setattr(api, "request", lambda *args, **kwargs: pytest.fail("request must not happen"))
    with pytest.raises(ValueError):
        api.owned_records(collection, owner, "fixture-account-token")


def test_failed_oracle_preserves_synthetic_observation_before_fixture_deletion(monkeypatch):
    from brain import anticipy_core, conversation, llm, memory, worker
    candidate = {"id": "fixture-job", "status": "done", "params": "{}",
                 "result": "A synthetic result without a valid receipt.", "owner_ref": "fixture-owner"}
    deleted = []
    class API:
        base = "http://127.0.0.1:18555"
        def request(self, method, path, *args, **kwargs):
            if path.endswith("auth-with-password"):
                return {"token": "fixture-token"}
            if path == "/me/delete":
                deleted.append(True)
                return {"account_deleted": True}
            return {"id": "fixture-owner" if "/owners/" in path else "fixture-input"}
        def owned_records(self, collection, owner_id, token):
            return [candidate] if collection == "jobs" else []
    class Core:
        def __init__(self, **kwargs): pass
        def hear(self, *args, **kwargs):
            return {"decision": SimpleNamespace(decision="act")}
    monkeypatch.setattr(anticipy_core, "Anticipy", Core)
    monkeypatch.setattr(llm, "LLM", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(memory, "Memory", lambda *args, **kwargs: None)
    monkeypatch.setattr(conversation, "Conversation", lambda *args, **kwargs: SimpleNamespace())
    monkeypatch.setattr(worker, "PB", worker.PB)
    monkeypatch.setattr(worker, "run_research_jobs", lambda *args: None)
    monkeypatch.setattr(worker, "report_finished_jobs", lambda *args: None)
    result = flow.run_case(API(), "private-draft")
    assert result["passed"] is False and result["failure_type"] == "KeyError"
    assert result["observed"] == {"jobs": [candidate], "events": []}
    assert result["fixture_deleted"] is True and deleted == [True]


def completed_server_fixture(text="Fixture draft: thank you for reviewing the blue folder.", *, research=False):
    """Actual server-work hash + actual Plan receipt, with scripted model text."""
    from brain import server_work
    from brain.workflow import Consequence, claim, new_plan, put_in_params, succeed
    replies = [json.dumps({"verdict": "research" if research else "compose", "reason": "Fixture approach."})]
    if not research:
        replies.append(text)
    replies.append(json.dumps({"verdict": "satisfied", "reason": "The fixture result is present."}))
    responses = iter(replies)
    model = SimpleNamespace(live=True, chat=lambda *a, **k: SimpleNamespace(text=next(responses)))
    def read(*args, **kwargs):
        if not research:
            pytest.fail("unexpected research")
        return {"ok": True, "result": text, "sources": [{"url": "https://fixture.invalid/source", "content": text}]}
    out = server_work.run("private draft", {"source": "Write a private fixture draft."}, model=model,
                          research_runner=read)
    assert out["ok"] is True
    plan = new_plan(owner_ref="fixture", lineage_key="input1", goal="private draft",
                    consequence=Consequence.READ_ONLY, source_event_id="input1")
    plan = claim(plan, expected_version=plan.version, actor_id="fixture-worker")
    plan = succeed(plan, lease_token=plan.lease.token, summary=out["result"],
                   evidence=out["evidence"], verified=out["verified"])
    params = put_in_params({"_server_work": {key: out[key] for key in ("approach", "verification", "candidate") if key in out}}, plan)
    return params, out["result"], plan.job_fields()["receipt"]


def test_unbound_receipt_cannot_pass_without_observing_actual_result():
    params, _, _ = completed_server_fixture()
    params["_workflow"]["receipt"]["evidence"] = ["unbound-fixture-evidence"]
    with pytest.raises(AssertionError):
        flow.verify_task_lineage(params, "input1")


@pytest.mark.parametrize("text", ["Fixture draft.", "Merci Camille pour ton aide hier. 🌱"])
def test_result_oracle_uses_actual_workflow_source_list_and_receipt(text):
    params, result, receipt = completed_server_fixture(text)
    flow.verify_task_lineage(params, "input1", result, receipt)
    with pytest.raises(AssertionError, match="lineage"):
        flow.verify_task_lineage(params, "different-input", result, receipt)
    params["_workflow"]["receipt"]["verified"] = False
    with pytest.raises(AssertionError, match="receipt"):
        flow.verify_task_lineage(params, "input1", result, receipt)


def test_research_receipt_preserves_exact_hash_bytes_and_trimmed_summary_contract():
    params, result, receipt = completed_server_fixture("\n  Fixture source result.  \n", research=True)
    assert result != result.strip()
    assert params["_workflow"]["receipt"]["summary"] == result.strip()
    assert "https://fixture.invalid/source" in params["_workflow"]["receipt"]["evidence"]
    flow.verify_task_lineage(params, "input1", result, receipt)
    with pytest.raises(AssertionError, match="hash"):
        flow.verify_task_lineage(params, "input1", result.strip(), receipt)


@pytest.mark.parametrize("evidence", [["unbound-fixture-evidence"], ["text-sha256:fixture"],
    ["text-sha256:" + "0" * 64], ["https://fixture.invalid/source"], []])
def test_unbound_or_forged_artifact_evidence_is_rejected(evidence):
    params, result, _ = completed_server_fixture()
    params["_workflow"]["receipt"]["evidence"] = evidence
    with pytest.raises(AssertionError):
        flow.verify_task_lineage(params, "input1", result, json.dumps(params["_workflow"]["receipt"]))


def test_an_extra_conflicting_artifact_hash_is_rejected():
    params, result, _ = completed_server_fixture()
    params["_workflow"]["receipt"]["evidence"].append("text-sha256:" + "0" * 64)
    with pytest.raises(AssertionError):
        flow.verify_task_lineage(params, "input1", result, json.dumps(params["_workflow"]["receipt"]))


@pytest.mark.parametrize("result", [None, "", "   ", 1, True, "Different output."])
def test_actual_result_must_match_receipted_text(result):
    params, _, receipt = completed_server_fixture()
    with pytest.raises(AssertionError):
        flow.verify_task_lineage(params, "input1", result, receipt)


@pytest.mark.parametrize("field,value", [("summary", "Different draft."), ("verified", False),
    ("evidence", ["text-sha256:" + "0" * 64])])
def test_d1_receipt_mirror_must_match_embedded_workflow(field, value):
    params, result, receipt = completed_server_fixture()
    changed = json.loads(receipt)
    changed[field] = value
    with pytest.raises(AssertionError):
        flow.verify_task_lineage(params, "input1", result, json.dumps(changed))


@pytest.mark.parametrize("receipt", [None, "", "not-json", "[]", "null", {}])
def test_malformed_d1_receipt_cannot_pass(receipt):
    params, result, _ = completed_server_fixture()
    with pytest.raises(AssertionError):
        flow.verify_task_lineage(params, "input1", result, receipt)


def test_even_matching_receipt_hash_does_not_certify_another_summary():
    params, result, _ = completed_server_fixture()
    params["_workflow"]["receipt"]["summary"] = "Different summary."
    with pytest.raises(AssertionError):
        flow.verify_task_lineage(params, "input1", result, json.dumps(params["_workflow"]["receipt"]))


@pytest.mark.parametrize("verdict", [None, "incomplete", "unavailable", "true"])
def test_server_work_verdict_must_still_be_satisfied(verdict):
    params, result, receipt = completed_server_fixture()
    params["_server_work"]["verification"]["verdict"] = verdict
    with pytest.raises(AssertionError):
        flow.verify_task_lineage(params, "input1", result, receipt)


@pytest.mark.parametrize("sources,evidence", [
    ("different-prefix-input1", ["proof"]), (["input1"], "not-a-list"),
    (["input1"], [""]), (["input1"], [1]), (["input1", None], ["proof"]),
])
def test_malformed_lineage_or_evidence_cannot_pass(sources, evidence):
    params, result, receipt = completed_server_fixture()
    params["_workflow"]["source_event_ids"] = sources
    params["_workflow"]["receipt"]["evidence"] = evidence
    with pytest.raises(AssertionError):
        flow.verify_task_lineage(params, "input1", result, receipt)
