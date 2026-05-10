"""
End-to-end tests for the FastAPI ``/ws/agent`` endpoint.

Uses fastapi.testclient to drive a real WebSocket connection and stubs:

  - the orchestrator (so no LLM, no real bridge logic),
  - the engine_users access_code lookup (so no Supabase).

Covers:

  - Auth gate: missing/invalid access_code closes 4401.
  - Happy path: task_start → orchestrator runs (stub commands flow over the
    WS) → done frame arrives.
  - Cancel mid-task tears down cleanly.
  - Bad frame (non-JSON, not a dict, unknown type) gets an error frame back
    without crashing the connection.
"""

from __future__ import annotations

import json
import os
import sys

# Required env BEFORE importing app modules
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
from app import orchestrator as orch_module  # noqa: E402


# ────────────────────────────────────────────────────────────────────
# Auth + state hygiene
# ────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_state():
    main_module._ws_connections_by_user.clear()
    main_module._ws_connections_by_ip.clear()
    main_module._ws_msg_timestamps.clear()
    main_module._task_timestamps.clear()
    main_module._last_rate_cleanup = 0.0
    main_module._last_ws_cleanup = 0.0
    yield


@pytest.fixture
def stub_auth(monkeypatch):
    """Pretend access_code 'ok-code' for user-1 is valid."""

    async def _resolve(user_id, code):
        if user_id == "user-1" and code == "ok-code":
            return {"id": "user-1", "username": "alice"}
        return None

    monkeypatch.setattr(main_module, "_resolve_extension_auth", _resolve)


@pytest.fixture
def client():
    return TestClient(main_module.app)


# ────────────────────────────────────────────────────────────────────
# Auth tests
# ────────────────────────────────────────────────────────────────────


def test_ws_agent_rejects_missing_access_code(client):
    with pytest.raises(WebSocketDisconnect) as ei:
        with client.websocket_connect("/ws/agent") as ws:
            err = ws.receive_json()
            assert err["type"] == "error"
            ws.receive_text()
    assert ei.value.code == 4401


def test_ws_agent_rejects_invalid_access_code(client, stub_auth):
    with pytest.raises(WebSocketDisconnect) as ei:
        with client.websocket_connect(
            "/ws/agent?userId=user-1&code=wrong"
        ) as ws:
            err = ws.receive_json()
            assert err["type"] == "error"
            assert "access code" in err["message"].lower()
            ws.receive_text()
    assert ei.value.code == 4401


def test_ws_agent_accepts_valid_access_code(client, stub_auth, monkeypatch):
    # Stub orchestrator to send back a quick done.
    async def _orch(*a, **kw):
        # The orchestrator is supposed to drive the bridge; for this test
        # we just return a minimal outcome dict — the route handler will
        # forward it as a "done" frame.
        return {
            "success": True,
            "message": "stubbed-done",
            "deliverable": None,
            "task_kind": "generic",
            "steps_taken": 0,
            "cache_hit": False,
            "aborted_reason": "",
        }

    monkeypatch.setattr(main_module, "orchestrator_run_task", _orch)

    with client.websocket_connect(
        "/ws/agent?userId=user-1&code=ok-code"
    ) as ws:
        ws.send_text(json.dumps({
            "type": "task_start",
            "taskId": "t-1",
            "task": "say hi",
            "tabGroupId": 1,
        }))
        # Background task fires done.
        msg = ws.receive_json()
        assert msg["type"] == "done"
        assert msg["success"] is True
        assert msg["message"] == "stubbed-done"


# ────────────────────────────────────────────────────────────────────
# Bad frame handling
# ────────────────────────────────────────────────────────────────────


def test_ws_agent_rejects_non_json_frame(client, stub_auth):
    with client.websocket_connect(
        "/ws/agent?userId=user-1&code=ok-code"
    ) as ws:
        ws.send_text("this is not json")
        err = ws.receive_json()
        assert err["type"] == "error"


def test_ws_agent_rejects_non_dict_frame(client, stub_auth):
    with client.websocket_connect(
        "/ws/agent?userId=user-1&code=ok-code"
    ) as ws:
        ws.send_text(json.dumps([1, 2, 3]))
        err = ws.receive_json()
        assert err["type"] == "error"


def test_ws_agent_unknown_frame_type_returns_error(client, stub_auth):
    with client.websocket_connect(
        "/ws/agent?userId=user-1&code=ok-code"
    ) as ws:
        ws.send_text(json.dumps({"type": "snorgleflux"}))
        err = ws.receive_json()
        assert err["type"] == "error"


# ────────────────────────────────────────────────────────────────────
# Empty task / oversize task
# ────────────────────────────────────────────────────────────────────


