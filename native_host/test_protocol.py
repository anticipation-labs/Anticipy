"""
Unit + integration tests for the v4 native-messaging stack.

Pure stdlib (unittest, asyncio, io) so it runs anywhere — no pytest, no
extra deps.

Coverage:
  - protocol.pack / unpack_message round-trip (small, large, unicode)
  - protocol.read_message / write_message with BytesIO streams
  - protocol.FrameTooLarge enforcement on both sides
  - protocol.IncompleteFrame on truncated streams
  - NativeBridge: command echo via a mock daemon-side responder
  - NativeBridge: cancel mid-command unblocks the awaiter
  - NativeBridge: timeout fires when responder doesn't reply
  - Daemon: task_start triggers orchestrator import (mock) and emits done

Run:  python -m unittest native_host.test_protocol -v
"""

from __future__ import annotations

import asyncio
import io
import json
import struct
import threading
import time
import unittest
from typing import Any

from . import protocol
from .native_bridge import (
    BridgeClosed,
    BridgeTimeout,
    CommandFailed,
    NativeBridge,
    TaskCancelled,
)


# ── protocol.py ─────────────────────────────────────────────────────────


class TestProtocolCodec(unittest.TestCase):
    def test_pack_small(self):
        frame = protocol.pack({"type": "hello"})
        self.assertEqual(frame[:4], struct.pack("<I", len(frame) - 4))
        self.assertEqual(json.loads(frame[4:].decode()), {"type": "hello"})

    def test_round_trip_unicode(self):
        obj = {"type": "task", "text": "find a flight — résumé café 你好"}
        frame = protocol.pack(obj)
        msg, leftover = protocol.unpack_message(frame)
        self.assertEqual(msg, obj)
        self.assertEqual(leftover, b"")

    def test_round_trip_two_frames(self):
        a = protocol.pack({"a": 1})
        b = protocol.pack({"b": 2})
        buf = a + b
        m1, rest = protocol.unpack_message(buf)
        self.assertEqual(m1, {"a": 1})
        m2, rest2 = protocol.unpack_message(rest)
        self.assertEqual(m2, {"b": 2})
        self.assertEqual(rest2, b"")

    def test_partial_frame_returns_none(self):
        frame = protocol.pack({"hello": "world"})
        truncated = frame[:6]  # half a payload
        msg, leftover = protocol.unpack_message(truncated)
        self.assertIsNone(msg)
        self.assertEqual(leftover, truncated)

    def test_pack_rejects_too_large(self):
        big = "x" * (protocol.MAX_PAYLOAD + 10)
        with self.assertRaises(protocol.FrameTooLarge):
            protocol.pack({"big": big})

    def test_unpack_rejects_declared_too_large(self):
        # Forge a header claiming a 2 MiB frame.
        header = struct.pack("<I", protocol.MAX_PAYLOAD + 1)
        with self.assertRaises(protocol.FrameTooLarge):
            protocol.unpack_message(header)

    def test_read_write_stream(self):
        sink = io.BytesIO()
        protocol.write_message(sink, {"type": "ping"})
        sink.seek(0)
        msg = protocol.read_message(sink)
        self.assertEqual(msg, {"type": "ping"})

    def test_read_message_incomplete(self):
        sink = io.BytesIO(struct.pack("<I", 100) + b"only-a-bit")
        with self.assertRaises(protocol.IncompleteFrame):
            protocol.read_message(sink)

    def test_malformed_json(self):
        bad = struct.pack("<I", 5) + b"\xff\xff\xff\xff\xff"
        with self.assertRaises(protocol.MalformedJSON):
            protocol.unpack_message(bad)


# ── NativeBridge integration ────────────────────────────────────────────


class _DuplexPipe:
    """A pair of BytesIO streams that can be read like real stdin/stdout.

    Daemon reads from `daemon_in` and writes to `daemon_out`.  Test code
    writes to `daemon_in` and reads from `daemon_out`.  Read is blocking
    until enough bytes arrive — implemented with a Condition.
    """

    def __init__(self) -> None:
        self._daemon_in = _BlockingByteStream()
        self._daemon_out = _BlockingByteStream()

    @property
    def daemon_in(self):
        return self._daemon_in

    @property
    def daemon_out(self):
        return self._daemon_out


