"""
WSBridge — adapter from the orchestrator loop to the thin-relay extension.

The extension at ``extension_v2/`` is a dumb DOM proxy. It opens one
WebSocket to ``/ws/agent``, accepts command messages keyed by ``cmdId``,
and echoes back ``{type: "result", cmdId, ok, data, error}``. This bridge
turns that protocol into the synchronous-looking ``BridgeProtocol``
contract that ``app.end_state_verifier`` and the orchestrator expect.

Protocol commands implemented (server → extension):

  - ``{type: "navigate",      cmdId, url, tabId?}``
  - ``{type: "click",         cmdId, selector, tabId?}``
  - ``{type: "type",          cmdId, selector, text, submit?, tabId?}``
  - ``{type: "extract",       cmdId, selector?, includeHtml?, tabId?}``
  - ``{type: "getDOMSnapshot",cmdId, selector?, limit?, tabId?}``
  - ``{type: "screenshot",    cmdId, tabId?}``
  - ``{type: "create_tab",    cmdId, url?}``
  - ``{type: "close_tab",     cmdId, tabId}``
  - ``{type: "task_step",     step, message?}``  (UI-only — no reply expected)
  - ``{type: "done",          summary?}``        (UI-only — no reply expected)
  - ``{type: "pong"}``                           (keepalive ack)

Inbound from the extension:

  - ``{type: "result", cmdId, ok, tabId?, data?, error?}``
  - ``{type: "cancel", taskId?, reason?}``
  - ``{type: "ping",   t}``
  - ``{type: "error",  cmdId?, message}``

Cancel handling: when the extension sends ``cancel``, we set
``self._cancelled = True``; every subsequent command method raises
``TaskCancelled`` immediately, and any pending awaiter is resolved with
the same exception so the orchestrator unblocks.

Timeouts: each command uses ``COMMAND_TIMEOUT_SECONDS`` (30s by default).
On timeout we raise ``BridgeTimeout`` and stop tracking the cmdId.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Optional


logger = logging.getLogger("engine.ws_bridge")


# ── Command timeout ────────────────────────────────────────────────────
# Browser actions occasionally take >10s on a heavy page. 30s gives the
# DOM time to settle while still bounding the worst case so the
# orchestrator can move on. The verifier's per-kind navigations land
# inside this same envelope.
COMMAND_TIMEOUT_SECONDS: float = 8.0  # fail-fast — extension should respond in <2s for any command


# ── Errors ──────────────────────────────────────────────────────────────


class BridgeTimeout(Exception):
    """A command did not get a result within COMMAND_TIMEOUT_SECONDS."""


class TaskCancelled(Exception):
    """The wearer (or the extension) cancelled the task; every command
    method raises this on subsequent calls."""


class BridgeClosed(Exception):
    """The underlying WebSocket disconnected before the command resolved."""


class CommandFailed(Exception):
    """The extension acknowledged the command but reported a failure
    (``ok=False``). The error string is the extension's report."""


# ── Bridge ──────────────────────────────────────────────────────────────


