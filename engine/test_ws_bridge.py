"""
Unit tests for app.ws_bridge.

Mocks the underlying WebSocket entirely. We verify:
  - command shape (type/cmdId/args) on the wire
  - cmdId-keyed result delivery
  - cancel raises TaskCancelled on subsequent calls
  - timeout raises BridgeTimeout
  - extract / get_url / get_dom_snapshot pull through cleanly
  - close while pending fails the awaiter with BridgeClosed
"""

from __future__ import annotations

import asyncio
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

from app.ws_bridge import (  # noqa: E402
    BridgeClosed,
    BridgeTimeout,
    CommandFailed,
    TaskCancelled,
    WSBridge,
)


class FakeWebSocket:
    """Drop-in stand-in for fastapi.WebSocket. Captures sent JSON frames
    in ``self.sent`` and lets tests synthesize inbound replies."""

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.send_should_fail = False

    async def send_json(self, payload: dict) -> None:
        if self.send_should_fail:
            raise RuntimeError("simulated send failure")
        self.sent.append(payload)


# ─────────────────────────────────────────────────────────────────────
# Command shape on the wire
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_navigate_sends_correct_shape_and_returns_data():
    ws = FakeWebSocket()
    bridge = WSBridge(ws)

    async def reply():
        # Wait until the navigate has been sent
        for _ in range(50):
            if ws.sent:
                break
            await asyncio.sleep(0.01)
        cmd_id = ws.sent[-1]["cmdId"]
        await bridge._handle_incoming({
            "type": "result",
            "cmdId": cmd_id,
            "ok": True,
            "data": {"navigated": True, "url": "https://example.com"},
        })

    task = asyncio.create_task(reply())
    result = await bridge.navigate("https://example.com")
    await task

    assert ws.sent[-1]["type"] == "navigate"
    assert ws.sent[-1]["url"] == "https://example.com"
    assert "cmdId" in ws.sent[-1]
    assert result == {"navigated": True, "url": "https://example.com"}


@pytest.mark.asyncio
async def test_click_sends_selector():
    ws = FakeWebSocket()
    bridge = WSBridge(ws)

    async def reply():
        for _ in range(50):
            if ws.sent:
                break
            await asyncio.sleep(0.01)
        cmd_id = ws.sent[-1]["cmdId"]
        await bridge._handle_incoming({
            "type": "result", "cmdId": cmd_id, "ok": True, "data": {"clicked": True},
        })

    task = asyncio.create_task(reply())
    await bridge.click("button.submit")
    await task

    assert ws.sent[-1]["type"] == "click"
    assert ws.sent[-1]["selector"] == "button.submit"


@pytest.mark.asyncio
async def test_type_includes_text_and_submit():
    ws = FakeWebSocket()
    bridge = WSBridge(ws)

    async def reply():
        for _ in range(50):
            if ws.sent:
                break
            await asyncio.sleep(0.01)
        cmd_id = ws.sent[-1]["cmdId"]
        await bridge._handle_incoming({
            "type": "result", "cmdId": cmd_id, "ok": True, "data": {},
        })

    task = asyncio.create_task(reply())
    await bridge.type("input#q", "hello world", submit=True)
    await task

    sent = ws.sent[-1]
    assert sent["type"] == "type"
    assert sent["selector"] == "input#q"
    assert sent["text"] == "hello world"
    assert sent["submit"] is True


@pytest.mark.asyncio
async def test_extract_returns_text_string():
    ws = FakeWebSocket()
    bridge = WSBridge(ws)

    async def reply():
        for _ in range(50):
            if ws.sent:
                break
            await asyncio.sleep(0.01)
        cmd_id = ws.sent[-1]["cmdId"]
        await bridge._handle_incoming({
            "type": "result", "cmdId": cmd_id, "ok": True,
            "data": {"text": "page text here"},
        })

    task = asyncio.create_task(reply())
    text = await bridge.extract()
    await task

    assert text == "page text here"
    assert ws.sent[-1]["type"] == "extract"


