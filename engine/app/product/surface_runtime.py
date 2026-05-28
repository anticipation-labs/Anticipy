"""Product surface runtime client for the installed Chrome bridge.

This is intentionally small and synchronous: the product backend only needs a
thin first-hop seam to the existing native-messaging daemon before it falls
back to frozen DSv4/CDP paths.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


BRIDGE_HOST = os.environ.get("ANTICIPY_SURFACE_HOST", "127.0.0.1")
try:
    BRIDGE_PORT = int(os.environ.get("ANTICIPY_SURFACE_PORT", "7777"))
except ValueError:
    BRIDGE_PORT = 7777
BRIDGE_SOURCE = "chrome_extension_native_messaging"
RUNTIME_SOURCE = "product_surface_runtime"


def _receipt(
    *,
    ok: bool,
    surface: dict[str, Any] | None = None,
    proof: dict[str, Any] | None = None,
    source: str = RUNTIME_SOURCE,
    error: str = "",
) -> dict[str, Any]:
    return {
        "ok": bool(ok),
        "surface": surface or {},
        "proof": proof or {},
        "source": source,
        "error": error or "",
    }


def normalize_browser_url(raw: str) -> str:
    """Return a navigable URL for explicit URL/domain inputs only."""
    target = re.sub(r"\s+", " ", raw or "").strip().strip("\"'")
    target = target.rstrip(".,);]")
    if not target:
        return ""
    if re.match(r"^https?://", target, re.IGNORECASE):
        return target
    if re.match(r"^www\.", target, re.IGNORECASE):
        return f"https://{target}"
    if re.match(r"^[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?:[/:?#].*)?$",
                target):
        return f"https://{target}"
    return ""


def google_search_url(query: str) -> str:
    clean = re.sub(r"\s+", " ", query or "").strip()
    if not clean:
        return ""
    return "https://www.google.com/search?" + urllib.parse.urlencode({"q": clean})


def browser_task_url(verb: str, target: str) -> str:
    if verb == "open_search_tab":
        return google_search_url(target)
    if verb in {"open_browser_tab", "navigate", "open"}:
        return normalize_browser_url(target)
    return ""


class SurfaceRuntime:
    """HTTP client for the loopback native bridge listener.

    The daemon is owned by the Chrome extension/native-messaging bridge and
    exposes a tiny loopback API on 127.0.0.1:7777. This client never launches
    Chrome and never speaks CDP directly. It sends bounded browser primitives
    through the user's installed Chrome extension/native-messaging bridge, then
    asks the same bridge for a visible surface receipt.
    """

    def __init__(
        self,
        *,
        host: str = BRIDGE_HOST,
        port: int = BRIDGE_PORT,
        secret: str | None = None,
        timeout: float = 2.0,
        command_timeout: float = 15.0,
        proof_timeout: float = 8.0,
        proof_limit: int = 20000,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.base_url = f"http://{host}:{self.port}"
        self.secret = (
            secret
            if secret is not None
            else os.environ.get("ANTICIPY_TRIGGER_SECRET", "local-dev")
        )
        self.timeout = float(timeout)
        self.command_timeout = float(command_timeout)
        self.proof_timeout = float(proof_timeout)
        self.proof_limit = int(proof_limit)

    def _surface(self, **extra: Any) -> dict[str, Any]:
        surface = {
            "kind": "browser",
            "bridge": "native_messaging",
            "host": self.host,
            "port": self.port,
            "runtime": RUNTIME_SOURCE,
        }
        surface.update(extra)
        return surface

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> tuple[int, dict[str, Any], str]:
        body = None
        headers: dict[str, str] = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            self.base_url + path,
            data=body,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(
                req, timeout=self.timeout if timeout is None else timeout
            ) as resp:
                raw = resp.read()
                status = int(getattr(resp, "status", 200))
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = int(exc.code)
        except Exception as exc:
            return 0, {}, f"{type(exc).__name__}: {exc}"
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            data = {"raw": raw.decode("utf-8", errors="replace")}
        return status, data if isinstance(data, dict) else {}, ""

    def availability(self) -> dict[str, Any]:
        status, data, error = self._request_json("GET", "/status")
        if error:
            return _receipt(
                ok=False,
                surface=self._surface(available=False),
                source=BRIDGE_SOURCE,
                error=error,
            )
        if status != 200 or data.get("ok") is not True:
            return _receipt(
                ok=False,
                surface=self._surface(available=False, status=status),
                source=BRIDGE_SOURCE,
                error=str(data.get("error") or f"status {status}"),
            )
        if data.get("bridge_closed"):
            return _receipt(
                ok=False,
                surface=self._surface(available=False, status=status),
                source=BRIDGE_SOURCE,
                error="native bridge is closed",
            )
        if data.get("current_task_running"):
            return _receipt(
                ok=False,
                surface=self._surface(available=False, status=status),
                source=BRIDGE_SOURCE,
                error="native bridge is busy",
            )
        return _receipt(
            ok=True,
            surface=self._surface(
                available=True,
                status=status,
                pid=data.get("pid"),
                platform=data.get("platform"),
            ),
            source=BRIDGE_SOURCE,
        )

    def available(self) -> bool:
        return bool(self.availability().get("ok"))

    def request_surface_proof(
        self,
        *,
        limit: int | None = None,
        url_prefix: str = "",
    ) -> dict[str, Any]:
        payload = {
            "secret": self.secret,
            "limit": int(limit or self.proof_limit),
            "url_prefix": url_prefix,
        }
        status, data, error = self._request_json(
            "POST", "/surface-proof", payload, timeout=self.proof_timeout
        )
        if error:
            return _receipt(
                ok=False,
                surface=self._surface(),
                source=BRIDGE_SOURCE,
                error=error,
            )
        proof = self._proof_summary(data)
        ok = status == 200 and data.get("ok") is True
        return _receipt(
            ok=ok,
            surface=self._surface(status=status),
            proof=proof,
            source=BRIDGE_SOURCE,
            error="" if ok else str(data.get("error") or f"proof status {status}"),
        )

    def run_click(
        self,
        *,
        selector: str,
        url_prefix: str = "",
        task: str = "",
    ) -> dict[str, Any]:
        return self.run_surface_command(
            command="click",
            selector=selector,
            url_prefix=url_prefix,
            task=task,
        )

    def run_type(
        self,
        *,
        selector: str,
        text: str,
        submit: bool = False,
        url_prefix: str = "",
        task: str = "",
    ) -> dict[str, Any]:
        return self.run_surface_command(
            command="type",
            selector=selector,
            text=text,
            submit=submit,
            url_prefix=url_prefix,
            task=task,
        )

    def run_key(
        self,
        *,
        key: str = "Enter",
        selector: str = "",
        modifiers: list[str] | None = None,
        url_prefix: str = "",
        task: str = "",
    ) -> dict[str, Any]:
        clean_key = (key or "Enter").strip()
        return self.run_surface_command(
            command="key",
            selector=selector,
            text=clean_key,
            url_prefix=url_prefix,
            task=task,
            extra={"key": clean_key, "modifiers": modifiers or []},
        )

    def read_surface(
        self,
        *,
        selector: str = "",
        url_prefix: str = "",
        task: str = "",
    ) -> dict[str, Any]:
        return self.run_surface_command(
            command="read",
            selector=selector,
            url_prefix=url_prefix,
            task=task,
            proof_after=True,
        )

    def wait_for_url(
        self,
        *,
        expected_url: str = "",
        contains: str = "",
        url_prefix: str = "",
        timeout: float = 10.0,
        interval: float = 0.25,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + max(0.0, float(timeout))
        attempts = 0
        last = _receipt(ok=False, surface=self._surface(), source=BRIDGE_SOURCE)
        while True:
            attempts += 1
            last = self.request_surface_proof(
                limit=self.proof_limit,
                url_prefix=url_prefix,
            )
            proof = last.get("proof") if isinstance(last.get("proof"), dict) else {}
            observed_url = str(proof.get("url") or "")
            url_match = self._wait_url_matches(
                observed_url,
                expected_url=expected_url,
                contains=contains,
            )
            proof["url_match"] = url_match
            proof["attempts"] = attempts
            proof["wait_timeout_seconds"] = float(timeout)
            last["proof"] = proof
            if last.get("ok") and url_match:
                return _receipt(
                    ok=True,
                    surface=last.get("surface") if isinstance(
                        last.get("surface"), dict) else self._surface(),
                    proof=proof,
                    source=BRIDGE_SOURCE,
                )
            if time.monotonic() >= deadline:
                if not last.get("error"):
                    last["error"] = "wait_for_url timed out"
                return last
            time.sleep(max(0.05, float(interval)))

    def run_surface_command(
        self,
        *,
        command: str,
        selector: str = "",
        text: str = "",
        url: str = "",
        submit: bool = False,
        url_prefix: str = "",
        task: str = "",
        proof_after: bool = True,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        supported = {
            "click",
            "type",
            "key",
            "read",
            "extract",
            "getDOMSnapshot",
        }
        if command not in supported:
            return _receipt(
                ok=False,
                surface=self._surface(command=command, supported=False),
                source=BRIDGE_SOURCE,
                error=f"unsupported surface command: {command}",
            )
        if command in {"click", "type"} and not selector:
            return _receipt(
                ok=False,
                surface=self._surface(command=command, supported=False),
                source=BRIDGE_SOURCE,
                error=f"{command} requires selector",
            )
        available = self.availability()
        if not available.get("ok"):
            return _receipt(
                ok=False,
                surface=self._surface(
                    command=command,
                    selector=selector,
                    task=task,
                    available=False,
                    supported=True,
                ),
                proof=available.get("proof") if isinstance(
                    available.get("proof"), dict) else {},
                source=available.get("source") or BRIDGE_SOURCE,
                error=str(available.get("error") or "native bridge unavailable"),
            )
        payload = {
            "secret": self.secret,
            "command": command,
            "selector": selector,
            "text": text,
            "url": url,
            "submit": bool(submit),
            "url_prefix": url_prefix,
        }
        if extra:
            payload.update(extra)
        status, data, error = self._request_json(
            "POST",
            "/surface-command",
            payload,
            timeout=self.command_timeout,
        )
        surface = self._surface(
            command=command,
            selector=selector,
            task=task,
            supported=True,
            available=True,
            command_status=status,
            url_prefix=url_prefix,
        )
        command_data = data.get("data") if isinstance(data.get("data"), dict) else {}
        if error:
            return _receipt(
                ok=False,
                surface=surface,
                source=BRIDGE_SOURCE,
                error=error,
            )
        if status != 200 or data.get("ok") is not True:
            return _receipt(
                ok=False,
                surface=surface,
                source=BRIDGE_SOURCE,
                error=str(data.get("error") or f"command status {status}"),
            )
        if not proof_after:
            return _receipt(
                ok=True,
                surface=surface,
                proof=self._command_proof(command, command_data),
                source=BRIDGE_SOURCE,
            )
        proof_receipt = self.request_surface_proof(
            limit=self.proof_limit,
            url_prefix=url_prefix,
        )
        proof = proof_receipt.get("proof") if isinstance(
            proof_receipt.get("proof"), dict) else {}
        proof.update(self._command_proof(command, command_data))
        ok = bool(proof_receipt.get("ok"))
        return _receipt(
            ok=ok,
            surface=surface,
            proof=proof,
            source=BRIDGE_SOURCE,
            error="" if ok else str(
                proof_receipt.get("error") or "surface proof did not confirm command"
            ),
        )

    def list_tabs(self) -> dict[str, Any]:
        available = self.availability()
        if not available.get("ok"):
            return _receipt(
                ok=False,
                surface=self._surface(
                    command="list_tabs",
                    supported=True,
                    available=False,
                ),
                source=available.get("source") or BRIDGE_SOURCE,
                error=str(available.get("error") or "native bridge unavailable"),
            )
        status, data, error = self._request_json(
            "POST",
            "/surface-command",
            {"secret": self.secret, "command": "list_tabs"},
            timeout=max(self.command_timeout, 45.0),
        )
        command_data = data.get("data") if isinstance(data.get("data"), dict) else {}
        ok = status == 200 and data.get("ok") is True
        return _receipt(
            ok=ok,
            surface=self._surface(command="list_tabs", supported=True,
                                  command_status=status),
            proof={"command": "list_tabs", **command_data},
            source=BRIDGE_SOURCE,
            error="" if ok else str(error or data.get("error")
                                    or f"command status {status}"),
        )

    def close_tabs_matching(
        self,
        *,
        url_prefix: str = "",
        url_includes: str = "",
        title_includes: str = "",
        max_close: int = 10,
    ) -> dict[str, Any]:
        if not (url_prefix or url_includes or title_includes):
            return _receipt(
                ok=False,
                surface=self._surface(
                    command="close_tabs_matching",
                    supported=False,
                ),
                source=BRIDGE_SOURCE,
                error="close_tabs_matching requires a URL or title constraint",
            )
        available = self.availability()
        if not available.get("ok"):
            return _receipt(
                ok=False,
                surface=self._surface(
                    command="close_tabs_matching",
                    supported=True,
                    available=False,
                ),
                source=available.get("source") or BRIDGE_SOURCE,
                error=str(available.get("error") or "native bridge unavailable"),
            )
        payload = {
            "secret": self.secret,
            "command": "close_tabs_matching",
            "url_prefix": url_prefix,
            "url_includes": url_includes,
            "title_includes": title_includes,
            "max_close": max(0, min(int(max_close), 50)),
        }
        status, data, error = self._request_json(
            "POST", "/surface-command", payload, timeout=max(self.command_timeout, 45.0)
        )
        command_data = data.get("data") if isinstance(data.get("data"), dict) else {}
        ok = status == 200 and data.get("ok") is True
        return _receipt(
            ok=ok,
            surface=self._surface(
                command="close_tabs_matching",
                supported=True,
                command_status=status,
            ),
            proof={"command": "close_tabs_matching", **command_data},
            source=BRIDGE_SOURCE,
            error="" if ok else str(error or data.get("error")
                                    or f"command status {status}"),
        )

    def run_browser_task(
        self,
        *,
        verb: str,
        target: str,
        task: str = "",
    ) -> dict[str, Any]:
        if verb not in {"open_browser_tab", "open_search_tab", "navigate", "open"}:
            return _receipt(
                ok=False,
                surface=self._surface(verb=verb, target=target, supported=False),
                source=BRIDGE_SOURCE,
                error=f"unsupported surface task: {verb}",
            )
        url = browser_task_url(verb, target)
        if not url:
            return _receipt(
                ok=False,
                surface=self._surface(verb=verb, target=target, supported=False),
                source=BRIDGE_SOURCE,
                error="surface task requires an explicit URL/domain or search query",
            )
        available = self.availability()
        if not available.get("ok"):
            surface = self._surface(
                verb=verb,
                target=target,
                url=url,
                task=task,
                supported=True,
                available=False,
            )
            return _receipt(
                ok=False,
                surface=surface,
                proof=available.get("proof") if isinstance(
                    available.get("proof"), dict) else {},
                source=available.get("source") or BRIDGE_SOURCE,
                error=str(available.get("error") or "native bridge unavailable"),
            )

        command_payload = {
            "secret": self.secret,
            "command": "navigate",
            "url": url,
        }
        status, data, error = self._request_json(
            "POST",
            "/surface-command",
            command_payload,
            timeout=self.command_timeout,
        )
        surface = self._surface(
            verb=verb,
            target=target,
            url=url,
            task=task,
            supported=True,
            available=True,
            command_status=status,
            command=data.get("command") or "navigate",
            command_data=data.get("data") if isinstance(data.get("data"), dict) else {},
        )
        if error:
            return _receipt(
                ok=False,
                surface=surface,
                source=BRIDGE_SOURCE,
                error=error,
            )
        if status != 200 or data.get("ok") is not True:
            return _receipt(
                ok=False,
                surface=surface,
                source=BRIDGE_SOURCE,
                error=str(data.get("error") or f"command status {status}"),
            )

        proof_receipt = self._proof_after_navigation(verb=verb, target=target, url=url)
        proof = proof_receipt.get("proof") if isinstance(
            proof_receipt.get("proof"), dict) else {}
        ok = bool(proof_receipt.get("ok") and proof.get("url_match"))
        return _receipt(
            ok=ok,
            surface=surface,
            proof=proof,
            source=BRIDGE_SOURCE,
            error="" if ok else str(
                proof_receipt.get("error")
                or "surface proof did not confirm navigation"
            ),
        )

    def _proof_after_navigation(
        self,
        *,
        verb: str,
        target: str,
        url: str,
    ) -> dict[str, Any]:
        last = _receipt(ok=False, surface=self._surface(), source=BRIDGE_SOURCE)
        for attempt in range(4):
            if attempt:
                time.sleep(0.45)
            last = self.request_surface_proof(limit=self.proof_limit)
            proof = last.get("proof") if isinstance(last.get("proof"), dict) else {}
            if last.get("ok") and self._proof_matches(
                str(proof.get("url") or ""), url, verb, target
            ):
                proof["url_match"] = True
                return _receipt(
                    ok=True,
                    surface=last.get("surface") if isinstance(
                        last.get("surface"), dict) else self._surface(),
                    proof=proof,
                    source=BRIDGE_SOURCE,
                )
            proof["url_match"] = False
            last["proof"] = proof
        if not last.get("error"):
            last["error"] = "surface proof URL did not match requested task"
        return last

    def _proof_summary(self, data: dict[str, Any]) -> dict[str, Any]:
        dom = str(data.get("dom") or "")
        screenshot = str(data.get("screenshot_data_url") or "")
        return {
            "ok": bool(data.get("ok")),
            "url": str(data.get("url") or ""),
            "acquired_via": str(data.get("acquired_via") or BRIDGE_SOURCE),
            "has_dom": bool(dom),
            "dom_chars": len(dom),
            "has_screenshot": bool(screenshot),
            "screenshot_chars": len(screenshot),
            "bridge_closed": bool(data.get("bridge_closed")),
            "pid": data.get("pid"),
        }

    def _proof_matches(
        self,
        observed_url: str,
        expected_url: str,
        verb: str,
        target: str,
    ) -> bool:
        if not observed_url:
            return False
        observed = urllib.parse.urlparse(observed_url)
        expected = urllib.parse.urlparse(expected_url)
        if verb == "open_search_tab":
            if "google." not in observed.netloc.lower():
                return False
            hay = urllib.parse.unquote_plus(observed_url).lower()
            tokens = [
                token.lower()
                for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9-]{1,}", target)
            ][:6]
            return all(token in hay for token in tokens) if tokens else True
        if observed.netloc.lower() == expected.netloc.lower():
            return True
        return observed_url.rstrip("/") == expected_url.rstrip("/")

    def _command_proof(
        self,
        command: str,
        command_data: dict[str, Any],
    ) -> dict[str, Any]:
        proof: dict[str, Any] = {
            "command": command,
            "command_data": command_data,
        }
        text = command_data.get("text")
        html = command_data.get("html")
        if isinstance(text, str):
            proof["text_chars"] = len(text)
            proof["text"] = text[:1000]
        if isinstance(html, str):
            proof["html_chars"] = len(html)
        for key in (
            "clicked",
            "typed",
            "selector",
            "submitted",
            "preservedValue",
            "key",
            "activeTag",
        ):
            if key in command_data:
                proof[key] = command_data.get(key)
        return proof

    def _wait_url_matches(
        self,
        observed_url: str,
        *,
        expected_url: str = "",
        contains: str = "",
    ) -> bool:
        if not observed_url:
            return False
        if expected_url and observed_url.rstrip("/") == expected_url.rstrip("/"):
            return True
        if contains and contains in observed_url:
            return True
        return False


__all__ = [
    "BRIDGE_SOURCE",
    "SurfaceRuntime",
    "browser_task_url",
    "google_search_url",
    "normalize_browser_url",
]
