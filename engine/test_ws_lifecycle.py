"""
End-to-end tests for the FastAPI `/ws/task` WebSocket handler.

Exercises the websocket via FastAPI's TestClient — no real LLM, no real
browser. Stubs `classify`, `execute_task`, `handle_chat`, `handle_question`
on `app.main` so the handler runs deterministically and fast.

Covers:

  - Auth gate (WS_REQUIRE_AUTH, query token vs in-band token, invalid token)
  - Frame validation (malformed JSON, non-dict, unknown msg_type, oversized)
  - Start-task input validation (empty, too long, blocked phrases)
  - Per-IP message-rate cap
  - Per-user concurrent-connection cap

Each test is one behavior; reset is in fixtures so they don't bleed.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass

# Required env BEFORE importing app.main or app.config
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("JWT_SECRET", "x" * 48)
os.environ.setdefault(
    "PROFILE_ENCRYPTION_KEY",
    "RoUzc1lJ3gkPkHrxoYQzv1trmEJSQbgo6mNhlQYgfJk=",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

from app import main as main_module  # noqa: E402
from app import auth as auth_module  # noqa: E402
from app import messages as msg  # noqa: E402
from app.config import (  # noqa: E402
    WS_MAX_MESSAGES_PER_MINUTE,
    WS_MAX_MESSAGE_BYTES,
    MAX_INPUT_LENGTH,
)


# --- Test stubs --------------------------------------------------------------


@dataclass
class _FakeClassification:
    category: str
    degraded: bool = False


async def _stub_classify_action(text, tracker):  # noqa: ARG001
    return _FakeClassification(category="action")


async def _stub_classify_chat(text, tracker):  # noqa: ARG001
    return _FakeClassification(category="chat")


async def _stub_handle_chat(text, tracker):  # noqa: ARG001
    return "stubbed-chat-reply"


async def _stub_handle_question(text, tracker):  # noqa: ARG001
    return "stubbed-question-reply"


async def _stub_execute_task(goal, send, receive_confirmation, user_id=None):  # noqa: ARG001
    """Send a single 'complete' frame and return — no browser, no LLM."""
    await send({"type": "complete", "message": "stubbed-execute-done"})


async def _stub_needs_clarification(text):  # noqa: ARG001
    """Skip the clarification gate so the action path actually reaches
    execute_task. Tests that need clarification can override per-test."""
    return None


# --- Fixtures ----------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_state():
    """Clear connection counters + rate buckets between tests so they don't
    bleed. Restored TRUST_FORWARDED_FOR too."""
    main_module._ws_connections_by_user.clear()
    main_module._ws_connections_by_ip.clear()
    main_module._ws_msg_timestamps.clear()
    main_module._task_timestamps.clear()
    main_module._last_rate_cleanup = 0.0
    main_module._last_ws_cleanup = 0.0
    saved_trust = os.environ.pop("TRUST_FORWARDED_FOR", None)
    yield
    if saved_trust is not None:
        os.environ["TRUST_FORWARDED_FOR"] = saved_trust
    else:
        os.environ.pop("TRUST_FORWARDED_FOR", None)


@pytest.fixture
def client():
    """A TestClient over the FastAPI app. Reused per-test."""
    return TestClient(main_module.app)


@pytest.fixture
def stubbed(monkeypatch):
    """Default stubs: classify→action, execute_task→one complete frame.
    Tests that need different behavior layer their own monkeypatches on top."""
    monkeypatch.setattr(main_module, "classify", _stub_classify_action)
    monkeypatch.setattr(main_module, "handle_chat", _stub_handle_chat)
    monkeypatch.setattr(main_module, "handle_question", _stub_handle_question)
    monkeypatch.setattr(main_module, "execute_task", _stub_execute_task)
    monkeypatch.setattr(main_module, "needs_clarification", _stub_needs_clarification)


def _valid_token() -> str:
    return auth_module._create_token("user-1", "alice")


# --- 1. Auth gate ------------------------------------------------------------


def test_ws_rejects_unauthenticated_when_auth_required(client, stubbed, monkeypatch):
    """With WS_REQUIRE_AUTH on, connecting without a token closes 4401."""
    monkeypatch.setattr(main_module, "WS_REQUIRE_AUTH", True)
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws/task") as ws:
            # First we receive the AUTH_REQUIRED error frame, then the close.
            err = ws.receive_json()
            assert err["type"] == "error"
            assert err["message"] == msg.AUTH_REQUIRED
            ws.receive_text()  # forces close to surface
    assert excinfo.value.code == 4401


def test_ws_accepts_valid_jwt_in_query_param(client, stubbed, monkeypatch):
    """With a valid token in the query string, a chat message round-trips."""
    monkeypatch.setattr(main_module, "WS_REQUIRE_AUTH", True)
    monkeypatch.setattr(main_module, "classify", _stub_classify_chat)
    token = _valid_token()
    with client.websocket_connect(f"/ws/task?token={token}") as ws:
        ws.send_text(json.dumps({"type": "start", "text": "hello"}))
        reply = ws.receive_json()
        assert reply["type"] == "complete"
        assert reply["message"] == "stubbed-chat-reply"


def test_ws_in_band_token_alone_does_not_satisfy_required_auth(client, stubbed, monkeypatch):
    """When WS_REQUIRE_AUTH=true, a connection without a query token is
    closed immediately (4401) before any in-band frame can be read. This
    documents the gate's pre-flight behavior: the in-band token path is
    only useful when auth is OPTIONAL (covered by the next test)."""
    monkeypatch.setattr(main_module, "WS_REQUIRE_AUTH", True)
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws/task") as ws:
            first = ws.receive_json()
            assert first["type"] == "error"
            assert first["message"] == msg.AUTH_REQUIRED
            ws.receive_text()  # forces the close to surface
    assert excinfo.value.code == 4401


def test_ws_accepts_valid_jwt_via_in_band_message(client, stubbed, monkeypatch):
    """When WS_REQUIRE_AUTH is off, the connection is admitted without a
    query token, and an in-band {"token": ...} field on the first message
    authenticates the user. After auth the per-user counter has been
    bumped, then released on disconnect."""
    monkeypatch.setattr(main_module, "WS_REQUIRE_AUTH", False)
    monkeypatch.setattr(main_module, "classify", _stub_classify_chat)
    token = _valid_token()
    with client.websocket_connect("/ws/task") as ws:
        # Send the token in-band, attached to a chat start.
        ws.send_text(json.dumps({"type": "start", "text": "hi", "token": token}))
        reply = ws.receive_json()
        assert reply["type"] == "complete"
        assert reply["message"] == "stubbed-chat-reply"
    # Counter should be back to zero on disconnect (release in finally).
    assert main_module._ws_connections_by_user.get("user-1", 0) == 0


def test_ws_rejects_invalid_jwt_in_query_param(client, stubbed, monkeypatch):
    """A bogus token in the query string is treated as no-auth: under
    WS_REQUIRE_AUTH=true the connection is closed with 4401."""
    monkeypatch.setattr(main_module, "WS_REQUIRE_AUTH", True)
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws/task?token=garbage-not-a-jwt") as ws:
            err = ws.receive_json()
            assert err["type"] == "error"
            assert err["message"] == msg.AUTH_REQUIRED
            ws.receive_text()
    assert excinfo.value.code == 4401


# --- 2. Frame validation -----------------------------------------------------


def test_ws_input_invalid_for_malformed_json(client, stubbed, monkeypatch):
    """Non-JSON text frames return INPUT_INVALID, connection stays open."""
    monkeypatch.setattr(main_module, "WS_REQUIRE_AUTH", False)
    with client.websocket_connect("/ws/task") as ws:
        ws.send_text("not-valid-json{{{")
        reply = ws.receive_json()
        assert reply["type"] == "error"
        assert reply["message"] == msg.INPUT_INVALID


def test_ws_input_invalid_for_non_dict_frame(client, stubbed, monkeypatch):
    """Valid JSON that isn't an object (e.g. an array) returns INPUT_INVALID."""
    monkeypatch.setattr(main_module, "WS_REQUIRE_AUTH", False)
    with client.websocket_connect("/ws/task") as ws:
        ws.send_text(json.dumps(["this", "is", "an", "array"]))
        reply = ws.receive_json()
        assert reply["type"] == "error"
        assert reply["message"] == msg.INPUT_INVALID