@pytest.mark.asyncio
async def test_get_url_pulls_from_dom_snapshot():
    ws = FakeWebSocket()
    bridge = WSBridge(ws)

    async def reply():
        for _ in range(50):
            if ws.sent:
                break
            await asyncio.sleep(0.01)
        cmd_id = ws.sent[-1]["cmdId"]
        await bridge._handle_incoming({
            "type": "result", "cmdId": cmd_id, "ok": True,
            "data": {"url": "https://example.com/page", "title": "T", "html": ""},
        })

    task = asyncio.create_task(reply())
    url = await bridge.get_url()
    await task

    assert url == "https://example.com/page"
    assert ws.sent[-1]["type"] == "getDOMSnapshot"


@pytest.mark.asyncio
async def test_create_tab_returns_int_tab_id():
    ws = FakeWebSocket()
    bridge = WSBridge(ws)

    async def reply():
        for _ in range(50):
            if ws.sent:
                break
            await asyncio.sleep(0.01)
        cmd_id = ws.sent[-1]["cmdId"]
        await bridge._handle_incoming({
            "type": "result", "cmdId": cmd_id, "ok": True, "tabId": 42,
        })

    task = asyncio.create_task(reply())
    tab_id = await bridge.create_tab("https://example.com")
    await task

    assert tab_id == 42


# ─────────────────────────────────────────────────────────────────────
# Cancel
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_inbound_raises_taskcancelled_on_pending():
    ws = FakeWebSocket()
    bridge = WSBridge(ws)

    async def cancel_after_send():
        for _ in range(50):
            if ws.sent:
                break
            await asyncio.sleep(0.01)
        await bridge._handle_incoming({"type": "cancel", "reason": "user_cancel"})

    cancel_task = asyncio.create_task(cancel_after_send())
    with pytest.raises(TaskCancelled) as exc:
        await bridge.navigate("https://example.com")
    await cancel_task
    assert "user_cancel" in str(exc.value) or "cancel" in str(exc.value).lower()
    assert bridge.cancelled is True


@pytest.mark.asyncio
async def test_command_after_cancel_raises_immediately():
    ws = FakeWebSocket()
    bridge = WSBridge(ws)
    bridge.mark_cancelled("test")
    with pytest.raises(TaskCancelled):
        await bridge.click("button")


# ─────────────────────────────────────────────────────────────────────
# Timeout
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_timeout_raises_bridgetimeout(monkeypatch):
    """Pin COMMAND_TIMEOUT_SECONDS to 0.05s and never reply."""
    from app import ws_bridge as ws_bridge_mod
    monkeypatch.setattr(ws_bridge_mod, "COMMAND_TIMEOUT_SECONDS", 0.05)

    ws = FakeWebSocket()
    bridge = WSBridge(ws)
    with pytest.raises(BridgeTimeout):
        await bridge.navigate("https://example.com")


# ─────────────────────────────────────────────────────────────────────
# Failure path
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_command_failed_raises_commandfailed():
    ws = FakeWebSocket()
    bridge = WSBridge(ws)

    async def reply():
        for _ in range(50):
            if ws.sent:
                break
            await asyncio.sleep(0.01)
        cmd_id = ws.sent[-1]["cmdId"]
        await bridge._handle_incoming({
            "type": "result", "cmdId": cmd_id, "ok": False, "error": "no such element",
        })

    task = asyncio.create_task(reply())
    with pytest.raises(CommandFailed) as exc:
        await bridge.click("nonexistent")
    await task
    assert "no such element" in str(exc.value)


# ─────────────────────────────────────────────────────────────────────
# Disconnect mid-pending
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_close_while_pending_raises_bridgeclosed():
    ws = FakeWebSocket()
    bridge = WSBridge(ws)

    async def closer():
        for _ in range(50):
            if ws.sent:
                break
            await asyncio.sleep(0.01)
        bridge.mark_closed()

    task = asyncio.create_task(closer())
    with pytest.raises((BridgeClosed, TaskCancelled)):
        await bridge.navigate("https://example.com")
    await task
    assert bridge.closed is True


