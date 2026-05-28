#!/usr/bin/env python3
"""
Anticipy agent daemon — entry point.

Launched by Chrome (over the native-messaging host manifest) every time
the extension calls ``chrome.runtime.connectNative("com.anticipy.agent")``.
Lifecycle ends when Chrome closes the port (stdin EOF).

Responsibilities:
  1. Load .env from /workspaces/Anticipy/.env.local in dev mode, or
     ~/.anticipy/.env on the user's Mac after install.
  2. Speak the native-messaging wire codec (see protocol.py).
  3. On {type: "task_start", task}: spin up the orchestrator and pipe
     bridge commands over stdout, results back over stdin.
  4. On {type: "cancel"}: abort the current task cleanly.
  5. Auto-update check: at startup, fetch
     https://anticipy.ai/anticipy-agent.py, hash-compare, write to a side
     file. Next launch picks it up. (Simple — don't over-engineer.)

The daemon does NOT import the orchestrator at import time. It imports
lazily so an import failure in (e.g.) supabase_client.py reaches Chrome's
error log instead of crashing on startup.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


# ── Paths & logging ────────────────────────────────────────────────────

def _log_dir() -> Path:
    """~/Library/Logs/Anticipy on macOS, ~/.anticipy/logs elsewhere."""
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Logs" / "Anticipy"
    return home / ".anticipy" / "logs"


def _state_dir() -> Path:
    """~/.anticipy/ — always.  Holds startup.log, startup_error.txt,
    last_status.json so a crashed daemon leaves visible evidence even
    when the main logger isn't initialized yet."""
    p = Path.home() / ".anticipy"
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p


def _startup_trace(step: str, ok: bool = True, detail: str = "") -> None:
    """Append one line to ~/.anticipy/startup.log. Independent of the
    logging module so it works even if _setup_logging hasn't run yet.
    Truncates after 100 lines so the file can't grow forever."""
    line = f"{int(time.time())} {'OK' if ok else 'FAIL'} {step}"
    if detail:
        line += f" :: {detail.strip().splitlines()[0][:200]}"
    line += "\n"
    try:
        p = _state_dir() / "startup.log"
        existing = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
        existing.append(line.rstrip())
        if len(existing) > 100:
            existing = existing[-100:]
        p.write_text("\n".join(existing) + "\n", encoding="utf-8")
    except Exception:
        pass


def _crash_report(phase: str, exc: BaseException) -> None:
    """Dump a full traceback to ~/.anticipy/startup_error.txt. Overwrites
    on each crash — only the most recent failure matters for debugging."""
    import traceback as _tb
    try:
        body = (
            f"phase={phase}\n"
            f"time={int(time.time())}\n"
            f"python={sys.version.split()[0]}\n"
            f"platform={sys.platform}\n"
            f"sys.argv={sys.argv}\n"
            f"sys.path[:5]={sys.path[:5]}\n"
            f"--- traceback ---\n"
            f"{_tb.format_exc()}\n"
        )
        (_state_dir() / "startup_error.txt").write_text(body, encoding="utf-8")
    except Exception:
        pass


def _setup_logging() -> None:
    log_dir = _log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_dir / "agent.log")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    ))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    # NEVER log to stderr in a native-messaging host — Chrome treats it as
    # a protocol error and kills the port. The log file is the only sink.


def _load_env() -> None:
    """Load env vars from .env.local (dev) or ~/.anticipy/.env (prod)."""
    candidates = [
        Path("/workspaces/Anticipy/.env.local"),
        Path.home() / ".anticipy" / ".env",
    ]
    for p in candidates:
        if not p.exists():
            continue
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                # Only set when not already present so explicit env wins.
                os.environ.setdefault(k, v)
        except Exception:
            logging.exception("env load failed for %s", p)


# ── Auto-update ────────────────────────────────────────────────────────

UPDATE_URL = "https://anticipy.ai/anticipy-agent.py"
UPDATE_INTERVAL_S = 12 * 3600  # once per 12h


def _self_path() -> Path:
    return Path(__file__).resolve()


def _hash_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _stamp_path() -> Path:
    return _self_path().with_suffix(".update-stamp")


def _should_check_update() -> bool:
    sp = _stamp_path()
    if not sp.exists():
        return True
    try:
        last = float(sp.read_text().strip())
    except Exception:
        return True
    return (time.time() - last) > UPDATE_INTERVAL_S


