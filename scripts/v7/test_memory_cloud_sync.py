"""Integration tests for V7 MemoryCloudSync outbox.

Stands up a local stdlib HTTP server that pretends to be Supabase
PostgREST. Real Supabase is never contacted; only the fake server.
Asserts: 5 items ship in 10s, retry recovery, flush drains, no-op
without SUPABASE_URL, kind-to-table routing.
"""

from __future__ import annotations

import http.server
import json
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[2]
_ENGINE = _ROOT / "engine"
if str(_ENGINE) not in sys.path:
    sys.path.insert(0, str(_ENGINE))

_PASSED: list[str] = []
_FAILED: list[tuple[str, str]] = []


def _ok(n): _PASSED.append(n); print(f"PASS  {n}")
def _fail(n, r): _FAILED.append((n, r)); print(f"FAIL  {n}: {r}")


def _assert(cond, name, reason="") -> bool:
    (_ok(name) if cond else _fail(name, reason or "assertion failed"))
    return cond


class _State:
    received: list[tuple[str, list[dict]]] = []
    lock = threading.Lock()
    force_fail_remaining: int = 0


_S = _State()


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_a, **_kw): return

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(n) if n > 0 else b""
        try:
            body = json.loads(raw.decode("utf-8") or "[]")
        except Exception:
            body = []
        table = self.path.lstrip("/").rsplit("/", 1)[-1]
        with _S.lock:
            if _S.force_fail_remaining > 0:
                _S.force_fail_remaining -= 1
                self.send_response(500); self.end_headers()
                self.wfile.write(b'{"error":"forced"}'); return
            _S.received.append((table, list(body or [])))
        self.send_response(201)
        self.send_header("Content-Length", "0")
        self.end_headers()


def _start_server() -> tuple[http.server.HTTPServer, str]:
    s = socket.socket(); s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]; s.close()
    srv = http.server.HTTPServer(("127.0.0.1", port), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{port}"


def _wait(cond, timeout=10.0, tick=0.05):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(tick)
    return False


def _reset():
    _S.received.clear(); _S.force_fail_remaining = 0


def _new_sync(url: str, outbox_dir: Path):
    from app.product.memory_cloud_sync import (
        MemoryCloudSync, reset_singleton_for_tests,
    )
    reset_singleton_for_tests()
    return MemoryCloudSync(
        supabase_url=url, supabase_service_role_key="fake-key",
        outbox_dir=outbox_dir,
    )


def test_ships_five(tmpdir: Path, base: str) -> None:
    _reset()
    sync = _new_sync(base, tmpdir)
    _assert(sync.start_worker(), "start_worker True with URL set")
    for i in range(5):
        sync.enqueue({"kind": "person", "key": f"P{i}",
                      "value": f"p{i}@example.com", "source": "t"})
    ok = _wait(lambda: sync.pending_count() == 0, timeout=10.0)
    sync.stop_worker(timeout=2.0)
    _assert(ok, "5 items shipped within 10s",
            f"pending={sync.pending_count()}")
    rows = sum(len(r) for _, r in _S.received)
    _assert(rows == 5, "server received 5 rows", f"got={rows}")
    _assert(sync.last_shipped_at() is not None,
            "last_shipped_at populated")


def test_retries_recover(tmpdir: Path, base: str) -> None:
    _reset(); _S.force_fail_remaining = 3
    sync = _new_sync(base, tmpdir)
    sync.start_worker()
    for i in range(3):
        sync.enqueue({"kind": "preference", "key": f"K{i}",
                      "value": f"v{i}", "source": "t"})
    ok = _wait(lambda: sync.pending_count() == 0, timeout=10.0)
    sync.stop_worker(timeout=2.0)
    _assert(ok, "items eventually ship after 500 burst",
            f"pending={sync.pending_count()}")
    keys = {r["key"] for _, rows in _S.received for r in rows}
    _assert(keys == {"K0", "K1", "K2"},
            "all 3 keys arrived after retry", f"got={keys}")
    tables = {t for t, _ in _S.received}
    _assert(tables == {"anticipy_preferences"},
            "preference routes to anticipy_preferences",
            f"got={tables}")


def test_flush_drains(tmpdir: Path, base: str) -> None:
    _reset()
    sync = _new_sync(base, tmpdir)
    for i in range(4):
        sync.enqueue({"kind": "dossier", "key": f"D{i}",
                      "value": json.dumps({"i": i}), "source": "t"})
    _assert(sync.pending_count() == 4, "pending=4 pre-flush")
    res = sync.flush(max_seconds=5.0)
    _assert(res.get("shipped") == 4, "flush shipped=4",
            f"res={res}")
    _assert(sync.pending_count() == 0, "pending=0 post-flush")
    tables = {t for t, _ in _S.received}
    _assert("dossiers" in tables,
            "dossier routes to dossiers", f"got={tables}")


def test_no_op_without_url(tmpdir: Path) -> None:
    sync = _new_sync("", tmpdir)
    _assert(not sync.start_worker(),
            "start_worker False without SUPABASE_URL")
    _assert(not sync.worker_running(), "worker_running False")
    iid = sync.enqueue({"kind": "person", "key": "Local",
                        "value": "local@test"})
    _assert(bool(iid), "enqueue still works durably")
    _assert(sync.pending_count() == 1, "pending tracks the item")
    res = sync.flush(max_seconds=1.0)
    _assert(res.get("note") == "supabase_url_unset",
            "flush returns supabase_url_unset note", f"res={res}")


def main() -> int:
    srv: Optional[http.server.HTTPServer] = None
    cases = [test_ships_five, test_retries_recover, test_flush_drains]
    try:
        srv, base = _start_server()
        for i, case in enumerate(cases, 1):
            with tempfile.TemporaryDirectory(
                prefix=f"v7_mcs_{i}_",
            ) as d:
                case(Path(d), base)
        with tempfile.TemporaryDirectory(prefix="v7_mcs_4_") as d:
            test_no_op_without_url(Path(d))
    except Exception as exc:
        _fail("harness", f"crashed: {exc!r}")
    finally:
        try:
            if srv is not None:
                srv.shutdown(); srv.server_close()
        except Exception:
            pass
    print()
    print(f"summary: {len(_PASSED)} passed, {len(_FAILED)} failed")
    return 0 if not _FAILED else 1


if __name__ == "__main__":
    for k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
              "SUPABASE_SERVICE_KEY"):
        os.environ.pop(k, None)
    raise SystemExit(main())
