"""Loopback API Worker for the installed-extension proof. Never deploys.

    python3 -m proof.audit.installed_extension.local_worker up   [--port 8791] [--state DIR]
    python3 -m proof.audit.installed_extension.local_worker down [--state DIR]

Real `migration/workers/src/index.ts` under `wrangler dev --local` over a fresh
local D1 built from the real `migration/d1/schema.sql`. The model proxy is
pointed at a LOOPBACK fake provider through the test-only `LLM_PROVIDER_BASE`
var (src/llm.ts ignores any non-loopback value), with a local-only token that
authenticates nothing anywhere else. No production account, secret, database
or provider is reachable from this process; the environment is rebuilt from
PATH/HOME/TMPDIR only, as proof/audit/run_isolated_task_flow.py does.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKERS = ROOT / "migration/workers"
DEFAULT_STATE = ROOT / "work/installed-extension/worker"
SERVICE_TOKEN = "installed-extension-local-only"
AUTH_SECRET = "installed-extension-auth-not-a-production-secret"
PROVIDER_TOKEN = "installed-extension-fake-provider-token"
BROWSER_MODEL = "fixture/scripted-browser"
VISION_MODEL = "fixture/scripted-vision"


def isolated_environment() -> dict[str, str]:
    keep = {k: os.environ[k] for k in ("PATH", "HOME", "TMPDIR") if k in os.environ}
    return {**keep, "PYTHON_DOTENV_DISABLED": "1", "CLOUDFLARE_LOAD_DEV_VARS_FROM_DOT_ENV": "false",
            "CLOUDFLARE_INCLUDE_PROCESS_ENV": "false", "WRANGLER_SEND_METRICS": "false",
            "CI": "1", "npm_config_offline": "true"}


def config_for(port: int, provider_port: int) -> dict:
    return {
        "name": "anticipy-installed-extension-proof", "main": str(WORKERS / "src/index.ts"),
        "compatibility_date": "2026-09-03", "compatibility_flags": ["nodejs_compat"],
        "d1_databases": [{"binding": "DB", "database_name": "installed-extension",
                          "database_id": "00000000-0000-4000-8000-000000000091"}],
        "r2_buckets": [{"binding": "EVIDENCE", "bucket_name": "installed-extension-evidence"}],
        "durable_objects": {"bindings": [{"name": "PAIR_CODE_COUNTER", "class_name": "PairCodeCounter"}]},
        "migrations": [{"tag": "v1", "new_sqlite_classes": ["PairCodeCounter"]}],
        "assets": {"directory": str(WORKERS / "public"), "binding": "ASSETS"},
        "vars": {"ANTICIPY_ENV": "test", "ANTICIPY_SERVICE_TOKEN": SERVICE_TOKEN,
                 "ANTICIPY_AUTH_SECRET": AUTH_SECRET,
                 "ANTICIPY_INTERNAL_KEY": "installed-extension-internal-local-only",
                 "OPENROUTER_API_KEY": PROVIDER_TOKEN,
                 "LLM_PROVIDER_BASE": f"http://127.0.0.1:{provider_port}",
                 "ANTICIPY_BROWSER_MODEL": BROWSER_MODEL, "ANTICIPY_VISION_MODEL": VISION_MODEL},
    }


def free(port: int) -> None:
    """Raises OSError when the port is taken. `down` waits on exactly that."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))


def health(base: str) -> bool:
    try:
        with urllib.request.urlopen(base + "/api/health", timeout=1) as r:  # noqa: S310 loopback only
            return r.status == 200
    except Exception:
        return False