def _maybe_self_update() -> None:
    """Best-effort: download latest agent, drop alongside as .pending."""
    if not _should_check_update():
        return
    try:
        req = urllib.request.Request(UPDATE_URL, headers={"User-Agent": "anticipy-agent/4.0"})
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            new = resp.read()
        if len(new) < 500:
            return  # tiny payload → likely an error page
        new_hash = hashlib.sha256(new).hexdigest()
        current_hash = _hash_file(_self_path())
        if new_hash == current_hash:
            _stamp_path().write_text(str(time.time()))
            return
        # Write side file; next launch replaces self.
        pending = _self_path().with_suffix(".py.pending")
        pending.write_bytes(new)
        _stamp_path().write_text(str(time.time()))
        logging.info("update staged at %s (hash %s)", pending, new_hash[:12])
    except Exception:
        logging.debug("self-update skipped (offline or 4xx)", exc_info=True)


def _activate_pending_update() -> None:
    """If a .pending file exists, swap it in as the live agent."""
    pending = _self_path().with_suffix(".py.pending")
    if not pending.exists():
        return
    try:
        backup = _self_path().with_suffix(".py.bak")
        if backup.exists():
            backup.unlink()
        _self_path().rename(backup)
        pending.rename(_self_path())
        logging.info("activated staged update")
    except Exception:
        logging.exception("update activation failed; keeping current")


# ── Adapter shim so engine imports resolve ─────────────────────────────


def _bootstrap_engine_imports() -> None:
    """Make ``engine.app.*`` modules importable from the daemon.

    In dev we're inside the repo so /workspaces/Anticipy/engine is on the
    sys.path.  On the user's Mac the installer drops the engine package
    next to anticipy_agent.py inside ~/.anticipy/, so add the parent dir
    so ``from app import orchestrator`` works.
    """
    here = _self_path().parent
    # Dev: repo at /workspaces/Anticipy
    repo_root = Path("/workspaces/Anticipy")
    engine_dir = repo_root / "engine"
    if engine_dir.exists():
        sys.path.insert(0, str(engine_dir))
        sys.path.insert(0, str(repo_root))
    # Prod: ~/.anticipy/engine bundled by installer
    alt = here / "engine"
    if alt.exists():
        sys.path.insert(0, str(alt))


def _patch_ws_bridge_exports() -> None:
    """Make ``from app.ws_bridge import *`` resolve to NativeBridge classes.

    The orchestrator currently does:
        from app.ws_bridge import BridgeClosed, BridgeTimeout, ...

    The cheapest way to keep the orchestrator unchanged is to replace
    those names in the imported ``app.ws_bridge`` module so they point at
    the NativeBridge versions.  Done at boot, before orchestrator import.
    """
    try:
        import app.ws_bridge as wsb  # type: ignore
    except Exception:
        # Engine package not on path (smoke run) — caller handles.
        return
    try:
        from . import native_bridge as nb  # type: ignore
    except (ImportError, ValueError):
        import native_bridge as nb
    # Re-point the classes so isinstance/identity checks line up.
    wsb.BridgeClosed = nb.BridgeClosed
    wsb.BridgeTimeout = nb.BridgeTimeout
    wsb.CommandFailed = nb.CommandFailed
    wsb.TaskCancelled = nb.TaskCancelled
    # WSBridge is referenced as a type-hint only — leave it alone.


# ── Visible Chrome compatibility primitives ───────────────────────────


def _apple_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _run_osascript(script: str, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["osascript", "-e", script],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def _chrome_list_tabs_applescript() -> list[dict]:
    """Read visible tabs from the user's actual Chrome on macOS.

    This is a compatibility path for stale unpacked extensions: the native
    daemon can still prove and perform tab-level browser actions on the user's
    real Chrome surface while the extension is being refreshed.
    """

    script = r'''
tell application "Google Chrome"
  set outText to ""
  repeat with w in windows
    set winId to id of w
    set tabCount to count of tabs of w
    repeat with i from 1 to tabCount
      set t to tab i of w
      set tabUrl to URL of t as text
      set tabTitle to title of t as text
      set outText to outText & (winId as text) & tab & (i as text) & tab & tabUrl & tab & tabTitle & linefeed
    end repeat
  end repeat
  return outText
end tell
'''
    result = _run_osascript(script)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "Chrome AppleScript failed").strip())
    tabs: list[dict] = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 3)
        if len(parts) != 4:
            continue
        window_id, index, url, title = parts
        try:
            index_value = int(index)
        except Exception:
            index_value = 0
        tabs.append({
            "windowId": window_id,
            "index": index_value,
            "url": url,
            "title": title,
            "source": "real_chrome_applescript",
        })
    return tabs


