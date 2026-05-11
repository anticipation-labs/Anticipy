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
    await daemon.run()


def main() -> int:
    _setup_logging()
    _activate_pending_update()
    _load_env()
    _bootstrap_engine_imports()
    _patch_ws_bridge_exports()
    # Self-update check runs in background — never blocks startup.
    try:
        import threading
        threading.Thread(target=_maybe_self_update, daemon=True).start()
    except Exception:
        pass
    try:
        asyncio.run(amain())
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        logging.exception("daemon crashed")
        # Emit one last frame so the extension sees something.
        try:
            from . import protocol  # type: ignore
        except (ImportError, ValueError):
            import protocol
        try:
            protocol.write_message(sys.stdout.buffer, {
                "type": "error", "message": f"daemon crashed: {exc}",
            })
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
