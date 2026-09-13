"""Transport/evaluation safety checks; never contact a model provider."""
import asyncio
from contextlib import contextmanager
import http.client
import json
import os
import socket
import sys
import threading

import httpx
import pytest

from proof.audit import isolated_model_gateway as gate


PRICING = {"fixture/model": {"context_length": 1000, "pricing": {
    "prompt": "0.000001", "completion": "0.000002"}}}
PAYLOAD = {"model": "fixture/model", "messages": [{"role": "user", "content": "hi"}]}


def gateway(tmp_path, **kwargs):
    return gate.IsolatedGateway(tmp_path, "private-test-key", PRICING, **kwargs)


def test_initialization_is_private_and_never_resets_evidence(tmp_path):
    instance = gateway(tmp_path)
    assert os.stat(tmp_path / "gateway-token").st_mode & 0o077 == 0
    before = (tmp_path / "spend.json").read_bytes()
    with pytest.raises(FileExistsError):
        gateway(tmp_path)
    assert (tmp_path / "spend.json").read_bytes() == before
    assert "private-test-key" not in before.decode()
    assert instance.budget.operating_limit == 5


def test_rejects_paid_addons_and_unknown_model_before_reservation(tmp_path):
    instance = gateway(tmp_path)
    for payload in ({**PAYLOAD, "plugins": []}, {**PAYLOAD, "model": "other"},
                    {**PAYLOAD, "tools": [None]}):
        with pytest.raises(gate.Refused):
            instance.handle(payload)
    assert json.loads((tmp_path / "spend.json").read_text())["calls"] == []


def test_success_reserves_before_io_and_records_cost(tmp_path, monkeypatch):
    instance = gateway(tmp_path, max_calls=1)
    async def fake(*args, **kwargs):
        state = json.loads((tmp_path / "spend.json").read_text())
        assert len(state["calls"]) == 1 and state["calls"][0]["state"] == "reserved"
        return {"id": "fixture", "choices": [], "usage": {"cost": 0.001}}
    monkeypatch.setattr(gate, "post_model", fake)
    assert instance.handle(PAYLOAD)["id"] == "fixture"
    with pytest.raises(gate.Refused, match="call limit"):
        instance.handle(PAYLOAD)
    state = json.loads((tmp_path / "spend.json").read_text())
    assert state["observed_cost_usd"] == 0.001


def test_unknown_charge_retained_and_further_calls_halted(tmp_path, monkeypatch):
    instance = gateway(tmp_path)
    async def fake(*args, **kwargs):
        raise RuntimeError("PRIVATE PROVIDER BODY")
    monkeypatch.setattr(gate, "post_model", fake)
    with pytest.raises(gate.Refused) as failure:
        instance.handle(PAYLOAD)
    assert "PRIVATE" not in str(failure.value)
    state = json.loads((tmp_path / "spend.json").read_text())
    assert state["calls"][0]["cost_usd"] is None
    assert state["calls"][0]["reserved_usd"] > 0 and state["halted"]
    with pytest.raises(gate.Refused):
        instance.handle(PAYLOAD)


@pytest.mark.parametrize("cost", [None, -1, float("nan"), True, 10])
def test_untrusted_or_over_reservation_cost_halts(tmp_path, monkeypatch, cost):
    instance = gateway(tmp_path)
    async def fake(*args, **kwargs):
        return {"choices": [], "usage": {"cost": cost}}
    monkeypatch.setattr(gate, "post_model", fake)
    with pytest.raises(gate.Refused):
        instance.handle(PAYLOAD)
    assert json.loads((tmp_path / "spend.json").read_text())["halted"]


def test_expired_run_cannot_dispatch(tmp_path):
    instance = gateway(tmp_path, lifetime=1)
    instance.deadline = 0
    with pytest.raises(gate.Refused, match="deadline"):
        instance.handle(PAYLOAD)


def test_inflight_call_receives_remaining_run_deadline(tmp_path, monkeypatch):
    instance = gateway(tmp_path, lifetime=1)
    observed = []
    async def fake(*args, **kwargs):
        observed.append(kwargs["timeout"])
        return {"choices": [], "usage": {"cost": 0.001}}
    monkeypatch.setattr(gate, "post_model", fake)
    instance.handle(PAYLOAD)
    assert len(observed) == 1 and 0 < observed[0] <= 1


def test_public_pricing_is_keyless_and_has_total_deadline():
    async def fake(request):
        assert "Authorization" not in request.headers
        await asyncio.sleep(1)
    with pytest.raises(gate.Refused, match="pricing"):
        asyncio.run(gate.fetch_pricing(transport=httpx.MockTransport(fake), timeout=0.02))


