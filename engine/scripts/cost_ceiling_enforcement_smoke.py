#!/usr/bin/env python3
"""Smoke test for cost-ceiling enforcement in the action engine.

Covers the two-part patch landed in:

  - engine/app/action_engine/openrouter_client.py
      Per-task budget gate at the top of chat(); record_call after
      a successful HTTP round trip.

  - engine/app/universal/action_loop.py
      Snapshot the active task id on the request thread and rebind
      it inside the worker thread so the gate has a task to read.

Assertions:

  1. OpenRouterClient.chat records the call into cost_telemetry's
     per-task ledger when an active task is bound on this thread.
  2. When the per-task ledger has already crossed PER_TASK_HARD_CAP_USD,
     the next chat() refuses with error="BUDGET_EXCEEDED: ..." and the
     HTTP layer is NEVER called.
  3. An action_loop-style worker thread that snapshots and rebinds the
     active task id observes the bound id inside _worker, and the bind
     is cleared after the worker exits.

The HTTP layer is stubbed via monkeypatch on requests.post so the
script runs with zero network and no real OpenRouter spend.

Run from repo root:

    python3 engine/scripts/cost_ceiling_enforcement_smoke.py

Exits 0 on PASS, 1 on FAIL.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "engine"))

# OpenRouterClient.__init__ raises if neither a direct sk-or- key nor a
# broker is configured, so we set a syntactically valid fake key BEFORE
# importing the module. The HTTP layer is stubbed below.
os.environ.setdefault("OPENROUTER_API_KEY", "sk-or-fake-smoke-test-key")


GREEN_CHECKS: list[str] = []
RED_CHECKS: list[str] = []


def ok(name: str) -> None:
    print(f"  PASS  {name}", flush=True)
    GREEN_CHECKS.append(name)


def bad(name: str, detail: str = "") -> None:
    suffix = f" -- {detail}" if detail else ""
    print(f"  FAIL  {name}{suffix}", flush=True)
    RED_CHECKS.append(f"{name}{suffix}")


def banner(s: str) -> None:
    print(f"\n=== {s} ===", flush=True)


# ---------------------------------------------------------------------------
# Stub for requests.post used by OpenRouterClient.chat
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int = 200, body: dict | None = None) -> None:
        self.status_code = status_code
        self._body = body or {
            "id": "fake-completion-001",
            "model": "deepseek/deepseek-v4-flash",
            "choices": [
                {
                    "message": {"content": "READY", "reasoning": ""},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4},
        }
        self.text = "stub"

    def json(self) -> dict:
        return self._body


def _install_request_stub() -> dict:
    """Replace requests.post with a counter-backed stub. Returns the
    counter dict so callers can assert how many HTTP calls happened."""
    counter = {"calls": 0, "last_payload": None}
    import requests  # type: ignore

    def _fake_post(url, *args, **kwargs):  # noqa: ANN001
        counter["calls"] += 1
        counter["last_payload"] = kwargs.get("json")
        return _FakeResponse()

    requests.post = _fake_post  # type: ignore[assignment]
    return counter


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_chat_records_cost_for_active_task() -> None:
    banner("1. OpenRouterClient.chat records cost into per-task ledger")
    from app.action_engine.openrouter_client import (  # type: ignore
        OpenRouterClient,
        TEXT_MODEL,
    )
    from app.product import cost_telemetry as ct  # type: ignore

    counter = _install_request_stub()
    task_id = f"smoke-task-record-{int(time.time() * 1000)}"
    ct.start_task(task_id)
    ct.set_active_for_thread(task_id)
    try:
        client = OpenRouterClient()
        resp = client.chat(
            [{"role": "user", "content": "ping"}],
            model=TEXT_MODEL,
            max_tokens=256,
        )
        if resp.error:
            bad("chat_returns_ok", f"got error={resp.error}")
            return
        if counter["calls"] != 1:
            bad("http_called_once", f"got {counter['calls']} calls")
            return
        rec = ct.current_task_record(task_id)
        if int(rec.get("call_count") or 0) != 1:
            bad(
                "ledger_call_count_is_1",
                f"got {rec.get('call_count')} (rec={rec})",
            )
            return
        if float(rec.get("cost_usd") or 0.0) <= 0.0:
            bad(
                "ledger_cost_recorded",
                f"got cost_usd={rec.get('cost_usd')} (rec={rec})",
            )
            return
        ok("chat_records_cost_for_active_task")
    finally:
        ct.set_active_for_thread(None)
        ct.finish_task(task_id, status="smoke_done")


def test_chat_refuses_when_budget_exceeded() -> None:
    banner("2. OpenRouterClient.chat refuses when per-task cap exceeded")
    from app.action_engine.openrouter_client import (  # type: ignore
        OpenRouterClient,
        TEXT_MODEL,
    )
    from app.product import cost_telemetry as ct  # type: ignore

    counter = _install_request_stub()
    task_id = f"smoke-task-exceed-{int(time.time() * 1000)}"
    ct.start_task(task_id)
    ct.set_active_for_thread(task_id)
    try:
        # Push the ledger above PER_TASK_HARD_CAP_USD without making a
        # network call. budget_gate trips on the NEXT call when total
        # cost is already greater than the cap.
        ct.record_call(
            task_id,
            "deepseek/deepseek-v4-flash",
            input_tokens=0,
            output_tokens=0,
            cost_usd=ct.PER_TASK_HARD_CAP_USD + 0.0005,
            is_vision=False,
        )
        client = OpenRouterClient()
        resp = client.chat(
            [{"role": "user", "content": "ping"}],
            model=TEXT_MODEL,
            max_tokens=256,
        )
        if not resp.error or "BUDGET_EXCEEDED" not in (resp.error or ""):
            bad(
                "chat_refused_with_budget_exceeded",
                f"expected BUDGET_EXCEEDED, got error={resp.error}",
            )
            return
        if counter["calls"] != 0:
            bad(
                "http_layer_not_called",
                f"expected 0 HTTP calls, got {counter['calls']}",
            )
            return
        rec = ct.current_task_record(task_id)
        if not rec.get("aborted"):
            bad(
                "ledger_marked_aborted",
                f"expected aborted=True, got rec={rec}",
            )
            return
        ok("chat_refuses_when_budget_exceeded")
    finally:
        ct.set_active_for_thread(None)
        ct.finish_task(task_id, status="smoke_exceeded")


def test_worker_rebinds_active_task_id() -> None:
    banner(
        "3. action_loop._worker style rebind keeps the active task id "
        "visible inside the worker thread"
    )
    from app.product import cost_telemetry as ct  # type: ignore
    from app.anticipy import platform_adapter as pa  # type: ignore

    task_id = f"smoke-task-worker-{int(time.time() * 1000)}"
    ct.start_task(task_id)
    ct.set_active_for_thread(task_id)
    pa.bind_active_task_id(task_id)

    observed: dict[str, str | None] = {
        "ct_id": None,
        "pa_id": None,
        "cleared_ct": None,
        "cleared_pa": None,
    }

    # Mirror the snapshot/rebind contract from action_loop._worker.
    snapshotted = ct.get_active_task_id_for_thread()

    def _worker() -> None:
        if snapshotted:
            ct.set_active_for_thread(snapshotted)
            pa.bind_active_task_id(snapshotted)
        try:
            observed["ct_id"] = ct.get_active_task_id_for_thread()
            observed["pa_id"] = pa.get_active_task_id()
        finally:
            ct.set_active_for_thread(None)
            pa.bind_active_task_id(None)
            observed["cleared_ct"] = ct.get_active_task_id_for_thread()
            observed["cleared_pa"] = pa.get_active_task_id()

    th = threading.Thread(target=_worker, daemon=True,
                          name="cost-ceiling-smoke-worker")
    th.start()
    th.join(timeout=5.0)

    try:
        if th.is_alive():
            bad("worker_finished", "worker thread did not exit in 5s")
            return
        if observed["ct_id"] != task_id:
            bad(
                "worker_sees_cost_telemetry_active_task",
                f"expected {task_id}, got {observed['ct_id']}",
            )
            return
        if observed["pa_id"] != task_id:
            bad(
                "worker_sees_platform_adapter_active_task",
                f"expected {task_id}, got {observed['pa_id']}",
            )
            return
        if observed["cleared_ct"] is not None:
            bad(
                "worker_clears_cost_telemetry_after_exit",
                f"expected None, got {observed['cleared_ct']}",
            )
            return
        if observed["cleared_pa"] is not None:
            bad(
                "worker_clears_platform_adapter_after_exit",
                f"expected None, got {observed['cleared_pa']}",
            )
            return
        ok("worker_rebinds_active_task_id")
    finally:
        ct.set_active_for_thread(None)
        pa.bind_active_task_id(None)
        ct.finish_task(task_id, status="smoke_worker_done")


def main() -> int:
    print("Cost ceiling enforcement smoke test", flush=True)
    print(f"  repo root: {ROOT}", flush=True)
    for fn in (
        test_chat_records_cost_for_active_task,
        test_chat_refuses_when_budget_exceeded,
        test_worker_rebinds_active_task_id,
    ):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            bad(fn.__name__, f"raised {type(exc).__name__}: {exc}")
            traceback.print_exc()
    print(
        f"\nPASS={len(GREEN_CHECKS)} FAIL={len(RED_CHECKS)}",
        flush=True,
    )
    return 0 if not RED_CHECKS else 1


if __name__ == "__main__":
    sys.exit(main())
