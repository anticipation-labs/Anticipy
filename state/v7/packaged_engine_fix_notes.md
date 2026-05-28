# Packaged Engine Fix: dossier_store ImportError

Date: 2026-05-27
Author: claude code worker (V7 worktree)

## Root cause

`engine/app/product/server.py` had two legacy endpoints, `/api/dossier/write`
and `/api/dossier` (read), that lazy-imported `app.anticipy.dossier_store`
at request-time. The `engine/app/anticipy` package is frozen and does not
export `dossier_store`; its `__init__.py` declares `__all__ = []`.

Symptom in the packaged engine:

```
ImportError: cannot import name 'dossier_store' from 'app.anticipy'
```

The dev uvicorn engine never crashes at startup because the import is
deferred inside the function body, but any caller hitting either
endpoint trips a 500 (same shape on dev and packaged).

The M1 dossier loader (`/api/dossier/active`, `/api/dossier/refresh`,
`/api/dossier/context`) is the supported replacement. Those routes are
already attached via `app/product/dossier_router_wire.py`.

## Fix chosen: Option C

Wrap the lazy import in `try`/`except ImportError` and return HTTP 410
Gone with a JSON body that names the replacement routes. Frozen path
`engine/app/anticipy/` is untouched. Only the unfrozen
`engine/app/product/server.py` was edited.

## Diff summary

Two locations, both inside `api_dossier_write` and `api_dossier_read`,
gain a `try: from app.anticipy import dossier_store` block. On
`ImportError`, the endpoint returns:

```json
{
  "ok": false,
  "error": "legacy_endpoint_retired",
  "reason": "/api/dossier was superseded by the M1 dossier loader. ...",
  "replacement": "/api/dossier/active"
}
```

with status 410.

## Verification path

After rebuild + reinstall + relaunch via `/Applications/Anticipy.app`,
`curl http://127.0.0.1:8731/api/dossier?user_id=test` should return
410 with the JSON shape above, not a 500. V7.3 gate
(`installed_user_device_engine_current`) checks for a live engine on
8731 served from the installed binary; it does not require the legacy
endpoint to function.

## Ship outcome 2026-05-27

- Fix commit: `ba8b19d v7: fix dossier_store import + reship packaged engine`
- Build manifest commit (created by `scripts/ship.sh`): `34d8c09 ship: update build manifest for ba8b19d`
- New DMG SHA-256: `d3b48063e6fa32d12c13943a5041a27b34284001e1a4cc0f717780ce1b2d5da2`
- DMG size: 2,515,615,248 bytes (about 2.34 GiB).
- R2 upload: succeeded (`s3://anticipy-downloads/Anticipy_1.0.0_aarch64.dmg`).
- Public DMG download (`https://www.anticipy.ai/dl/Anticipy_1.0.0_aarch64.dmg`) now returns the new SHA, so V7.5 (`public_dmg_sha_green`) flips green via the existing `non_dmg_manifest_commit_exception` path.

## Push to GitHub failed: pre-existing >2 GiB blob in history

`scripts/ship.sh` push step failed with:

```
error: RPC failed; HTTP 500 curl 22 The requested URL returned error: 500
send-pack: unexpected disconnect while reading sideband packet
fatal: the remote end hung up unexpectedly
Everything up-to-date
```

Root cause: two earlier supervisor commits accidentally checked in
mounted DMG copies under
`state/v7/clean_room_public_install_runs/`:

- Commit `2c315be` adds `cleanroom-20260527T151958Z/Anticipy.dmg` at
  1,734,406,144 bytes (1.62 GiB).
- Commit `cf5d369` updates that DMG to 2,515,616,076 bytes (2.34 GiB).

GitHub's hard per-file push limit is 2 GiB. Once the second DMG was
committed locally the entire push chain was unpushable, so my fix
commit `ba8b19d` is also stuck behind it. This is **independent of
this fix** and would have blocked the next ship even if no engine
change had been made.

Mitigation (outside this task's scope, requires explicit Omar
sign-off because it rewrites history):

1. `git-filter-repo --strip-blobs-bigger-than 100M` on a fresh clone,
   or
2. `git rebase --onto <main_tip> <bad_commit>^ HEAD` to drop the two
   supervisor checkpoint commits.

For now the autocommit loop in `tools/anticipy_supervisor.sh` keeps
trying to push every five minutes and keeps failing; the local
commit chain continues to extend. Engine on port 8731 is the
freshly-installed packaged binary (PID 69992 at install time) so
V7.3 is green.

## Gate state immediately after install

```
V7.3_installed_user_device_engine_current: true   (newly green)
V7.4_deploy_parity_green:                  false  (push blocked, see above)
V7.5_public_dmg_sha_green:                 true   (R2 upload landed)
V7.10_real_chrome_user_surface_no_clone:   false  (stale real_surface_proof.json from May 26, not engine-related)
```

