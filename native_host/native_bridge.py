"""
NativeBridge — drop-in replacement for ``engine.app.ws_bridge.WSBridge``
that speaks the Chrome native-messaging protocol over stdin/stdout
instead of a WebSocket.

API surface matches WSBridge so ``engine.app.orchestrator.run_task`` and
``engine.app.end_state_verifier.verify_at_done`` work unchanged.  We
re-export the same exception classes that ws_bridge defines, so import
sites in the orchestrator keep resolving.

Wire format: see ``protocol.pack`` / ``protocol.read_message``. Frames are
4-byte LE length prefix + UTF-8 JSON payload.

Threading model:
  - One background thread reads stdin into a buffer.
  - The asyncio loop pulls decoded frames off a queue.
  - All writes go through a single asyncio.Lock so two coroutines never
    interleave a frame.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
import uuid
from typing import Any

try:
    from . import protocol  # type: ignore
except (ImportError, ValueError):
    import protocol


logger = logging.getLogger("anticipy.bridge")


COMMAND_TIMEOUT_SECONDS: float = 30.0


# ── Errors (mirror ws_bridge for orchestrator compatibility) ────────────


class BridgeTimeout(Exception):
    pass


class TaskCancelled(Exception):
    pass


class BridgeClosed(Exception):
    pass


class CommandFailed(Exception):
    pass


# ── Bridge ──────────────────────────────────────────────────────────────


class NativeBridge:
    """Pumps frames between an asyncio task and the Chrome extension over
    stdio.  Replaces WSBridge in the daemon context.

    Usage:
        bridge = NativeBridge(loop=asyncio.get_event_loop())
        bridge.start_reader()
        try:
            await orchestrator.run_task(task, user_id, bridge, task_id)
        finally:
            await bridge.aclose()
    """

    def __init__(
        self,
        *,
        stdin: Any | None = None,
        stdout: Any | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        self._stdin = stdin if stdin is not None else sys.stdin.buffer
        self._stdout = stdout if stdout is not None else sys.stdout.buffer
        self._loop = loop or asyncio.get_event_loop()
        self._inbox: asyncio.Queue = asyncio.Queue()
        self._pending: dict[str, asyncio.Future] = {}
        self._send_lock = asyncio.Lock()
        self._cancelled = False
        self._cancel_reason = ""
        self._closed = False
        self._cancel_event = asyncio.Event()
        self._reader_thread: threading.Thread | None = None
        self._stop_reader = threading.Event()
        # Filled by callers (e.g. the daemon main loop) to receive
        # extension-initiated frames that aren't replies to a command.
        self.on_inbound: Any = None  # coroutine fn(msg) or None

    # ── Lifecycle hooks ────────────────────────────────────────────────

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def cancel_reason(self) -> str:
        return self._cancel_reason

    async def wait_cancel(self) -> None:
        await self._cancel_event.wait()

    def mark_cancelled(self, reason: str = "cancel") -> None:
        if self._cancelled:
            return
        self._cancelled = True
        self._cancel_reason = reason or "cancel"
        self._cancel_event.set()
        exc = TaskCancelled(self._cancel_reason)
        for cmd_id, fut in list(self._pending.items()):
            if not fut.done():
                fut.set_exception(exc)
            self._pending.pop(cmd_id, None)

    def mark_closed(self) -> None:
        if self._closed:
            return
        self._closed = True
        if not self._cancelled:
            self._cancel_reason = "stdio_closed"
            self._cancel_event.set()
        exc = BridgeClosed("stdio disconnected")
        for cmd_id, fut in list(self._pending.items()):
            if not fut.done():
                fut.set_exception(exc)
            self._pending.pop(cmd_id, None)

    async def aclose(self) -> None:
        self.mark_closed()
        self._stop_reader.set()

    # ── Reader thread → asyncio queue ──────────────────────────────────

    def start_reader(self) -> None:
        if self._reader_thread is not None:
            return
        self._reader_thread = threading.Thread(
            target=self._reader_loop, name="anticipy-stdin-reader", daemon=True,
        )
        self._reader_thread.start()

    def _reader_loop(self) -> None:
        while not self._stop_reader.is_set():
            try:
                msg = protocol.read_message(self._stdin)
            except protocol.IncompleteFrame:
                logger.info("stdin closed — extension disconnected")
                self._loop.call_soon_threadsafe(self.mark_closed)
                return
            except protocol.ProtocolError as exc:
                logger.warning("protocol error: %s", exc)
                continue
            except Exception:
                logger.exception("reader thread crashed")
                self._loop.call_soon_threadsafe(self.mark_closed)
                return
            self._loop.call_soon_threadsafe(self._dispatch_frame, msg)

    def _dispatch_frame(self, msg: Any) -> None:
        if not isinstance(msg, dict):
            return
        msg_type = msg.get("type")
        if msg_type == "result":
            cmd_id = msg.get("cmdId")
            fut = self._pending.get(cmd_id) if isinstance(cmd_id, str) else None
            if fut is not None and not fut.done():
                if msg.get("ok"):
                    fut.set_result({
                        "data": msg.get("data"),
                        "tabId": msg.get("tabId"),
                        "ok": True,
                    })
                else:
                    fut.set_exception(CommandFailed(str(msg.get("error") or "command failed")))
            return
        if msg_type == "cancel":
            self.mark_cancelled(str(msg.get("reason") or "cancel"))
            return
        if msg_type == "ping":
            # async write — schedule a pong
            asyncio.ensure_future(self._safe_send({"type": "pong"}), loop=self._loop)
            return
        # Other frames (popup:start_task, ready, etc.) go to the daemon's
        # main loop via the on_inbound hook.
        if self.on_inbound is not None:
            try:
                coro = self.on_inbound(msg)
                if asyncio.iscoroutine(coro):
                    asyncio.ensure_future(coro, loop=self._loop)
            except Exception:
                logger.exception("on_inbound raised")

    # ── Send plumbing ──────────────────────────────────────────────────

    async def _safe_send(self, payload: dict) -> None:
        try:
            await self._send(payload)
        except Exception:
            logger.debug("safe_send swallowed", exc_info=True)

    async def _send(self, payload: dict) -> None:
        if self._closed:
            raise BridgeClosed("bridge already closed")
        async with self._send_lock:
            try:
                # protocol.write_message is sync, so offload to executor.
                await self._loop.run_in_executor(None, protocol.write_message, self._stdout, payload)
            except Exception as exc:
                self.mark_closed()
                raise BridgeClosed(str(exc) or "send failed") from exc

    def _new_cmd_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def _check_state(self) -> None:
        if self._cancelled:
            raise TaskCancelled(self._cancel_reason or "cancelled")
        if self._closed:
            raise BridgeClosed("bridge already closed")

    async def _send_and_await(
        self,
        payload: dict,
        timeout: float | None = None,
    ) -> dict:
        self._check_state()
        if timeout is None:
            timeout = COMMAND_TIMEOUT_SECONDS
        cmd_id = self._new_cmd_id()
        payload = dict(payload)
        payload["cmdId"] = cmd_id
        fut: asyncio.Future = self._loop.create_future()
        self._pending[cmd_id] = fut
        try:
            await self._send(payload)
        except BridgeClosed:
            self._pending.pop(cmd_id, None)
            raise
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError as exc:
            self._pending.pop(cmd_id, None)
            raise BridgeTimeout(
                f"command {payload.get('type')!r} (cmdId={cmd_id}) timed out after {timeout:.1f}s"
            ) from exc
        finally:
            self._pending.pop(cmd_id, None)

    # ── BridgeProtocol surface (mirrors WSBridge) ──────────────────────

    async def navigate(
        self,
        url: str,
        *,
        use_active: bool = False,
        url_prefix: str = "",
    ) -> dict:
        result = await self._send_and_await({
            "type": "navigate",
            "url": url,
            "useActiveTab": bool(use_active),
            "urlPrefix": url_prefix,
        })
        data = result.get("data")
        return data if isinstance(data, dict) else {}

    async def click(
        self,
        selector: str,
        *,
        use_active: bool = False,
        url_prefix: str = "",
    ) -> dict:
        result = await self._send_and_await({
            "type": "click",
            "selector": selector,
            "useActiveTab": bool(use_active),
            "urlPrefix": url_prefix,
        })
        data = result.get("data")
        return data if isinstance(data, dict) else {}

    async def type(
        self,
        selector: str,
        text: str,
        *,
        submit: bool = False,
        use_active: bool = False,
        url_prefix: str = "",
    ) -> dict:
        result = await self._send_and_await({
            "type": "type",
            "selector": selector,
            "text": text,
            "submit": bool(submit),
            "useActiveTab": bool(use_active),
            "urlPrefix": url_prefix,
        })
        data = result.get("data")
        return data if isinstance(data, dict) else {}

    async def key(
        self,
        key: str,
        *,
        selector: str = "",
        code: str = "",
        modifiers: list[str] | None = None,
        use_active: bool = False,
        url_prefix: str = "",
    ) -> dict:
        result = await self._send_and_await({
            "type": "key",
            "key": key or "Enter",
            "code": code or "",
            "selector": selector or "",
            "modifiers": modifiers or [],
            "useActiveTab": bool(use_active),
            "urlPrefix": url_prefix,
        })
        data = result.get("data")
        return data if isinstance(data, dict) else {}

    async def extract(self, selector: str | None = None) -> str:
        result = await self._send_and_await({"type": "extract", "selector": selector})
        data = result.get("data")
        if isinstance(data, dict):
            t = data.get("text")
            if isinstance(t, str):
                return t
        if isinstance(data, str):
            return data
        return ""

    async def get_text(self, selector: str | None = None) -> str:
        return await self.extract(selector)

    async def read(self, selector: str | None = None) -> str:
        return await self.extract(selector)

    async def get_url(self, *, use_active: bool = False, url_prefix: str = "") -> str:
        result = await self._send_and_await({
            "type": "getDOMSnapshot",
            "limit": 0,
            "useActiveTab": bool(use_active),
            "urlPrefix": url_prefix,
        })
        data = result.get("data")
        if isinstance(data, dict):
            u = data.get("url")
            if isinstance(u, str):
                return u
        return ""

    async def get_dom_snapshot(
        self,
        *,
        limit: int | None = None,
        use_active: bool = False,
        url_prefix: str = "",
    ) -> str:
        payload: dict = {
            "type": "getDOMSnapshot",
            "useActiveTab": bool(use_active),
            "urlPrefix": url_prefix,
        }
        if isinstance(limit, int) and limit > 0:
            payload["limit"] = int(limit)
        result = await self._send_and_await(payload)
        data = result.get("data")
        if isinstance(data, dict):
            h = data.get("html")
            if isinstance(h, str):
                return h
        return ""

    async def screenshot(self, *, use_active: bool = False, url_prefix: str = "") -> str:
        result = await self._send_and_await({
            "type": "screenshot",
            "useActiveTab": bool(use_active),
            "urlPrefix": url_prefix,
        })
        data = result.get("data")
        if isinstance(data, dict):
            url = data.get("dataUrl")
            if isinstance(url, str):
                return url
        return ""

    async def create_tab(self, url: str | None = None) -> int:
        # In v4 there's no about:blank seed — the daemon must always supply
        # a real URL.  Refuse blank creates to keep the contract honest.
        if not url:
            raise CommandFailed("create_tab requires a real URL in v4 (no about:blank)")
        result = await self._send_and_await({"type": "create_tab", "url": url})
        tab_id = result.get("tabId")
        if isinstance(tab_id, int):
            return tab_id
        data = result.get("data")
        if isinstance(data, dict):
            inner = data.get("tabId")
            if isinstance(inner, int):
                return inner
        return 0

    async def close_tab(self, tab_id: int) -> None:
        await self._send_and_await({"type": "close_tab", "tabId": int(tab_id)})

    async def list_tabs(self) -> list[dict]:
        result = await self._send_and_await({"type": "list_tabs"})
        data = result.get("data")
        if isinstance(data, dict):
            tabs = data.get("tabs")
            if isinstance(tabs, list):
                return [tab for tab in tabs if isinstance(tab, dict)]
        return []

    async def close_tabs_matching(
        self,
        *,
        url_prefix: str = "",
        url_includes: str = "",
        title_includes: str = "",
        max_close: int = 10,
    ) -> dict:
        result = await self._send_and_await({
            "type": "close_tabs_matching",
            "urlPrefix": url_prefix,
            "urlIncludes": url_includes,
            "titleIncludes": title_includes,
            "maxClose": int(max_close),
        })
        data = result.get("data")
        return data if isinstance(data, dict) else {}

    async def wait_for_url(
        self,
        *,
        expected_url: str = "",
        contains: str = "",
        url_prefix: str = "",
        timeout: float = 10.0,
        interval: float = 0.25,
        use_active: bool = True,
    ) -> dict:
        deadline = self._loop.time() + max(0.0, float(timeout))
        observed = ""
        attempts = 0
        while True:
            attempts += 1
            observed = await self.get_url(
                use_active=use_active and not bool(url_prefix),
                url_prefix=url_prefix,
            )
            if expected_url and observed.rstrip("/") == expected_url.rstrip("/"):
                return {"ok": True, "url": observed, "attempts": attempts}
            if contains and contains in observed:
                return {"ok": True, "url": observed, "attempts": attempts}
            if self._loop.time() >= deadline:
                return {"ok": False, "url": observed, "attempts": attempts}
            await asyncio.sleep(max(0.05, float(interval)))

    # ── UI frames (no reply) ───────────────────────────────────────────

    async def stream_step(self, step: int, message: str) -> None:
        if self._cancelled or self._closed:
            return
        try:
            await self._send({
                "type": "task_step",
                "step": message or f"Step {step}",
                "stepIndex": int(step),
                "message": message or "",
            })
        except BridgeClosed:
            return

    async def emit_done(self, success: bool, message: str, deliverable: dict | None = None) -> None:
        if self._closed:
            return
        try:
            await self._send({
                "type": "done",
                "success": bool(success),
                "summary": message or "",
                "message": message or "",
                "deliverable": deliverable if isinstance(deliverable, dict) else None,
            })
        except BridgeClosed:
            return

    async def emit_error(self, message: str, *, cmd_id: str | None = None) -> None:
        if self._closed:
            return
        try:
            payload: dict = {"type": "error", "message": message or "error"}
            if cmd_id:
                payload["cmdId"] = cmd_id
            await self._send(payload)
        except BridgeClosed:
            return


__all__ = [
    "BridgeClosed",
    "BridgeTimeout",
    "COMMAND_TIMEOUT_SECONDS",
    "CommandFailed",
    "NativeBridge",
    "TaskCancelled",
]
