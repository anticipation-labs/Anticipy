"""NativeBridgeLink - BrowserLink-compatible transport for the local bridge.

The Chrome extension normally drives WebVoyager over the engine WebSocket. The
installed native bridge exposes the same real Chrome surface over
127.0.0.1:7777. This adapter maps WebVoyager's observe/act primitives onto that
HTTP bridge so the browser hand can keep working when the extension socket is
not connected.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Any, Optional
import urllib.error
import urllib.parse
import urllib.request


ACTIONABLE_TAGS = {"a", "button", "textarea", "select"}
ACTIONABLE_ROLES = {
    "button",
    "link",
    "tab",
    "menuitem",
    "checkbox",
    "option",
    "searchbox",
    "textbox",
    "combobox",
}
MAX_NATIVE_MARKS = 600
MAX_NATIVE_LABEL_CHARS = 180
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
TEXT_SKIP_TAGS = {"script", "style", "noscript", "template"}


def _bool_env(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _origin(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url or "")
    except Exception:
        return ""
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _css_string(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace('"', '\\"')


def _clean_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str]
    parent: Optional["_Node"] = None
    children: list[Any] = field(default_factory=list)


class _DOMMarks(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("document", {})
        self.stack: list[_Node] = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        name = tag.lower()
        clean_attrs = {str(k).lower(): (v or "") for k, v in attrs if k}
        node = _Node(name, clean_attrs, self.stack[-1])
        self.stack[-1].children.append(node)
        if name not in VOID_TAGS:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == name:
                del self.stack[i:]
                return

    def handle_data(self, data: str) -> None:
        if not data or any(n.tag in TEXT_SKIP_TAGS for n in self.stack):
            return
        self.stack[-1].children.append(data)

    def text(self, node: Optional[_Node] = None, limit: int = 2500) -> str:
        parts: list[str] = []

        def walk(cur: _Node) -> None:
            if cur.tag in TEXT_SKIP_TAGS:
                return
            for child in cur.children:
                if isinstance(child, str):
                    parts.append(child)
                elif isinstance(child, _Node):
                    walk(child)
                if sum(len(p) for p in parts) > limit + 500:
                    return

        walk(node or self.root)
        return _clean_space(" ".join(parts))[:limit]

    def actionable_elements(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for node in self._walk_nodes(self.root):
            if not self._actionable(node):
                continue
            selector = self._selector(node)
            if not selector:
                continue
            name = self._name(node)
            if not name:
                continue
            idx = len(out)
            out.append(
                {
                    "idx": idx,
                    "role": node.attrs.get("role") or node.tag,
                    "name": name[:MAX_NATIVE_LABEL_CHARS],
                    "type": node.attrs.get("type", ""),
                    "state": "disabled" if "disabled" in node.attrs else "",
                    "inView": True,
                    "sponsored": bool(re.search(r"\bsponsored|promoted|advertisement\b", name, re.I)),
                    "selector": selector,
                }
            )
            if len(out) >= MAX_NATIVE_MARKS:
                break
        return out

    def _walk_nodes(self, node: _Node):
        for child in node.children:
            if isinstance(child, _Node):
                yield child
                yield from self._walk_nodes(child)

    def _actionable(self, node: _Node) -> bool:
        tag = node.tag
        role = (node.attrs.get("role") or "").lower()
        if tag == "input":
            return (node.attrs.get("type") or "").lower() != "hidden"
        if tag in ACTIONABLE_TAGS or role in ACTIONABLE_ROLES:
            return True
        if "onclick" in node.attrs:
            return True
        if "contenteditable" in node.attrs:
            return (node.attrs.get("contenteditable") or "").lower() in {"", "true"}
        return False

    def _name(self, node: _Node) -> str:
        for key in ("aria-label", "placeholder", "title", "value", "alt", "name"):
            value = _clean_space(node.attrs.get(key, ""))
            if value:
                return value
        if node.tag == "a" and node.attrs.get("href"):
            label = self.text(node, limit=220)
            return label or node.attrs.get("href", "")
        return self.text(node, limit=220)

    def _selector(self, node: _Node) -> str:
        id_value = node.attrs.get("id")
        if id_value:
            return f'[id="{_css_string(id_value)}"]'
        parts: list[str] = []
        cur: Optional[_Node] = node
        while cur and cur.parent and cur.parent.tag != "document":
            id_value = cur.attrs.get("id")
            if id_value:
                parts.append(f'[id="{_css_string(id_value)}"]')
                break
            siblings = [
                child
                for child in cur.parent.children
                if isinstance(child, _Node) and child.tag == cur.tag
            ]
            nth = next((i + 1 for i, sibling in enumerate(siblings) if sibling is cur), 1)
            parts.append(f"{cur.tag}:nth-of-type({nth})")
            cur = cur.parent
        if not parts and cur:
            parts.append(cur.tag)
        return " > ".join(reversed(parts))


class NativeBridgeLink:
    """Duck-typed BrowserLink fallback backed by the local native bridge."""

    def __init__(
        self,
        *,
        host: Optional[str] = None,
        port: Optional[int] = None,
        secret: Optional[str] = None,
        request_timeout: Optional[float] = None,
    ) -> None:
        self.host = host or os.environ.get("ANTICIPY_TRIGGER_HOST", "127.0.0.1")
        self.port = int(port or os.environ.get("ANTICIPY_TRIGGER_PORT", "7777"))
        self.base_url = f"http://{self.host}:{self.port}"
        self.secret = secret if secret is not None else os.environ.get("ANTICIPY_TRIGGER_SECRET", "local-dev")
        self.request_timeout = float(request_timeout or os.environ.get("ANTICIPY_NATIVE_BRIDGE_TIMEOUT", "8"))
        self.cdp_host = os.environ.get("ANTICIPY_CDP_HOST", "localhost")
        self.cdp_port = int(os.environ.get("ANTICIPY_CDP_PORT", "9222"))
        self._selectors: dict[int, str] = {}
        self._selector_meta: dict[int, dict[str, Any]] = {}
        self._url_prefix = ""
        self._available_cache: tuple[float, bool, str] = (0.0, False, "")
        self._last_start_attempt = 0.0
        self._last_cdp_start_attempt = 0.0
        self._started_process: Optional[subprocess.Popen] = None
        self._started_chrome: Optional[subprocess.Popen] = None
        self._cdp_target_id = ""

    @property
    def connected(self) -> bool:
        return self.available()

    def available(self) -> bool:
        now = time.monotonic()
        expires, cached, _ = self._available_cache
        if now < expires:
            return cached
        ok, reason = self._check_available()
        if not ok and _bool_env("ANTICIPY_NATIVE_BRIDGE_AUTOSTART", True):
            self._start_bridge_once()
            ok, reason = self._check_available(retries=5)
        self._available_cache = (time.monotonic() + 1.5, ok, reason)
        return ok

    def last_error(self) -> str:
        return self._available_cache[2]

    def fresh_probe(self) -> "NativeBridgeLink":
        """Return an independent observer for read-back checks.

        It shares the same bridge and Chrome debug endpoint, but starts with no
        cached selectors or target id. This keeps cart proof from depending on
        tab-local state in the agent's active bridge instance.
        """
        return type(self)(
            host=self.host,
            port=self.port,
            secret=self.secret,
            request_timeout=self.request_timeout,
        )

    async def send_browse(self, job_id: str, intent: str, args: dict, timeout: float) -> dict:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._send_browse_sync, job_id, intent, args or {}, timeout),
                timeout=max(0.5, float(timeout)),
            )
        except asyncio.TimeoutError:
            raise
        except ConnectionError:
            raise
        except Exception as exc:
            return {
                "type": "result",
                "job_id": job_id,
                "status": "needs_human",
                "output": {"reason": f"native bridge failed: {type(exc).__name__}: {exc}"},
                "proof": None,
            }

    def _send_browse_sync(self, job_id: str, intent: str, args: dict, timeout: float) -> dict:
        if not self.available():
            raise ConnectionError(self.last_error() or "native bridge unavailable")
        if intent in {"observe", "read_page", "browse_task"}:
            return self._observe(job_id, args)
        if intent == "act":
            return self._act(job_id, args)
        return {
            "type": "result",
            "job_id": job_id,
            "status": "needs_human",
            "output": {"reason": f"native bridge does not support browser intent {intent}"},
            "proof": None,
        }

    def _observe(self, job_id: str, args: dict) -> dict:
        self._ensure_cdp_chrome()
        url = str(args.get("url") or "").strip()
        if url:
            status, data, error = self._command({"command": "navigate", "url": url, "new_tab": True})
            if error or status != 200 or data.get("ok") is not True:
                return self._needs_human(job_id, error or str(data.get("error") or f"navigate status {status}"))
            nav_data = data.get("data") or {}
            self._cdp_target_id = str(nav_data.get("targetId") or self._cdp_target_id)
            self._url_prefix = url or _origin(url) or self._url_prefix
            time.sleep(0.5)

        last_reason = ""
        out: dict[str, Any] = {}
        screenshot = ""
        for attempt in range(6 if url else 1):
            status, proof, error = self._proof()
            if error or status != 200 or proof.get("ok") is not True:
                last_reason = error or str(proof.get("error") or f"proof status {status}")
            else:
                out, screenshot = self._output_from_proof(proof)
                if self._surface_ready(out, url):
                    break
                last_reason = "browser surface not ready"
            if attempt < 5:
                time.sleep(0.7 + attempt * 0.35)
        if not out:
            return self._needs_human(job_id, last_reason)
        if out.get("url"):
            self._url_prefix = str(out.get("url") or "") or _origin(str(out.get("url") or "")) or self._url_prefix
        return {
            "type": "result",
            "job_id": job_id,
            "status": "success",
            "proof": {"screenshot": screenshot, "url": out.get("url"), "title": out.get("title")},
            "output": out,
        }

    def _act(self, job_id: str, args: dict) -> dict:
        action = str(args.get("action") or "").strip()
        payload: dict[str, Any]
        if action == "navigate":
            url = str(args.get("url") or "").strip()
            if not url:
                return self._needs_human(job_id, "native bridge navigate action has no URL")
            payload = {"command": "navigate", "url": url, "new_tab": False, "prefer_in_place": True}
            self._url_prefix = url or _origin(url) or self._url_prefix
        elif action == "scroll":
            direction = str(args.get("dir") or "down").lower()
            dy = -700 if direction == "up" else 700
            if _bool_env("ANTICIPY_NATIVE_BRIDGE_DIRECT_CDP_SCROLL", True):
                ok, details = self._direct_cdp_scroll(dy)
                if ok:
                    return self._success(job_id, {"ok": True, "action": action, "data": details})
            status, data, error = self._command({"command": "scroll", "dy": dy})
            if status == 200 and data.get("ok") is True and not error:
                return self._success(job_id, {"ok": True, "action": action})
            payload = {"command": "eval_js", "code": f"window.scrollBy(0,{dy}); true"}
        elif action in {"click", "type"}:
            try:
                index = int(args.get("index"))
            except Exception:
                return self._needs_human(job_id, f"native bridge {action} action has no element index")
            selector = self._selectors.get(index)
            if not selector:
                return self._needs_human(job_id, f"native bridge has no selector for element {index}")
            meta = self._selector_meta.get(index) or {}
            if action == "click" and _bool_env("ANTICIPY_NATIVE_BRIDGE_TRUSTED_CLICK", True):
                ok, details = self._trusted_cdp_click(selector, meta)
                if ok:
                    return self._success(job_id, {"ok": True, "action": action, "data": details})
            payload = {"command": action, "selector": selector}
            if action == "type":
                payload["text"] = str(args.get("text") or "")
                payload["submit"] = bool(args.get("enter"))
        else:
            return self._needs_human(job_id, f"native bridge does not support action {action}")

        status, data, error = self._command(payload)
        if error or status != 200 or data.get("ok") is not True:
            return self._needs_human(job_id, error or str(data.get("error") or f"{action} status {status}"))
        if action == "navigate":
            nav_data = data.get("data") or {}
            self._cdp_target_id = str(nav_data.get("targetId") or self._cdp_target_id)
        return self._success(job_id, {"ok": True, "action": action, "data": data.get("data") or {}})

    def _trusted_cdp_click(self, selector: str, meta: Optional[dict[str, Any]] = None) -> tuple[bool, dict[str, Any]]:
        if not self._cdp_up():
            return False, {"error": "cdp unavailable"}
        ws_url = self._cdp_page_ws_url()
        if not ws_url:
            return False, {"error": "no matching cdp page target"}
        try:
            return asyncio.run(self._trusted_cdp_click_async(ws_url, selector, meta or {}))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(self._trusted_cdp_click_async(ws_url, selector, meta or {}))
            finally:
                loop.close()
        except Exception as exc:
            return False, {"error": f"{type(exc).__name__}: {exc}"}

    def _cdp_page_ws_url(self) -> str:
        try:
            with urllib.request.urlopen(f"http://{self.cdp_host}:{self.cdp_port}/json/list", timeout=1.5) as resp:
                pages = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return ""
        if not isinstance(pages, list):
            return ""
        page_items = [p for p in pages if isinstance(p, dict) and p.get("type") == "page"]
        chosen = None
        if self._cdp_target_id:
            chosen = next((p for p in page_items if str(p.get("id") or "") == self._cdp_target_id), None)
        if chosen is None and self._url_prefix:
            matches = [p for p in page_items if str(p.get("url") or "").startswith(self._url_prefix)]
            if matches:
                chosen = matches[-1]
        if chosen is None and page_items:
            chosen = page_items[-1]
        ws_url = str((chosen or {}).get("webSocketDebuggerUrl") or "")
        return ws_url.replace("127.0.0.1", "localhost")

    async def _trusted_cdp_click_async(
        self,
        ws_url: str,
        selector: str,
        meta: dict[str, Any],
    ) -> tuple[bool, dict[str, Any]]:
        import websockets

        counter = 0

        async def call(ws, method: str, params: dict[str, Any], timeout: float = 8.0) -> dict[str, Any]:
            nonlocal counter
            counter += 1
            await ws.send(json.dumps({"id": counter, "method": method, "params": params}))
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                msg = json.loads(raw)
                if int(msg.get("id") or 0) == counter:
                    return msg

        selector_json = json.dumps(selector)
        name_json = json.dumps(str(meta.get("name") or "")[:180])
        role_json = json.dumps(str(meta.get("role") or "").lower())
        href_json = json.dumps(str(meta.get("href") or ""))
        click_token = f"click-{time.time_ns()}"
        click_token_json = json.dumps(click_token)
        rect_expr = (
            "(()=>{const selector=" + selector_json + ";"
            "const expectedName=" + name_json + ";"
            "const expectedRole=" + role_json + ";"
            "const expectedHref=" + href_json + ";"
            "const clickToken=" + click_token_json + ";"
            "const clean=v=>String(v||'').replace(/\\s+/g,' ').trim();"
            "const norm=v=>clean(v).toLowerCase();"
            "const label=el=>clean(el.innerText||el.getAttribute('aria-label')||"
            "el.getAttribute('placeholder')||el.getAttribute('title')||el.value||"
            "el.getAttribute('alt')||el.getAttribute('name')||el.getAttribute('href')||'');"
            "const role=el=>String(el.getAttribute('role')||el.tagName||'').toLowerCase();"
            "const visible=el=>{const s=getComputedStyle(el);const r=el.getBoundingClientRect();"
            "return s.display!=='none'&&s.visibility!=='hidden'&&!!r.width&&!!r.height;};"
            "const roleOk=el=>!expectedRole||role(el)===expectedRole||"
            "(expectedRole==='a'&&role(el)==='link')||"
            "(expectedRole==='button'&&role(el).includes('button'));"
            "const nameOk=el=>{if(!expectedName)return true;"
            "const a=norm(label(el));const b=norm(expectedName);"
            "return a===b||a.includes(b)||b.includes(a);};"
            "const good=el=>{if(!el||!visible(el)||!roleOk(el))return false;"
            "if(expectedHref&&String(el.href||el.getAttribute('href')||'')===expectedHref)return true;"
            "return nameOk(el);};"
            "let el=document.querySelector(selector);"
            "if(!good(el)){"
            "const candidates=Array.from(document.querySelectorAll("
            "'a,button,input,textarea,select,[role=button],[role=link],[onclick],"
            "[contenteditable=true],[contenteditable=\"\"]'));"
            "el=candidates.find(good)||null;"
            "}"
            "if(!el)return {ok:false,error:'NOTFOUND_OR_CHANGED'};"
            "el.scrollIntoView({block:'center',inline:'center'});"
            "const r=el.getBoundingClientRect();"
            "if(!r.width||!r.height)return {ok:false,error:'EMPTY_RECT'};"
            "el.setAttribute('data-anticipy-click-token',clickToken);"
            "const x=Math.max(1,Math.min(window.innerWidth-2,r.left+r.width/2));"
            "const y=Math.max(1,Math.min(window.innerHeight-2,r.top+r.height/2));"
            "return {ok:true,x,y,tag:el.tagName,name:label(el).slice(0,120),"
            "href:String(el.href||el.getAttribute('href')||''),role:role(el)};})()"
        )
        async with websockets.connect(
            ws_url,
            max_size=16 * 1024 * 1024,
            open_timeout=5.0,
            ping_interval=None,
            close_timeout=2.0,
        ) as ws:
            rect_msg = await call(
                ws,
                "Runtime.evaluate",
                {"expression": rect_expr, "returnByValue": True, "awaitPromise": False},
                timeout=8.0,
            )
            error = rect_msg.get("error")
            if error:
                return False, {"error": str(error)}
            value = (((rect_msg.get("result") or {}).get("result") or {}).get("value") or {})
            if not isinstance(value, dict) or not value.get("ok"):
                return False, {"error": str((value or {}).get("error") or "no element rect")}
            x = float(value.get("x"))
            y = float(value.get("y"))
            await call(ws, "Page.bringToFront", {}, timeout=4.0)
            await call(ws, "Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y,
                                                        "button": "none", "buttons": 0})
            await call(ws, "Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y,
                                                        "button": "left", "buttons": 1, "clickCount": 1})
            await call(ws, "Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y,
                                                        "button": "left", "buttons": 0, "clickCount": 1})
            js_fallback = False
            if _bool_env("ANTICIPY_NATIVE_BRIDGE_CLICK_JS_FALLBACK_AFTER_CDP", True):
                token_json = json.dumps(click_token)
                js_msg = await call(
                    ws,
                    "Runtime.evaluate",
                    {
                        "expression": (
                            "(()=>{const el=document.querySelector('[data-anticipy-click-token=' + "
                            + token_json
                            + " + ']');if(!el)return {ok:false,error:'MISSING_CLICK_TARGET'};"
                            "el.click();return {ok:true,name:(el.innerText||el.getAttribute('aria-label')||'').slice(0,120)};})()"
                        ),
                        "returnByValue": True,
                        "awaitPromise": False,
                    },
                    timeout=4.0,
                )
                js_value = (((js_msg.get("result") or {}).get("result") or {}).get("value") or {})
                js_fallback = bool(isinstance(js_value, dict) and js_value.get("ok"))
            return True, {"trusted_cdp_click": True, "js_fallback_click": js_fallback,
                          "x": x, "y": y, "name": value.get("name") or ""}

    def _direct_cdp_scroll(self, dy: int) -> tuple[bool, dict[str, Any]]:
        if not self._cdp_up():
            return False, {"error": "cdp unavailable"}
        ws_url = self._cdp_page_ws_url()
        if not ws_url:
            return False, {"error": "no matching cdp page target"}
        try:
            return asyncio.run(self._direct_cdp_scroll_async(ws_url, dy))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(self._direct_cdp_scroll_async(ws_url, dy))
            finally:
                loop.close()
        except Exception as exc:
            return False, {"error": f"{type(exc).__name__}: {exc}"}

    async def _direct_cdp_scroll_async(self, ws_url: str, dy: int) -> tuple[bool, dict[str, Any]]:
        import websockets

        counter = 0

        async def call(ws, method: str, params: dict[str, Any], timeout: float = 8.0) -> dict[str, Any]:
            nonlocal counter
            counter += 1
            await ws.send(json.dumps({"id": counter, "method": method, "params": params}))
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                msg = json.loads(raw)
                if int(msg.get("id") or 0) == counter:
                    return msg

        dy = int(dy)
        scroll_pos_expr = (
            "(()=>window.scrollY||document.documentElement.scrollTop||document.body.scrollTop||0)()"
        )
        async with websockets.connect(
            ws_url,
            max_size=16 * 1024 * 1024,
            open_timeout=5.0,
            ping_interval=None,
            close_timeout=2.0,
        ) as ws:
            await call(ws, "Page.bringToFront", {}, timeout=4.0)
            before_msg = await call(
                ws,
                "Runtime.evaluate",
                {"expression": scroll_pos_expr, "returnByValue": True, "awaitPromise": False},
                timeout=4.0,
            )
            before = (((before_msg.get("result") or {}).get("result") or {}).get("value") or 0)
            wheel = await call(
                ws,
                "Input.dispatchMouseEvent",
                {"type": "mouseWheel", "x": 500, "y": 500, "deltaX": 0, "deltaY": dy},
                timeout=4.0,
            )
            if wheel.get("error"):
                return False, {"error": str(wheel.get("error"))}
            expr = (
                "(()=>{"
                "const dy=" + json.dumps(dy) + ";"
                "const before=" + json.dumps(before) + ";"
                "const pos=()=>window.scrollY||document.documentElement.scrollTop||document.body.scrollTop||0;"
                "let after=pos();let fallback=false;"
                "if(Math.abs(after-before)<2){"
                "fallback=true;"
                "window.scrollBy(0,dy);"
                "after=pos();"
                "if(Math.abs(after-before)<2){"
                "const se=document.scrollingElement||document.documentElement||document.body;"
                "if(se)se.scrollTop=(se.scrollTop||0)+dy;"
                "after=pos();"
                "}"
                "}"
                "return {ok:true,before,after,dy,fallback};"
                "})()"
            )
            msg = await call(
                ws,
                "Runtime.evaluate",
                {"expression": expr, "returnByValue": True, "awaitPromise": False},
                timeout=4.0,
            )
        value = (((msg.get("result") or {}).get("result") or {}).get("value") or {})
        if not isinstance(value, dict) or not value.get("ok"):
            return False, {"error": "scroll did not return a valid CDP result"}
        return True, {
            "direct_cdp_scroll": True,
            "dy": dy,
            "before": value.get("before"),
            "after": value.get("after"),
            "fallback": bool(value.get("fallback")),
        }

    def _output_from_proof(self, proof: dict[str, Any]) -> tuple[dict[str, Any], str]:
        dom = str(proof.get("dom") or "")
        screenshot = str(proof.get("screenshot_data_url") or "")
        elements: list[dict[str, Any]] = []
        self._selectors = {}
        self._selector_meta = {}
        som = proof.get("set_of_mark")
        if isinstance(som, list):
            elements = self._elements_from_set_of_mark(som)
        if not elements and dom:
            parser = _DOMMarks()
            parser.feed(dom)
            elements = parser.actionable_elements()
        for el in elements:
            idx = el.get("idx")
            selector = el.pop("selector", None)
            if isinstance(idx, int) and selector:
                self._selectors[idx] = str(selector)
                self._selector_meta[idx] = {
                    "name": str(el.get("name") or ""),
                    "role": str(el.get("role") or ""),
                    "href": str(el.get("href") or ""),
                    "type": str(el.get("type") or ""),
                }
        text = str(proof.get("text") or "")
        if not text and dom:
            parser = _DOMMarks()
            parser.feed(dom)
            text = parser.text(limit=2500)
        return (
            {
                "url": str(proof.get("url") or ""),
                "title": str(proof.get("title") or ""),
                "text": text,
                "elements": elements,
                "native_bridge": True,
                "acquired_via": str(proof.get("acquired_via") or ""),
            },
            screenshot,
        )

    def _surface_ready(self, out: dict[str, Any], requested_url: str = "") -> bool:
        elements = out.get("elements") or []
        text = (out.get("text") or "").strip()
        if not elements and not text:
            return False
        query_tokens = self._query_tokens(requested_url)
        if not query_tokens:
            return True
        hay = " ".join(str(e.get("name") or "").lower() for e in elements)
        hits = sum(1 for token in query_tokens if token in hay)
        return hits >= min(2, len(query_tokens))

    @staticmethod
    def _query_tokens(url: str) -> list[str]:
        try:
            parsed = urllib.parse.urlparse(url or "")
            params = urllib.parse.parse_qs(parsed.query)
        except Exception:
            return []
        raw = " ".join(
            " ".join(params.get(key, []))
            for key in ("q", "query", "keywords", "search", "searchTerm", "searchinfo", "st")
        )
        tokens = re.findall(r"[a-z0-9]{3,}", raw.lower())
        return [t for t in tokens if t not in {"the", "and", "for", "with"}][:6]

    def _elements_from_set_of_mark(self, som: list[Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for pos, raw in enumerate(som):
            if not isinstance(raw, dict):
                continue
            try:
                idx = int(raw.get("idx", raw.get("index", pos)))
            except Exception:
                idx = pos
            name = _clean_space(
                str(raw.get("name") or raw.get("label") or raw.get("text") or raw.get("aria") or "")
            )
            if not name:
                continue
            selector = raw.get("selector") or raw.get("css") or raw.get("path")
            if not selector:
                selector = f'[data-anticipy-idx="{idx}"]'
            out.append(
                {
                    "idx": idx,
                    "role": str(raw.get("role") or raw.get("tag") or ""),
                    "name": name[:MAX_NATIVE_LABEL_CHARS],
                    "type": str(raw.get("type") or ""),
                    "state": str(raw.get("state") or ""),
                    "inView": bool(raw.get("inView", True)),
                    "sponsored": bool(raw.get("sponsored", False)),
                    "href": str(raw.get("href") or ""),
                    "selector": str(selector),
                }
            )
            if len(out) >= MAX_NATIVE_MARKS:
                break
        return out

    def _check_available(self, retries: int = 1) -> tuple[bool, str]:
        last_error = ""
        for attempt in range(max(1, retries)):
            status, data, error = self._request_json("GET", "/status", None, timeout=0.8)
            if not error and status == 200 and data.get("ok") is True:
                if data.get("bridge_closed"):
                    return False, "native bridge is closed"
                if data.get("current_task_running"):
                    return False, "native bridge is busy"
                return True, ""
            last_error = error or str(data.get("error") or f"status {status}")
            if attempt + 1 < retries:
                time.sleep(0.35)
        return False, last_error

    def _start_bridge_once(self) -> None:
        now = time.monotonic()
        if now - self._last_start_attempt < 20:
            return
        self._last_start_attempt = now
        self._ensure_cdp_chrome()
        script = Path(os.environ.get("ANTICIPY_NATIVE_BRIDGE_SCRIPT", "~/.anticipy/anticipy-bridge.py")).expanduser()
        if not script.exists():
            return
        py = Path.home() / ".anticipy" / "venv" / "bin" / "python"
        exe = str(py if py.exists() else Path(sys.executable))
        try:
            self._started_process = subprocess.Popen(
                [exe, str(script)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception:
            return

    def _ensure_cdp_chrome(self) -> bool:
        if self.cdp_port <= 0:
            return False
        if not _bool_env("ANTICIPY_NATIVE_BRIDGE_CDP_AUTOSTART", True):
            return self._cdp_up()
        if self._cdp_up():
            return True
        now = time.monotonic()
        if now - self._last_cdp_start_attempt < 20:
            return False
        self._last_cdp_start_attempt = now
        user_data = self._chrome_user_data_dir()
        if user_data is None:
            return False
        chrome = self._chrome_binary()
        if not chrome:
            return False
        try:
            self._started_chrome = subprocess.Popen(
                [
                    chrome,
                    f"--remote-debugging-port={self.cdp_port}",
                    "--remote-allow-origins=http://localhost:*",
                    f"--user-data-dir={user_data}",
                    "--profile-directory=Default",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-features=Translate",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception:
            return False
        for _ in range(36):
            if self._cdp_up():
                return True
            time.sleep(0.5)
        return False

    def _cdp_up(self) -> bool:
        try:
            with urllib.request.urlopen(
                f"http://{self.cdp_host}:{self.cdp_port}/json/version",
                timeout=0.8,
            ) as resp:
                return int(getattr(resp, "status", 200)) == 200
        except Exception:
            return False

    @staticmethod
    def _chrome_binary() -> str:
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            shutil.which("google-chrome") or "",
            shutil.which("chromium") or "",
        ]
        return next((c for c in candidates if c and Path(c).exists()), "")

    @staticmethod
    def _chrome_user_data_dir() -> Optional[Path]:
        configured = os.environ.get("ANTICIPY_CHROME_USER_DATA_DIR", "").strip()
        if configured:
            p = Path(configured).expanduser()
            try:
                p.mkdir(parents=True, exist_ok=True)
            except Exception:
                return None
            return p
        clone = Path.home() / ".anticipy" / "chrome-real-clone"
        return clone if clone.exists() else None

    def _proof(self) -> tuple[int, dict[str, Any], str]:
        if _bool_env("ANTICIPY_NATIVE_BRIDGE_DIRECT_CDP_PROOF", True) and self._cdp_target_id:
            status, proof, error = self._direct_cdp_proof()
            if not error and status == 200 and proof.get("ok") is True:
                return status, proof, error
        payload = {
            "secret": self.secret,
            "limit": 200_000,
            "url_prefix": self._url_prefix,
        }
        return self._request_json("POST", "/surface-proof", payload, timeout=self.request_timeout)

    def _direct_cdp_proof(self) -> tuple[int, dict[str, Any], str]:
        if not self._cdp_up():
            return 0, {}, "cdp unavailable"
        ws_url = self._cdp_page_ws_url()
        if not ws_url:
            return 0, {}, "no matching cdp page target"
        try:
            return 200, asyncio.run(self._direct_cdp_proof_async(ws_url)), ""
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                return 200, loop.run_until_complete(self._direct_cdp_proof_async(ws_url)), ""
            finally:
                loop.close()
        except Exception as exc:
            return 0, {}, f"{type(exc).__name__}: {exc}"

    async def _direct_cdp_proof_async(self, ws_url: str) -> dict[str, Any]:
        import websockets

        counter = 0

        async def call(ws, method: str, params: dict[str, Any], timeout: float = 10.0) -> dict[str, Any]:
            nonlocal counter
            counter += 1
            await ws.send(json.dumps({"id": counter, "method": method, "params": params}))
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                msg = json.loads(raw)
                if int(msg.get("id") or 0) == counter:
                    return msg

        def eval_value(msg: dict[str, Any]) -> Any:
            return (((msg.get("result") or {}).get("result") or {}).get("value"))

        async with websockets.connect(
            ws_url,
            max_size=32 * 1024 * 1024,
            open_timeout=5.0,
            ping_interval=None,
            close_timeout=2.0,
        ) as ws:
            url_msg = await call(ws, "Runtime.evaluate", {"expression": "location.href", "returnByValue": True})
            title_msg = await call(ws, "Runtime.evaluate", {"expression": "document.title", "returnByValue": True})
            snapshot_expr = r"""
            (()=>{
              const ATTR='data-anticipy-native-idx';
              try {
                document.querySelectorAll('['+ATTR+']').forEach(el=>el.removeAttribute(ATTR));
              } catch (_) {}
              const clean = v => String(v || '').replace(/\s+/g,' ').trim();
              const selector = [
                'a','button','input','textarea','select',
                '[role=button]','[role=link]','[role=tab]','[role=menuitem]',
                '[role=checkbox]','[role=option]','[role=searchbox]',
                '[role=textbox]','[role=combobox]','[onclick]',
                '[contenteditable=true]','[contenteditable=""]'
              ].join(',');
              const nodes = Array.from(document.querySelectorAll(selector));
              const candidates = [];
              for (const el of nodes) {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                if (style.display === 'none' || style.visibility === 'hidden') continue;
                if (!rect.width || !rect.height) continue;
                const name = clean(
                  el.innerText ||
                  el.getAttribute('aria-label') ||
                  el.getAttribute('placeholder') ||
                  el.getAttribute('title') ||
                  el.value ||
                  el.getAttribute('alt') ||
                  el.getAttribute('name') ||
                  el.getAttribute('href') ||
                  ''
                );
                const href = el.href || el.getAttribute('href') || '';
                if (!name && !href) continue;
                const inView = rect.bottom >= 0 && rect.right >= 0 &&
                  rect.top <= window.innerHeight && rect.left <= window.innerWidth;
                const hay = (name + ' ' + href).toLowerCase();
                const actionish = /\b(add|put)\b.{0,60}\b(cart|basket|bag)\b|\b(view|open|go to)\b.{0,30}\b(cart|basket|bag)\b/.test(hay);
                const productish = /\/(product|products|p|ip|pd|dp)(\/|$)|\/a\/products\/|\/site\/.+\/\d+\.p|\/sku\/\d+/.test(hay);
                const searchish = /\bsearch\b/.test(hay);
                const y = Math.max(0, rect.top + (window.scrollY || document.documentElement.scrollTop || 0));
                const priority =
                  (inView ? 1000000 : 0) +
                  (actionish ? 600000 : 0) +
                  (productish ? 400000 : 0) +
                  (searchish ? 50000 : 0) -
                  Math.min(200000, y / 10);
                candidates.push({
                  el,
                  priority,
                  originalIndex: candidates.length,
                  role: el.getAttribute('role') || el.tagName.toLowerCase(),
                  tag: el.tagName.toLowerCase(),
                  name: name.slice(0, 180),
                  href: String(href || ''),
                  type: el.getAttribute('type') || '',
                  state: el.disabled ? 'disabled' : '',
                  inView,
                  sponsored: /sponsored|promoted|advertisement/i.test(name),
                });
              }
              const out = candidates
                .sort((a,b) => (b.priority - a.priority) || (a.originalIndex - b.originalIndex))
                .slice(0, 600)
                .map((row, idx) => {
                  row.el.setAttribute(ATTR, String(idx));
                  return {
                    idx,
                    role: row.role,
                    tag: row.tag,
                    name: row.name,
                    href: row.href,
                    type: row.type,
                    state: row.state,
                    inView: row.inView,
                    sponsored: row.sponsored,
                    selector: '[' + ATTR + '="' + idx + '"]'
                  };
                });
              return {
                text: clean(document.body && document.body.innerText || '').slice(0, 5000),
                elements: out
              };
            })()
            """
            snapshot_msg = await call(
                ws,
                "Runtime.evaluate",
                {"expression": snapshot_expr, "returnByValue": True, "awaitPromise": True},
                timeout=16.0,
            )
            html_msg = await call(
                ws,
                "Runtime.evaluate",
                {"expression": "document.documentElement?document.documentElement.outerHTML:''",
                 "returnByValue": True},
                timeout=16.0,
            )
            shot_msg = await call(
                ws,
                "Page.captureScreenshot",
                {"format": "png", "captureBeyondViewport": False},
                timeout=12.0,
            )
        html = str(eval_value(html_msg) or "")
        snapshot = eval_value(snapshot_msg)
        if not isinstance(snapshot, dict):
            snapshot = {}
        b64 = str(((shot_msg.get("result") or {}).get("data") or ""))
        return {
            "ok": bool(html or snapshot.get("text") or snapshot.get("elements")),
            "url": str(eval_value(url_msg) or ""),
            "title": str(eval_value(title_msg) or ""),
            "dom": html[:200_000],
            "text": str(snapshot.get("text") or "")[:5000],
            "set_of_mark": snapshot.get("elements") if isinstance(snapshot.get("elements"), list) else [],
            "screenshot_data_url": ("data:image/png;base64," + b64) if b64 else "",
            "bridge_closed": False,
            "pid": os.getpid(),
            "acquired_via": "native_bridge_direct_cdp_target",
            "bridge_kind": "cdp_direct_target",
            "error": "",
        }

    def _command(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any], str]:
        body = dict(payload)
        body["secret"] = self.secret
        if self._url_prefix and "url_prefix" not in body:
            body["url_prefix"] = self._url_prefix
        return self._request_json("POST", "/surface-command", body, timeout=self.request_timeout)

    def _request_json(
        self,
        method: str,
        path: str,
        payload: Optional[dict[str, Any]],
        *,
        timeout: float,
    ) -> tuple[int, dict[str, Any], str]:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base_url + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                status = int(getattr(resp, "status", 200))
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = int(exc.code)
        except Exception as exc:
            return 0, {}, f"{type(exc).__name__}: {exc}"
        try:
            parsed = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            parsed = {"raw": raw.decode("utf-8", errors="replace")}
        return status, parsed if isinstance(parsed, dict) else {}, ""

    @staticmethod
    def _success(job_id: str, output: dict[str, Any]) -> dict[str, Any]:
        return {"type": "result", "job_id": job_id, "status": "success", "proof": None, "output": output}

    @staticmethod
    def _needs_human(job_id: str, reason: str) -> dict[str, Any]:
        return {
            "type": "result",
            "job_id": job_id,
            "status": "needs_human",
            "proof": None,
            "output": {"reason": reason or "native bridge needs attention"},
        }