def _chrome_active_tab_applescript() -> dict:
    script = r'''
tell application "Google Chrome"
  set w to front window
  set t to active tab of w
  return (id of w as text) & tab & (active tab index of w as text) & tab & (URL of t as text) & tab & (title of t as text)
end tell
'''
    result = _run_osascript(script, timeout=6.0)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "Chrome active tab failed").strip())
    parts = result.stdout.strip().split("\t", 3)
    if len(parts) != 4:
        raise RuntimeError("Chrome active tab returned an unexpected shape")
    window_id, index, url, title = parts
    try:
        index_value = int(index)
    except Exception:
        index_value = 0
    return {
        "windowId": window_id,
        "index": index_value,
        "url": url,
        "title": title,
        "active": True,
        "source": "real_chrome_applescript",
    }


def _tab_matches_constraint(
    tab: dict,
    *,
    url_prefix: str = "",
    url_includes: str = "",
    title_includes: str = "",
) -> bool:
    url = str(tab.get("url") or "")
    title = str(tab.get("title") or "")
    url_l = url.lower()
    title_l = title.lower()
    if url_prefix and url_l.startswith(url_prefix.lower()):
        return True
    if url_includes and url_includes.lower() in url_l:
        return True
    if title_includes and title_includes.lower() in title_l:
        return True
    return False


def _chrome_close_front_tab_applescript() -> None:
    script = 'tell application "Google Chrome" to close active tab of front window'
    result = _run_osascript(script, timeout=6.0)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "Chrome close active tab failed").strip())


def _chrome_close_tabs_matching_applescript(
    *,
    url_prefix: str = "",
    url_includes: str = "",
    title_includes: str = "",
    max_close: int = 10,
) -> dict:
    try:
        active_tab = _chrome_active_tab_applescript()
        if _tab_matches_constraint(
            active_tab,
            url_prefix=url_prefix,
            url_includes=url_includes,
            title_includes=title_includes,
        ):
            if int(max_close or 0) > 0:
                _chrome_close_front_tab_applescript()
                closed = [active_tab]
            else:
                closed = []
            return {
                "matched": [active_tab],
                "closed": closed,
                "matchedCount": 1,
                "closedCount": len(closed),
                "source": "real_chrome_applescript_active_tab",
            }
    except Exception:
        logging.debug("active-tab close fallback missed", exc_info=True)

    tabs = _chrome_list_tabs_applescript()
    matched: list[dict] = []
    for tab in tabs:
        if _tab_matches_constraint(
            tab,
            url_prefix=url_prefix,
            url_includes=url_includes,
            title_includes=title_includes,
        ):
            matched.append(tab)

    max_close = max(0, min(int(max_close or 0), 50))
    to_close = matched[:max_close]
    by_window: dict[str, list[int]] = {}
    for tab in to_close:
        window_id = str(tab.get("windowId") or "")
        index = int(tab.get("index") or 0)
        if window_id and index > 0:
            by_window.setdefault(window_id, []).append(index)

    if by_window:
        lines = ['tell application "Google Chrome"']
        for window_id, indices in by_window.items():
            lines.append("  repeat with w in windows")
            lines.append(f"    if (id of w as text) is {_apple_quote(window_id)} then")
            for index in sorted(indices, reverse=True):
                lines.append("      try")
                lines.append(f"        close tab {index} of w")
                lines.append("      end try")
            lines.append("    end if")
            lines.append("  end repeat")
        lines.append("end tell")
        result = _run_osascript("\n".join(lines), timeout=12.0)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "Chrome close tabs failed").strip())

    return {
        "matched": matched,
        "closed": to_close,
        "matchedCount": len(matched),
        "closedCount": len(to_close),
        "source": "real_chrome_applescript",
    }


# ── Daemon main loop ───────────────────────────────────────────────────


