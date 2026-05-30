# Cost Ceiling Runtime Enforcement Audit

Date: 2026-05-29
Auditor: Claude (Anticipy auditor)
Verdict: **PARTIALLY_ENFORCED**

## Summary

The `$0.005` per-task hard cap (G11) is enforced only for LLM calls that go through `app.anticipy.platform_adapter.model_call`. A large second LLM code path, `app.action_engine.openrouter_client.OpenRouterClient.chat`, bypasses the budget gate entirely. The `OpenRouterClient` is the one used by the universal action loop, the vision verifier, and the DSv4 skill runner (decompose, ledger, decide, completion, vision verifier), which is the single biggest spend surface in the product. A runaway LLM session here is mechanically possible: nothing in code refuses the next chat call when accumulated task cost crosses `$0.005`.

Below answers Phase 1's five questions.

## 1. Is there a budget gate?

Yes. Defined at `engine/app/product/cost_telemetry.py:360-399` as `budget_gate(task_id)`. It returns a non-empty reason string when:
- `cost_usd > PER_TASK_HARD_CAP_USD` (line 380, `0.005` USD, defined at line 52), or
- `vision_call_count >= VISION_ABORT_COUNT` (line 389, 5 calls).

When triggered, the record is marked `aborted = True` so subsequent calls also refuse.

## 2. Where is it checked?

Two places only:

### a) `platform_adapter.model_call` BEFORE the HTTP request
`engine/app/anticipy/platform_adapter.py:295-310`. The gate is called as
```
gate_reason = gate(effective_task_id)
if gate_reason:
    res = ModelResult("", False, f"BUDGET_EXCEEDED: {gate_reason}",
                      0, 0, 0.0, 0.0)
    _log_model_call({..., "budget_exceeded": True, "reason": ...})
    return res
```
The gate is wired at module import in `engine/app/product/server.py:77-83` via
```
_pa_for_telemetry.set_telemetry_sink(_cost_telemetry.record_call_from_log_row)
_pa_for_telemetry.set_budget_gate(_cost_telemetry.budget_gate)
```
This catches the planner cascade (`compose_task`), memory reconcile, taxonomy, onboarding extract, addressee resolver, comms generator, grader, hedge, durable, harness, trivia answer, coldstart auto_inhale, and every other site listed by `grep model_call`.

### b) `VisionSurface._call` BEFORE Kimi K2.6 vision dispatch (count gate only)
`engine/app/product/surface_runtime_vision.py:246-260` calls `_ct.vision_gate(task_id)` which counts vision calls, NOT cost. It returns `VISION_BUDGET_ABORTED` when `vision_call_count >= 5`. Cost is not checked here; only count.

`OpenRouterClient.chat` (`engine/app/action_engine/openrouter_client.py:108-248`) does NOT check the gate. It posts directly to OpenRouter, logs to a separate file `~/.anticipy/openrouter_calls.jsonl`, and is the LLM call path for:
- `engine/app/action_engine/dsv4_skill_runner.py:739, 765, 789, 826, 850, 864` (decompose, ledger build, ledger status, decide, completion, fix) called from `run_until_done` in the universal action loop;
- `engine/app/action_engine/vision_verifier.py:106-108`.

This is the bypass.

## 3. What happens when exceeded?

For path (a), `platform_adapter.model_call`:
- Returns `ModelResult(ok=False, error="BUDGET_EXCEEDED: ...", cost=0)` immediately.
- Logs a row with `budget_exceeded: True`, `cost_usd: 0`.
- Calls remain refused for the rest of the task because `rec["aborted"] = True` (`cost_telemetry.py:381`).
- The single caller that special-cases this is `compose_task` in `engine/app/product/server.py:7004-7025`, which returns a clarify with the message "This task crossed the $0.005 per task hard cap. Tell me how to proceed." All other callers just see `res.ok == False` and fall to their documented safe default.

For path (b), `OpenRouterClient.chat`: nothing. The call proceeds, cost accumulates in the separate JSONL log, and the per-task cost telemetry never sees it. The DSv4 skill runner can keep looping up to `max_iters=30` with multi-thousand-token vision payloads on each iteration. With Kimi K2.6 priced at `$0.60 in / $2.50 out` per million tokens and a ~1800-token vision payload per iteration (image bytes dominate prompt tokens via base64), each decide call is roughly `$0.0011` for prompt plus completion. 30 iterations of decide alone is `~$0.033`, well past the `$0.005` cap. Add decompose + ledger build + ledger status + completion check + fix-loop and a single `/api/universal/run` invocation can plausibly bill `>$0.05` with no runtime refusal. The only ceiling is the wall-clock `deadline_sec` (60 s default) and the iteration cap.