class _BlockingByteStream:
    """File-like object that blocks on read until enough bytes have been
    written.  Read returns b"" on close (matches EOF semantics)."""

    def __init__(self) -> None:
        self._buf = bytearray()
        self._cond = threading.Condition()
        self._closed = False

    def write(self, data: bytes) -> int:
        with self._cond:
            self._buf.extend(data)
            self._cond.notify_all()
        return len(data)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    def read(self, n: int) -> bytes:
        with self._cond:
            while len(self._buf) < n and not self._closed:
                self._cond.wait(timeout=2.0)
                if len(self._buf) < n and self._closed:
                    break
            if not self._buf and self._closed:
                return b""
            out = bytes(self._buf[:n])
            del self._buf[:n]
            return out


class TestNativeBridge(unittest.IsolatedAsyncioTestCase):
    async def _make_bridge(self):
        pipe = _DuplexPipe()
        bridge = NativeBridge(stdin=pipe.daemon_in, stdout=pipe.daemon_out)
        bridge.start_reader()
        return bridge, pipe

    async def asyncTearDown(self):
        # Give reader threads a moment to wind down.
        await asyncio.sleep(0.05)

    async def test_command_round_trip(self):
        bridge, pipe = await self._make_bridge()

        async def responder():
            # Sit on the daemon_out stream — that's what the bridge writes
            # commands TO.  Read one full frame, then write a result back
            # on daemon_in (which the bridge reads).
            await asyncio.get_event_loop().run_in_executor(None, _read_one_frame, pipe.daemon_out)
            # We just read it; now respond.  Use the same cmdId — pluck
            # from the parsed body. Actually we need to inspect first:
            # restart by reading again? Simpler: parse the frame we read.

        # Restart with a cleaner pattern — issue command, mock responder
        # reads cmdId, replies with matching result.
        pipe = _DuplexPipe()
        bridge = NativeBridge(stdin=pipe.daemon_in, stdout=pipe.daemon_out)
        bridge.start_reader()

        async def auto_respond():
            # Read the frame the bridge wrote to daemon_out.
            sent = await asyncio.get_event_loop().run_in_executor(
                None, _read_one_frame, pipe.daemon_out,
            )
            cmd_id = sent.get("cmdId")
            # Write a result frame to daemon_in for the bridge to consume.
            protocol.write_message(pipe.daemon_in, {
                "type": "result", "cmdId": cmd_id, "ok": True,
                "data": {"navigatedTo": sent.get("url")},
            })

        responder_task = asyncio.create_task(auto_respond())
        result = await bridge.navigate("https://example.com")
        await responder_task
        self.assertEqual(result, {"navigatedTo": "https://example.com"})
        await bridge.aclose()

    async def test_command_failure_propagates(self):
        pipe = _DuplexPipe()
        bridge = NativeBridge(stdin=pipe.daemon_in, stdout=pipe.daemon_out)
        bridge.start_reader()

        async def auto_respond_fail():
            sent = await asyncio.get_event_loop().run_in_executor(
                None, _read_one_frame, pipe.daemon_out,
            )
            protocol.write_message(pipe.daemon_in, {
                "type": "result", "cmdId": sent["cmdId"], "ok": False,
                "error": "selector not found: #missing",
            })

        responder_task = asyncio.create_task(auto_respond_fail())
        with self.assertRaises(CommandFailed) as cm:
            await bridge.click("#missing")
        await responder_task
        self.assertIn("selector not found", str(cm.exception))
        await bridge.aclose()

    async def test_cancel_unblocks_pending_command(self):
        pipe = _DuplexPipe()
        bridge = NativeBridge(stdin=pipe.daemon_in, stdout=pipe.daemon_out)
        bridge.start_reader()

        async def cancel_after_50ms():
            await asyncio.sleep(0.05)
            protocol.write_message(pipe.daemon_in, {"type": "cancel", "reason": "user"})

        # Drain whatever the bridge writes so it doesn't block forever
        async def drain():
            await asyncio.get_event_loop().run_in_executor(
                None, _read_one_frame, pipe.daemon_out,
            )

        drain_task = asyncio.create_task(drain())
        cancel_task = asyncio.create_task(cancel_after_50ms())
        with self.assertRaises(TaskCancelled):
            await bridge.navigate("https://slow.example")
        await drain_task
        await cancel_task
        self.assertTrue(bridge.cancelled)
        self.assertEqual(bridge.cancel_reason, "user")
        await bridge.aclose()

    async def test_timeout_fires_when_no_reply(self):
        pipe = _DuplexPipe()
        bridge = NativeBridge(stdin=pipe.daemon_in, stdout=pipe.daemon_out)
        bridge.start_reader()

        # Drain bridge command so we don't deadlock.
        async def drain():
            await asyncio.get_event_loop().run_in_executor(
                None, _read_one_frame, pipe.daemon_out,
            )

        drain_task = asyncio.create_task(drain())
        with self.assertRaises(BridgeTimeout):
            await bridge._send_and_await({"type": "navigate", "url": "x"}, timeout=0.1)
        await drain_task
        await bridge.aclose()

    async def test_stream_step_writes_frame(self):
        pipe = _DuplexPipe()
        bridge = NativeBridge(stdin=pipe.daemon_in, stdout=pipe.daemon_out)
        bridge.start_reader()
        await bridge.stream_step(3, "Filling in the details...")
        # Read what was written.
        frame = await asyncio.get_event_loop().run_in_executor(
            None, _read_one_frame, pipe.daemon_out,
        )
        self.assertEqual(frame["type"], "task_step")
        self.assertEqual(frame["stepIndex"], 3)
        self.assertEqual(frame["message"], "Filling in the details...")
        await bridge.aclose()

    async def test_inbound_dispatch_for_non_result_frames(self):
        pipe = _DuplexPipe()
        bridge = NativeBridge(stdin=pipe.daemon_in, stdout=pipe.daemon_out)
        bridge.start_reader()
        seen: list[dict] = []

        async def on_in(msg: dict) -> None:
            seen.append(msg)

        bridge.on_inbound = on_in
        protocol.write_message(pipe.daemon_in, {"type": "task_start", "task": "find a flight"})
        # Wait for the reader thread → asyncio queue → on_inbound roundtrip.
        for _ in range(20):
            if seen:
                break
            await asyncio.sleep(0.05)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0]["type"], "task_start")
        await bridge.aclose()


