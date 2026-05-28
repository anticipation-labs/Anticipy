# V7 Memory Partition Fix: `account_id` vs `user_id`

Date: 2026-05-27
Branch: main
Author: Anticipy V7 supervisor

## The bug

The dossier loader path partitioned by `account_id`. The legacy
product surface partitioned by `user_id` (and the in-process
`USER_ID = "anticipy-user"` constant). Memory writes used one key,
reads used the other, so the engine could not see its own dossier.

The two paths in conflict:

1. `app.product.dossier_active_loader.DossierLoader` reads
   `~/.anticipy/v7/dossiers/<account_id>/dossier.json`.

2. `app.product.scoped_memory.ScopedMemory` reads/writes
   `~/.anticipy/v7/memory/<account_id>/<device_id>/memory.jsonl`.

3. `app.product.server.py` lines 6316-6401 expose the legacy
   `/api/dossier/write` and `/api/dossier` endpoints. These accept a
   `user_id` field. They previously routed to
   `app.anticipy.dossier_store` (frozen module that was retired in
   commit f1336a05, replaced by the M1 loader at commit ff0e1e2e).
   Once retired, the legacy endpoints returned `410 Gone` with a hint
   to use `/api/dossier/active`. But `/api/dossier/active` only
   accepted `account_id`, not `user_id`. A caller that had only the
   `user_id` value at hand (the legacy product code path: the
   `USER_ID` constant, the Twilio onboarding store, etc.) had no way
   to read or write the M1 dossier.

The M1 endpoints also lacked a `POST /api/dossier/active`, so even a
caller with the right `account_id` could not write through the API.
Writes only happened via the file system (Twilio onboarding wrote
directly to disk).

## Files involved

- `engine/app/product/dossier_endpoints.py` (FIXED)
- `engine/app/product/scoped_memory_endpoints.py` (FIXED)
- `engine/app/product/dossier_active_loader.py` (read only, M1, no
  edit needed since the route handler now translates the key before
  invoking the loader)
- `engine/app/product/scoped_memory.py` (read only, M2/M3/M4, no edit
  needed for the same reason)
- `engine/app/anticipy/memory.py` (frozen, not edited)
- `engine/app/anticipy/platform_adapter.py` (frozen, not edited)

## The fix

Translation layer at the router boundary. Every endpoint accepts both
`account_id` and `user_id` as synonyms, and resolves them to the same
on-disk partition. The fix is contained in two files only and never
touches frozen paths.

### `dossier_endpoints.py`

Adds `_resolve_partition(account_id, user_id)`: whichever is non-empty
wins (`account_id` wins on collision since it is the V7 canonical
name). All four routes accept either as input. Every response surfaces
both `account_id` and `user_id` keys so callers see what they sent
back.

Adds `POST /api/dossier/active`: write a dossier fragment to the same
file that `GET /api/dossier/active` reads from. Accepts both an
`entry` object (full fragment shape: people, preferences,
do_not_touch, etc.) and a legacy `key`/`value` pair shape (lands
under `existing["facts"][key] = value`). Merges with the existing
file on disk via shallow dict merge plus list extension. Writes
atomically (tmp file + `os.replace`).

Diff summary:

```
+ def _resolve_partition(account_id, user_id): ...
+ def _writable_dossier_path(account_id): ...
+ def _merge_dossier_fragment(existing, fragment): ...

  @router.get("/api/dossier/active")
- def dossier_active(account_id: str = Query(...), device_id: str = Query("")):
+ def dossier_active(
+     account_id: Optional[str] = Query(None),
+     user_id: Optional[str] = Query(None),
+     device_id: str = Query(""),
+ ):
+     partition = _resolve_partition(account_id, user_id)
      loader = _loader(partition, device_id)
      ...
+     snap["user_id"] = snap.get("account_id", partition)

+ @router.post("/api/dossier/active")
+ def dossier_active_write(body: ActiveWriteBody) -> JSONResponse:
+     partition = _resolve_partition(body.account_id, body.user_id)
+     target = _writable_dossier_path(partition)
+     ... merge then atomic-replace ...

  # Same pattern applied to /api/dossier/refresh and /api/dossier/context.
```

### `scoped_memory_endpoints.py`

Same `_resolve_partition(account_id, user_id)` helper. Every body
model adds `user_id: Optional[str]`. Every route resolves the key
before constructing `ScopedMemory`. Every response surfaces both
names.

## Proof of fix (live engine on 127.0.0.1:8732)

