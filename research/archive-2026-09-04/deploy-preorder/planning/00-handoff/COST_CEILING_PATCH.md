# Cost Ceiling Patch (Proposal Only, NOT Applied)

Date: 2026-05-29
Author: Claude (Anticipy auditor)
Status: PROPOSAL. Do not apply without review.

## Goal

Make the `$0.005` per-task hard cap enforced on EVERY LLM HTTP call in the engine, including the `OpenRouterClient` path used by the universal action loop, the DSv4 skill runner, and the vision verifier. Today the cap is enforced only for calls that go through `platform_adapter.model_call`; the universal loop path bypasses it entirely (see `COST_CEILING_AUDIT.md`).

## Minimum diff

Three small changes, no module restructure. The fix has two parts: (1) make `OpenRouterClient.chat` ask the cost telemetry gate before posting and accrue cost after, (2) propagate the active task id into the action-loop worker thread so the gate has a task to read.

### 1. `engine/app/action_engine/openrouter_client.py`

Add a budget-gate check at the top of `chat()` and accrue cost into the per-task ledger after each successful call. The client stays standalone; if cost telemetry is not importable (older test rigs) it falls through transparently.

```diff
--- a/engine/app/action_engine/openrouter_client.py
+++ b/engine/app/action_engine/openrouter_client.py
@@ -106,6 +106,18 @@ class OpenRouterClient:
         max_tokens = max(max_tokens, MIN_TOKENS)
         msgs = [dict(m) for m in messages]
+        # Per-task budget gate. Mirrors platform_adapter.model_call.
+        # If the active task has already crossed the hard cap, refuse
+        # the call so the loop escalates instead of burning more money.
+        try:
+            from app.product import cost_telemetry as _ct
+            _task_id = _ct.get_active_task_id_for_thread()
+            if _task_id:
+                _gate = _ct.budget_gate(_task_id)
+                if _gate:
+                    return ORResponse(
+                        content="", model=model, latency_s=0.0,
+                        error=f"BUDGET_EXCEEDED: {_gate}",
+                    )
+        except Exception:
+            _ct = None  # cost telemetry optional
         if image_b64:
             # Attach the image to the last user turn.
@@ -228,6 +240,17 @@ class OpenRouterClient:
                 reasoning=reasoning if isinstance(reasoning, str) else "",
                 finish_reason=finish,
                 cost_usd=_estimate_cost(model, p_tok, c_tok),
                 raw=j,
             )
             resp.raw["_credential_mode"] = credential_mode
+            # Accrue cost into the per-task ledger so the budget gate
+            # has accurate totals for the NEXT call. Best-effort; never
+            # break the call path.
+            try:
+                if _ct is not None and _task_id:
+                    _ct.record_call(
+                        _task_id, resp.model,
+                        int(resp.prompt_tokens or 0),
+                        int(resp.completion_tokens or 0),
+                        float(resp.cost_usd or 0.0),
+                        is_vision=bool(image_b64),
+                    )
+            except Exception:
+                pass

             # Reasoning model starved the answer: retry once, 2x budget.
             if (not content and reasoning and finish == "length"
```

Note: this also records vision-call counts because `is_vision=bool(image_b64)` flows into `record_call`, which keeps `VISION_ABORT_COUNT` enforcement working when an image is attached via the action-engine path.

### 2. `engine/app/universal/action_loop.py`

Propagate the active task id into the worker thread. `_active_task` and `_active_per_thread` are both `threading.local()`, so the worker thread sees `None` by default. The fix snapshots both bindings on the request thread and re-binds them on the worker.

```diff
--- a/engine/app/universal/action_loop.py
+++ b/engine/app/universal/action_loop.py
@@ -167,9 +167,28 @@ def run_until_done(intent: str,
     box: dict[str, Any] = {"result": None, "error": None}

+    # Snapshot the active task id from the calling thread so the worker
+    # can rebind it. Without this rebind, every LLM call inside the
+    # runner sees task_id=None and the budget gate has no record to
+    # consult. Best-effort import: if cost telemetry is unavailable
+    # the worker still runs.
+    _active_task_id = None
+    try:
+        from app.product import cost_telemetry as _ct
+        _active_task_id = _ct.get_active_task_id_for_thread()
+    except Exception:
+        _ct = None  # type: ignore
+
     def _worker() -> None:
         try:
+            if _active_task_id:
+                try:
+                    if _ct is not None:
+                        _ct.set_active_for_thread(_active_task_id)
+                    from app.anticipy import platform_adapter as _pa
+                    _pa.bind_active_task_id(_active_task_id)
+                except Exception:
+                    pass
             tr = runner.run(task, starting_url=starting_url)
             box["result"] = tr
         except Exception as exc:  # noqa: BLE001
             box["error"] = f"{type(exc).__name__}: {exc}"
+        finally:
+            try:
+                if _ct is not None:
+                    _ct.set_active_for_thread(None)
+                from app.anticipy import platform_adapter as _pa
+                _pa.bind_active_task_id(None)
+            except Exception:
+                pass
```

