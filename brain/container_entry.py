#!/usr/bin/env python3
"""Container entrypoint for one owner's brain on Cloudflare Containers.

  ┌───────────────────────────────────────────────────────────────┐
  │ container_entry.py                                             │
  │   1. pull memory.db + clock_state.json  ◄── R2 anticipy-owner-state
  │   2. control HTTP server :8731  (so the DO can see the container up)
  │   3. exec child: python -m brain.worker   (UNCHANGED, 22,614 lines)
  │   4. snapshot loop ─────────────────────►  R2 anticipy-owner-state
  │   5. daily verified zip ────────────────►  R2 …-backups-production
  │   6. SIGTERM: stop child, final snapshot, exit                 │
  └───────────────────────────────────────────────────────────────┘

╔══════════════════════════════════════════════════════════════════════════╗
║ UNTESTED. Written 2026-09-04 from migration/BRAIN-ON-CONTAINERS.md §5.3,     ║
║ with NO container runtime, NO Docker, and NO R2 API token available to run  ║
║ it against. Unlike every route ported this session, there is NO ORACLE for  ║
║ this code — it could not be diffed against a working system. Its failure    ║
║ mode is SILENT DATA LOSS: booting on an empty dir when the object exists     ║
║ loses an owner's memory. DO NOT DEPLOY until it has run green against a      ║
║ container runtime with a real R2 bucket. This is scaffolding for that        ║
║ session, faithful to the design, not a validated artifact.                  ║
╚══════════════════════════════════════════════════════════════════════════╝

The one rule that must not be got wrong (§5.3.1): a FAILED R2 GET aborts the
boot loudly; only a genuine 404 (absent object = new owner) is allowed to
continue. Booting on an empty dir when the object exists is how 31 people lose
their memory quietly.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Reuse the TESTED routines rather than rewriting the dangerous parts. §5.3.4
# is explicit: use state_backup._snapshot_sqlite (SQLite online backup API +
# quick_check), never a byte copy of a live file.
from brain.state_backup import (
    _client,
    _sha256,
    _snapshot_sqlite,
    backup_config,
    backup_state_to_s3,
)

# ── configuration, all from the environment the DO passes in ──────────────
OWNER_REF = str(os.environ.get("ANTICIPY_OWNER_REF") or "").strip()
STATE_ROOT = Path(os.environ.get("ANTICIPY_STATE_ROOT") or "/data/owners")
R2_BUCKET = str(os.environ.get("ANTICIPY_STATE_R2_BUCKET") or "anticipy-owner-state").strip()
R2_PREFIX = str(os.environ.get("ANTICIPY_STATE_R2_PREFIX") or "owners").strip().strip("/")
SNAPSHOT_SECONDS = int(os.environ.get("ANTICIPY_STATE_SNAPSHOT_SECONDS") or "60")
BACKUP_SECONDS = int(os.environ.get("ANTICIPY_STATE_BACKUP_SECONDS") or "86400")
CONTROL_PORT = int(os.environ.get("ANTICIPY_CONTROL_PORT") or "8731")

# The two files that ARE an owner's durable mind. memory.db is the assistant's
# long-term memory; clock_state.json is the outreach limiter — small and
# dangerous, because a half-written one reads back as the permissive default
# and wipes the limit (supervisor.py records this happening).
STATE_NAMES = ("memory.db", "clock_state.json")

_owner_dir = STATE_ROOT / OWNER_REF
_stop = threading.Event()
_child: subprocess.Popen | None = None


def _log(msg: str) -> None:
    # stdout is the container's log; the DO cannot see inside otherwise (§3.2).
    print(f"[container_entry owner={OWNER_REF or '?'}] {msg}", flush=True)


def _r2():
    """An S3 client onto R2. The owner-state bucket lives in the same R2 account
    as the daily archive, so it uses the same ANTICIPY_BACKUP_S3_* credentials
    backup_config already validates. A partial config is an error, not an
    opt-out — state that cannot be persisted must not boot silently."""
    config = backup_config()
    if config is None:
        raise RuntimeError(
            "R2/S3 configuration is absent; refusing to boot a brain whose "
            "memory could not be persisted. Set ANTICIPY_BACKUP_S3_* (and, if "
            "you truly mean ephemeral, that is a code change, not a missing var)."
        )
    return _client(config)


def _r2_key(name: str) -> str:
    return f"{R2_PREFIX}/{OWNER_REF}/{name}"


# ── 1. pull durable state before the child starts ────────────────────────
def pull_state(s3) -> None:
    """GET each state file from R2 into the owner's dir. Absent (404) = a new
    owner; create the dir 0o700 and continue. ANY OTHER failure aborts the boot
    loudly — that is the whole safety property of this function."""
    _owner_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in STATE_NAMES:
        key = _r2_key(name)
        dest = _owner_dir / name
        try:
            s3.download_file(R2_BUCKET, key, str(dest))
            _log(f"pulled {key} -> {dest} ({dest.stat().st_size} bytes)")
        except Exception as err:  # noqa: BLE001 — we must inspect the code
            if _is_not_found(err):
                _log(f"no {key} in R2 yet — new owner, starting with an empty {name}")
                continue
            # A failed GET (as against a 404) MUST abort. Booting on an empty
            # dir when the object exists is silent memory loss for a real person.
            raise RuntimeError(
                f"R2 GET failed for {key} and it is NOT a 404. Aborting the boot "
                f"rather than starting on an empty {name} and overwriting a live "
                f"memory on the next snapshot. Underlying error: {err!r}"
            ) from err


def _is_not_found(err: Exception) -> bool:
    """True only for a genuine object-absent (404 / NoSuchKey), never for auth,
    network, or permission failures — those must abort."""
    code = ""
    resp = getattr(err, "response", None)
    if isinstance(resp, dict):
        code = str(resp.get("Error", {}).get("Code") or "")
        status = resp.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if status == 404:
            return True
    name = err.__class__.__name__
    return code in ("404", "NoSuchKey", "NotFound") or name in ("NoSuchKey", "404")


# ── 4. snapshot durable state to R2 ───────────────────────────────────────
def snapshot_once(s3) -> None:
    """One consistent snapshot of both files, uploaded. THE SNAPSHOT INTERVAL IS
    THE CRASH-LOSS WINDOW: a container lost without SIGTERM costs this owner up
    to SNAPSHOT_SECONDS of memory. That number was chosen at 60s knowingly."""
    mem = _owner_dir / "memory.db"
    if mem.exists():
        tmp = _owner_dir / ".memory.snapshot.db"
        try:
            _snapshot_sqlite(mem, tmp)  # online backup API + PRAGMA quick_check
            s3.upload_file(str(tmp), R2_BUCKET, _r2_key("memory.db"))
        finally:
            tmp.unlink(missing_ok=True)
    clock = _owner_dir / "clock_state.json"
    if clock.exists():
        # A small JSON; the online-backup routine is for SQLite only, so this
        # one is a plain PUT. It is written atomically by the child (rename),
        # so a whole-file read is consistent.
        s3.upload_file(str(clock), R2_BUCKET, _r2_key("clock_state.json"))


def snapshot_loop(s3) -> None:
    last_backup = 0.0
    while not _stop.wait(SNAPSHOT_SECONDS):
        try:
            snapshot_once(s3)
        except Exception as err:  # noqa: BLE001
            # A failed snapshot is loud but not fatal: the child keeps running,
            # and the NEXT snapshot may succeed. Losing the process to a snapshot
            # error would be worse than the window it protects.
            _log(f"snapshot failed (will retry next tick): {err!r}")
        # 6. daily verified zip — reuse the tested routine, wholly unchanged.
        now = time.monotonic()
        if now - last_backup >= BACKUP_SECONDS:
            last_backup = now
            try:
                key = backup_state_to_s3(STATE_ROOT)
                if key:
                    _log(f"daily verified archive uploaded: {key}")
            except Exception as err:  # noqa: BLE001
                _log(f"daily archive failed (non-fatal): {err!r}")


# ── 2. control HTTP server so the DO can see the container is up ──────────
class _Control(BaseHTTPRequestHandler):
    def log_message(self, *_args):  # silence default access logging
        return

    def do_GET(self):  # noqa: N802 — http.server naming
        if self.path.rstrip("/") in ("", "/health"):
            # Report which credentials arrived NON-EMPTY — names only, never
            # values. A container that boots and then fails on first use is
            # invisible otherwise (§4.3).
            def present(n: str) -> bool:
                return bool(str(os.environ.get(n) or "").strip())
            body = (
                b'{"ok":true,"owner":"' + OWNER_REF.encode() + b'",'
                b'"child_running":' + (b"true" if _child and _child.poll() is None else b"false") + b','
                b'"has_pb":' + (b"true" if present("ANTICIPY_PB") else b"false") + b','
                b'"has_service_token":' + (b"true" if present("ANTICIPY_SERVICE_TOKEN") else b"false") + b','
                b'"has_s3":' + (b"true" if present("ANTICIPY_BACKUP_S3_BUCKET") else b"false") + b"}"
            )
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


def start_control_server() -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("0.0.0.0", CONTROL_PORT), _Control)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _log(f"control server listening on :{CONTROL_PORT}")
    return server


# ── 3 / 5. the child, and shutdown ────────────────────────────────────────
def start_child() -> subprocess.Popen:
    """python -m brain.worker, inheriting the environment the DO handed us."""
    return subprocess.Popen([sys.executable, "-m", "brain.worker"], env=os.environ.copy())


def _handle_sigterm(_signum, _frame) -> None:
    """On SIGTERM: stop the child, take ONE final snapshot, PUT it, then exit.
    wrangler.brain.jsonc sets rollout_active_grace_period: 3600 to give this
    room. The final snapshot is what makes a graceful stop lossless."""
    _log("SIGTERM — stopping child and taking a final snapshot")
    _stop.set()
    global _child
    if _child and _child.poll() is None:
        _child.terminate()
        try:
            _child.wait(timeout=25)
        except subprocess.TimeoutExpired:
            _child.kill()
    try:
        snapshot_once(_r2())
        _log("final snapshot uploaded")
    except Exception as err:  # noqa: BLE001
        _log(f"final snapshot FAILED on shutdown — up to one interval may be lost: {err!r}")
    sys.exit(0)


def main() -> int:
    if not OWNER_REF:
        _log("ANTICIPY_OWNER_REF is empty; the DO must set it. Refusing to boot.")
        return 2

    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)

    s3 = _r2()
    pull_state(s3)                 # 1 — aborts loudly on a non-404 failure
    start_control_server()         # 2 — before the child, so ports are seen
    threading.Thread(target=snapshot_loop, args=(s3,), daemon=True).start()  # 4

    global _child
    # KEEP-ALIVE (2026-09-05): supervise the child in a restart loop rather than
    # exiting when it dies. On Cloudflare Containers the container process is
    # PID 1 — if it exits, the whole container STOPS ("inactive"), and the brain
    # is down for that owner until the DO's next reconcile (up to a minute).
    # A transient worker exit (a bad deploy of the backend, a network blip, an
    # unhandled exception in the 2-second poll) should NOT take the container
    # down: restart the child in place, keeping the snapshot loop and control
    # server alive. A genuine crash-loop is still surfaced — if the child dies
    # too many times too fast, give up so a permanently-broken build fails
    # visibly instead of masquerading as "healthy".
    restarts: list[float] = []          # monotonic timestamps of recent starts
    RAPID_WINDOW = 120.0                 # seconds
    RAPID_MAX = 5                        # >5 restarts in 2 min = crash loop
    while not _stop.is_set():
        _child = start_child()          # 3 — the untouched worker
        now = time.monotonic()
        restarts.append(now)
        restarts[:] = [t for t in restarts if now - t <= RAPID_WINDOW]
        _log(f"child started pid={_child.pid} (starts in last {int(RAPID_WINDOW)}s: {len(restarts)})")

        code = _child.wait()
        if _stop.is_set():
            break                        # SIGTERM path handles its own snapshot
        _log(f"child exited code={code}; snapshotting, then restarting")
        try:
            snapshot_once(s3)            # preserve memory before the restart
        except Exception as err:  # noqa: BLE001
            _log(f"snapshot after child exit failed (continuing): {err!r}")

        if len(restarts) > RAPID_MAX:
            _log(f"child crash-looped ({len(restarts)} starts in {int(RAPID_WINDOW)}s) — "
                 f"giving up so the failure is visible, not hidden behind a restart")
            return code if isinstance(code, int) and code != 0 else 1
        # brief backoff so a fast-failing child does not spin the CPU
        _stop.wait(min(5.0, 1.0 * len(restarts)))

    _log("stop requested; child supervision loop exiting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
