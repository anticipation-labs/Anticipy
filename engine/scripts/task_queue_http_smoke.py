#!/usr/bin/env python3
"""HTTP-surface smoke test for the persistent task queue.

Boots the full FastAPI app in-process via uvicorn on a free port, then
drives the new /api/task_queue/* endpoints and verifies wake_at firing
end-to-end through the same code path the production engine uses.

Run from repo root:
    python3 engine/scripts/task_queue_http_smoke.py
"""

from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request


SANDBOX = tempfile.mkdtemp(prefix="taskq_http_")
os.environ["ANTICIPY_TASK_QUEUE_DIR"] = SANDBOX
os.environ["ANTICIPY_TASK_QUEUE_INTERVAL_SECONDS"] = "2"
os.environ["ANTICIPY_DATA_DIR"] = tempfile.mkdtemp(prefix="taskq_http_data_")
# Avoid the singleton lock taking the real engine's port slot.

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


PORT = free_port()
os.environ["ANTICIPY_ENGINE_PORT"] = str(PORT)
BASE = f"http://127.0.0.1:{PORT}"


def http_get(path: str, *, timeout: float = 20.0) -> tuple[int, dict]:
    req = urllib.request.Request(BASE + path, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            return e.code, {}


def http_post(path: str, body: dict | None = None,
              *, timeout: float = 20.0) -> tuple[int, dict]:
    raw = json.dumps(body or {}).encode("utf-8")
    req = urllib.request.Request(
        BASE + path,
        data=raw,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            return e.code, {}


def boot_server() -> threading.Thread:
    """Launch uvicorn in a background thread; wait for /health 200."""
    import uvicorn

    from app.product import server as srv  # noqa: F401

    def _run():
        # serve forever; the test exits via sys.exit which kills the
        # daemon thread.
        config = uvicorn.Config(
            "app.product.server:app",
            host="127.0.0.1",
            port=PORT,
            log_level="warning",
            access_log=False,
        )
        uvicorn.Server(config).run()

    t = threading.Thread(target=_run, daemon=True, name="taskq-http-server")
    t.start()

    # Wait for /health 200.
    deadline = time.time() + 25.0
    while time.time() < deadline:
        try:
            s, _ = http_get("/health", timeout=2.0)
            if s == 200:
                return t
        except Exception:
            pass
        time.sleep(0.4)
    raise RuntimeError("server failed to boot")


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", flush=True)
    sys.exit(1)


def main() -> int:
    print(f"sandbox dir = {SANDBOX}")
    print(f"port = {PORT}")
    boot_server()
    print("server up", flush=True)

    # --- Enqueue with wake_in_seconds = 5 -------------------------------
    s, data = http_post("/api/task_queue/enqueue", {
        "instruction": "echo: scheduled remind in 5s",
        "wake_in_seconds": 5,
        "metadata": {"test": "http_smoke"},
    })
    if s != 200 or not data.get("ok"):
        fail(f"enqueue failed: {s} {data}")
    task_id = data["task"]["task_id"]
    wake_at = data["task"].get("wake_at")
    print(f"enqueued {task_id} wake_at_delta={wake_at - time.time():.1f}s")

    # --- Immediate list shows pending -----------------------------------
    s, data = http_get("/api/task_queue/list")
    rows = data.get("tasks", [])
    if not any(r["task_id"] == task_id for r in rows):
        fail(f"task not in list: {rows}")
    own = next(r for r in rows if r["task_id"] == task_id)
    if own["status"] != "pending":
        fail(f"expected pending immediately, got {own['status']}")
    print(f"list shows {len(rows)} task(s), ours is {own['status']}")

    # --- Force a scan now (instead of waiting 5s for the timer) ---------
    # Wait 5 seconds for wake_at to be due, then force scan
    print("waiting 5.5s for wake_at...")
    time.sleep(5.5)

    s, data = http_post("/api/task_queue/scan")
    print(f"scan result: ok={data.get('ok')} "
          f"fired_count={data.get('fired_count')}")
    if not data.get("ok"):
        fail(f"scan failed: {data}")

    # --- Verify the task is now in_progress or done ---------------------
    time.sleep(2.0)
    s, data = http_get(f"/api/task_queue/{task_id}")
    if not data.get("ok"):
        fail(f"get task failed: {data}")
    final_status = data["task"]["status"]
    print(f"final status: {final_status}")
    if final_status not in ("done", "in_progress", "failed", "waiting", "pending"):
        # any post-fire status is acceptable; we only need to prove the
        # scanner picked it up (claimed_at is set on claim).
        fail(f"unexpected status: {final_status}")
    if data["task"].get("claimed_at") is None and final_status == "pending":
        fail(f"scanner did not claim task: {data['task']}")
    print(f"claimed_at={data['task'].get('claimed_at')}, "
          f"completed_at={data['task'].get('completed_at')}")

    print("\nALL HTTP SMOKE TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
