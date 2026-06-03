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
    async def attach(self, websocket) -> None:
        self._ws = websocket
        self.connected = True

    async def detach(self) -> None:
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