# ─────────────────────────────────────────────────────────────────────
# Inbound dispatch — error frames + ping/pong
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_error_frame_with_cmdid_fails_pending():
    ws = FakeWebSocket()
    bridge = WSBridge(ws)

    async def reply():
        for _ in range(50):
            if ws.sent:
                break
            await asyncio.sleep(0.01)
        cmd_id = ws.sent[-1]["cmdId"]
        await bridge._handle_incoming({
            "type": "error", "cmdId": cmd_id, "message": "unknown command navigate",
        })

    task = asyncio.create_task(reply())
    with pytest.raises(CommandFailed) as exc:
        await bridge.navigate("https://example.com")
    await task
    assert "unknown command" in str(exc.value)


@pytest.mark.asyncio
async def test_ping_inbound_replies_with_pong():
    ws = FakeWebSocket()
    bridge = WSBridge(ws)
    await bridge._handle_incoming({"type": "ping", "t": 12345})
    assert any(s.get("type") == "pong" for s in ws.sent)


# ─────────────────────────────────────────────────────────────────────
# UI-only frames (no awaited reply)
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stream_step_emits_task_step_frame():
    ws = FakeWebSocket()
    bridge = WSBridge(ws)
    await bridge.stream_step(3, "Looking at the page...")
    assert ws.sent[-1]["type"] == "task_step"
    assert ws.sent[-1]["step"] == "Looking at the page..."
    assert ws.sent[-1]["stepIndex"] == 3
    assert ws.sent[-1]["message"] == "Looking at the page..."


@pytest.mark.asyncio
async def test_emit_done_emits_done_frame():
    ws = FakeWebSocket()
    bridge = WSBridge(ws)
    await bridge.emit_done(success=True, message="Hello", deliverable={"a": 1})
    last = ws.sent[-1]
    assert last["type"] == "done"
    assert last["success"] is True
    assert last["summary"] == "Hello"
    assert last["message"] == "Hello"
    assert last["deliverable"] == {"a": 1}


@pytest.mark.asyncio
async def test_late_result_after_timeout_does_not_crash(monkeypatch):
    """A result that arrives after the awaiter's timeout fired is dropped
    silently; nothing in the bridge should crash."""
    from app import ws_bridge as ws_bridge_mod
    monkeypatch.setattr(ws_bridge_mod, "COMMAND_TIMEOUT_SECONDS", 0.05)

    ws = FakeWebSocket()
    bridge = WSBridge(ws)
    with pytest.raises(BridgeTimeout):
        await bridge.navigate("https://example.com")
    # Now a stale result arrives — must not raise.
    cmd_id = ws.sent[-1]["cmdId"]
    await bridge._handle_incoming({
        "type": "result", "cmdId": cmd_id, "ok": True, "data": {},
    })


# ─────────────────────────────────────────────────────────────────────
# Multiple parallel commands — cmdId routing
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_parallel_commands_route_by_cmdid():
    ws = FakeWebSocket()
    bridge = WSBridge(ws)

    async def reply_when_two_sent():
        for _ in range(100):
            if len(ws.sent) >= 2:
                break
            await asyncio.sleep(0.01)
        # Reply to the second one first.
        await bridge._handle_incoming({
            "type": "result", "cmdId": ws.sent[1]["cmdId"], "ok": True,
            "data": {"text": "second"},
        })
        await bridge._handle_incoming({
            "type": "result", "cmdId": ws.sent[0]["cmdId"], "ok": True,
            "data": {"text": "first"},
        })

    asyncio.create_task(reply_when_two_sent())
    res = await asyncio.gather(
        bridge.extract("a"),
        bridge.extract("b"),
    )
    assert res[0] == "first"
    assert res[1] == "second"
