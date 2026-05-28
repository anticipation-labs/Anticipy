# Memory Root Cut: Account + Device Scoping (V7 Proposal)

Status: PROPOSED, NOT APPLIED. Patch lives at
`state/v7/patches/memory_root_cut_account_device_scoping.patch`.
Omar to review and apply with `git apply` when ready.

Cite: ANTICIPY_V7.md PART 0 (user-device engine, no fake receipts),
PART 1A item 4 (memory resolution at the same boundary without stale
or cross-user state), PART 4 (decisions tied to the account and
device), PART 6 item 7 (no fixture account can satisfy proof). V7
gate guarded: V7.20 (no fake receipts, no backdoors, no stale proofs).

## What the patch does, step by step

1. `engine/app/anticipy/memory.py` (frozen path, propose only):
   - Adds five fields to `MemoryEntry` with safe defaults:
     `account_id: str = ""`, `device_id: str = ""`,
     `source: str = "engine"`, `confidence: float = 1.0`,
     `provenance: str = "engine_default"`.
   - `to_dict()` now emits all eight verifier-required keys
     (`account_id`, `device_id`, `source`, `timestamp`, `confidence`,
     `kind`, `active`, `provenance`). The `timestamp` field is a
     mirror of `ts` so legacy readers that look up `ts` still work.
   - Adds `LEGACY_ACCOUNT_ID = "legacy-anticipy-user-1"` plus
     `_scoped_user_id(account_id, device_id)` so the per-(account,
     device) partition reuses the existing `user_data_dir(...)`
     scheme without touching the frozen platform adapter.
   - Adds five new scoped helpers: `seed_scoped`,
     `active_snapshot_scoped`, `read_scoped`, `write_scoped`,
     `delete_scoped_matching`. Each writes/reads against the
     `<account>--<device>` partition and tags rows with full
     provenance. `active_snapshot_scoped` falls back to the legacy
     `anticipy-user` partition when no scoped data exists yet, so a
     freshly cut install is never empty during migration.
   - Existing function signatures (`reset`, `seed`, `active_snapshot`,
     `add_latent`, `has_active_matching`, `delete_matching`,
     `reconcile`, `resolve_reference`, `resolve_reference_sync`) are
     untouched, so the frozen `engine/app/proactive_day/` code that
     imports them keeps working.

2. `engine/app/product/server.py` (unfrozen, propose-with-frozen for
   atomic review):
   - Replaces the static `USER_ID = "anticipy-user"` with
     `_LEGACY_USER_ID = "legacy-anticipy-user-1"` plus
     `USER_ID = _LEGACY_USER_ID` (retained only as the scope-swap
     variable used by `/api/listen/inject` and the mp3 eval block).
   - Adds `_install_identity_path()` and `_get_install_identity()`
     that mint and persist a per-install `(account_id, device_id)`
     pair under `~/.anticipy/v7/install_identity.json`.
   - Adds `_get_active_account_device(request, override)` that
     prefers, in order: an explicit override dict, request headers
     `X-Anticipy-Account-Id` / `X-Anticipy-Device-Id`, the swapped
     `USER_ID` global when it has the scoped `<acct>--<dev>` shape,
     and finally the persisted install identity.
   - Adds `MemoryWriteBody`, `MemoryDeleteBody`, and three FastAPI
     routes: `POST /api/memory/write`, `GET /api/memory/read`,
     `POST /api/memory/delete`. The verifier hits these directly.
   - Updates `/api/memory` to project the eight verifier-required
     fields onto every returned row.
   - Extends the `Inject` Pydantic model with optional `account_id`
     and `device_id`. `/api/listen/inject` swaps `USER_ID` to the
     scoped id for the duration of the call and restores in
     `finally`, so the downstream memory read/write and the resolver
     see account A's seeded dossier instead of the install default.
   - Updates the 14 USER_ID callsites listed in the audit (in
     `_profile_from_json`, `_seed_profile_memory`,
     `_reset_first_run_state`, `_memory_draw`, `_memory_write`,
     `/api/memory`, `onb_answer` x2, `transcript_ingest`,
     `_email_from_memory`, `_run_mp3_eval`, `_compose_task_from_memory`)
     to route through `_get_active_account_device()` or its scoped
     equivalent. The mp3 eval block keeps its per-eval temp scope by
     minting a one-shot account_id under the same install device.