class WSBridge:
    """Wraps a FastAPI ``WebSocket`` so the orchestrator can call DOM
    operations like normal coroutines.

    Typical usage:

        bridge = WSBridge(websocket)
        # Spawn a reader that pumps inbound frames:
        reader = asyncio.create_task(bridge.reader_loop())
        try:
            await orchestrator.run_task(task, user_id, bridge, task_id)
        finally:
            reader.cancel()
    """

    def __init__(self, websocket: Any) -> None:
        self._ws = websocket
        # cmdId → Future[result-payload]. Kept on instance so concurrent
        # commands (rare, but possible if the orchestrator pre-fetches
        # state in parallel) don't collide.
        self._pending: dict[str, asyncio.Future[dict]] = {}
        self._cancelled: bool = False
        self._closed: bool = False
        # Reason recorded when cancel arrives — surfaced to the orchestrator
        # via TaskCancelled.args.
        self._cancel_reason: str = ""
        # Set when the extension reports task-tabs closed; orchestrator
        # may poll this to surface a friendlier message.
        self._cancel_event: asyncio.Event = asyncio.Event()
        # Single send-lock so two coroutines never interleave a JSON write.
        self._send_lock: asyncio.Lock = asyncio.Lock()

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
        """Block until cancel arrives. Used by the orchestrator to race
        cancel against long-running primitives (e.g., a chain of LLM calls
        between bridge commands)."""
        await self._cancel_event.wait()

    def mark_cancelled(self, reason: str = "cancel") -> None:
        """Externally trigger cancel — used when the WebSocket closes
        while we still have pending work."""
        if self._cancelled:
            return
        self._cancelled = True
        self._cancel_reason = reason or "cancel"
        self._cancel_event.set()
        # Resolve all pending futures so awaiters unblock immediately.
        exc = TaskCancelled(self._cancel_reason)
        for cmd_id, fut in list(self._pending.items()):
            if not fut.done():
                fut.set_exception(exc)
            self._pending.pop(cmd_id, None)

    def mark_closed(self) -> None:
        """The WebSocket itself is gone. Subsequent sends will fail; mark
        all pending futures as closed so callers don't hang."""
        if self._closed:
            return
        self._closed = True
        if not self._cancelled:
            # Treat a hard disconnect as a cancel — same effect on the
            # orchestrator (stop the loop), but distinct reason for logs.
            self._cancel_reason = "ws_disconnected"
            self._cancel_event.set()
        exc = BridgeClosed("WebSocket disconnected")
        for cmd_id, fut in list(self._pending.items()):
            if not fut.done():
                fut.set_exception(exc)
            self._pending.pop(cmd_id, None)

    # ── Send / receive plumbing ────────────────────────────────────────

    def _new_cmd_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def _check_state(self) -> None:
        """Fail-fast guard run before sending any command."""
        if self._cancelled:
            raise TaskCancelled(self._cancel_reason or "cancelled")
        if self._closed:
            raise BridgeClosed("bridge already closed")

    async def _send(self, payload: dict) -> None:
        async with self._send_lock:
            try:
                await self._ws.send_json(payload)
            except Exception as exc:
                # If the socket is gone, mark closed so callers stop
                # accumulating futures we'll never resolve.
                self.mark_closed()
                raise BridgeClosed(str(exc) or "send failed") from exc

    async def _send_and_await(
        self,
        payload: dict,
        timeout: float | None = None,
    ) -> dict:
        """Issue a command, register a future, await the matching result.

        ``timeout`` defaults to the module-level ``COMMAND_TIMEOUT_SECONDS``
        (resolved at call time so tests can monkey-patch it).
        """
        self._check_state()
        if timeout is None:
            timeout = COMMAND_TIMEOUT_SECONDS

        cmd_id = self._new_cmd_id()
        payload = dict(payload)  # don't mutate caller's dict
        payload["cmdId"] = cmd_id

        fut: asyncio.Future[dict] = asyncio.get_event_loop().create_future()
        self._pending[cmd_id] = fut

        try:
            await self._send(payload)
        except BridgeClosed:
            self._pending.pop(cmd_id, None)
            raise

        try:
            result = await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError as exc:
            self._pending.pop(cmd_id, None)
            raise BridgeTimeout(
                f"command {payload.get('type')!r} (cmdId={cmd_id}) timed out "
                f"after {timeout:.1f}s"
            ) from exc
        finally:
            self._pending.pop(cmd_id, None)

        return result

    # ── Inbound dispatch ───────────────────────────────────────────────

    async def _handle_incoming(self, msg: dict) -> None:
        """Dispatch one parsed inbound frame to the right awaiter.

        Public so the route handler can wire its own receive-loop. Always
        async-safe — never raises through to the caller.
        """
        if not isinstance(msg, dict):
            logger.debug("ws_bridge ignoring non-dict frame")
            return

        msg_type = msg.get("type")

        if msg_type == "result":
            cmd_id = msg.get("cmdId")
            if not isinstance(cmd_id, str):
                logger.debug("result frame missing cmdId")
                return
            fut = self._pending.get(cmd_id)
            if fut is None or fut.done():
                # Late or duplicate — drop silently. (Could be a result
                # that arrived after our timeout fired.)
                return
            ok = bool(msg.get("ok"))
            if not ok:
                err = str(msg.get("error") or "command failed")
                fut.set_exception(CommandFailed(err))
                return
            # Return the normalised payload: whatever shape the extension
            # gave us under "data", plus the tabId if present.
            payload: dict = {
                "data": msg.get("data"),
                "tabId": msg.get("tabId"),
                "ok": True,
            }
            fut.set_result(payload)
            return

        if msg_type == "cancel":
            reason = str(msg.get("reason") or "cancel")
            logger.info("ws_bridge got cancel from extension: %s", reason)
            self.mark_cancelled(reason)
            return

        if msg_type == "ping":
            # Keepalive — echo a pong. Best-effort, never raises.
            try:
                await self._send({"type": "pong"})
            except Exception:
                pass
            return

        if msg_type == "error":
            # Either a general client-side error or one tied to a cmdId.
            cmd_id = msg.get("cmdId")
            err_msg = str(msg.get("message") or "client error")
            if isinstance(cmd_id, str):
                fut = self._pending.get(cmd_id)
                if fut is not None and not fut.done():
                    fut.set_exception(CommandFailed(err_msg))
                self._pending.pop(cmd_id, None)
            else:
                logger.warning("ws_bridge client error: %s", err_msg[:200])
            return

        # Unknown inbound type — log and drop.
        logger.debug("ws_bridge unknown inbound type: %r", msg_type)

    # ── BridgeProtocol surface ─────────────────────────────────────────
    # These methods match the shape ``app.end_state_verifier.BridgeProtocol``
    # expects (navigate / get_text / get_url) plus the broader command
    # surface the orchestrator drives.

    async def navigate(self, url: str) -> dict:
        """Navigate the active task tab to ``url``. Returns the extension's
        ``data`` payload (may be empty)."""
        result = await self._send_and_await({"type": "navigate", "url": url})
        data = result.get("data")
        return data if isinstance(data, dict) else {}

    async def click(self, selector: str) -> dict:
        result = await self._send_and_await(
            {"type": "click", "selector": selector}
        )
        data = result.get("data")
        return data if isinstance(data, dict) else {}

    async def type(
        self,
        selector: str,
        text: str,
        *,
        submit: bool = False,
    ) -> dict:
        result = await self._send_and_await({
            "type": "type",
            "selector": selector,
            "text": text,
            "submit": bool(submit),
        })
        data = result.get("data")
        return data if isinstance(data, dict) else {}

    async def extract(self, selector: str | None = None) -> str:
        """Extract visible text. Used by the verifier to assert evidence
        on the post-action page."""
        result = await self._send_and_await(
            {"type": "extract", "selector": selector}
        )
        data = result.get("data")
        if isinstance(data, dict):
            text = data.get("text")
            if isinstance(text, str):
                return text
        # Some extension builds may return a bare string under data.
        if isinstance(data, str):
            return data
        return ""

    async def get_text(self, selector: str | None = None) -> str:
        """Alias for ``extract`` to satisfy ``BridgeProtocol.get_text``."""
        return await self.extract(selector)

    async def get_url(self) -> str:
        """Pull the current URL via a getDOMSnapshot call. The extension
        returns ``{url, title, html}``; we only need ``url`` here."""
        result = await self._send_and_await({
            "type": "getDOMSnapshot",
            "limit": 0,
        })
        data = result.get("data")
        if isinstance(data, dict):
            url = data.get("url")
            if isinstance(url, str):
                return url
        return ""

    async def get_dom_snapshot(self, *, limit: int | None = None) -> str:
        """Return the truncated HTML snapshot of the current page. Used by
        the planner / executor to ground the LLM in actual DOM state."""
        payload: dict = {"type": "getDOMSnapshot"}
        if isinstance(limit, int) and limit > 0:
            payload["limit"] = int(limit)
        result = await self._send_and_await(payload)
        data = result.get("data")
        if isinstance(data, dict):
            html = data.get("html")
            if isinstance(html, str):
                return html
        return ""

    async def screenshot(self) -> str:
        """Returns a data: URL. Empty string when the extension couldn't
        capture (some tabs forbid captureVisibleTab)."""
        result = await self._send_and_await({"type": "screenshot"})
        data = result.get("data")
        if isinstance(data, dict):
            url = data.get("dataUrl")
            if isinstance(url, str):
                return url
        return ""

    async def create_tab(self, url: str | None = None) -> int:
        """Open a new tab inside the Anticipy tab group. Returns tabId."""
        payload: dict = {"type": "create_tab"}
        if url:
            payload["url"] = url
        result = await self._send_and_await(payload)
        tab_id = result.get("tabId")
        if isinstance(tab_id, int):
            return tab_id
        # Some payloads may carry it inside data.
        data = result.get("data")
        if isinstance(data, dict):
            inner = data.get("tabId")
            if isinstance(inner, int):
                return inner
        return 0

    async def close_tab(self, tab_id: int) -> None:
        await self._send_and_await({"type": "close_tab", "tabId": int(tab_id)})

    # ── UI-only frames (no awaited reply) ──────────────────────────────

    async def stream_step(self, step: int, message: str) -> None:
        """Push an ephemeral progress event to the popup UI.

        ``step`` is the 1-based step index for telemetry; ``message`` is the
        wearer-friendly description (renders in the popup). The extension
        ignores the ``message`` field today but stores ``step`` as
        ``activeTask.currentStep`` — hence we send the message AS the step
        string for legacy compatibility, with the numeric step index in a
        separate field.
        """
        if self._cancelled or self._closed:
            return
        # background.js stores msg.step verbatim; popups render whatever
        # string is in there. So we put the human message into ``step`` and
        # pass the index in ``stepIndex``. New extension builds can read
        # the structured fields; old ones get the friendly string for free.
        try:
            await self._send({
                "type": "task_step",
                "step": message or f"Step {step}",
                "stepIndex": int(step),
                "message": message or "",
            })
        except BridgeClosed:
            return

    async def emit_done(
        self,
        success: bool,
        message: str,
        deliverable: dict | None = None,
    ) -> None:
        """Final wire-frame the orchestrator emits when the task ends.

        Sends BOTH a ``done`` frame (which the extension's background.js
        recognises and surfaces to the popup) and a structured status the
        popup can render directly. Always best-effort — never raises.
        """
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
        """Surface a non-fatal client-visible error frame."""
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
    "TaskCancelled",
    "WSBridge",
]
