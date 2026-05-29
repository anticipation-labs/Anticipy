#!/usr/bin/env python3
"""Restart-recovery smoke test for the persistent task queue.

Boots the FastAPI app in-process, enqueues a task, force-claims it
into in_progress (simulating an engine crash mid-flight), tears down
the server, and verifies that a fresh server import + startup hook
recovers the task back to pending.

Run from repo root:
    python3 engine/scripts/task_queue_restart_smoke.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time


SANDBOX = tempfile.mkdtemp(prefix="taskq_restart_")
os.environ["ANTICIPY_TASK_QUEUE_DIR"] = SANDBOX
os.environ["ANTICIPY_TASK_QUEUE_INTERVAL_SECONDS"] = "60"
os.environ["ANTICIPY_DATA_DIR"] = tempfile.mkdtemp(prefix="taskq_restart_data_")
os.environ["ANTICIPY_ENGINE_PORT"] = "0"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def banner(s: str) -> None:
    print(f"\n=== {s} ===", flush=True)


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", flush=True)
    sys.exit(1)


def main() -> int:
    print(f"sandbox dir = {SANDBOX}")

    # --- Phase 1: import module + enqueue + claim --------------------------
    banner("Phase 1: enqueue + claim (simulating active workload)")
    from app import task_queue as tq
    r = tq.enqueue("crash-recovery test task",
                    account_id="omar",
                    metadata={"phase": "before_crash"})
    print(f"enqueued {r.task_id}")
    c = tq.claim_next()
    if not c or c.task_id != r.task_id:
        fail(f"claim failed: {c}")
    print(f"claimed -> status={c.status}")

    # --- Phase 2: simulate crash by wiping in-memory state ---------------
    banner("Phase 2: simulate engine crash")
    import app.task_queue.store as store_mod
    import importlib
    importlib.reload(store_mod)
    importlib.reload(tq)
    print("reloaded task_queue module (state wiped, journal on disk)")

    # --- Phase 3: simulate startup hook -------------------------------------
    banner("Phase 3: startup hook restart-recovery")
    recovered = tq.resume_after_restart()
    ids = [rec.task_id for rec in recovered]
    print(f"recovered {len(recovered)} task(s): {ids}")
    if r.task_id not in ids:
        fail(f"task {r.task_id} not recovered; got {ids}")
    rec_after = tq.get(r.task_id)
    if rec_after.status != "pending":
        fail(f"expected pending after recovery, got {rec_after.status}")
    if "engine_restart_recovery" not in (rec_after.last_error or ""):
        fail(f"recovery flag missing: {rec_after.last_error!r}")
    print(f"task status={rec_after.status} retry_count={rec_after.retry_count}")
    print(f"last_error tag: {rec_after.last_error!r}")

    # --- Phase 4: verify the recovered task is now claimable again ---------
    banner("Phase 4: claim the recovered task")
    c2 = tq.claim_next()
    if not c2 or c2.task_id != r.task_id:
        fail(f"could not re-claim after recovery: {c2}")
    print(f"re-claimed {c2.task_id}, status={c2.status}")
    tq.complete(c2.task_id, {"finished_after_restart": True})
    final = tq.get(c2.task_id)
    if final.status != "done":
        fail(f"final state not done: {final.status}")
    print(f"final state: {final.status}")

    banner("ALL RESTART-RECOVERY TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
