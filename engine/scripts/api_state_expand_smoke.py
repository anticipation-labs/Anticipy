#!/usr/bin/env python3
"""Smoke test for the expanded /api/state response.

Imports the server module, calls the state() handler directly, and
asserts that every new live-observability key is present and shaped
right. Does NOT spawn uvicorn or touch the live engine binary. Pins
ANTICIPY_PORT to a sandbox port so the singleton lock does not collide
with Omar's launchd-managed pid 66923 on 8731.

Exit codes:
  0 every assertion passes
  1 any assertion fails (message printed)

Run from repo root:
  python3 engine/scripts/api_state_expand_smoke.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time


# Force a sandbox port and a private data dir BEFORE importing server.
# server.py acquires a flock on /tmp/anticipy_product_<port>.lock at
# import time. Using a high port keeps this test independent of any
# live engine on 8731.
os.environ.setdefault("ANTICIPY_PORT", "18745")
os.environ.setdefault(
    "ANTICIPY_DATA_DIR", tempfile.mkdtemp(prefix="anticipy_state_smoke_")
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", flush=True)
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"  ok  {msg}", flush=True)


def banner(msg: str) -> None:
    print(f"\n=== {msg} ===", flush=True)


def main() -> None:
    banner("import server module")
    from app.product import server  # noqa: E402

    ok("server module imported")
    if not any(getattr(r, "path", "") == "/api/state"
               for r in server.app.routes):
        fail("/api/state route missing on the FastAPI app")
    ok("/api/state route registered")

    banner("call state() handler directly")
    t0 = time.perf_counter()
    resp = server.state()
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    ok(f"handler returned in {elapsed_ms:.1f}ms")
    if elapsed_ms > 250.0:
        # 50ms is the budget; 250ms is a generous CI-safe ceiling that
        # still catches accidental blocking I/O.
        fail(f"handler took {elapsed_ms:.1f}ms; budget is under 50ms")

    body = json.loads(resp.body.decode("utf-8"))
    ok(f"response keys: {len(body)}")

    banner("check new live-observability keys")
    expected_keys = [
        "quiet_mode",
        "proactive_status",
        "tab_activity_60s",
        "task_queue_summary",
        "cost_last_hour",
        "engine_health",
    ]
    for k in expected_keys:
        if k not in body:
            fail(f"missing key: {k}")
        ok(f"present: {k}")

    banner("quiet_mode shape")
    if not isinstance(body["quiet_mode"], bool):
        fail(f"quiet_mode must be bool, got {type(body['quiet_mode']).__name__}")
    ok(f"quiet_mode = {body['quiet_mode']}")

    banner("proactive_status shape")
    ps = body["proactive_status"]
    if ps is None:
        ok("proactive_status is null (subsystem not initialized)")
    else:
        if not isinstance(ps, dict):
            fail(f"proactive_status must be dict or null, got {type(ps).__name__}")
        for sub in [
            "coldstart_inhale_running",
            "calendar_prep_last_fire_ts",
            "calendar_prep_briefs_fired_24h",
            "notifier_dispatches_24h",
        ]:
            if sub not in ps and "error" not in ps:
                fail(f"proactive_status missing subkey: {sub}")
        ok(f"proactive_status keys: {sorted(ps.keys())}")

    banner("tab_activity_60s shape")
    ta = body["tab_activity_60s"]
    if not isinstance(ta, dict):
        fail(f"tab_activity_60s must be dict, got {type(ta).__name__}")
    for sub in [
        "tabs_opened_by_anticipy_60s",
        "tabs_currently_owned",
        "last_tab_host",
    ]:
        if sub not in ta:
            fail(f"tab_activity_60s missing subkey: {sub}")
    if not isinstance(ta["tabs_opened_by_anticipy_60s"], int):
        fail("tabs_opened_by_anticipy_60s must be int")
    ok(f"tab_activity_60s = {ta}")

    # Exercise the recorder and re-check the snapshot.
    server._record_anticipy_tab_open("https://mail.google.com/mail/u/0/?param=secret")
    server._record_anticipy_tab_open("https://calendar.google.com/calendar/u/0/r")
    resp2 = server.state()
    body2 = json.loads(resp2.body.decode("utf-8"))
    ta2 = body2["tab_activity_60s"]
    if ta2["tabs_opened_by_anticipy_60s"] < 2:
        fail(
            f"after recording two opens, expected >= 2, got "
            f"{ta2['tabs_opened_by_anticipy_60s']}"
        )
    if ta2["last_tab_host"] != "calendar.google.com":
        fail(
            f"last_tab_host should be host-only, got {ta2['last_tab_host']!r}"
        )
    if "secret" in json.dumps(ta2):
        fail("PII from URL leaked into snapshot")
    ok(f"after two recorded opens: {ta2}")

    banner("task_queue_summary shape")
    tq = body["task_queue_summary"]
    if tq is None:
        ok("task_queue_summary is null (queue not initialized)")
    else:
        if not isinstance(tq, dict):
            fail(f"task_queue_summary must be dict or null, got {type(tq).__name__}")
        if "error" not in tq:
            for sub in ["total", "waiting", "running", "done_24h", "failed_24h"]:
                if sub not in tq:
                    fail(f"task_queue_summary missing subkey: {sub}")
                if not isinstance(tq[sub], int):
                    fail(f"task_queue_summary.{sub} must be int")
        ok(f"task_queue_summary = {tq}")

    banner("cost_last_hour shape")
    cl = body["cost_last_hour"]
    if cl is None:
        ok("cost_last_hour is null (telemetry not initialized)")
    else:
        if not isinstance(cl, dict):
            fail(f"cost_last_hour must be dict or null, got {type(cl).__name__}")
        if "error" not in cl:
            for sub in ["tasks_run", "total_usd", "p95_per_task_usd"]:
                if sub not in cl:
                    fail(f"cost_last_hour missing subkey: {sub}")
        ok(f"cost_last_hour = {cl}")

    banner("engine_health shape")
    eh = body["engine_health"]
    if not isinstance(eh, dict):
        fail(f"engine_health must be dict, got {type(eh).__name__}")
    if "error" not in eh:
        for sub in ["pid", "etime_seconds", "rss_mb", "bound_port", "bundled_binary"]:
            if sub not in eh:
                fail(f"engine_health missing subkey: {sub}")
        if not isinstance(eh["pid"], int):
            fail("engine_health.pid must be int")
        if eh["pid"] != os.getpid():
            fail(f"engine_health.pid={eh['pid']} expected {os.getpid()}")
        if not isinstance(eh["etime_seconds"], int) or eh["etime_seconds"] < 0:
            fail("engine_health.etime_seconds must be non-negative int")
        if eh["rss_mb"] is not None and not isinstance(eh["rss_mb"], int):
            fail("engine_health.rss_mb must be int or null")
        if not isinstance(eh["bound_port"], int):
            fail("engine_health.bound_port must be int")
        if eh["bound_port"] != 18745:
            fail(f"engine_health.bound_port={eh['bound_port']} expected 18745")
        if not isinstance(eh["bundled_binary"], bool):
            fail("engine_health.bundled_binary must be bool")
    ok(f"engine_health = {eh}")

    banner("re-call must be idempotent and side-effect free")
    pid_before = eh.get("pid")
    resp3 = server.state()
    body3 = json.loads(resp3.body.decode("utf-8"))
    if body3["engine_health"].get("pid") != pid_before:
        fail("pid changed across calls; state() has side effects")
    ok("pid stable across calls")

    banner("PASS")
    print("All assertions passed.", flush=True)


if __name__ == "__main__":
    main()
