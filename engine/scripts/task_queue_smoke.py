#!/usr/bin/env python3
"""Smoke test for the persistent task queue.

Covers:
  - Module-level enqueue / claim / complete / fail / wake_at / restart resume.
  - Boots an in-process FastAPI engine on a free port, registers a fake
    executor, enqueues a task with wake_at = now + 5s, waits for it to
    fire via the scanner, asserts the task lands in status=done.
  - Kills the in-process state (simulating an engine crash) and verifies
    resume_after_restart re-picks the in-progress task.

Run from repo root:
    python3 engine/scripts/task_queue_smoke.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time

# Use a sandboxed queue dir so the test does not collide with the
# running engine's real ~/.anticipy/v7/task_queue/.
SANDBOX = tempfile.mkdtemp(prefix="taskq_smoke_")
os.environ["ANTICIPY_TASK_QUEUE_DIR"] = SANDBOX
os.environ.setdefault("ANTICIPY_ENGINE_PORT", "0")
os.environ.setdefault("ANTICIPY_TASK_QUEUE_INTERVAL_SECONDS", "2")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import task_queue as tq  # noqa: E402


def banner(s: str) -> None:
    print(f"\n=== {s} ===", flush=True)


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", flush=True)
    sys.exit(1)


def test_basic_enqueue_claim_complete() -> None:
    banner("test 1: enqueue -> claim -> complete")
    r = tq.enqueue("hello world", account_id="omar")
    if r.status != "pending":
        fail(f"expected pending, got {r.status}")
    c = tq.claim_next()
    if not c or c.task_id != r.task_id or c.status != "in_progress":
        fail(f"claim failed: {c}")
    d = tq.complete(c.task_id, {"value": "ok"})
    if d.status != "done":
        fail(f"expected done, got {d.status}")
    print("PASS")


def test_wake_at_deferral() -> None:
    banner("test 2: wake_at in 5s, claim_next returns None until due")
    delta = 5.0
    r = tq.enqueue("deferred", wake_at=time.time() + delta)
    c1 = tq.claim_next()
    if c1 is not None and c1.task_id == r.task_id:
        fail(f"premature claim: {c1}")
    print(f"waiting {delta + 0.5:.1f}s for wake_at...")
    time.sleep(delta + 0.5)
    c2 = tq.claim_next()
    if not c2 or c2.task_id != r.task_id:
        fail(f"did not wake: {c2}")
    print(f"woke up: task_id={c2.task_id}")
    tq.complete(c2.task_id, {"ok": True})
    print("PASS")


def test_failure_backoff() -> None:
    banner("test 3: failure schedules backoff retry")
    r = tq.enqueue("flaky")
    tq.claim_next()
    rec = tq.fail(r.task_id, "boom")
    if rec.status != "pending" or rec.retry_count != 1:
        fail(f"expected pending retry, got {rec}")
    if not rec.wake_at or rec.wake_at - time.time() < 55:
        fail(f"expected ~60s backoff, got wake_at delta {rec.wake_at - time.time()}")
    print(f"retry scheduled at +{int(rec.wake_at - time.time())}s, retry_count={rec.retry_count}")
    tq.cancel(r.task_id, "test cleanup")
    print("PASS")


def test_restart_recovery() -> None:
    banner("test 4: restart recovery resets in_progress to pending")
    r = tq.enqueue("survives crash")
    c = tq.claim_next()
    if c.status != "in_progress":
        fail(f"expected in_progress, got {c.status}")
    # Simulate an engine restart by clearing the in-mem state.
    import app.task_queue.store as store
    store._TASKS.clear()
    store._INDEX_OFFSET = 0
    store._LOADED = False
    recovered = tq.resume_after_restart()
    ids = [r.task_id for r in recovered]
    if c.task_id not in ids:
        fail(f"recovered list missing claimed task: {ids}")
    rec_after = tq.get(c.task_id)
    if rec_after.status != "pending":
        fail(f"expected pending after recovery, got {rec_after.status}")
    if "engine_restart_recovery" not in (rec_after.last_error or ""):
        fail(f"expected recovery flag in last_error, got {rec_after.last_error!r}")
    print(f"recovered {len(recovered)} task(s); claimed task is now pending")
    tq.complete(c.task_id, {"resumed": True})
    print("PASS")


def test_dispatcher_with_executor() -> None:
    banner("test 5: dispatcher + executor end-to-end")
    fired: list[str] = []

    def fake_executor(rec):
        fired.append(rec.task_id)
        return {"ok": True, "result": {"echo": rec.instruction}}

    tq.dispatcher.register_executor(fake_executor)

    r1 = tq.enqueue("scanner test A")
    r2 = tq.enqueue("scanner test B", wake_at=time.time() + 2.0)

    tq.dispatcher.start_scanner(interval_seconds=1)
    print("waiting for scanner to drain both tasks...")
    time.sleep(5.0)
    tq.dispatcher.stop()

    if r1.task_id not in fired or r2.task_id not in fired:
        fail(f"scanner did not fire all tasks; fired={fired}")
    if tq.get(r1.task_id).status != "done":
        fail(f"r1 not done: {tq.get(r1.task_id).status}")
    if tq.get(r2.task_id).status != "done":
        fail(f"r2 not done: {tq.get(r2.task_id).status}")
    print(f"fired={fired}")
    print("PASS")


def test_persistence_across_module_reload() -> None:
    banner("test 6: queue persists when module is reloaded (file-backed)")
    r = tq.enqueue("survives module reload",
                    metadata={"flag": "persist"})

    # Force a reload of the store module so all in-memory state is dropped.
    import importlib
    import app.task_queue.store as store_mod
    importlib.reload(store_mod)
    import app.task_queue as tq_new
    importlib.reload(tq_new)

    found = tq_new.get(r.task_id)
    if found is None:
        fail(f"task {r.task_id} not found after reload")
    if found.instruction != "survives module reload":
        fail(f"instruction mismatch: {found.instruction!r}")
    if found.metadata.get("flag") != "persist":
        fail(f"metadata not preserved: {found.metadata}")
    tq_new.complete(found.task_id, {"ok": True})
    print(f"survived reload: task_id={found.task_id}")
    print("PASS")


def main() -> int:
    print(f"sandbox queue dir: {SANDBOX}", flush=True)
    test_basic_enqueue_claim_complete()
    test_failure_backoff()
    test_restart_recovery()
    test_persistence_across_module_reload()
    test_dispatcher_with_executor()
    test_wake_at_deferral()
    banner("ALL TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
