#!/usr/bin/env python3
"""Smoke test for the task queue cleanup policy.

Covers:
  - stale_trivia_swept: status=waiting + needs_user_clarification + age > 1h
    + trivia-opener instruction cancels with reason "stale_trivia_swept".
  - dev_test_leak_purged: instruction containing a known synthetic test
    recipient cancels with reason "dev_test_leak_purged".
  - rolled_up: recovery sibling chains over the retry budget collapse to
    one task (the newest) and the rest cancel with reason "rolled_up";
    a stub escalator is called exactly once per group.
  - real: a real waiting clarification task is left alone.
  - max_visible_in_ui: surfaces via store.max_visible_in_ui() and via
    the summary dict.
  - audit trail: every cancellation appears in the JSONL journal.

Run from repo root:
    python3 engine/scripts/task_queue_cleanup_smoke.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time

SANDBOX = tempfile.mkdtemp(prefix="taskq_cleanup_smoke_")
os.environ["ANTICIPY_TASK_QUEUE_DIR"] = SANDBOX

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import task_queue as tq  # noqa: E402


PASS = 0
FAIL = 0


def banner(s: str) -> None:
    print(f"\n=== {s} ===", flush=True)


def assert_eq(label: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}: {got!r}", flush=True)
    else:
        FAIL += 1
        print(f"  FAIL {label}: got {got!r}, want {want!r}", flush=True)


def assert_true(label: str, cond: bool) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {label}", flush=True)
    else:
        FAIL += 1
        print(f"  FAIL {label}", flush=True)


def main() -> int:
    print(f"sandbox queue dir: {SANDBOX}", flush=True)

    banner("seed: build a synthetic waiting queue")

    now = time.time()

    # Trivia, stale (> 1h). Should sweep.
    trivia_stale_1 = tq.enqueue("wait, when did the Roman Empire fall")
    trivia_stale_2 = tq.enqueue("what is the capital of France")
    trivia_stale_3 = tq.enqueue("why did Rome decline")
    for r in (trivia_stale_1, trivia_stale_2, trivia_stale_3):
        # Backdate so the cleanup considers them stale.
        r.created_at = now - 7200  # 2h old
        tq.wait_for(r.task_id, "needs_user_clarification")

    # Trivia, fresh (< 1h). Should be kept (real-kept), because the policy
    # only sweeps trivia that has actually gone stale.
    trivia_fresh = tq.enqueue("when was Anticipy founded")
    tq.wait_for(trivia_fresh.task_id, "needs_user_clarification")

    # Dev / test leak. Should purge.
    leak_1 = tq.enqueue("draft email to omarkebrahim+anticipy-demo@gmail.com")
    leak_2 = tq.enqueue("email skylar@anticipy-test.local about receipts")
    leak_3 = tq.enqueue("draft to cam@example.com about Q3 roadmap")
    for r in (leak_1, leak_2, leak_3):
        tq.wait_for(r.task_id, "needs_user_clarification")

    # Real clarification. Should stay.
    real = tq.enqueue("Send a follow up email about the marketing review")
    tq.wait_for(real.task_id, "needs_user_clarification")

    # Recovery chain that should roll up: 5 siblings, same kind,
    # backdated so the newest is freshest.
    recovery_chain = []
    for i in range(5):
        r = tq.enqueue(f"send Sarah the deck attempt {i}")
        r.created_at = now - (1000 - i * 10)
        tq.wait_for(
            r.task_id,
            "recovery:login_required",
            wake_at=None,
        )
        # Attach recovery metadata so the cleanup groups them.
        rec = tq.get(r.task_id)
        rec.metadata = {"recovery_failure_kind": "login_required"}
        recovery_chain.append(r.task_id)

    # Single recovery task that should stay (under budget).
    recovery_solo = tq.enqueue("ping Stripe dashboard")
    tq.wait_for(recovery_solo.task_id, "recovery:mfa_challenge")
    rec_solo = tq.get(recovery_solo.task_id)
    rec_solo.metadata = {"recovery_failure_kind": "mfa_challenge"}

    # 3 stale trivia + 1 fresh trivia + 3 leaks + 1 real + 5 recovery
    # chain + 1 recovery solo = 14 waiting before cleanup runs.
    waiting_before = [r for r in tq.list_tasks(status="waiting", limit=500)]
    assert_eq("waiting count before", len(waiting_before), 14)

    banner("run cleanup_expired_tasks with stub escalator")

    escalator_calls = []

    def stub_escalator(rec):
        escalator_calls.append(rec.task_id)
        return {"ok": True, "sms_body": "stubbed", "sms_mock": True}

    summary = tq.cleanup_expired_tasks(escalator=stub_escalator)
    print(json.dumps(summary, indent=2, default=str), flush=True)

    banner("assertions")

    # Cancel counts.
    assert_eq("stale_trivia_swept count",
              summary["stale_trivia_swept"], 3)
    assert_eq("dev_test_leak_purged count",
              summary["dev_test_leak_purged"], 3)
    assert_eq("rolled_up count", summary["rolled_up"], 4)
    assert_eq("escalated count", summary["escalated"], 1)
    assert_eq("escalator_calls", len(escalator_calls), 1)
    # The newest sibling (last enqueued) is what gets kept and escalated.
    assert_eq("escalated id is newest sibling",
              escalator_calls[0], recovery_chain[-1])
    # real + fresh trivia (under 1h, so survives) + recovery_chain_newest
    # + recovery_solo = 4 kept.
    assert_eq("kept count", summary["kept"], 4)
    assert_eq("real_kept count", summary["real_kept"], 2)
    assert_eq("recovery_kept count", summary["recovery_kept"], 2)

    # Each stale trivia became cancelled.
    for tid in (trivia_stale_1.task_id, trivia_stale_2.task_id,
                trivia_stale_3.task_id):
        r = tq.get(tid)
        assert_eq(f"trivia {tid[:18]} status", r.status, "cancelled")
        assert_eq(f"trivia {tid[:18]} reason",
                  r.last_error, "stale_trivia_swept")

    # Each leak became cancelled.
    for tid in (leak_1.task_id, leak_2.task_id, leak_3.task_id):
        r = tq.get(tid)
        assert_eq(f"leak {tid[:18]} status", r.status, "cancelled")
        assert_eq(f"leak {tid[:18]} reason",
                  r.last_error, "dev_test_leak_purged")

    # Recovery rollup: the first 4 cancel, the newest stays waiting.
    for tid in recovery_chain[:-1]:
        r = tq.get(tid)
        assert_eq(f"rolled_up {tid[:18]} status",
                  r.status, "cancelled")
        assert_eq(f"rolled_up {tid[:18]} reason",
                  r.last_error, "rolled_up")
    r = tq.get(recovery_chain[-1])
    assert_eq("recovery kept status", r.status, "waiting")

    # Solo recovery untouched.
    r = tq.get(recovery_solo.task_id)
    assert_eq("recovery solo status", r.status, "waiting")

    # Real clarification untouched.
    r = tq.get(real.task_id)
    assert_eq("real clarification status", r.status, "waiting")

    # Fresh trivia untouched (under 1h).
    r = tq.get(trivia_fresh.task_id)
    assert_eq("fresh trivia status", r.status, "waiting")

    # max_visible_in_ui: default is 5, env override is honoured.
    assert_eq("default max_visible_in_ui", tq.max_visible_in_ui(), 5)
    os.environ["ANTICIPY_TASK_QUEUE_MAX_VISIBLE_IN_UI"] = "3"
    assert_eq("env-overridden max_visible_in_ui",
              tq.max_visible_in_ui(), 3)
    os.environ.pop("ANTICIPY_TASK_QUEUE_MAX_VISIBLE_IN_UI", None)

    # Journal audit: every cancel must appear as a cancel event.
    jrn = tq.queue_dir() / "queue.jsonl"
    cancel_events = 0
    for line in jrn.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if entry.get("event") == "cancel":
            cancel_events += 1
    # 3 stale trivia + 3 leak + 4 rolled_up = 10.
    assert_eq("journal cancel events", cancel_events, 10)

    banner("idempotency: second run is a no-op")

    summary2 = tq.cleanup_expired_tasks(escalator=stub_escalator)
    assert_eq("second run cancelled", summary2["cancelled"], 0)
    assert_eq("second run escalated", summary2["escalated"], 0)

    banner(f"result: {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