@pytest.mark.parametrize("status", [302, 402, 500])
def test_redirect_or_provider_error_body_never_forwarded(status):
    calls = []
    def fake(request):
        calls.append(str(request.url))
        return httpx.Response(status, headers={"Location": "https://elsewhere.invalid"},
                              text="PRIVATE PROVIDER BODY")
    with pytest.raises(gate.Refused) as failure:
        asyncio.run(gate.post_model("secret", {}, transport=httpx.MockTransport(fake)))
    assert len(calls) == 1 and "PRIVATE" not in str(failure.value)


def test_total_deadline_cancels_transport():
    cancelled = []
    async def fake(request):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(True)
    with pytest.raises(gate.Refused, match="deadline"):
        asyncio.run(gate.post_model("secret", {}, timeout=0.02, transport=httpx.MockTransport(fake)))
    assert cancelled == [True]


def test_oversized_response_refused():
    def fake(request):
        return httpx.Response(200, content=b"x" * (gate.MAX_RESPONSE_BYTES + 1))
    with pytest.raises(gate.Refused, match="response size"):
        asyncio.run(gate.post_model("secret", {}, transport=httpx.MockTransport(fake)))


def test_private_key_reader_does_not_source_env(tmp_path):
    path = tmp_path / "private.env"
    path.write_text("OPENROUTER_API_KEY=test-key\nANTICIPY_PB=https://production.invalid\n")
    path.chmod(0o600)
    assert gate.read_key(path) == "test-key"
    path.chmod(0o644)
    with pytest.raises(gate.Refused):
        gate.read_key(path)


@contextmanager
def actual_loopback_server(tmp_path, monkeypatch, *, lifetime=30, provider_cost=0.001,
                           **gateway_options):
    """Real HTTP handler/socket; intercept construction only to learn port 0."""
    instance = gateway(tmp_path, lifetime=lifetime, **gateway_options)
    actual_server_class = gate.ThreadingHTTPServer
    servers, errors, provider_calls = [], [], []
    ready = threading.Event()

    def capture_server(address, handler):
        server = actual_server_class(address, handler)
        servers.append(server)
        ready.set()
        return server

    async def provider(key, payload, **kwargs):
        assert key == "private-test-key"
        state = json.loads((tmp_path / "spend.json").read_text())
        assert state["calls"][-1]["state"] == "reserved"
        provider_calls.append(payload)
        return {"id": "http-fixture", "choices": [], "usage": {"cost": provider_cost}}

    def run():
        try:
            gate.serve(instance, 0)
        except BaseException as error:
            errors.append(error)
            ready.set()

    monkeypatch.setattr(gate, "ThreadingHTTPServer", capture_server)
    monkeypatch.setattr(gate, "post_model", provider)
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        assert ready.wait(3), "loopback server did not bind"
        assert not errors and len(servers) == 1
        server = servers[0]
        assert server.server_address[0] == "127.0.0.1"
        yield instance, server, thread, provider_calls
    finally:
        if servers and thread.is_alive():
            servers[0].shutdown()
        thread.join(3)
        assert not thread.is_alive() and not errors
        if servers:
            assert servers[0].socket.fileno() == -1


