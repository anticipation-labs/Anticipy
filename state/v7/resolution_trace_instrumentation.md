# Resolution-trace instrumentation (M1 R3)

## What this adds

A per-ingest_id resolution trace surfaced via
`GET /api/inference/trace/{ingest_id}`. Each entry records which
entity the planner consulted, what it resolved to, and with what
confidence.

## Buffer

Module-level dict in `engine/app/product/server.py`:

- `_RESOLUTION_TRACE_BUFFER: dict[str, list[dict]]` keyed by ingest_id.
- `_RESOLUTION_TRACE_ORDER: list[str]` FIFO order tracker.
- `_RESOLUTION_TRACE_PLANS: dict[str, dict]` per-ingest plan snapshot.
- `_RESOLUTION_TRACE_LOCK = threading.Lock()` for all mutations.
- Cap: 100 ingest_ids. When the 101st utterance comes in, the oldest
  buffer + plan slot is dropped.

## Thread-local context

`_CURRENT_INGEST_ID` (a `threading.local`) is set by
`_process_utterance` at the top of every utterance and cleared after.
Resolver hooks read it via `_get_current_ingest_id()` so they know
which buffer slot to append to. A standalone resolver call (no active
ingest) records nothing, which is the intended behavior.

## Hooks installed (4)

1. **`PersonResolver.resolve`** in `engine/app/product/person_resolver.py`.
   Wraps the original method as `_resolve_inner`; the public `resolve`
   appends `{kind: "person", reference, resolved_to, confidence,
   alternatives, reason, context_text}` after the inner call returns.

2. **`memory.resolve_reference_sync` caller** in `_memory_draw`
   (`engine/app/product/server.py`). The frozen
   `app.anticipy.memory` is not touched. The caller appends
   `{kind: "memory_resolve_reference", reference, resolved_to,
   confidence, resolved, reason, layer, alternatives}`.

3. **`DossierLoader.is_blocked`** in
   `engine/app/product/dossier_active_loader.py`. Appends
   `{kind: "blocked_check", topic, blocked, reason, pattern, surfaces}`.

4. **`_compose_task_from_memory`** in
   `engine/app/product/server.py`. Appends
   `{kind: "compose_task_from_memory", instruction,
   dossier_snapshot_keys, profile_keys, recent_window_count}`.

## Endpoint

`GET /api/inference/trace/{ingest_id}` returns:

```
{
  "ok": true,
  "ingest_id": "<id>",
  "trace": [<list of hook entries in append order>],
  "trace_length": <int>,
  "plan": {<final planner output for that ingest>}
}
```

Returns 404 when the ingest_id is not in the buffer (either never
seen or already evicted by FIFO cap).

## `_trace_from_record` compatibility

The original single-entity payload (reference, resolved_to,
layer_used, confidence, candidates, plan) is preserved unchanged. The
function now also writes `rec["resolution_trace"]` and includes
`resolution_trace` in its return dict, so the existing cloud-sync
payload picks up the new field automatically. Downstream consumers
that read the legacy fields are unaffected.

## Test evidence

- Source uvicorn on port 8732 (live engine on 8731 left running).
- Inject: `"Hey, I should circle back with Maya about Friday."`
- Captured trace: `state/v7/resolution_trace_runs/maya_inject_trace.json`.
- 404 path verified for unknown ingest_id.
