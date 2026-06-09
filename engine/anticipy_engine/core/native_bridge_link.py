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
                    "name": name[:110],
                    "type": node.attrs.get("type", ""),
                    "state": "disabled" if "disabled" in node.attrs else "",
                    "inView": True,
                    "sponsored": bool(re.search(r"\bsponsored|promoted|advertisement\b", name, re.I)),
                    "selector": selector,
                }
            )
            if len(out) >= 140:
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
            try:
                nth = siblings.index(cur) + 1
            except ValueError:
                nth = 1
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
        self._selectors: dict[int, str] = {}
        self._url_prefix = ""
        self._available_cache: tuple[float, bool, str] = (0.0, False, "")
        self._last_start_attempt = 0.0
        self._started_process: Optional[subprocess.Popen] = None

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
        url = str(args.get("url") or "").strip()
        if url:
            status, data, error = self._command({"command": "navigate", "url": url, "new_tab": True})
            if error or status != 200 or data.get("ok") is not True:
                return self._needs_human(job_id, error or str(data.get("error") or f"navigate status {status}"))
            self._url_prefix = _origin(url) or self._url_prefix
            time.sleep(0.8)

        status, proof, error = self._proof()
        if error or status != 200 or proof.get("ok") is not True:
            return self._needs_human(job_id, error or str(proof.get("error") or f"proof status {status}"))
        out, screenshot = self._output_from_proof(proof)
        if out.get("url"):
            self._url_prefix = _origin(str(out.get("url") or "")) or self._url_prefix
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
            self._url_prefix = _origin(url) or self._url_prefix
        elif action == "scroll":
            direction = str(args.get("dir") or "down").lower()
            dy = -700 if direction == "up" else 700
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
            payload = {"command": action, "selector": selector}
            if action == "type":
                payload["text"] = str(args.get("text") or "")
                payload["submit"] = bool(args.get("enter"))
        else:
            return self._needs_human(job_id, f"native bridge does not support action {action}")

        status, data, error = self._command(payload)
        if error or status != 200 or data.get("ok") is not True:
            return self._needs_human(job_id, error or str(data.get("error") or f"{action} status {status}"))
        return self._success(job_id, {"ok": True, "action": action, "data": data.get("data") or {}})

    def _output_from_proof(self, proof: dict[str, Any]) -> tuple[dict[str, Any], str]:
        dom = str(proof.get("dom") or "")
        screenshot = str(proof.get("screenshot_data_url") or "")
        elements: list[dict[str, Any]] = []
        self._selectors = {}
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
        text = ""
        if dom:
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
                    "name": name[:110],
                    "type": str(raw.get("type") or ""),
                    "state": str(raw.get("state") or ""),
                    "inView": bool(raw.get("inView", True)),
                    "sponsored": bool(raw.get("sponsored", False)),
                    "selector": str(selector),
                }
            )
            if len(out) >= 140:
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

    def _proof(self) -> tuple[int, dict[str, Any], str]:
        payload = {
            "secret": self.secret,
            "limit": 200_000,
            "url_prefix": self._url_prefix,
        }
        return self._request_json("POST", "/surface-proof", payload, timeout=self.request_timeout)

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
