"""Universal surface runtime: read, act, verify primitives.

The HANDS of Anticipy. Drives the user's real Chrome via the loopback bridge
(http://127.0.0.1:7777) when available, and falls back to osascript for read
primitives so Anticipy never returns "I cannot do X." Every primitive emits a
structured receipt with surface state, proof artifacts, and an OK flag the
dispatcher can branch on.

Set-of-Mark labels: when DOM/extension is unavailable we expose visible
clickables as "M1, M2, M3..." derived from a System Events accessibility scan.
The planner picks a mark label or a CSS selector; both routes lead here.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


BRIDGE_HOST = os.environ.get("ANTICIPY_SURFACE_HOST", "127.0.0.1")
try:
    BRIDGE_PORT = int(os.environ.get("ANTICIPY_SURFACE_PORT", "7777"))
except ValueError:
    BRIDGE_PORT = 7777
BRIDGE_SECRET = os.environ.get("ANTICIPY_TRIGGER_SECRET", "local-dev")
SCREENSHOT_DIR = Path(os.environ.get(
    "ANTICIPY_UNIVERSAL_SCREENSHOTS",
    str(Path.home() / ".anticipy" / "screenshots" / "universal"),
))


@dataclass
class PrimitiveResult:
    """Single receipt returned by every primitive."""

    ok: bool
    primitive: str
    surface: dict[str, Any] = field(default_factory=dict)
    proof: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    source: str = "universal_surface_runtime"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": bool(self.ok),
            "primitive": self.primitive,
            "surface": dict(self.surface),
            "proof": dict(self.proof),
            "error": self.error or "",
            "source": self.source,
        }


def _apple_quote(value: str) -> str:
    return '"' + (value or "").replace("\\", "\\\\").replace('"', '\\"') + '"'


def _run_osascript(script: str, timeout: float = 20.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


class UniversalSurfaceRuntime:
    """Read-act-verify primitives over Chrome + native UI."""

    BASE_URL = f"http://{BRIDGE_HOST}:{BRIDGE_PORT}"

    def __init__(
        self,
        *,
        secret: str = BRIDGE_SECRET,
        bridge_timeout: float = 15.0,
        screenshot_dir: Path = SCREENSHOT_DIR,
    ) -> None:
        self.secret = secret
        self.bridge_timeout = float(bridge_timeout)
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ HTTP

    def _post(self, path: str, payload: dict[str, Any]) -> tuple[bool, dict[str, Any], str]:
        body = json.dumps({**payload, "secret": self.secret}).encode("utf-8")
        req = urllib.request.Request(
            self.BASE_URL + path,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.bridge_timeout) as resp:
                raw = resp.read()
            data = json.loads(raw.decode("utf-8")) if raw else {}
            return True, data if isinstance(data, dict) else {}, ""
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read()
                data = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                data = {}
            return False, data, f"http {exc.code}"
        except Exception as exc:
            return False, {}, f"{type(exc).__name__}: {exc}"

    def bridge_alive(self) -> bool:
        try:
            req = urllib.request.Request(self.BASE_URL + "/status", method="GET")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return bool(data.get("ok"))
        except Exception:
            return False

    # ------------------------------------------------------------- primitives

    def read(self, surface_target: str = "active_tab") -> PrimitiveResult:
        """Unified snapshot from the live Chrome tab. Falls back to osascript."""
        snapshot: dict[str, Any] = {
            "url": "",
            "title": "",
            "dom_text": "",
            "dom_structure": "",
            "screenshot_path": "",
            "visible_elements_with_set_of_mark_labels": [],
            "source": "",
        }

        bridge_ok = False
        if self.bridge_alive():
            sent, data, err = self._post(
                "/surface-proof", {"limit": 20000, "url_prefix": ""},
            )
            if sent and data.get("ok"):
                snapshot["url"] = str(data.get("url") or "")
                snapshot["title"] = str(data.get("title") or "")
                raw_dom = str(data.get("dom") or "")
                snapshot["dom_text"] = raw_dom[:20000]
                snapshot["dom_structure"] = raw_dom[:20000]
                snapshot["screenshot_path"] = str(data.get("screenshot_path") or "")
                snapshot["source"] = "bridge_surface_proof"
                bridge_ok = True

        if not bridge_ok:
            tab = self._osascript_active_tab()
            snapshot["url"] = tab.get("url", "")
            snapshot["title"] = tab.get("title", "")
            shot = self._screencapture()
            snapshot["screenshot_path"] = shot.get("path", "")
            snapshot["source"] = "osascript_fallback"

        # If DOM is empty/weak, extract Set-of-Mark via System Events ax tree.
        is_weak = (
            len(snapshot["dom_text"]) < 200
            or "data-bridge='applescript'" in snapshot["dom_text"]
        )
        if is_weak and surface_target == "active_tab":
            marks = self._scan_set_of_mark()
            snapshot["visible_elements_with_set_of_mark_labels"] = marks
            snapshot["dom_structure"] = self._compact_ax_tree(marks)

        ok = bool(snapshot["url"] or snapshot["title"] or snapshot["screenshot_path"])
        return PrimitiveResult(
            ok=ok,
            primitive="read",
            surface={"kind": "browser", "target": surface_target,
                     "bridge_alive": bridge_ok},
            proof=snapshot,
            error="" if ok else "read produced no surface signal",
        )

    def open(self, url_or_app: str) -> PrimitiveResult:
        """Navigate Chrome to URL or activate a native app by name."""
        target = (url_or_app or "").strip()
        if not target:
            return PrimitiveResult(
                ok=False, primitive="open", error="open requires url_or_app",
            )
        if target.startswith("http://") or target.startswith("https://"):
            sent, data, err = self._post(
                "/surface-command", {"command": "navigate", "url": target},
            )
            if sent and data.get("ok"):
                return PrimitiveResult(
                    ok=True, primitive="open",
                    surface={"kind": "browser", "navigated_to": target},
                    proof={"url": (data.get("data") or {}).get("url", ""),
                           "title": (data.get("data") or {}).get("title", "")},
                )
            # bridge dead -> osascript navigate
            return self._osascript_navigate(target)
        # native app activation
        result = _run_osascript(
            f'tell application {_apple_quote(target)} to activate'
        )
        ok = result.returncode == 0
        return PrimitiveResult(
            ok=ok, primitive="open",
            surface={"kind": "native_app", "app": target},
            proof={"stdout": result.stdout.strip(), "stderr": result.stderr.strip()},
            error="" if ok else result.stderr.strip()[:200],
        )

    def click(self, selector_or_set_of_mark_label: str) -> PrimitiveResult:
        """Click via CSS selector through bridge, or by mark label via System Events."""
        target = (selector_or_set_of_mark_label or "").strip()
        if not target:
            return PrimitiveResult(
                ok=False, primitive="click", error="click requires a target",
            )
        # Set-of-Mark label like M3
        if target.startswith("M") and target[1:].isdigit():
            return self._click_set_of_mark(int(target[1:]))
        # CSS selector path: requires upgraded bridge; fallback to keyboard nav.
        sent, data, err = self._post(
            "/surface-command",
            {"command": "click", "selector": target, "url_prefix": ""},
        )
        if sent and data.get("ok"):
            return PrimitiveResult(
                ok=True, primitive="click",
                surface={"kind": "browser", "selector": target},
                proof={"data": data.get("data") or {}},
            )
        # Bridge can't click; emit honest receipt so dispatcher can re-plan.
        return PrimitiveResult(
            ok=False, primitive="click",
            surface={"kind": "browser", "selector": target},
            error=str(data.get("error") or err or "selector click not supported by bridge"),
        )

    def type(self, text: str, *, selector: str = "") -> PrimitiveResult:
        """Type text into Chrome via System Events (universal) and bridge if available."""
        if not text:
            return PrimitiveResult(
                ok=False, primitive="type", error="type requires text",
            )
        # Try bridge first when a selector is provided.
        if selector:
            sent, data, err = self._post(
                "/surface-command",
                {"command": "type", "selector": selector, "text": text},
            )
            if sent and data.get("ok"):
                return PrimitiveResult(
                    ok=True, primitive="type",
                    surface={"kind": "browser", "selector": selector},
                    proof={"chars": len(text), "data": data.get("data") or {}},
                )
        # Universal fallback: focus Chrome, then keystroke.
        _run_osascript('tell application "Google Chrome" to activate')
        time.sleep(0.15)
        result = _run_osascript(
            f'tell application "System Events" to keystroke {_apple_quote(text)}',
            timeout=30.0,
        )
        ok = result.returncode == 0
        return PrimitiveResult(
            ok=ok, primitive="type",
            surface={"kind": "browser", "selector": selector or "focused"},
            proof={"chars": len(text), "via": "system_events"},
            error="" if ok else result.stderr.strip()[:200],
        )

    def key(self, key_name: str, *, modifiers: list[str] | None = None) -> PrimitiveResult:
        """Press a named key. Supports return/enter/tab/esc/space + modifiers."""
        name = (key_name or "").strip().lower()
        if not name:
            return PrimitiveResult(
                ok=False, primitive="key", error="key requires key_name",
            )
        key_code_map = {
            "return": 36, "enter": 36, "tab": 48, "space": 49,
            "delete": 51, "escape": 27, "esc": 27, "up": 126, "down": 125,
            "left": 123, "right": 124,
        }
        _run_osascript('tell application "Google Chrome" to activate')
        time.sleep(0.1)
        mods = modifiers or []
        if name in key_code_map:
            code = key_code_map[name]
            if mods:
                using = ", ".join(f"{m} down" for m in mods)
                script = (
                    f'tell application "System Events" to key code {code} using {{{using}}}'
                )
            else:
                script = f'tell application "System Events" to key code {code}'
        else:
            # treat as a single character keystroke
            script = (
                f'tell application "System Events" to keystroke {_apple_quote(key_name)}'
            )
        result = _run_osascript(script)
        ok = result.returncode == 0
        return PrimitiveResult(
            ok=ok, primitive="key",
            surface={"key": name, "modifiers": mods},
            proof={"via": "system_events"},
            error="" if ok else result.stderr.strip()[:200],
        )

    def wait(self, condition: dict[str, Any], *, timeout: float = 10.0,
             interval: float = 0.5) -> PrimitiveResult:
        """Wait for url_contains / title_contains. Polls read() until match or timeout."""
        deadline = time.monotonic() + max(0.1, float(timeout))
        url_needle = str(condition.get("url_contains") or "")
        title_needle = str(condition.get("title_contains") or "")
        attempts = 0
        last_snapshot: dict[str, Any] = {}
        while time.monotonic() < deadline:
            attempts += 1
            snap = self.read().proof
            last_snapshot = snap
            url = str(snap.get("url") or "")
            title = str(snap.get("title") or "")
            url_hit = (not url_needle) or (url_needle in url)
            title_hit = (not title_needle) or (title_needle in title)
            if url_hit and title_hit and (url_needle or title_needle):
                return PrimitiveResult(
                    ok=True, primitive="wait",
                    surface={"attempts": attempts},
                    proof={"url": url, "title": title, "condition": condition},
                )
            time.sleep(interval)
        return PrimitiveResult(
            ok=False, primitive="wait",
            surface={"attempts": attempts},
            proof={"last_url": last_snapshot.get("url", ""),
                   "last_title": last_snapshot.get("title", ""),
                   "condition": condition},
            error=f"wait timed out after {timeout}s",
        )

    def verify(self, expected: dict[str, Any]) -> PrimitiveResult:
        """Read current surface and check expected url/title/text substrings."""
        snap = self.read().proof
        url = str(snap.get("url") or "")
        title = str(snap.get("title") or "")
        dom_text = str(snap.get("dom_text") or "")
        checks: dict[str, bool] = {}
        for k in ("url_contains", "title_contains", "dom_contains"):
            needle = str(expected.get(k) or "")
            if needle:
                haystack = {"url_contains": url, "title_contains": title,
                            "dom_contains": dom_text}[k]
                checks[k] = needle in haystack
        ok = bool(checks) and all(checks.values())
        return PrimitiveResult(
            ok=ok, primitive="verify",
            surface={"url": url, "title": title},
            proof={"checks": checks, "expected": expected,
                   "screenshot_path": snap.get("screenshot_path", "")},
            error="" if ok else f"verify failed: {checks}",
        )

    def ask_user(self, question: str,
                 options: list[str] | None = None) -> PrimitiveResult:
        """Surface a clarifying question; the caller is responsible for routing."""
        return PrimitiveResult(
            ok=True, primitive="ask_user",
            surface={"kind": "prompt"},
            proof={"question": question, "options": list(options or [])},
        )

    def notify_user(self, message: str) -> PrimitiveResult:
        """Best-effort native notification."""
        title = "Anticipy"
        script = (
            f'display notification {_apple_quote(message)} '
            f'with title {_apple_quote(title)}'
        )
        result = _run_osascript(script)
        ok = result.returncode == 0
        return PrimitiveResult(
            ok=ok, primitive="notify_user",
            surface={"kind": "notification"},
            proof={"message": message},
            error="" if ok else result.stderr.strip()[:200],
        )

    # --------------------------------------------------------------- helpers

    def execute(self, plan_step: dict[str, Any]) -> PrimitiveResult:
        """Dispatch a planner output {primitive, args, why}."""
        primitive = str(plan_step.get("primitive") or "").strip()
        a = plan_step.get("args") or {}
        if not isinstance(a, dict):
            a = {}
        m = {
            "read": lambda: self.read(a.get("surface_target", "active_tab")),
            "open": lambda: self.open(a.get("url_or_app", "")),
            "click": lambda: self.click(a.get("target", "")),
            "type": lambda: self.type(a.get("text", ""), selector=a.get("selector", "")),
            "key": lambda: self.key(a.get("key", ""), modifiers=a.get("modifiers")),
            "wait": lambda: self.wait(a.get("condition") or {},
                                       timeout=float(a.get("timeout", 10.0))),
            "verify": lambda: self.verify(a.get("expected") or {}),
            "ask_user": lambda: self.ask_user(a.get("question", ""), a.get("options")),
            "notify_user": lambda: self.notify_user(a.get("message", "")),
        }
        if primitive not in m:
            return PrimitiveResult(ok=False, primitive=primitive or "unknown",
                                   error=f"unknown primitive: {primitive}")
        return m[primitive]()

    def _osascript_active_tab(self) -> dict[str, str]:
        r = _run_osascript(
            'tell application "Google Chrome" to return '
            '(URL of active tab of front window) & "|||" & '
            '(title of active tab of front window)'
        )
        if r.returncode == 0 and "|||" in r.stdout:
            url, title = r.stdout.strip().split("|||", 1)
            return {"url": url, "title": title}
        return {"url": "", "title": ""}

    def _screencapture(self) -> dict[str, str]:
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        out_path = self.screenshot_dir / f"{ts}_universal.png"
        try:
            subprocess.run(["screencapture", "-x", str(out_path)],
                            capture_output=True, timeout=10.0, check=False)
            if out_path.exists():
                return {"path": str(out_path), "bytes": str(out_path.stat().st_size)}
        except Exception:
            pass
        return {"path": "", "bytes": "0"}

    def _osascript_navigate(self, url: str) -> PrimitiveResult:
        r = _run_osascript(
            'tell application "Google Chrome"\n  activate\n  set URL of active tab '
            f'of front window to {_apple_quote(url)}\nend tell'
        )
        ok = r.returncode == 0
        time.sleep(0.8)
        return PrimitiveResult(
            ok=ok, primitive="open",
            surface={"kind": "browser", "navigated_to": url, "via": "osascript"},
            error="" if ok else r.stderr.strip()[:200],
        )

    def _scan_set_of_mark(self) -> list[dict[str, Any]]:
        script = (
            'tell application "System Events" to tell process "Google Chrome"\n'
            '  try\n    set _btns to buttons of window 1\n    set out to ""\n'
            '    repeat with i from 1 to (count of _btns)\n'
            '      try\n        set out to out & i & ":" & (name of item i of _btns) & "\\n"\n'
            '      end try\n    end repeat\n    return out\n'
            '  on error errMsg\n    return "ERR:" & errMsg\n  end try\nend tell'
        )
        try:
            r = _run_osascript(script, timeout=8.0)
            if r.returncode != 0 or r.stdout.startswith("ERR:"):
                return []
            out: list[dict[str, Any]] = []
            for line in r.stdout.strip().splitlines()[:24]:
                if ":" in line:
                    idx, name = line.split(":", 1)
                    if idx.isdigit():
                        out.append({"label": f"M{idx}", "name": name.strip(),
                                    "kind": "button"})
            return out
        except Exception:
            return []

    def _compact_ax_tree(self, marks: list[dict[str, Any]]) -> str:
        return "\n".join(f"{m['label']} button: {m['name'][:80]}" for m in marks)

    def _click_set_of_mark(self, idx: int) -> PrimitiveResult:
        r = _run_osascript(
            'tell application "System Events" to tell process "Google Chrome"\n'
            f'  try\n    click (button {idx} of window 1)\n    return "OK"\n'
            '  on error errMsg\n    return "ERR:" & errMsg\n  end try\nend tell'
        )
        ok = r.returncode == 0 and not r.stdout.startswith("ERR:")
        return PrimitiveResult(
            ok=ok, primitive="click",
            surface={"kind": "set_of_mark", "label": f"M{idx}"},
            proof={"stdout": r.stdout.strip()},
            error="" if ok else r.stdout.strip()[:200] or r.stderr.strip()[:200],
        )


__all__ = ["UniversalSurfaceRuntime", "PrimitiveResult"]
