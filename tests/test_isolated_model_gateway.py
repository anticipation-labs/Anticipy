"""Transport/evaluation safety checks; never contact a model provider."""
import asyncio
from contextlib import contextmanager
import http.client
import json
import os
import socket
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
def actual_loopback_server(tmp_path, monkeypatch, *, lifetime=30):
    """Real HTTP handler/socket; intercept construction only to learn port 0."""
    instance = gateway(tmp_path, lifetime=lifetime)
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
        return {"id": "http-fixture", "choices": [], "usage": {"cost": 0.001}}

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