def up(port: int, provider_port: int, state: Path) -> int:
    state.mkdir(parents=True, exist_ok=True)
    pidfile = state / "wrangler.pid"
    if pidfile.exists():
        print(f"refusing: {pidfile} exists — run `down` first", file=sys.stderr)
        return 2
    # The inspector sits on --port + 1 and nothing else says so; a busy port
    # used to surface as a bare bind traceback rather than a sentence.
    for p, what in ((port, "the Worker"), (port + 1, "the Worker's inspector")):
        try:
            free(p)
        except OSError as error:
            print(f"refusing to start: 127.0.0.1:{p} ({what}) is already in use "
                  f"({error.strerror}). Run `down` first, or pass a different --port.",
                  file=sys.stderr)
            return 2
    config = state / "wrangler.json"
    config.write_text(json.dumps(config_for(port, provider_port), indent=2))
    log = open(state / "workerd.log", "a")
    wrangler = ["node", str(WORKERS / "node_modules/wrangler/bin/wrangler.js")]
    persist = state / "local-state"
    schema = subprocess.run([*wrangler, "d1", "execute", "DB", "--local", "--config", str(config),
                             "--persist-to", str(persist), "--file", str(ROOT / "migration/d1/schema.sql")],
                            cwd=WORKERS, env=isolated_environment(), stdout=log, stderr=log, timeout=90)
    if schema.returncode != 0:
        print("schema load failed; see workerd.log", file=sys.stderr)
        return 1
    proc = subprocess.Popen([*wrangler, "dev", "--local", "--config", str(config), "--persist-to", str(persist),
                             "--ip", "127.0.0.1", "--port", str(port), "--inspector-port", str(port + 1),
                             "--env-file", "/dev/null"],
                            cwd=WORKERS, env=isolated_environment(), stdout=log, stderr=log, start_new_session=True)
    pidfile.write_text(str(proc.pid))
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            print("wrangler exited early; see workerd.log", file=sys.stderr)
            pidfile.unlink(missing_ok=True)
            return 1
        if health(base):
            (state / "base").write_text(base)
            print(json.dumps({"base": base, "pid": proc.pid, "service_token": SERVICE_TOKEN,
                              "browser_model": BROWSER_MODEL, "vision_model": VISION_MODEL}))
            return 0
        time.sleep(0.5)
    print("the local Worker never answered /api/health", file=sys.stderr)
    return 1


def down(state: Path) -> int:
    pidfile = state / "wrangler.pid"
    if not pidfile.exists():
        print("nothing recorded as running")
        return 0
    pid = int(pidfile.read_text().strip())
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    for _ in range(40):
        try:
            os.killpg(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.25)
    else:
        os.killpg(pid, signal.SIGKILL)
    pidfile.unlink(missing_ok=True)
    # wrangler's own child (workerd) can outlive the group leader and keep the
    # listener. Every process that names THIS rig's state directory is ours by
    # construction (the path is under work/installed-extension), so end them.
    try:
        # `pgrep -f <state>` is a substring match on the WHOLE command line, so
        # on its own it also matches an editor, a grep or a tail that happens to
        # name this directory. Match the runtime as well: only wrangler/workerd
        # processes that are serving this rig are ours to end.
        found = subprocess.run(
            ["pgrep", "-f", rf"(wrangler|workerd|miniflare).*{re.escape(str(state))}"],
            capture_output=True, text=True).stdout.split()
        for pid in found:
            if int(pid) != os.getpid():
                try:
                    os.kill(int(pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass
    except Exception:
        pass
    # workerd can hold the listener for a moment after wrangler is gone; an
    # immediate `up` then fails with EADDRINUSE. Wait for the ports, bounded.
    base = state / "base"
    port = int(base.read_text().rsplit(":", 1)[1]) if base.exists() else 0
    if port:
        for _ in range(60):
            try:
                free(port); free(port + 1)
                break
            except OSError:
                time.sleep(0.25)
    print("stopped")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("command", choices=["up", "down"])
    p.add_argument("--port", type=int, default=8791)
    p.add_argument("--provider-port", type=int, default=8796)
    p.add_argument("--state", type=Path, default=DEFAULT_STATE)
    a = p.parse_args(argv)
    return up(a.port, a.provider_port, a.state) if a.command == "up" else down(a.state)


if __name__ == "__main__":
    sys.exit(main())
