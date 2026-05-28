#!/usr/bin/env python3
"""CDP-first loopback bridge for the surface runtime.

Backwards-compatible with the AppleScript variant of
``anticipy_bridge_fallback.py``. Speaks the SAME HTTP surface on
127.0.0.1:7777 (``/status`` GET, ``/surface-proof`` POST,
``/surface-command`` POST) and accepts the same JSON payloads.

CDP path (primary)
==================
On startup, probes ``http://localhost:9222/json/version``. If 9222 is
listening, every command goes through the Chrome DevTools Protocol on
the user's already-running Chrome (started with
``--remote-debugging-port=9222 --remote-allow-origins=http://localhost:*``).

CDP unlocks three things AppleScript cannot do safely:

1. ``Target.createTarget {background: true}`` opens new tabs without
   stealing OS focus. The Anticipy car can navigate while the user is
   typing in another tab.
2. ``Runtime.evaluate`` runs arbitrary JS in the tab without requiring
   Chrome > View > Developer > Allow JavaScript from Apple Events.
3. ``Page.captureScreenshot`` returns a base64 PNG of the actual
   rendered tab, even if a different window is frontmost.

AppleScript path (fallback)
===========================
If port 9222 is not responding at startup OR mid-request, the bridge
falls back to the original AppleScript code paths. Behaviour matches
the previous bridge exactly (so existing tests that survived the
AppleScript era still pass when CDP is unavailable).

Async CDP client
================
Uses ``websockets`` (the legacy async client at ``websockets.connect``)
because Chrome 148+ with ``--remote-allow-origins=http://localhost:*``
rejects the Origin header that ``websocket-client`` always sends. The
async ``websockets.connect`` omits Origin by default, so the WS
handshake passes.

A single persistent WebSocket to the browser endpoint
(``ws://localhost:9222/devtools/browser/<guid>``) is shared across all
concurrent requests. Per-request correlation is by message id. A
reader task pumps messages off the socket and resolves the future
registered for each id. ``Target.attachToTarget`` with ``flatten=true``
gives a ``sessionId`` for each tab so subsequent commands route on the
same WS without opening a per-tab socket.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import itertools
import json
import logging
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    import websockets  # noqa: F401
    _WEBSOCKETS_AVAILABLE = True
except Exception:
    _WEBSOCKETS_AVAILABLE = False


HOST = os.environ.get("ANTICIPY_TRIGGER_HOST", "127.0.0.1")
try:
    PORT = int(os.environ.get("ANTICIPY_TRIGGER_PORT", "7777"))
except Exception:
    PORT = 7777
SECRET = os.environ.get("ANTICIPY_TRIGGER_SECRET") or "local-dev"
CDP_HOST = os.environ.get("ANTICIPY_CDP_HOST", "localhost")
try:
    CDP_PORT = int(os.environ.get("ANTICIPY_CDP_PORT", "9222"))
except Exception:
    CDP_PORT = 9222
CDP_BASE = f"http://{CDP_HOST}:{CDP_PORT}"

ACQUIRED_VIA_CDP = "chrome_cdp_loopback_bridge"
ACQUIRED_VIA_APPLESCRIPT = "chrome_applescript_loopback_bridge"


# -----------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------
def _log_dir() -> Path:
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Logs" / "Anticipy"
    return home / ".anticipy" / "logs"


def _setup_logging() -> None:
    d = _log_dir()
    d.mkdir(parents=True, exist_ok=True)
    h = logging.FileHandler(d / "bridge_fallback.log")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(h)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root.addHandler(sh)


# -----------------------------------------------------------------------
# CDP probe + helpers
# -----------------------------------------------------------------------
# Cache /json/version probe so concurrent /status calls don't each
# make a fresh HTTP roundtrip to Chrome.
_alive_cache: dict[str, Any] = {"checked_at": 0.0, "alive": False}


def _cdp_alive_sync(timeout: float = 2.5) -> bool:
    if not _WEBSOCKETS_AVAILABLE:
        return False
    try:
        r = urllib.request.urlopen(f"{CDP_BASE}/json/version", timeout=timeout)
        return r.status == 200
    except Exception:
        return False


async def _cdp_alive(timeout: float = 2.5, ttl: float = 2.0) -> bool:
    """Return True iff Chrome's CDP HTTP endpoint is responsive.

    Cached for ``ttl`` seconds so concurrent requests don't each probe.
    """
    now = time.monotonic()
    if now - _alive_cache.get("checked_at", 0.0) < ttl:
        return bool(_alive_cache.get("alive"))
    alive = await asyncio.to_thread(_cdp_alive_sync, timeout)
    _alive_cache["alive"] = alive
    _alive_cache["checked_at"] = now
    return alive


def _browser_ws_url_sync(timeout: float = 5.0) -> str:
    v = urllib.request.urlopen(f"{CDP_BASE}/json/version", timeout=timeout)
    info = json.loads(v.read().decode("utf-8"))
    return (info.get("webSocketDebuggerUrl") or "").replace("127.0.0.1", "localhost")


async def _browser_ws_url(timeout: float = 5.0) -> str:
    return await asyncio.to_thread(_browser_ws_url_sync, timeout)


async def _cdp_list_pages_ws(timeout: float = 8.0) -> list[dict]:
    """List page targets via Target.getTargets on the persistent WS.

    Returns a list of dicts shaped like ``/json/list`` entries.
    """
    try:
        client = await _get_client()
        msg = await client.browser_call(
            "Target.getTargets", {}, timeout=timeout
        )
    except Exception as exc:
        logging.warning("cdp Target.getTargets failed: %s", exc)
        return []
    result, err = _unpack_result(msg)
    if err:
        logging.warning("cdp Target.getTargets error: %s", err)
        return []
    infos = result.get("targetInfos") or []
    out = []
    for t in infos:
        out.append({
            "id": t.get("targetId") or "",
            "type": t.get("type") or "",
            "url": t.get("url") or "",
            "title": t.get("title") or "",
            "attached": bool(t.get("attached")),
        })
    return out


async def _cdp_find_page_by_url_prefix(prefix: str) -> dict | None:
    pages = [p for p in (await _cdp_list_pages_ws())
             if p.get("type") == "page"]
    if not pages:
        return None
    if not prefix:
        return pages[-1]
    for p in pages:
        u = (p.get("url") or "")
        if u.startswith(prefix):
            return p
    return None


async def _cdp_find_page_by_id(target_id: str) -> dict | None:
    for p in await _cdp_list_pages_ws():
        if p.get("id") == target_id:
            return p
    return None


# -----------------------------------------------------------------------
# Persistent async CDP client (one WS to browser endpoint, request-id mux)
# -----------------------------------------------------------------------
class _CDPClient:
    """Single persistent async WebSocket to Chrome's browser endpoint.

    All CDP method calls share this connection. Each call gets a unique
    integer id; a reader task pulls messages off the socket and resolves
    futures by id. Per-target commands use sessionId routing via
    Target.attachToTarget(flatten=true).
    """

    def __init__(self) -> None:
        self._ws: Any = None
        self._reader_task: asyncio.Task | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._id_counter = itertools.count(1)
        # target_id -> sessionId for already-attached targets
        self._sessions: dict[str, str] = {}
        self._connect_lock = asyncio.Lock()
        self._attach_locks: dict[str, asyncio.Lock] = {}
        self._browser_ws_url: str = ""

    def _next_id(self) -> int:
        return next(self._id_counter)

    async def _ensure_connected(self) -> None:
        if self._ws is not None and not self._ws.closed:
            return
        async with self._connect_lock:
            if self._ws is not None and not self._ws.closed:
                return
            try:
                self._browser_ws_url = await _browser_ws_url()
            except Exception as exc:
                raise RuntimeError(f"cdp /json/version: {exc}") from exc
            if not self._browser_ws_url:
                raise RuntimeError("no browser webSocketDebuggerUrl")
            try:
                self._ws = await websockets.connect(
                    self._browser_ws_url,
                    max_size=64 * 1024 * 1024,
                    open_timeout=10.0,
                    ping_interval=None,
                    close_timeout=2.0,
                )
            except Exception as exc:
                raise RuntimeError(f"ws connect: {exc}") from exc
            self._sessions.clear()
            self._attach_locks.clear()
            self._reader_task = asyncio.create_task(self._reader_loop())
            logging.info("cdp client connected to %s", self._browser_ws_url)

    async def _reader_loop(self) -> None:
        ws = self._ws
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                mid = msg.get("id")
                if mid is None:
                    continue
                fut = self._pending.pop(int(mid), None)
                if fut is not None and not fut.done():
                    fut.set_result(msg)
        except Exception as exc:
            logging.warning("cdp reader exiting: %s", exc)
        finally:
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(RuntimeError("cdp ws closed"))
            self._pending.clear()
            try:
                await ws.close()
            except Exception:
                pass
            self._ws = None
            self._sessions.clear()
            self._attach_locks.clear()

    async def _send_and_await(self, payload: dict, timeout: float) -> dict:
        await self._ensure_connected()
        mid = self._next_id()
        payload = dict(payload)
        payload["id"] = mid
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[mid] = fut
        try:
            await self._ws.send(json.dumps(payload))
        except Exception as exc:
            self._pending.pop(mid, None)
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
            return {"error": f"ws send: {exc}"}
        try:
            msg = await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(mid, None)
            return {"error": f"timeout waiting for {payload.get('method')} response"}
        except Exception as exc:
            self._pending.pop(mid, None)
            return {"error": f"ws recv: {exc}"}
        return msg

    async def browser_call(self, method: str, params: dict | None = None,
                           timeout: float = 15.0) -> dict:
        """Call a CDP method at the browser level (no sessionId)."""
        return await self._send_and_await(
            {"method": method, "params": params or {}},
            timeout=timeout,
        )

    async def _attach_to_target(self, target_id: str,
                                timeout: float = 8.0) -> tuple[str, str]:
        cached = self._sessions.get(target_id)
        if cached:
            return cached, ""
        lock = self._attach_locks.setdefault(target_id, asyncio.Lock())
        async with lock:
            cached = self._sessions.get(target_id)
            if cached:
                return cached, ""
            msg = await self._send_and_await(
                {
                    "method": "Target.attachToTarget",
                    "params": {"targetId": target_id, "flatten": True},
                },
                timeout=timeout,
            )
            if msg.get("error") and not isinstance(msg.get("error"), dict):
                return "", str(msg["error"])
            err = msg.get("error")
            if isinstance(err, dict):
                return "", str(err.get("message") or err)
            session_id = ((msg.get("result") or {}).get("sessionId") or "")
            if not session_id:
                return "", f"no sessionId in attachToTarget response: {str(msg)[:200]}"
            self._sessions[target_id] = session_id
            return session_id, ""

    async def session_call(self, target_id: str, method: str,
                           params: dict | None = None,
                           timeout: float = 15.0) -> dict:
        session_id, err = await self._attach_to_target(target_id,
                                                       timeout=min(timeout, 8.0))
        if err:
            return {"error": f"attach: {err}"}
        msg = await self._send_and_await(
            {"sessionId": session_id, "method": method, "params": params or {}},
            timeout=timeout,
        )
        cdp_err = msg.get("error")
        if isinstance(cdp_err, dict):
            text = str(cdp_err.get("message") or "")
            if "Session" in text and "not found" in text:
                self._sessions.pop(target_id, None)
        return msg

    async def close(self) -> None:
        ws = self._ws
        self._ws = None
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            with contextlib.suppress(Exception):
                await self._reader_task
        if ws is not None:
            with contextlib.suppress(Exception):
                await ws.close()


_cdp_client: _CDPClient | None = None
_cdp_client_lock: asyncio.Lock | None = None


def _ensure_client_lock() -> asyncio.Lock:
    global _cdp_client_lock
    if _cdp_client_lock is None:
        _cdp_client_lock = asyncio.Lock()
    return _cdp_client_lock


async def _get_client() -> _CDPClient:
    global _cdp_client
    lock = _ensure_client_lock()
    async with lock:
        if _cdp_client is None:
            _cdp_client = _CDPClient()
        return _cdp_client


def _unpack_result(msg: dict) -> tuple[dict, str]:
    """Return (result_dict, error_string). CDP returns errors in 'error'
    (dict with code/message) and successes in 'result'.
    """
    if not isinstance(msg, dict):
        return {}, f"non-dict cdp response: {type(msg).__name__}"
    err = msg.get("error")
    if isinstance(err, str) and err:
        return {}, err
    if isinstance(err, dict):
        return {}, str(err.get("message") or err)
    return (msg.get("result") or {}), ""


# -----------------------------------------------------------------------
# CDP high-level operations (used by the HTTP handlers; all async)
# -----------------------------------------------------------------------
async def _cdp_create_target(url: str, background: bool = True) -> dict:
    """Open a new tab via Target.createTarget. Returns {ok, targetId, error}."""
    try:
        client = await _get_client()
        msg = await client.browser_call(
            "Target.createTarget",
            {"url": url, "background": bool(background)},
            timeout=12.0,
        )
    except Exception as exc:
        return {"ok": False, "error": f"cdp createTarget: {exc}"}
    result, err = _unpack_result(msg)
    if err:
        return {"ok": False, "error": err}
    target_id = result.get("targetId")
    if not target_id:
        return {"ok": False, "error": f"no targetId in response: {str(msg)[:200]}"}
    return {"ok": True, "targetId": target_id}


async def _cdp_evaluate(target_id: str, expression: str,
                        await_promise: bool = False,
                        timeout: float = 12.0) -> dict:
    try:
        client = await _get_client()
        msg = await client.session_call(
            target_id,
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": bool(await_promise),
            },
            timeout=timeout,
        )
    except Exception as exc:
        return {"ok": False, "error": f"cdp evaluate: {exc}",
                "value": None, "type": ""}
    result, err = _unpack_result(msg)
    if err:
        return {"ok": False, "error": err, "value": None, "type": ""}
    res = result.get("result") or {}
    exc = result.get("exceptionDetails")
    if exc:
        text = (exc.get("exception") or {}).get("description") or json.dumps(exc)[:300]
        return {"ok": False, "error": f"js exception: {text}",
                "value": None, "type": res.get("type") or ""}
    return {"ok": True, "value": res.get("value"),
            "type": res.get("type") or "", "error": ""}


async def _cdp_page_screenshot(target_id: str, timeout: float = 15.0) -> dict:
    """Page.captureScreenshot. Returns {ok, data_url, png_bytes, error}.

    We do NOT call Page.bringToFront, so this stays a background read.
    """
    try:
        client = await _get_client()
        msg = await client.session_call(
            target_id,
            "Page.captureScreenshot",
            {"format": "png", "captureBeyondViewport": False},
            timeout=timeout,
        )
    except Exception as exc:
        return {"ok": False, "error": f"cdp screenshot: {exc}",
                "data_url": "", "png_bytes": b""}
    result, err = _unpack_result(msg)
    if err:
        return {"ok": False, "error": err, "data_url": "", "png_bytes": b""}
    b64 = result.get("data") or ""
    if not b64:
        return {"ok": False, "error": "empty screenshot data",
                "data_url": "", "png_bytes": b""}
    try:
        raw = base64.b64decode(b64)
    except Exception as exc:
        return {"ok": False, "error": f"b64 decode: {exc}",
                "data_url": "", "png_bytes": b""}
    return {"ok": True, "data_url": "data:image/png;base64," + b64,
            "png_bytes": raw, "error": ""}


async def _cdp_navigate(url: str, prefer_in_place: bool = True) -> dict:
    """Open url. If an existing 'page' tab already has the same host
    loaded, reuse it via Page.navigate (in-place). Otherwise open a
    background tab via Target.createTarget.

    Returns {ok, url, title, targetId, in_place, error}.
    """
    if not url:
        return {"ok": False, "error": "missing url"}
    target_id = ""
    in_place = False
    if prefer_in_place:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            host_prefix = f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            host_prefix = ""
        if host_prefix:
            existing = await _cdp_find_page_by_url_prefix(host_prefix)
            if existing:
                target_id = existing.get("id") or ""
                if target_id:
                    try:
                        client = await _get_client()
                        msg = await client.session_call(
                            target_id,
                            "Page.navigate",
                            {"url": url},
                            timeout=15.0,
                        )
                    except Exception as exc:
                        msg = {"error": f"cdp page.navigate: {exc}"}
                    _, err = _unpack_result(msg)
                    if not err:
                        in_place = True
                    else:
                        target_id = ""
    if not target_id:
        out = await _cdp_create_target(url, background=True)
        if not out.get("ok"):
            return {"ok": False, "error": out.get("error") or "createTarget failed",
                    "url": "", "title": "", "targetId": "", "in_place": False}
        target_id = out.get("targetId") or ""

    # Read URL + title via CDP on that tab. No fixed sleep -- the WS
    # round trips already give Chrome the cycle it needs.
    cur_url = url
    cur_title = ""
    if target_id:
        u = await _cdp_evaluate(target_id, "location.href")
        if u.get("ok") and isinstance(u.get("value"), str):
            cur_url = u.get("value") or cur_url
        t = await _cdp_evaluate(target_id, "document.title")
        if t.get("ok") and isinstance(t.get("value"), str):
            cur_title = t.get("value") or cur_title
    return {"ok": True, "url": cur_url, "title": cur_title,
            "targetId": target_id, "in_place": in_place, "error": ""}


async def _cdp_pick_target_for_command(url_prefix: str) -> tuple[str, str, str]:
    """Find the most-recent page tab matching ``url_prefix`` (if any) or
    the most recent page tab otherwise. Returns (target_id, url, title).
    """
    page = await _cdp_find_page_by_url_prefix(url_prefix or "")
    if not page:
        return "", "", ""
    return (
        page.get("id") or "",
        page.get("url") or "",
        page.get("title") or "",
    )


def _js_string_literal(value: str) -> str:
    return json.dumps(value)


async def _cdp_click(selector: str, url_prefix: str = "") -> dict:
    target_id, _, _ = await _cdp_pick_target_for_command(url_prefix)
    if not target_id:
        return {"ok": False, "error": f"no page tab matches prefix={url_prefix!r}",
                "value": None}
    sel = _js_string_literal(selector)
    expr = (
        "(()=>{const el=document.querySelector(" + sel + ");"
        "if(!el)return 'NOTFOUND';"
        "el.scrollIntoView({block:'center'});"
        "el.click();return 'OK';})()"
    )
    out = await _cdp_evaluate(target_id, expr)
    if not out.get("ok"):
        return {"ok": False, "error": out.get("error"), "value": out.get("value")}
    val = out.get("value")
    return {"ok": val == "OK", "value": val,
            "error": "" if val == "OK" else f"click returned {val!r}"}


async def _cdp_type(selector: str, text: str, submit: bool = False,
                    url_prefix: str = "") -> dict:
    target_id, _, _ = await _cdp_pick_target_for_command(url_prefix)
    if not target_id:
        return {"ok": False, "error": f"no page tab matches prefix={url_prefix!r}",
                "value": None}
    sel = _js_string_literal(selector)
    val = _js_string_literal(text)
    expr = (
        "(()=>{const el=document.querySelector(" + sel + ");"
        "if(!el)return 'NOTFOUND';"
        "const tag=el.tagName==='TEXTAREA'?window.HTMLTextAreaElement.prototype:window.HTMLInputElement.prototype;"
        "const setter=Object.getOwnPropertyDescriptor(tag,'value').set;"
        "el.focus();setter.call(el," + val + ");"
        "el.dispatchEvent(new Event('input',{bubbles:true}));"
        "el.dispatchEvent(new Event('change',{bubbles:true}));"
        "return el.value;})()"
    )
    out = await _cdp_evaluate(target_id, expr)
    if not out.get("ok"):
        return {"ok": False, "error": out.get("error"), "value": out.get("value")}
    value = out.get("value")
    ok = isinstance(value, str) and value == text
    if ok and submit:
        s_expr = (
            "(()=>{const el=document.querySelector(" + sel + ");"
            "if(!el)return 'NOTFOUND';"
            "const f=el.form;if(f){f.requestSubmit?f.requestSubmit():f.submit();return 'OK';}"
            "el.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));"
            "el.dispatchEvent(new KeyboardEvent('keypress',{key:'Enter',bubbles:true}));"
            "el.dispatchEvent(new KeyboardEvent('keyup',{key:'Enter',bubbles:true}));"
            "return 'KEYS';})()"
        )
        await _cdp_evaluate(target_id, s_expr)
    return {"ok": ok, "value": value,
            "error": "" if ok else f"type readback mismatch: got {value!r} want {text!r}"}


async def _cdp_read(selector: str = "", url_prefix: str = "") -> dict:
    target_id, _, _ = await _cdp_pick_target_for_command(url_prefix)
    if not target_id:
        return {"ok": False, "error": f"no page tab matches prefix={url_prefix!r}",
                "html": "", "text": "", "url": "", "title": ""}
    if selector:
        sel = _js_string_literal(selector)
        html_expr = (
            "(()=>{const el=document.querySelector(" + sel + ");"
            "return el?el.outerHTML:'';})()"
        )
        text_expr = (
            "(()=>{const el=document.querySelector(" + sel + ");"
            "return el?el.innerText||el.textContent||'':'';})()"
        )
    else:
        html_expr = "document.documentElement.outerHTML"
        text_expr = "document.body?document.body.innerText:''"
    html_out, text_out, url_out, title_out = await asyncio.gather(
        _cdp_evaluate(target_id, html_expr, timeout=20.0),
        _cdp_evaluate(target_id, text_expr, timeout=12.0),
        _cdp_evaluate(target_id, "location.href"),
        _cdp_evaluate(target_id, "document.title"),
    )
    return {
        "ok": bool(html_out.get("ok")),
        "html": str(html_out.get("value") or "")[:200_000],
        "text": str(text_out.get("value") or "")[:200_000],
        "url": str(url_out.get("value") or ""),
        "title": str(title_out.get("value") or ""),
        "error": html_out.get("error") or "",
    }


async def _cdp_eval_js(code: str, url_prefix: str = "") -> dict:
    target_id, _, _ = await _cdp_pick_target_for_command(url_prefix)
    if not target_id:
        return {"ok": False, "error": f"no page tab matches prefix={url_prefix!r}",
                "result": ""}
    out = await _cdp_evaluate(target_id, code)
    if not out.get("ok"):
        return {"ok": False, "error": out.get("error") or "", "result": ""}
    val = out.get("value")
    if val is None:
        result = ""
    elif isinstance(val, str):
        result = val
    else:
        try:
            result = json.dumps(val)
        except Exception:
            result = str(val)
    return {"ok": True, "result": result, "error": ""}


# -----------------------------------------------------------------------
# AppleScript fallback (only used when CDP probe fails). Synchronous;
# called via asyncio.to_thread so the event loop is never blocked.
# -----------------------------------------------------------------------
def _apple_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _run_osascript(script: str, timeout: float = 30.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["osascript", "-e", script],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def _as_active_tab_sync() -> dict:
    script = r'''
tell application "Google Chrome"
  if (count of windows) = 0 then return "NO_WINDOWS"
  set t to active tab of front window
  set u to URL of t as text
  set ti to title of t as text
  return u & "|||" & ti
end tell
'''
    result = _run_osascript(script, timeout=18.0)
    if result.returncode != 0:
        return {"ok": False, "error": (result.stderr or "active tab failed").strip(),
                "url": "", "title": ""}
    raw = (result.stdout or "").rstrip()
    if raw == "NO_WINDOWS":
        return {"ok": False, "error": "no chrome windows open", "url": "", "title": ""}
    parts = raw.split("|||", 1)
    if len(parts) < 2:
        return {"ok": False, "error": f"unexpected applescript result: {raw[:200]!r}",
                "url": "", "title": ""}
    return {"ok": True, "url": parts[0].strip(), "title": parts[1].strip()}


def _as_navigate_sync(url: str) -> dict:
    script = f'''
tell application "Google Chrome"
  activate
  if (count of windows) = 0 then make new window
  set newTab to make new tab at end of tabs of front window with properties {{URL:{_apple_quote(url)}}}
  set active tab index of front window to (count of tabs of front window)
  set winId to id of front window
  return (winId as string)
end tell
'''
    result = _run_osascript(script, timeout=28.0)
    if result.returncode != 0:
        return {"ok": False, "error": (result.stderr or "navigate failed").strip()}
    return {"ok": True, "window_id": (result.stdout or "").strip(), "navigatedTo": url}


def _as_eval_js_sync(code: str) -> dict:
    safe = code.replace("\\", "\\\\").replace('"', '\\"')
    script = (
        'tell application "Google Chrome"\n'
        '  if (count of windows) = 0 then return "NO_WINDOWS"\n'
        '  set t to active tab of front window\n'
        f'  set r to execute t javascript "{safe}"\n'
        '  if r is missing value then return ""\n'
        '  return r as text\n'
        'end tell'
    )
    result = _run_osascript(script, timeout=20.0)
    if result.returncode != 0:
        msg = (result.stderr or "eval_js failed").strip()
        hint = ""
        if "Allow JavaScript from Apple Events" in msg or "(12)" in msg:
            hint = " (enable Chrome > View > Developer > Allow JavaScript from Apple Events)"
        return {"ok": False, "error": msg + hint, "result": ""}
    raw = (result.stdout or "").rstrip()
    if raw == "NO_WINDOWS":
        return {"ok": False, "error": "no chrome windows open", "result": ""}
    return {"ok": True, "result": raw}


def _screencapture_sync(out_path: Path) -> dict:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["screencapture", "-x", str(out_path)],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=20.0, check=False,
    )
    if result.returncode != 0 or not out_path.exists():
        return {"ok": False, "error": (result.stderr or "screencapture failed").strip()}
    data = out_path.read_bytes()
    encoded = "data:image/png;base64," + base64.b64encode(data).decode("ascii")
    return {"ok": True, "path": str(out_path), "bytes": len(data), "data_url": encoded}


async def _as_active_tab() -> dict:
    return await asyncio.to_thread(_as_active_tab_sync)


async def _as_navigate(url: str) -> dict:
    return await asyncio.to_thread(_as_navigate_sync, url)


async def _as_eval_js(code: str) -> dict:
    return await asyncio.to_thread(_as_eval_js_sync, code)


async def _screencapture(out_path: Path) -> dict:
    return await asyncio.to_thread(_screencapture_sync, out_path)


# -----------------------------------------------------------------------
# HTTP handler
# -----------------------------------------------------------------------
async def _handle(reader: asyncio.StreamReader,
                  writer: asyncio.StreamWriter) -> None:
    try:
        request_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
        if not request_line:
            writer.close()
            return
        content_length = 0
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            if not line or line in (b"\r\n", b"\n"):
                break
            if line.lower().startswith(b"content-length:"):
                try:
                    content_length = int(line.split(b":", 1)[1].strip())
                except Exception:
                    content_length = 0
        method, path, *_ = (request_line.decode("ascii", "replace").strip() + " ").split(" ")

        def _resp(status_line: str, body: bytes,
                  content_type: str = "application/json") -> bytes:
            return (
                f"HTTP/1.1 {status_line}\r\n"
                f"Content-Type: {content_type}\r\n"
                f"Content-Length: {len(body)}\r\n\r\n"
            ).encode() + body

        async def _send(status_line: str, body: bytes,
                        content_type: str = "application/json") -> None:
            try:
                writer.write(_resp(status_line, body, content_type))
                await writer.drain()
            except ConnectionResetError:
                pass
            except Exception:
                logging.exception("response send failed")

        # ------- GET /status -------
        if method == "GET" and path.startswith("/status"):
            cdp_ok = await _cdp_alive()
            kind = "cdp_primary" if cdp_ok else "applescript_loopback_fallback"
            acquired = ACQUIRED_VIA_CDP if cdp_ok else ACQUIRED_VIA_APPLESCRIPT
            payload = {
                "ok": True,
                "current_task_running": False,
                "bridge_closed": False,
                "pid": os.getpid(),
                "python": sys.version.split()[0],
                "platform": sys.platform,
                "acquired_via": acquired,
                "bridge_kind": kind,
                "cdp_alive": cdp_ok,
                "cdp_base": CDP_BASE,
                "websockets_available": _WEBSOCKETS_AVAILABLE,
                "startup_log_tail": [],
                "last_error": "",
            }
            await _send("200 OK", json.dumps(payload).encode())
            return

        # Read + parse body for POST endpoints.
        body = b""
        if content_length > 0:
            body = await asyncio.wait_for(reader.readexactly(content_length), timeout=10.0)
        try:
            payload_in = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            await _send("400 Bad Request", b"bad json")
            return
        if not isinstance(payload_in, dict):
            payload_in = {}

        secret_in = str(payload_in.get("secret") or "")
        if not secrets.compare_digest(secret_in, SECRET):
            await _send("401 Unauthorized", b'{"ok":false,"error":"bad secret"}')
            return

        cdp_ok = await _cdp_alive()
        acquired_via = ACQUIRED_VIA_CDP if cdp_ok else ACQUIRED_VIA_APPLESCRIPT

        # ------- POST /surface-proof -------
        if method == "POST" and path.startswith("/surface-proof"):
            url_prefix = str(payload_in.get("url_prefix") or "").strip()
            if cdp_ok:
                target_id, _, _ = await _cdp_pick_target_for_command(url_prefix)
                if target_id:
                    url_o, title_o, html_o, shot = await asyncio.gather(
                        _cdp_evaluate(target_id, "location.href"),
                        _cdp_evaluate(target_id, "document.title"),
                        _cdp_evaluate(target_id,
                                      "document.documentElement.outerHTML",
                                      timeout=20.0),
                        _cdp_page_screenshot(target_id, timeout=15.0),
                    )
                    screenshot_path = ""
                    screenshot_bytes = 0
                    if shot.get("ok") and shot.get("png_bytes"):
                        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
                        screenshot_path = f"/Users/omarebrahim/.anticipy/screenshots/{ts}_proof_cdp.png"
                        try:
                            Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
                            Path(screenshot_path).write_bytes(shot["png_bytes"])
                            screenshot_bytes = len(shot["png_bytes"])
                        except Exception:
                            screenshot_path = ""
                    proof = {
                        "ok": bool(url_o.get("ok") and html_o.get("ok")),
                        "url": str(url_o.get("value") or ""),
                        "title": str(title_o.get("value") or ""),
                        "dom": str(html_o.get("value") or "")[:200_000],
                        "screenshot_data_url": shot.get("data_url") or "",
                        "screenshot_path": screenshot_path,
                        "screenshot_bytes": screenshot_bytes,
                        "bridge_closed": False,
                        "pid": os.getpid(),
                        "acquired_via": acquired_via,
                        "bridge_kind": "cdp_primary",
                        "error": url_o.get("error") or html_o.get("error")
                                  or shot.get("error") or "",
                    }
                    await _send("200 OK", json.dumps(proof).encode())
                    return
                logging.warning("CDP /surface-proof: no tab matched prefix=%r, falling through",
                                url_prefix)
            tab = await _as_active_tab()
            ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            screenshot_path = Path(f"/Users/omarebrahim/.anticipy/screenshots/{ts}_proof.png")
            screen = await _screencapture(screenshot_path)
            ok = tab.get("ok") and screen.get("ok")
            proof = {
                "ok": bool(ok),
                "url": tab.get("url") or "",
                "title": tab.get("title") or "",
                "dom": "<html><body data-bridge='applescript'></body></html>",
                "screenshot_data_url": screen.get("data_url") or "",
                "screenshot_path": screen.get("path") or "",
                "screenshot_bytes": screen.get("bytes") or 0,
                "bridge_closed": False,
                "pid": os.getpid(),
                "acquired_via": ACQUIRED_VIA_APPLESCRIPT,
                "bridge_kind": "applescript_loopback_fallback",
                "error": tab.get("error") or screen.get("error") or "",
            }
            await _send("200 OK", json.dumps(proof).encode())
            return

        # ------- POST /surface-command -------
        if method == "POST" and path.startswith("/surface-command"):
            command = str(payload_in.get("command") or "").strip()
            url = str(payload_in.get("url") or "").strip()
            selector = str(payload_in.get("selector") or "").strip()
            text = str(payload_in.get("text") or "")
            url_prefix = str(payload_in.get("url_prefix") or "").strip()
            submit = bool(payload_in.get("submit") or False)

            # --- navigate ---
            if command == "navigate":
                if not url:
                    await _send("400 Bad Request",
                                b'{"ok":false,"error":"missing url"}')
                    return
                if cdp_ok:
                    n = await _cdp_navigate(url, prefer_in_place=True)
                    response = {
                        "ok": bool(n.get("ok")),
                        "command": "navigate",
                        "data": {
                            "navigatedTo": url,
                            "url": n.get("url") or "",
                            "title": n.get("title") or "",
                            "targetId": n.get("targetId") or "",
                            "in_place": bool(n.get("in_place")),
                            "background_tab": not bool(n.get("in_place")),
                        },
                        "acquired_via": ACQUIRED_VIA_CDP,
                        "bridge_kind": "cdp_primary",
                        "error": n.get("error") or "",
                    }
                    await _send("200 OK", json.dumps(response).encode())
                    return
                # AppleScript fallback (legacy behaviour).
                result = await _as_navigate(url)
                await asyncio.sleep(1.0)
                tab = await _as_active_tab()
                response = {
                    "ok": bool(result.get("ok") and tab.get("ok")),
                    "command": "navigate",
                    "data": {
                        "navigatedTo": url,
                        "url": tab.get("url") or "",
                        "title": tab.get("title") or "",
                    },
                    "acquired_via": ACQUIRED_VIA_APPLESCRIPT,
                    "bridge_kind": "applescript_loopback_fallback",
                    "error": result.get("error") or tab.get("error") or "",
                }
                await _send("200 OK", json.dumps(response).encode())
                return

            # --- eval_js ---
            if command == "eval_js":
                code = str(payload_in.get("code") or "")
                if not code:
                    await _send("400 Bad Request",
                                b'{"ok":false,"error":"missing code"}')
                    return
                if cdp_ok:
                    ev = await _cdp_eval_js(code, url_prefix=url_prefix)
                    response = {"ok": bool(ev.get("ok")), "command": "eval_js",
                                "data": {"result": ev.get("result") or ""},
                                "acquired_via": ACQUIRED_VIA_CDP,
                                "bridge_kind": "cdp_primary",
                                "error": ev.get("error") or ""}
                    await _send("200 OK", json.dumps(response).encode())
                    return
                ev = await _as_eval_js(code)
                response = {"ok": bool(ev.get("ok")), "command": "eval_js",
                            "data": {"result": ev.get("result") or ""},
                            "acquired_via": ACQUIRED_VIA_APPLESCRIPT,
                            "bridge_kind": "applescript_loopback_fallback",
                            "error": ev.get("error") or ""}
                await _send("200 OK", json.dumps(response).encode())
                return

            # --- click (CDP-only command) ---
            if command == "click":
                if not selector:
                    await _send("400 Bad Request",
                                b'{"ok":false,"error":"missing selector"}')
                    return
                if not cdp_ok:
                    err = {"ok": False, "command": "click",
                           "error": "click requires CDP (port 9222) which is not responding",
                           "acquired_via": ACQUIRED_VIA_APPLESCRIPT,
                           "bridge_kind": "applescript_loopback_fallback"}
                    await _send("200 OK", json.dumps(err).encode())
                    return
                c = await _cdp_click(selector, url_prefix=url_prefix)
                response = {"ok": bool(c.get("ok")), "command": "click",
                            "data": {"selector": selector, "result": c.get("value") or ""},
                            "acquired_via": ACQUIRED_VIA_CDP,
                            "bridge_kind": "cdp_primary",
                            "error": c.get("error") or ""}
                await _send("200 OK", json.dumps(response).encode())
                return

            # --- type (CDP-only command) ---
            if command == "type":
                if not selector:
                    await _send("400 Bad Request",
                                b'{"ok":false,"error":"missing selector"}')
                    return
                if not cdp_ok:
                    err = {"ok": False, "command": "type",
                           "error": "type requires CDP (port 9222) which is not responding",
                           "acquired_via": ACQUIRED_VIA_APPLESCRIPT,
                           "bridge_kind": "applescript_loopback_fallback"}
                    await _send("200 OK", json.dumps(err).encode())
                    return
                t = await _cdp_type(selector, text, submit=submit, url_prefix=url_prefix)
                response = {"ok": bool(t.get("ok")), "command": "type",
                            "data": {"selector": selector, "value": t.get("value") or ""},
                            "acquired_via": ACQUIRED_VIA_CDP,
                            "bridge_kind": "cdp_primary",
                            "error": t.get("error") or ""}
                await _send("200 OK", json.dumps(response).encode())
                return

            # --- read / extract / getDOMSnapshot (CDP-only) ---
            if command in {"read", "extract", "getDOMSnapshot"}:
                if not cdp_ok:
                    err = {"ok": False, "command": command,
                           "error": f"{command} requires CDP (port 9222) which is not responding",
                           "acquired_via": ACQUIRED_VIA_APPLESCRIPT,
                           "bridge_kind": "applescript_loopback_fallback"}
                    await _send("200 OK", json.dumps(err).encode())
                    return
                r = await _cdp_read(selector, url_prefix=url_prefix)
                response = {"ok": bool(r.get("ok")), "command": command,
                            "data": {
                                "url": r.get("url") or "",
                                "title": r.get("title") or "",
                                "html": r.get("html") or "",
                                "text": r.get("text") or "",
                            },
                            "acquired_via": ACQUIRED_VIA_CDP,
                            "bridge_kind": "cdp_primary",
                            "error": r.get("error") or ""}
                await _send("200 OK", json.dumps(response).encode())
                return

            err = {"ok": False, "command": command,
                   "error": f"bridge does not support command: {command}",
                   "acquired_via": acquired_via}
            await _send("200 OK", json.dumps(err).encode())
            return

        await _send("404 Not Found", b"")
    except asyncio.TimeoutError:
        try:
            writer.write(b"HTTP/1.1 408 Request Timeout\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
        except Exception:
            pass
    except Exception:
        logging.exception("handler crashed")
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def amain() -> int:
    _setup_logging()
    try:
        server = await asyncio.start_server(_handle, host=HOST, port=PORT)
    except OSError as exc:
        logging.error("could not bind %s:%s -- %s", HOST, PORT, exc)
        return 1
    cdp_ok = await _cdp_alive()
    kind = "cdp_primary" if cdp_ok else "applescript_loopback_fallback"
    logging.info(
        "bridge listening on %s:%s kind=%s cdp_alive=%s pid=%s ws_lib=%s",
        HOST, PORT, kind, cdp_ok, os.getpid(), _WEBSOCKETS_AVAILABLE,
    )
    if not cdp_ok:
        logging.warning(
            "CDP probe at %s/json/version FAILED; falling back to AppleScript. "
            "AppleScript brings tabs to foreground and requires Chrome > View > "
            "Developer > Allow JavaScript from Apple Events.",
            CDP_BASE,
        )
    async with server:
        await server.serve_forever()
    return 0


def main() -> int:
    return asyncio.run(amain())


if __name__ == "__main__":
    sys.exit(main())