def http_post(port, body, *, auth=None, path="/api/v1/chat/completions", framing=None,
              end_input=False):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.putrequest("POST", path)
        if auth is not None:
            connection.putheader("Authorization", auth)
        for name, value in framing if framing is not None else [("Content-Length", str(len(body)))]:
            connection.putheader(name, value)
        connection.endheaders(body)
        if end_input:
            connection.sock.shutdown(socket.SHUT_WR)
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def test_actual_http_rejections_never_reserve_and_valid_call_reconciles(tmp_path, monkeypatch):
    with actual_loopback_server(tmp_path, monkeypatch) as (instance, server, _, provider_calls):
        port = server.server_address[1]
        auth = "Bearer " + instance.token
        body = json.dumps(PAYLOAD).encode()
        before = (tmp_path / "spend.json").read_bytes()
        cases = [
            ({}, 401),
            ({"auth": "Bearer incorrect-local-token"}, 401),
            ({"auth": auth, "path": "/not-a-model-route"}, 400),
            ({"auth": auth, "path": "/api/v1/chat/completions?other=1"}, 400),
            ({"auth": auth, "path": "/api/v1/chat/completions?audit_run=a&audit_run=b"}, 400),
            ({"auth": auth, "path": "/api/v1/chat/completions?audit_run=%0A"}, 400),
            ({"auth": auth, "body": b"{"}, 502),
            ({"auth": auth, "body": b"[]"}, 402),
            ({"auth": auth, "framing": [("Content-Length", "invalid")]}, 502),
            ({"auth": auth, "framing": [("Content-Length", "0")], "body": b""}, 402),
            ({"auth": auth, "framing": [("Content-Length", str(gate.MAX_REQUEST_BYTES + 1))],
              "body": b""}, 402),
            ({"auth": auth, "framing": [("Content-Length", str(len(body))),
                                          ("Transfer-Encoding", "chunked")]}, 402),
            ({"auth": auth, "framing": [("Content-Length", str(len(body) + 1))],
              "end_input": True}, 402),
        ]
        for options, expected_status in cases:
            options = dict(options)
            sent_body = options.pop("body", body)
            status, response = http_post(port, sent_body, **options)
            assert status == expected_status
            assert "error" in response and "private-test-key" not in json.dumps(response)
            assert provider_calls == []
            assert (tmp_path / "spend.json").read_bytes() == before

        status, response = http_post(port, body, auth=auth,
                                    path="/api/v1/chat/completions?audit_run=http-fixture")
        assert status == 200 and response["id"] == "http-fixture"
        assert len(provider_calls) == 1
        state = json.loads((tmp_path / "spend.json").read_text())
        assert len(state["calls"]) == 1 and state["calls"][0]["audit_run"] == "http-fixture"
        assert state["calls"][0]["state"] == "returned"
        assert state["observed_cost_usd"] == state["committed_estimate_usd"] == 0.001


def test_actual_http_run_deadline_closes_listener(tmp_path, monkeypatch):
    with actual_loopback_server(tmp_path, monkeypatch, lifetime=0.05) as (_, server, thread, provider_calls):
        port = server.server_address[1]
        thread.join(3)
        assert not thread.is_alive(), "run deadline did not stop the HTTP server"
        assert server.socket.fileno() == -1
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.5)
            assert probe.connect_ex(("127.0.0.1", port)) != 0
        assert provider_calls == []


def test_smaller_authorized_budget_is_used_and_cannot_restart_larger(tmp_path):
    instance = gateway(tmp_path, budget_usd=2, max_calls=20)
    state = json.loads((tmp_path / "spend.json").read_text())
    assert state["budget_usd"] == instance.budget.operating_limit == 2
    assert state["max_calls"] == instance.max_calls == 20
    assert state["lifetime_seconds"] == 1800
    before = (tmp_path / "spend.json").read_bytes()
    with pytest.raises(FileExistsError):
        gateway(tmp_path, budget_usd=5, max_calls=100)
    assert (tmp_path / "spend.json").read_bytes() == before


def test_full_context_reservation_over_selected_cap_stays_refused(tmp_path, monkeypatch):
    pricing = {"fixture/model": {"context_length": 1_000_000,
                               "pricing": {"prompt": "0.000003", "completion": "0.000015"}}}
    instance = gate.IsolatedGateway(tmp_path, "fixture-key", pricing, budget_usd=2, max_calls=20)
    calls = []
    async def provider(*args, **kwargs):
        calls.append(True)
    monkeypatch.setattr(gate, "post_model", provider)
    before = (tmp_path / "spend.json").read_bytes()
    with pytest.raises(gate.Refused, match="spending limit"):
        instance.handle(PAYLOAD)
    assert calls == [] and (tmp_path / "spend.json").read_bytes() == before


def test_journal_dollar_edit_cannot_raise_process_operating_cap(tmp_path, monkeypatch):
    pricing = {"fixture/model": {"context_length": 1_000_000,
                               "pricing": {"prompt": "0.000003", "completion": "0.000015"}}}
    instance = gate.IsolatedGateway(tmp_path, "fixture-key", pricing, budget_usd=2, max_calls=20)
    with instance.budget.locked() as state:
        state["budget_usd"] = 5
        gate.atomic_json(instance.budget.path, state)
    calls = []
    async def provider(*args, **kwargs):
        calls.append(True)
    monkeypatch.setattr(gate, "post_model", provider)
    with pytest.raises(gate.Refused, match="spending limit"):
        instance.handle(PAYLOAD)
    assert calls == [] and json.loads(instance.budget.path.read_text())["calls"] == []


@pytest.mark.parametrize("budget", [0, -1, 5.01, float("nan"), float("inf"),
                                   float("-inf"), True, "2", None])