def test_ws_input_invalid_for_unknown_msg_type(client, stubbed, monkeypatch):
    """A msg_type the handler doesn't know about returns INPUT_INVALID."""
    monkeypatch.setattr(main_module, "WS_REQUIRE_AUTH", False)
    with client.websocket_connect("/ws/task") as ws:
        ws.send_text(json.dumps({"type": "totally-unknown-action"}))
        reply = ws.receive_json()
        assert reply["type"] == "error"
        assert reply["message"] == msg.INPUT_INVALID


def test_ws_rejects_oversized_frame(client, stubbed, monkeypatch):
    """A frame larger than WS_MAX_MESSAGE_BYTES returns INPUT_INVALID."""
    monkeypatch.setattr(main_module, "WS_REQUIRE_AUTH", False)
    huge = json.dumps({"type": "start", "text": "x" * (WS_MAX_MESSAGE_BYTES + 100)})
    assert len(huge) > WS_MAX_MESSAGE_BYTES
    with client.websocket_connect("/ws/task") as ws:
        ws.send_text(huge)
        reply = ws.receive_json()
        assert reply["type"] == "error"
        assert reply["message"] == msg.INPUT_INVALID


# --- 3. Start-task input validation ------------------------------------------


def test_ws_start_empty_text_is_ambiguous(client, stubbed, monkeypatch):
    """A start frame with empty/whitespace-only text returns AMBIGUOUS_REQUEST."""
    monkeypatch.setattr(main_module, "WS_REQUIRE_AUTH", False)
    with client.websocket_connect("/ws/task") as ws:
        ws.send_text(json.dumps({"type": "start", "text": "   "}))
        reply = ws.receive_json()
        assert reply["type"] == "error"
        assert reply["message"] == msg.AMBIGUOUS_REQUEST