### 3. `engine/app/action_engine/vision_verifier.py`

The verifier instantiates its own `OpenRouterClient` (line 106-108). After change (1) it inherits the gate automatically because every `chat()` call now checks the active thread-local task id. No code change needed in this file. Listed here for completeness so a future reviewer does not assume it was missed.

## Why this is the minimum

- One call-site change in `OpenRouterClient.chat` covers all six DSv4 skill-runner call sites and the vision verifier without touching any of them.
- One thread-binding change in `action_loop._worker` covers the cross-thread gap for the entire universal path; the `/api/act` path was already correct because its work runs on the request thread.
- No new ceilings or thresholds are introduced. The patch reuses the existing `cost_telemetry.budget_gate` and `cost_telemetry.record_call`. The `$0.005` cap stays the single source of truth at `cost_telemetry.PER_TASK_HARD_CAP_USD`.

## Edge cases the patch still misses

1. **Concurrent calls on the same task.** Two parallel chat calls can both read `cost = 0.004` before either updates the ledger, and both pass the gate even though their sum will breach the cap. The current `platform_adapter.model_call` has the same race; mitigation would require holding `_lock` across the HTTP round trip, which would serialize all spend and is not worth it. Worst case overrun stays bounded to one extra call.

2. **OpenRouter retry storm.** `OpenRouterClient.chat` retries on 429/5xx up to five times with exponential backoff. The gate is checked once at the top of `chat()`, not before each retry. A long outage that bills a full call on the fifth attempt cannot be refused mid-retry. Acceptable: the gate fires on the NEXT call after the cap is reached. Adding a per-retry gate check would only help in a very narrow failure mode.

3. **Vision verifier bypass via `urllib`.** `VisionSurface._post_chat` uses `urllib.request.urlopen` directly (`engine/app/product/surface_runtime_vision.py:301-322`), not `OpenRouterClient`. This path already has its OWN gate via `vision_gate` (count-based) and `record_vision_call`, so the dollar cap is partially covered through the count limit. A future tightening could route this through the cost gate too, but it is not the minimum patch.

4. **Tasks that do not bind a task id.** A direct test invocation of `DSv4SkillRunner.run` outside any `/api/...` endpoint will not have an active task id. The gate falls open (returns `None`). This matches today's behavior for unattributed calls.

## Verification plan

After applying:

1. `pytest engine/app/product/tests/test_cost_telemetry.py` (or the closest existing suite) to confirm no regression on the path that already worked.
2. Manual probe: start a universal-loop run with a deliberately verbose intent, then `curl 127.0.0.1:8731/api/cost/stats` after the run. The recent-tasks list should now show the universal task with its real cost (today it shows `$0.0`).
3. Synthetic overrun: temporarily lower `PER_TASK_HARD_CAP_USD` to `0.0005` in a copy of `cost_telemetry.py`, run a universal task, and confirm the runner returns mid-loop with `BUDGET_EXCEEDED` instead of running to `max_iters`.
4. Restore the cap to `0.005` and re-run G11 to confirm `p95_cost_usd` now reflects real universal-loop spend.

## Out of scope for this patch

- Per-user daily / weekly cap enforcement (the `DAILY_BUDGET_USD = 0.55` and `WEEKLY_BUDGET_USD = 3.85` values are exposed in `/api/cost/stats` but no gate consults them today).
- Restructuring the action engine to use `platform_adapter.model_call` directly. That is the cleaner long-term fix, but it touches every call site and is not the minimum change.
- Adding a separate G-test that verifies the gate actually fires (the current G11 verifies observed cost, not enforcement). Recommended as a follow-up unit but not part of this patch.