class Daemon:
    """One Daemon per Chrome connection.

    Owns the NativeBridge and runs at most one orchestrator task at a
    time.  ``run()`` returns when stdin closes.
    """

    def __init__(self, bridge) -> None:
        self.bridge = bridge
        self.current_task: asyncio.Task | None = None
        self.shutdown_event = asyncio.Event()
        bridge.on_inbound = self._on_inbound

    async def _on_inbound(self, msg: dict) -> None:
        """Handle frames that aren't replies to a pending command."""
        mtype = msg.get("type")
        if mtype == "task_start":
            task_text = str(msg.get("task") or "")
            task_id = str(msg.get("taskId") or f"t-{int(time.time())}")
            if self.current_task and not self.current_task.done():
                await self.bridge.emit_error("task already running")
                return
            self.current_task = asyncio.create_task(
                self._run_task(task_text, task_id),
                name=f"task-{task_id}",
            )
        elif mtype == "cancel":
            if self.current_task and not self.current_task.done():
                self.bridge.mark_cancelled(str(msg.get("reason") or "user_cancel"))
            else:
                # No task running — nothing to do.
                pass
        elif mtype == "ready":
            logging.info("extension ready: %s", msg.get("version"))
        elif mtype == "stop":
            self.shutdown_event.set()

    async def _run_task(self, task_text: str, task_id: str) -> None:
        # Lazy-import the orchestrator so import errors land in the log,
        # not in Chrome's protocol error path.
        try:
            from app import orchestrator  # type: ignore
        except Exception as exc:
            logging.exception("orchestrator import failed")
            await self.bridge.emit_done(False, f"agent unavailable: {exc}")
            return

        user_id = os.environ.get("ANTICIPY_USER_ID", "local")
        try:
            outcome = await orchestrator.run_task(
                task=task_text,
                user_id=user_id,
                bridge=self.bridge,
                task_id=task_id,
                monthly_cap_usd=float(os.environ.get("ANTICIPY_MONTHLY_CAP_USD", "10.0")),
            )
            await self.bridge.emit_done(
                bool(outcome.get("success")),
                str(outcome.get("message") or "Done."),
                outcome.get("deliverable") if isinstance(outcome.get("deliverable"), dict) else None,
            )
        except Exception as exc:
            logging.exception("task failed")
            await self.bridge.emit_done(False, f"task crashed: {exc}")

    async def run(self) -> None:
        # Wait for either stdin EOF (bridge.closed) or explicit shutdown.
        done, _pending = await asyncio.wait(
            [
                asyncio.create_task(self.bridge.wait_cancel()),
                asyncio.create_task(self.shutdown_event.wait()),
            ],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for d in done:
            d.exception()  # consume to silence "task exception never retrieved"
        if self.current_task and not self.current_task.done():
            self.current_task.cancel()
            try:
                await self.current_task
            except Exception:
                pass


async def amain() -> None:
    # Import the bridge inside async ctx so its loop ref is correct.
    try:
        from .native_bridge import NativeBridge
    except ImportError:
        from native_bridge import NativeBridge  # type: ignore
    bridge = NativeBridge()
    bridge.start_reader()
    daemon = Daemon(bridge)
    # Localhost HTTP listener for autonomous task firing.
    # Codespace exposes via `cloudflared tunnel --url http://127.0.0.1:7777`.
    asyncio.create_task(_start_trigger_listener(daemon))
    await daemon.run()


async def _start_trigger_listener(daemon: "Daemon") -> None:
    """HTTP listener on 127.0.0.1:7777 for POST /trigger {task, secret, task_id?}.

    Stays loopback-bound — never reachable from the public internet
    directly.  Pair with cloudflared/ngrok if remote firing is needed.
    Secret defaults to ANTICIPY_TRIGGER_SECRET env, falls back to
    "local-dev".  The endpoint enqueues a synthetic ``task_start`` frame
    into the daemon, identical to what the extension popup would send.
    """
    import secrets as _secrets
    host = os.environ.get("ANTICIPY_TRIGGER_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("ANTICIPY_TRIGGER_PORT", "7777"))
    except Exception:
        port = 7777
    expected_secret = os.environ.get("ANTICIPY_TRIGGER_SECRET") or "local-dev"

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            if not request_line:
                writer.close(); return
            # Read headers
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
            if method == "GET" and path.startswith("/status"):
                # Public, unauthenticated read of daemon health. Returns
                # startup.log tail + last error so I can diagnose a stuck
                # extension without the user touching a terminal.
                try:
                    startup_log = (_state_dir() / "startup.log")
                    log_text = startup_log.read_text() if startup_log.exists() else ""
                except Exception:
                    log_text = ""
                try:
                    err_path = _state_dir() / "startup_error.txt"
                    err_text = err_path.read_text() if err_path.exists() else ""
                except Exception:
                    err_text = ""
                status_payload = {
                    "ok": True,
                    "current_task_running": bool(daemon.current_task and not daemon.current_task.done()),
                    "bridge_closed": bool(getattr(daemon.bridge, "closed", False)),
                    "startup_log_tail": log_text.splitlines()[-30:],
                    "last_error": err_text[-3000:] if err_text else "",
                    "pid": os.getpid(),
                    "python": sys.version.split()[0],
                    "platform": sys.platform,
                }
                body_bytes = json.dumps(status_payload).encode("utf-8")
                resp = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + \
                       str(len(body_bytes)).encode() + b"\r\n\r\n" + body_bytes
                writer.write(resp); await writer.drain(); writer.close(); return
            if method == "POST" and path.startswith("/surface-proof"):
                body = b""
                if content_length > 0:
                    body = await asyncio.wait_for(reader.readexactly(content_length), timeout=5.0)
                try:
                    payload = json.loads(body.decode("utf-8")) if body else {}
                except Exception:
                    resp = b'HTTP/1.1 400 Bad Request\r\nContent-Length: 13\r\n\r\nbad json body'
                    writer.write(resp); await writer.drain(); writer.close(); return
                secret_in = str(payload.get("secret") or "")
                if not _secrets.compare_digest(secret_in, expected_secret):
                    resp = b'HTTP/1.1 401 Unauthorized\r\nContent-Length: 14\r\n\r\nbad secret    '
                    writer.write(resp); await writer.drain(); writer.close(); return
                try:
                    limit = int(payload.get("limit") or 50000)
                except Exception:
                    limit = 50000
                limit = max(1000, min(limit, 200000))
                url_prefix = str(payload.get("url_prefix") or payload.get("urlPrefix") or "")
                try:
                    # Surface proof is about the user's current visible Chrome
                    # surface or an explicitly requested public app tab. Do not
                    # reuse a stale Anticipy task tab here.
                    url = await daemon.bridge.get_url(
                        use_active=not bool(url_prefix),
                        url_prefix=url_prefix,
                    )
                    dom = await daemon.bridge.get_dom_snapshot(
                        limit=limit,
                        use_active=not bool(url_prefix),
                        url_prefix=url_prefix,
                    )
                    screenshot = await daemon.bridge.screenshot(
                        use_active=not bool(url_prefix),
                        url_prefix=url_prefix,
                    )
                    proof_payload = {
                        "ok": bool(url and dom and screenshot),
                        "url": url,
                        "dom": dom,
                        "screenshot_data_url": screenshot,
                        "bridge_closed": bool(getattr(daemon.bridge, "closed", False)),
                        "pid": os.getpid(),
                        "acquired_via": "chrome_extension_native_messaging",
                    }
                except Exception as exc:
                    logging.exception("surface proof failed")
                    proof_payload = {
                        "ok": False,
                        "error": f"{type(exc).__name__}: {exc}",
                        "bridge_closed": bool(getattr(daemon.bridge, "closed", False)),
                        "pid": os.getpid(),
                        "acquired_via": "chrome_extension_native_messaging",
                    }
                body_bytes = json.dumps(proof_payload).encode("utf-8")
                resp = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + \
                       str(len(body_bytes)).encode() + b"\r\n\r\n" + body_bytes
                writer.write(resp); await writer.drain(); writer.close(); return
            if method == "POST" and path.startswith("/surface-command"):
                body = b""
                if content_length > 0:
                    body = await asyncio.wait_for(reader.readexactly(content_length), timeout=5.0)
                try:
                    payload = json.loads(body.decode("utf-8")) if body else {}
                except Exception:
                    resp = b'HTTP/1.1 400 Bad Request\r\nContent-Length: 13\r\n\r\nbad json body'
                    writer.write(resp); await writer.drain(); writer.close(); return
                secret_in = str(payload.get("secret") or "")
                if not _secrets.compare_digest(secret_in, expected_secret):
                    resp = b'HTTP/1.1 401 Unauthorized\r\nContent-Length: 14\r\n\r\nbad secret    '
                    writer.write(resp); await writer.drain(); writer.close(); return
                command = str(payload.get("command") or "").strip()
                selector = str(payload.get("selector") or "").strip()
                text = str(payload.get("text") or "")
                url = str(payload.get("url") or "").strip()
                url_prefix = str(payload.get("url_prefix") or payload.get("urlPrefix") or "")
                url_includes = str(payload.get("url_includes") or payload.get("urlIncludes") or "")
                title_includes = str(payload.get("title_includes") or payload.get("titleIncludes") or "")
                try:
                    max_close = int(payload.get("max_close") or payload.get("maxClose") or 10)
                except Exception:
                    max_close = 10
                try:
                    if command == "navigate":
                        if not url:
                            raise ValueError("navigate requires url")
                        data = await daemon.bridge.navigate(
                            url,
                            use_active=not bool(url_prefix),
                            url_prefix=url_prefix,
                        )
                    elif command == "click":
                        if not selector:
                            raise ValueError("click requires selector")
                        data = await daemon.bridge.click(
                            selector,
                            use_active=not bool(url_prefix),
                            url_prefix=url_prefix,
                        )
                    elif command == "type":
                        if not selector:
                            raise ValueError("type requires selector")
                        data = await daemon.bridge.type(
                            selector,
                            text,
                            submit=bool(payload.get("submit")),
                            use_active=not bool(url_prefix),
                            url_prefix=url_prefix,
                        )
                    elif command == "key":
                        key = str(payload.get("key") or "Enter")
                        code = str(payload.get("code") or "")
                        modifiers = payload.get("modifiers")
                        if not isinstance(modifiers, list):
                            modifiers = []
                        data = await daemon.bridge.key(
                            key,
                            selector=selector,
                            code=code,
                            modifiers=[str(m) for m in modifiers],
                            use_active=not bool(url_prefix),
                            url_prefix=url_prefix,
                        )
                    elif command == "read":
                        data = {"text": await daemon.bridge.extract(selector or None)}
                    elif command == "extract":
                        data = {"text": await daemon.bridge.extract(selector or None)}
                    elif command == "getDOMSnapshot":
                        try:
                            limit = int(payload.get("limit") or 50000)
                        except Exception:
                            limit = 50000
                        data = {
                            "url": await daemon.bridge.get_url(
                                use_active=not bool(url_prefix),
                                url_prefix=url_prefix,
                            ),
                            "html": await daemon.bridge.get_dom_snapshot(
                                limit=max(1000, min(limit, 200000)),
                                use_active=not bool(url_prefix),
                                url_prefix=url_prefix,
                            ),
                        }
                    elif command == "list_tabs":
                        if sys.platform == "darwin" and os.environ.get("ANTICIPY_APPLESCRIPT_TAB_FALLBACK") == "1":
                            data = {
                                "tabs": await asyncio.to_thread(_chrome_list_tabs_applescript),
                                "source": "real_chrome_applescript",
                            }
                        else:
                            data = {"tabs": await daemon.bridge.list_tabs()}
                    elif command == "close_tabs_matching":
                        if sys.platform == "darwin" and os.environ.get("ANTICIPY_APPLESCRIPT_TAB_FALLBACK") == "1":
                            data = await asyncio.to_thread(
                                _chrome_close_tabs_matching_applescript,
                                url_prefix=url_prefix,
                                url_includes=url_includes,
                                title_includes=title_includes,
                                max_close=max_close,
                            )
                        else:
                            data = await daemon.bridge.close_tabs_matching(
                                url_prefix=url_prefix,
                                url_includes=url_includes,
                                title_includes=title_includes,
                                max_close=max_close,
                            )
                    else:
                        raise ValueError("unsupported surface command")
                    command_payload = {
                        "ok": True,
                        "command": command,
                        "data": data if isinstance(data, dict) else {"value": data},
                        "acquired_via": "chrome_extension_native_messaging",
                        "use_active_tab": not bool(url_prefix),
                        "url_prefix": url_prefix,
                    }
                except Exception as exc:
                    logging.exception("surface command failed")
                    command_payload = {
                        "ok": False,
                        "command": command,
                        "error": f"{type(exc).__name__}: {exc}",
                        "acquired_via": "chrome_extension_native_messaging",
                        "use_active_tab": not bool(url_prefix),
                        "url_prefix": url_prefix,
                    }
                body_bytes = json.dumps(command_payload).encode("utf-8")
                resp = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + \
                       str(len(body_bytes)).encode() + b"\r\n\r\n" + body_bytes
                writer.write(resp); await writer.drain(); writer.close(); return
            if method != "POST" or not path.startswith("/trigger"):
                resp = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n"
                writer.write(resp); await writer.drain(); writer.close(); return
            body = b""
            if content_length > 0:
                body = await asyncio.wait_for(reader.readexactly(content_length), timeout=5.0)
            try:
                payload = json.loads(body.decode("utf-8")) if body else {}
            except Exception:
                resp = b'HTTP/1.1 400 Bad Request\r\nContent-Length: 13\r\n\r\nbad json body'
                writer.write(resp); await writer.drain(); writer.close(); return
            secret_in = str(payload.get("secret") or "")
            if not _secrets.compare_digest(secret_in, expected_secret):
                resp = b'HTTP/1.1 401 Unauthorized\r\nContent-Length: 14\r\n\r\nbad secret    '
                writer.write(resp); await writer.drain(); writer.close(); return
            task_text = str(payload.get("task") or "").strip()
            if not task_text:
                resp = b'HTTP/1.1 400 Bad Request\r\nContent-Length: 9\r\n\r\nno task  '
                writer.write(resp); await writer.drain(); writer.close(); return
            task_id = str(payload.get("task_id") or f"http-{int(time.time())}")
            if daemon.current_task and not daemon.current_task.done():
                resp_body = b'{"ok":false,"error":"task already running"}'
                resp = b"HTTP/1.1 409 Conflict\r\nContent-Type: application/json\r\nContent-Length: " + \
                       str(len(resp_body)).encode() + b"\r\n\r\n" + resp_body
                writer.write(resp); await writer.drain(); writer.close(); return
            await daemon._on_inbound({"type": "task_start", "task": task_text, "taskId": task_id})
            resp_body = json.dumps({"ok": True, "task_id": task_id}).encode("utf-8")
            resp = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + \
                   str(len(resp_body)).encode() + b"\r\n\r\n" + resp_body
            writer.write(resp); await writer.drain()
        except asyncio.TimeoutError:
            try:
                writer.write(b"HTTP/1.1 408 Request Timeout\r\nContent-Length: 0\r\n\r\n")
                await writer.drain()
            except Exception:
                pass
        except Exception:
            logging.exception("trigger listener handler crashed")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    try:
        server = await asyncio.start_server(handle, host=host, port=port)
        logging.info("trigger listener on %s:%s", host, port)
        async with server:
            await server.serve_forever()
    except OSError as exc:
        logging.warning("trigger listener failed to bind %s:%s — %s", host, port, exc)


def main() -> int:
    # Every step writes a trace line to ~/.anticipy/startup.log. If any
    # step throws, we dump a full traceback to startup_error.txt before
    # we die — so the user (or remote diagnostic) can see exactly where
    # the daemon failed without needing stderr (which Chrome would treat
    # as a protocol error).
    _startup_trace("main_entry", detail=f"pid={os.getpid()}")
    for step_name, step_fn in [
        ("setup_logging", _setup_logging),
        ("activate_pending_update", _activate_pending_update),
        ("load_env", _load_env),
        ("bootstrap_engine_imports", _bootstrap_engine_imports),
        ("patch_ws_bridge_exports", _patch_ws_bridge_exports),
    ]:
        try:
            step_fn()
            _startup_trace(step_name)
        except SystemExit:
            raise
        except BaseException as exc:  # incl. KeyboardInterrupt — fail visibly
            _startup_trace(step_name, ok=False, detail=str(exc))
            _crash_report(step_name, exc)
            try:
                logging.exception("startup failed at %s", step_name)
            except Exception:
                pass
            return 1
    try:
        import threading
        threading.Thread(target=_maybe_self_update, daemon=True).start()
        _startup_trace("update_thread")
    except Exception as exc:
        _startup_trace("update_thread", ok=False, detail=str(exc))
    try:
        _startup_trace("asyncio_run_enter")
        asyncio.run(amain())
        _startup_trace("clean_exit")
        return 0
    except KeyboardInterrupt:
        _startup_trace("keyboard_interrupt")
        return 0
    except BaseException as exc:
        _startup_trace("amain", ok=False, detail=str(exc))
        _crash_report("amain", exc)
        try:
            logging.exception("daemon crashed")
        except Exception:
            pass
        # Emit one last frame so the extension sees something.
        try:
            from . import protocol  # type: ignore
        except (ImportError, ValueError):
            try:
                import protocol  # type: ignore
            except Exception:
                return 1
        try:
            protocol.write_message(sys.stdout.buffer, {
                "type": "error", "message": f"daemon crashed: {exc}",
            })
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