def _read_one_frame(stream) -> dict:
    """Helper: blocking read of one frame from a BlockingByteStream."""
    return protocol.read_message(stream)


# ── Daemon end-to-end (mock orchestrator) ──────────────────────────────


class TestDaemonE2E(unittest.IsolatedAsyncioTestCase):
    async def test_task_start_triggers_orchestrator_and_emits_done(self):
        # Skip the orchestrator import test if engine package isn't on
        # sys.path — that's fine in unit-test only mode.
        try:
            from .anticipy_agent import Daemon  # type: ignore
        except Exception:
            self.skipTest("anticipy_agent not importable directly")
            return
        pipe = _DuplexPipe()
        bridge = NativeBridge(stdin=pipe.daemon_in, stdout=pipe.daemon_out)
        bridge.start_reader()
        daemon = Daemon(bridge)

        # Monkey-patch the orchestrator import inside _run_task by
        # injecting a fake module.
        import sys, types
        fake_app = types.ModuleType("app")
        fake_orch = types.ModuleType("app.orchestrator")

        async def fake_run_task(**kwargs):
            # Verify the bridge is the one we passed in.
            assert kwargs["bridge"] is bridge
            return {
                "success": True,
                "message": "Mock task done.",
                "deliverable": None,
                "task_kind": "generic",
                "steps_taken": 1,
                "cache_hit": False,
                "aborted_reason": "",
            }

        fake_orch.run_task = fake_run_task
        sys.modules["app"] = fake_app
        sys.modules["app.orchestrator"] = fake_orch
        fake_app.orchestrator = fake_orch  # type: ignore

        # Send task_start; daemon should run our fake orchestrator and emit done.
        await daemon._on_inbound({"type": "task_start", "task": "test task", "taskId": "t-1"})
        # Wait for the task to complete + emit done.
        if daemon.current_task is not None:
            await daemon.current_task
        # Read what was written to daemon_out.
        # First frame: emit_done from our fake.
        frame = await asyncio.get_event_loop().run_in_executor(
            None, _read_one_frame, pipe.daemon_out,
        )
        self.assertEqual(frame["type"], "done")
        self.assertTrue(frame["success"])
        self.assertEqual(frame["message"], "Mock task done.")
        await bridge.aclose()
        # Cleanup module table.
        del sys.modules["app.orchestrator"]
        del sys.modules["app"]


if __name__ == "__main__":
    unittest.main()