## 4. Hard cap value vs G11 threshold

Both are `$0.005`. `PER_TASK_HARD_CAP_USD = 0.005` at `cost_telemetry.py:52`, matching the G11 verify "p95 per-task cost < $0.005" in `planning/00-handoff/CYCLE_PROCEDURE.md:60`. The soft ceiling is `PER_TASK_CEILING_USD = 0.002` (the `$200/user/year` math), and the hard cap is `2.5x` the ceiling per the spec note in the docstring (line 31-33). G11 verifies the p95 of OBSERVED per-task cost; it does not verify the gate fires.

## 5. Per-task or per-call?

Per task. `budget_gate(task_id)` reads the accumulated `cost_usd` for the active task record and trips once the cumulative total has already exceeded the cap. The check happens BEFORE the next call, so the call that pushes the total over the line is allowed to complete; the gate refuses the call AFTER it. Worst case overrun is one full LLM call past the cap.

Two thread-safety notes:

- `cost_telemetry._lock` is a single `threading.RLock` protecting `_active` and the per-task record. Concurrent calls on the same task update the cost atomically, but two calls that both read `cost = 0.004` before either updates would both be allowed by the gate even if their combined cost would breach `0.005`. In practice each task runs single-threaded through the cascade, so this is unlikely to bite. The universal action loop spawns ONE worker thread per request (`engine/app/universal/action_loop.py:176-179`), so the worst case is one in-flight call past the cap per task.

- `bind_active_task_id` and `set_active_for_thread` use `threading.local()`. When `/api/universal/run` (`server.py:10760-10764`) binds the task on the asyncio request thread but the action loop spawns a separate worker thread (`action_loop.py:176-179`) that calls into `OpenRouterClient.chat`, the thread-local task id is NOT visible on the worker. Even if `OpenRouterClient.chat` were retrofitted to call the gate, it would not find an active task on its thread today. The fix has two parts: (i) route `OpenRouterClient` through `platform_adapter.model_call` or call the gate directly, AND (ii) propagate the task id into the worker thread.

## Phase 2: Observed in practice

Live engine at `127.0.0.1:8731`. Snapshot from `/api/cost/stats`:
- `window_size: 0` (zero finished tasks in the per-task aggregator window).
- `p95_cost_usd: 0.0`, `max_cost_usd: 0.0`, `above_hard_cap_count: 0`.
- `running_daily_total_usd: 0.0`, `daily_calls: 0`.

Across the disk log `~/.anticipy/system_v1/model_calls.jsonl` (`41,506` rows), only `5` rows carry a `task_id` and only `4` distinct task ids appear. Aggregated totals:
- `sim-task-1`: `$0.001350`
- `act-7a3445c0660c`: `$0.000697`
- `act-0cf11e351ddd`: `$0.000681`
- `integration-test`: `$0.0`

Max per-task cost: `$0.001350`. No task above the cap.

The separate action-engine log `~/.anticipy/openrouter_calls.jsonl` (`5,921` rows) has no `task_id` field at all. Per-row cost on that file is anywhere from `$0.000295` to `$0.001316`; the highest single row in the tail is `$0.001316` (one Kimi vision call). A 30-iteration loop on this code path would easily clear the cap.

This explains G11's `p95 = $0.0`: the action-engine path simply does not show up in the cost aggregator at all. G11 is true today because the universal path's spend is invisible to the metric, not because cost is bounded.

## What is enforced

- Planner cascade and every other call through `platform_adapter.model_call`: cap enforced on the same thread that bound the task id.
- Vision call count via `VisionSurface._call`: count-based abort at 5 calls per task.

## What is NOT enforced

- Every LLM call made through `OpenRouterClient.chat` (DSv4 skill runner, vision verifier). The single biggest spend surface in the product.
- Cross-thread task binding (universal action loop spawns a worker thread without rebinding the task id).
- Cost contribution of vision calls toward the dollar cap when the vision path uses the `OpenRouterClient` (the cost is logged to `openrouter_calls.jsonl` but never billed to a per-task ledger).

## Recommendation

A patch is recommended. See `planning/00-handoff/COST_CEILING_PATCH.md`.
