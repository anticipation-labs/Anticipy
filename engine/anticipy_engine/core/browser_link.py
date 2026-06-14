"""BrowserLink — the authenticated WS transport to the browser extension.

Owns a per-session token (the extension presents it on connect; the engine
rejects connections without it, and the socket binds to 127.0.0.1 only). Tracks
connection state and correlates browse jobs with their results. One extension
connection at a time (the user's own Chrome).
"""
from __future__ import annotations

import asyncio
import secrets
from typing import Dict, Optional

from .navwall import nav_block_reason


def _walled_nav_url(intent: str, args: dict) -> Optional[str]:
    """If this browse job would navigate the browser, return the target URL; else None.

    Both transports funnel navigation through ``send_browse``: an ``observe`` with a ``url``
    re-points the tab, and an ``act`` with ``action == "navigate"`` carries the model's own
    ``url``. Either is a navigation the hard wall must vet before it reaches the browser.
    """
    args = args or {}
    if intent == "observe":
        url = args.get("url")
        return str(url).strip() if url else None
    if intent == "act" and str(args.get("action") or "").strip() == "navigate":
        url = args.get("url")
        return str(url).strip() if url else None
    return None


class BrowserLink:
    def __init__(self) -> None:
        self.token = secrets.token_urlsafe(24)
        self._ws = None
        self.connected = False
        self._pending: Dict[str, "asyncio.Future[dict]"] = {}

    # ---- auth ----
    def check_token(self, token: Optional[str]) -> bool:
        return bool(token) and secrets.compare_digest(token, self.token)

    # ---- connection lifecycle (driven by the WS endpoint) ----
    async def attach(self, websocket) -> bool:
        # Last-writer-wins: a fresh connection takes over the driver slot (this also
        # recovers cleanly from a stale socket whose close wasn't detected). The
        # detach guard below stops a disconnecting OLD socket from clobbering it.
        self._ws = websocket
        self.connected = True
        return True

    async def detach(self, websocket=None) -> None:
        # A rejected duplicate disconnecting must NOT tear down the live driver.
        if websocket is not None and websocket is not self._ws:
            return
        self._ws = None
        self.connected = False
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(ConnectionError("extension disconnected"))
        self._pending.clear()

    async def on_message(self, msg: dict) -> None:
        if msg.get("type") == "result":
            fut = self._pending.pop(msg.get("job_id"), None)
            if fut is not None and not fut.done():
                fut.set_result(msg)

    # ---- job dispatch (used by the browser hand) ----
    async def send_browse(self, job_id: str, intent: str, args: dict, timeout: float) -> dict:
        # HARD NAVIGATION WALL (code-level), enforced at the transport so it holds for BOTH
        # the extension WS and the native bridge. A model-emitted navigate (or a re-point
        # observe) to a private/metadata host, a non-http(s) scheme, or a banking/password
        # domain is DENIED here before the job is ever sent to the browser — regardless of
        # what a page-injection talked the model into emitting. The planner prompt fence is
        # defense-in-depth; this is the wall that actually stops the navigate.
        nav_url = _walled_nav_url(intent, args)
        if nav_url is not None:
            reason = nav_block_reason(nav_url)
            if reason:
                return {
                    "type": "result",
                    "job_id": job_id,
                    "status": "needs_human",
                    "proof": None,
                    "output": {"reason": f"navigation blocked: {reason}"},
                }
        if not self.connected or self._ws is None:
            raise ConnectionError("extension not connected")
        loop = asyncio.get_running_loop()
        fut: "asyncio.Future[dict]" = loop.create_future()
        self._pending[job_id] = fut
        await self._ws.send_json({"type": "browse_job", "job_id": job_id, "intent": intent, "args": args})
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pending.pop(job_id, None)

    # ---- dev hot-reload ----
    async def reload(self) -> bool:
        if self._ws is None:
            return False
        await self._ws.send_json({"type": "reload"})
        return True