def test_invalid_dollar_caps_fail_before_creating_state(tmp_path, budget):
    with pytest.raises(gate.Refused, match="bounds"):
        gateway(tmp_path, budget_usd=budget)
    assert not (tmp_path / "run-created").exists()
    assert not (tmp_path / "spend.json").exists()


@pytest.mark.parametrize("calls", [0, -1, 101, 1.5, float("nan"), float("inf"), True, "20", None])
def test_invalid_call_caps_fail_before_creating_state(tmp_path, calls):
    with pytest.raises(gate.Refused, match="bounds"):
        gateway(tmp_path, max_calls=calls)
    assert not (tmp_path / "run-created").exists()


@pytest.mark.parametrize("lifetime", [0, -1, 1801, float("nan"), float("inf"), True, "30", None])
def test_invalid_lifetime_fails_before_creating_state(tmp_path, lifetime):
    with pytest.raises(gate.Refused, match="bounds"):
        gateway(tmp_path, lifetime=lifetime)
    assert not (tmp_path / "run-created").exists()


def test_actual_http_honors_twenty_calls_and_reports_two_dollar_cap(tmp_path, monkeypatch, capsys):
    with actual_loopback_server(tmp_path, monkeypatch, budget_usd=2, max_calls=20) as (instance, server, _, calls):
        port = server.server_address[1]
        body, auth = json.dumps(PAYLOAD).encode(), "Bearer " + instance.token
        for _ in range(20):
            assert http_post(port, body, auth=auth)[0] == 200
        before = (tmp_path / "spend.json").read_bytes()
        status, response = http_post(port, body, auth=auth)
        assert status == 402 and "call limit" in response["error"]
        assert len(calls) == 20
        assert (tmp_path / "spend.json").read_bytes() == before
        report = json.loads(capsys.readouterr().out)
        assert report["budget_usd"] == 2 and report["max_calls"] == 20


def test_actual_http_honors_smaller_dollar_limit_before_dispatch(tmp_path, monkeypatch):
    with actual_loopback_server(tmp_path, monkeypatch, budget_usd=0.01,
                               max_calls=20, provider_cost=0.009) as (instance, server, _, calls):
        port = server.server_address[1]
        body, auth = json.dumps(PAYLOAD).encode(), "Bearer " + instance.token
        assert http_post(port, body, auth=auth)[0] == 200
        before = (tmp_path / "spend.json").read_bytes()
        status, response = http_post(port, body, auth=auth)
        assert status == 402 and "spending limit" in response["error"]
        assert len(calls) == 1
        assert (tmp_path / "spend.json").read_bytes() == before


def test_cli_passes_explicit_caps_into_real_gateway(tmp_path, monkeypatch):
    reads, served = [], []
    monkeypatch.setattr(gate, "read_key", lambda path: reads.append(path) or "fixture-key")
    async def pricing():
        return PRICING
    monkeypatch.setattr(gate, "fetch_pricing", pricing)
    monkeypatch.setattr(gate, "MODELS", set(PRICING))
    monkeypatch.setattr(gate, "serve", lambda instance, port: served.append((instance, port)))
    monkeypatch.setattr(sys, "argv", ["gateway", "--state-dir", str(tmp_path), "--env-file", "/fixture.env",
                                    "--budget-usd", "2", "--max-calls", "20", "--port", "18794"])
    gate.main()
    assert len(reads) == len(served) == 1
    instance, port = served[0]
    assert instance.budget.operating_limit == 2 and instance.max_calls == 20 and port == 18794
    assert json.loads((tmp_path / "spend.json").read_text())["max_calls"] == 20


@pytest.mark.parametrize("caps", [[], ["--budget-usd", "2"], ["--max-calls", "20"],
                                  ["--budget-usd", "nan", "--max-calls", "20"],
                                  ["--budget-usd", "2", "--max-calls", "1.5"],
                                  ["--budget-usd", "5.01", "--max-calls", "20"],
                                  ["--budget-usd", "2", "--max-calls", "0"]])
def test_cli_invalid_or_missing_caps_do_not_read_key_or_fetch_pricing(tmp_path, monkeypatch, caps):
    calls = []
    monkeypatch.setattr(gate, "read_key", lambda *a: calls.append("key"))
    async def pricing():
        calls.append("pricing")
    monkeypatch.setattr(gate, "fetch_pricing", pricing)
    monkeypatch.setattr(sys, "argv", ["gateway", "--state-dir", str(tmp_path), "--env-file", "/fixture.env", *caps])
    with pytest.raises(SystemExit) as failure:
        gate.main()
    assert failure.value.code == 2 and calls == []
    assert not (tmp_path / "run-created").exists()