def test_ws_start_too_long_text_rejected(client, stubbed, monkeypatch):
    """Text > MAX_INPUT_LENGTH returns INPUT_TOO_LONG before classify."""
    monkeypatch.setattr(main_module, "WS_REQUIRE_AUTH", False)
    too_long = "a" * (MAX_INPUT_LENGTH + 50)
    # Stay under the 8KB frame cap so the SIZE gate doesn't fire first.
    payload = json.dumps({"type": "start", "text": too_long})
    assert len(payload) <= WS_MAX_MESSAGE_BYTES
    with client.websocket_connect("/ws/task") as ws:
        ws.send_text(payload)
        reply = ws.receive_json()
        assert reply["type"] == "error"
        assert reply["message"] == msg.INPUT_TOO_LONG


def test_ws_start_blocked_phrase_returns_block_message(client, stubbed, monkeypatch):
    """A blocked phrase is caught by the deterministic safety floor and
    returns a 'complete' frame with a block-category message — not an
    'error' frame, because the user isn't doing anything wrong."""
    monkeypatch.setattr(main_module, "WS_REQUIRE_AUTH", False)
    with client.websocket_connect("/ws/task") as ws:
        ws.send_text(json.dumps({"type": "start", "text": "delete my account"}))
        reply = ws.receive_json()
        assert reply["type"] == "complete"
        # Match against any of the three category messages.
        assert reply["message"] in {
            msg.BLOCKED_ACTION,
            msg.PASSWORD_REQUEST_BLOCKED,
            msg.FINANCIAL_TRANSACTION_BLOCKED,
        }


# --- 4. Per-IP message-rate cap ----------------------------------------------


def test_ws_per_ip_message_rate_cap_throttles(client, stubbed, monkeypatch):
    """Once an IP exceeds WS_MAX_MESSAGES_PER_MINUTE, the next message
    receives RATE_LIMIT_WS instead of being processed."""
    monkeypatch.setattr(main_module, "WS_REQUIRE_AUTH", False)
    # Pre-fill the rate bucket so the very next inbound message trips the cap.
    # (TestClient connects from "testclient" host, so we mirror that.)
    import time as _t
    test_ip = "testclient"
    main_module._ws_msg_timestamps[test_ip] = [_t.time()] * (
        WS_MAX_MESSAGES_PER_MINUTE + 1
    )
    with client.websocket_connect("/ws/task") as ws:
        # Any frame triggers the rate check — use a malformed one so we
        # don't trigger any classification path.
        ws.send_text("anything")
        reply = ws.receive_json()
        assert reply["type"] == "error"
        assert reply["message"] == msg.RATE_LIMIT_WS


# --- 5. Per-user concurrent-connection cap -----------------------------------


def test_ws_per_user_connection_cap_rejects_extra(client, stubbed, monkeypatch):
    """After MAX_WS_CONCURRENT_PER_USER live connections, the next one is
    refused with code 4429."""
    monkeypatch.setattr(main_module, "WS_REQUIRE_AUTH", True)
    cap = main_module.MAX_WS_CONCURRENT_PER_USER
    token = _valid_token()
    open_sessions = []
    try:
        # Open `cap` connections successfully.
        for _ in range(cap):
            cm = client.websocket_connect(f"/ws/task?token={token}")
            ws = cm.__enter__()
            open_sessions.append((cm, ws))
        # The (cap+1)-th must fail with 4429.
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect(f"/ws/task?token={token}") as ws:
                err = ws.receive_json()
                assert err["type"] == "error"
                assert "user" in err["message"].lower()
                ws.receive_text()  # force close
        assert excinfo.value.code == 4429
    finally:
        for cm, _ws in open_sessions:
            try:
                cm.__exit__(None, None, None)
            except Exception:
                pass


# --- runner ------------------------------------------------------------------


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