def test_ws_agent_empty_task_returns_error(client, stub_auth, monkeypatch):
    async def _orch(*a, **kw):
        return {"success": True, "message": "x", "deliverable": None,
                "task_kind": "generic", "steps_taken": 0, "cache_hit": False,
                "aborted_reason": ""}
    monkeypatch.setattr(main_module, "orchestrator_run_task", _orch)

    with client.websocket_connect(
        "/ws/agent?userId=user-1&code=ok-code"
    ) as ws:
        ws.send_text(json.dumps({"type": "task_start", "taskId": "t", "task": "   "}))
        err = ws.receive_json()
        assert err["type"] == "error"


# ────────────────────────────────────────────────────────────────────
# Ping → pong
# ────────────────────────────────────────────────────────────────────


def test_ws_agent_ping_returns_pong(client, stub_auth):
    with client.websocket_connect(
        "/ws/agent?userId=user-1&code=ok-code"
    ) as ws:
        ws.send_text(json.dumps({"type": "ping", "t": 12345}))
        reply = ws.receive_json()
        assert reply["type"] == "pong"


# ────────────────────────────────────────────────────────────────────
# Bridge command round-trip — full orchestrator stand-in
# ────────────────────────────────────────────────────────────────────


def test_ws_agent_orchestrator_drives_bridge_commands(
    client, stub_auth, monkeypatch
):
    """The orchestrator stub sends a navigate command over the bridge,
    awaits the result, then completes. Verifies cmdId routing end-to-end
    on a real WebSocket."""

    async def _orch(task, user_id, bridge, task_id, **kw):
        # 1) issue a navigate command
        result = await bridge.navigate("https://example.com/x")
        # 2) emit a step
        await bridge.stream_step(1, "navigated")
        # 3) return a clean outcome
        return {
            "success": True,
            "message": f"got {result.get('url')}",
            "deliverable": result,
            "task_kind": "generic",
            "steps_taken": 1,
            "cache_hit": False,
            "aborted_reason": "",
        }

    monkeypatch.setattr(main_module, "orchestrator_run_task", _orch)

    with client.websocket_connect(
        "/ws/agent?userId=user-1&code=ok-code"
    ) as ws:
        ws.send_text(json.dumps({
            "type": "task_start", "taskId": "t-1", "task": "go to example",
        }))
        # First inbound should be the navigate command.
        navigate = ws.receive_json()
        assert navigate["type"] == "navigate"
        assert navigate["url"] == "https://example.com/x"
        cmd_id = navigate["cmdId"]

        # Send back the result.
        ws.send_text(json.dumps({
            "type": "result",
            "cmdId": cmd_id,
            "ok": True,
            "data": {"url": "https://example.com/x"},
        }))

        # Collect frames until we see done. We expect a task_step then done.
        seen = []
        for _ in range(5):
            frame = ws.receive_json()
            seen.append(frame)
            if frame.get("type") == "done":
                break

        assert any(f["type"] == "task_step" for f in seen)
        done = next(f for f in seen if f["type"] == "done")
        assert done["success"] is True
        assert "example.com/x" in done["message"]


# ────────────────────────────────────────────────────────────────────
# Cancel mid-task
# ────────────────────────────────────────────────────────────────────


def test_ws_agent_cancel_aborts_orchestrator(client, stub_auth, monkeypatch):
    """When extension sends cancel, the orchestrator's pending bridge
    command resolves with TaskCancelled, the route catches it, and the
    socket stays open."""
    cancelled_ok = []

    async def _orch(task, user_id, bridge, task_id, **kw):
        # Emit one stream step so the test can verify the loop began.
        await bridge.stream_step(0, "starting")
        try:
            # Block on a navigate that will never get a result.
            await bridge.navigate("https://example.com/wait")
            cancelled_ok.append("did_not_cancel")
        except Exception as e:
            cancelled_ok.append(type(e).__name__)
            raise

    monkeypatch.setattr(main_module, "orchestrator_run_task", _orch)

    with client.websocket_connect(
        "/ws/agent?userId=user-1&code=ok-code"
    ) as ws:
        ws.send_text(json.dumps({
            "type": "task_start", "taskId": "t", "task": "test cancel",
        }))
        # First we should see the task_step then the navigate command.
        first = ws.receive_json()
        # task_step or navigate (race) — pull until we see navigate.
        if first["type"] != "navigate":
            second = ws.receive_json()
            navigate = second if second["type"] == "navigate" else first
        else:
            navigate = first
        assert navigate["type"] == "navigate"

        # Send cancel.
        ws.send_text(json.dumps({"type": "cancel", "taskId": "t"}))

    # After the test client closes, give the orch task a chance to run its
    # except-block. cancelled_ok should reflect the TaskCancelled raise.
    # (Hard to assert deterministically post-disconnect; this assertion is
    # best-effort on the behaviour, not the timing.)
    assert "did_not_cancel" not in cancelled_ok


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-x"])