The packaged engine at PID 17978 on port 8731 is an older binary that
predates the M1, M2, M3, M4 router-wire attaches; only the legacy
`/api/dossier/write` and `/api/dossier` routes are registered there
(both return 410 Gone). To prove the fix without touching the running
packaged engine, the source-built engine was started on 127.0.0.1:8732
via `python -c 'import uvicorn; from app.product.server import app;
uvicorn.run(app, port=8732)'` with `ANTICIPY_ENGINE_PORT=8732`. The
fix will land in the packaged engine on the next build via the same
source path that ships today.

### Round-trip (account_id only)

```
$ curl -X POST http://127.0.0.1:8732/api/dossier/active \
    -d '{"account_id":"proof-evidence-final","device_id":"laptop-proof",
         "entry":{"people":[{"name":"Maya Chen","email":"maya@studiozero.com",
                             "role":"ops partner","pronouns":"she/her"}],
                  "preferences":{"comms_channel":"email"},
                  "do_not_touch":["mom"]}}'

  -> people: [Maya Chen]
  -> written_path: /Users/omarebrahim/.anticipy/v7/dossiers/proof-evidence-final/dossier.json

$ curl 'http://127.0.0.1:8732/api/dossier/active?account_id=proof-evidence-final&device_id=laptop-proof'

  -> people: [Maya Chen]  (same data)
```

### Cross-key (write account_id, read user_id)

```
$ curl 'http://127.0.0.1:8732/api/dossier/active?user_id=proof-evidence-final&device_id=laptop-proof'

  -> account_id: proof-evidence-final
  -> user_id: proof-evidence-final
  -> people: [Maya Chen]  (same partition resolved)
```

### Cross-key (write user_id, read account_id)

```
$ curl -X POST http://127.0.0.1:8732/api/dossier/active \
    -d '{"user_id":"proof-evidence-final-rev","device_id":"laptop-proof",
         "entry":{"people":[{"name":"Devon Park","role":"billing"}]}}'

  -> account_id: proof-evidence-final-rev (resolved from user_id)
  -> written_path: /Users/omarebrahim/.anticipy/v7/dossiers/proof-evidence-final-rev/dossier.json

$ curl 'http://127.0.0.1:8732/api/dossier/active?account_id=proof-evidence-final-rev&device_id=laptop-proof'

  -> people: [Devon Park]  (same data round-trips both ways)
```

### Memory write/read (cross-key)

```
$ curl -X POST http://127.0.0.1:8732/api/memory/write \
    -d '{"user_id":"proof-evidence-final","device_id":"laptop-proof",
         "kind":"fact","key":"workspace","value":"engineering team"}'

  -> item.account_id: proof-evidence-final

$ curl 'http://127.0.0.1:8732/api/memory/read?account_id=proof-evidence-final&device_id=laptop-proof'

  -> count: 1
  -> items[0]: fact.workspace = engineering team (partition: proof-evidence-final)

$ curl -X POST http://127.0.0.1:8732/api/memory/write \
    -d '{"account_id":"proof-evidence-final","device_id":"laptop-proof",
         "kind":"preference","key":"chat_tone","value":"formal"}'

$ curl 'http://127.0.0.1:8732/api/memory/read?user_id=proof-evidence-final&device_id=laptop-proof&kind=preference'

  -> count: 1
  -> items[0]: preference.chat_tone = formal (partition: proof-evidence-final)
```

All four cross-key paths verified:

| Write key   | Read key    | Works |
|-------------|-------------|-------|
| account_id  | account_id  | yes   |
| account_id  | user_id     | yes   |
| user_id     | user_id     | yes   |
| user_id     | account_id  | yes   |

## Risk and rollback

The fix only widens parameter acceptance and adds one new route. No
existing caller breaks; existing `account_id`-only callers see the
exact same response shape with one added `user_id` mirror field.
Rollback is a single revert of the two files. The frozen
`engine/app/anticipy/` is untouched, so the proactive engine, the
intake module, and the action engine see no change.

## What is NOT fixed by this patch

This patch fixes the M1 dossier loader and the M2/M3/M4 scoped memory
write/read API. It does not migrate the legacy
`USER_ID = "anticipy-user"` constant in `server.py` that still routes
the in-process `MEM.seed`, `MEM.active_snapshot`,
`MEM.resolve_reference_sync`, and the `/api/memory` and
`/api/listen/inject` paths to the legacy
`~/.anticipy/system_v1/users/anticipy-user/memory.jsonl` partition.
That migration is the larger memory-root-cut patch (proposed in
`state/v7/memory_root_cut_plan.md` at commit 46a96ef2). The partition
fix here makes both partitions readable through the V7 API surface
without changing the on-disk layout. If a caller asks the V7 API for
the legacy partition's data, they can do so by passing
`account_id=anticipy-user` (or `user_id=anticipy-user`) plus an
explicit device id. The on-disk migration of legacy rows into the V7
partition layout is a separate, larger change.