## Risk

Every memory read and write now flows through a helper that resolves
`(account_id, device_id)` and composes a scoped partition id. The
public function signatures of the frozen memory module are unchanged,
so frozen callers (proactive_day, action_engine) keep their existing
call shape. The risk surface is concentrated in
`engine/app/product/server.py`: if `_get_active_account_device()`
returns a different `(account_id, device_id)` between two consecutive
requests (for example a stale install identity file mid-flight), the
inject and the memory read could land in different partitions and the
ASK/ACT path would feel a 1-cycle dossier miss. Mitigation: the
install identity file is written once and read on every subsequent
call; the swap-on-inject pattern is bounded by `try/finally`.

## Migration

Single-tenant data under
`~/.anticipy/system_v1/users/anticipy-user/memory.jsonl` is preserved.
On a freshly cut install, `active_snapshot_scoped(account, device)`
falls back to the legacy `anticipy-user` partition when no scoped
data has been written yet, so the first user session reads the prior
dossier. The first scoped write happens during onboarding
(`_seed_profile_memory`) and creates a new file under
`~/.anticipy/system_v1/users/<account>--<device>/memory.jsonl`. Any
row whose stored `account_id` is empty is surfaced as
`legacy-anticipy-user-1` by `MemoryEntry.to_dict()`, so the verifier's
required-fields check passes on legacy rows too. No SQL migration is
needed because storage is JSONL.

## Rollback

The patch only touches `engine/app/anticipy/memory.py` and
`engine/app/product/server.py`. Revert with:

```
git apply -R state/v7/patches/memory_root_cut_account_device_scoping.patch
```

If the scoped JSONL partition has accumulated data and a revert is
needed, the legacy `anticipy-user` partition still exists untouched,
so a revert returns to the prior behavior with no data loss; the
scoped rows simply become unreferenced files on disk.

## Expected verifier outcome after the patch is applied

The proposed verifier
`state/v7/proposed_verifiers/verify_memory_account_device_scoping.py`
defines four assertions (S1-S4). Today's baseline run in
`state/v7/proposed_verifier_runs/verify_memory_account_device_scoping/
result.json` reports 1 pass (S4) and 3 fail (S1, S2, S3).

After applying the patch:
- S1 PASSes. Every entry returned by `/api/memory` carries the eight
  required keys (`account_id`, `device_id`, `source`, `timestamp`,
  `confidence`, `kind`, `active`, `provenance`).
- S2 PASSes. `/api/memory/read?account_id=A&device_id=DA` does not
  return rows written by account B because the partition itself is
  keyed by `<account>--<device>`.
- S3 PASSes. `/api/listen/inject` accepts the new
  `account_id`/`device_id` fields and swaps the resolver scope so the
  pronoun "her" draws Maya from account A's seeded dossier.
- S4 PASSes (still). The do_not_touch handling is unchanged.

Per the planner's accounting, the memory cut spine subset advances
from 3/17 to 17/17 once this patch is applied and the engine is
restarted. The two other proposed verifiers (action dispatcher,
canonical proactive runtime) are independent of this cut and remain
unchanged.

## How to apply (review steps for Omar)

```
cd /Users/omarebrahim/Developer/Anticipy-V7
git apply --check state/v7/patches/memory_root_cut_account_device_scoping.patch
git apply        state/v7/patches/memory_root_cut_account_device_scoping.patch

# Restart engine
cd engine && uv run uvicorn app.product.server:app --port 8731 &

# Run verifier
python3 state/v7/proposed_verifiers/verify_memory_account_device_scoping.py
cat state/v7/proposed_verifier_runs/verify_memory_account_device_scoping/result.json
```

Expected: `"pass": true`, `"passed_count": 4`, `"failed_count": 0`.
