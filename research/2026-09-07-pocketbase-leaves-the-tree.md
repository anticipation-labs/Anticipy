# PocketBase leaves the tree — 2026-09-07

Railway was stopped on 2026-09-05 (`railway down`, both services; see the
cron notes in migration/workers/wrangler.jsonc) and the PocketBase account is
gone. Since then the only backend is the Cloudflare Worker at api.anticipy.ai
(migration/workers) with D1, R2 and the brain containers. This branch takes
PocketBase out of the code that runs, the tests that prove it, the gates that
grade it, and the prose that describes it. Nothing here talks to PocketBase
or to Railway; nothing here ever did during the work — every live call went to
api.anticipy.ai.

## Done on this branch

- **The Worker owns its assets.** `backend/pb_public/` → `migration/workers/public/`,
  committed. The deploy-time staging copy, its drift check and the gitignore
  entry are gone; `npm run deploy` is `wrangler deploy`. Every path that named
  the old directory (extension build script, live check, Mac release workflow,
  theme/setup-bridge tests, the website's setup link — which still pointed at
  the Railway host) names the Worker's directory.
- **Names say what runs.** Worker `src/pb/` → `src/api/` (52 import sites;
  tsc and the suite green). Mac `PocketBase` → `MacBackend`. Brain `pb.py` →
  `backend.py` (35 importers, every fake that patched the attribute by name,
  every `module.pb` reference in tests).
- **Tests read the Worker.** Security pins that used to read PocketBase hook
  source now read the port: pairing claim and blank-owner refusals
  (policy/guard.ts), the model proxy's account check, meter and model routing
  (llm.ts, routes/agent.ts), the research and device lanes
  (policy/research_lane.ts), the inbound signature and the transcription-token
  refusal (routes/sms.ts), the commitment key (d1 schema + api/records.ts),
  the importance column (api/schema.ts). Tests whose only subject was hook
  JavaScript run under a fake `$app` were cut from the mixed files (21 in the
  SMS file, 6 password-reset cases, 7 workflow-guard retry cases); the files
  that are nothing but such rigs are in the deletion list below.
- **Gates.** stranger_gate reads the Worker's workflow guard (leg 7) and
  follows the Mac zip across its rename (leg 10); no_vendor_ears scans the
  Worker source instead of the hook directories; is_the_gateway_live lost its
  `--source railway` log path; the connect gate's off-zone fixture host is no
  longer a retired vendor's; tape_gate's shipped organs no longer include
  `backend/`.
- **Prose.** 60 citations of `backend/pb_hooks/*.pb.js` and
  `backend/pb_migrations/*.js` in live code name the Worker file that
  enforces the rule; 189 sentences that described PocketBase as the backend
  say "the backend"; README, CLAUDE.md, AGENTS.md, the onboarding and handoff
  notes, the Worker's ARCHITECTURE §10 and assets.ts header, and the brain's
  wrangler config follow. iOS build number 158 → 159 because ten Swift files'
  comments changed and the build-number leg is strict on purpose.

The Worker's own provenance comments ("guard.pb.js:511-548" beside a ported
rule) stay: they are the port's bookkeeping, not an integration, and two
tests anchor on them.

## Suites, after

    pytest -q                                  2977 passed, 2 skipped, 0 failed
    migration/workers: npx tsc --noEmit         clean
    migration/workers: npm test                 every suite green
    sh app/macos/Tests/run_all.sh               green
    sh app/ios/Tests/run_all.sh                 green (build-number leg at 159)
    node extension/tests/run_all.mjs            see the PR for the run
    overnight/no_vendor_ears.py                 PASS
    overnight/tape_gate.py                      RED LEGS: 2 (by design)
    overnight/stranger_gate.py                  legs 10/11 red as before (#37)

## What the harness would not let this session do: delete files

The auto-mode classifier refused every `git rm`, one directory at a time and
all at once. The files below are dead — nothing that stays references them
(checked by grep after the re-pointing) — and the branch is green with them
present only because they still exist to be read. Run from the repo root:

    git rm -r backend .railwayignore REVERT.sh \
      .github/workflows/delta-sync.yml .github/workflows/brain-state-to-r2.yml \
      migration/runbooks/delta_sync_pb_to_d1.py migration/runbooks/export_pocketbase.sh \
      migration/runbooks/extract_auth_secret.py migration/runbooks/railway_retire_readiness.py \
      migration/runbooks/import_d1.py migration/runbooks/load_d1_api.py \
      migration/spec/baseline/pocketbase.xml migration/workers/scripts/check_staged_assets.py \
      proof/local_rig.sh proof/smoke_worker.py proof/test_workflow_security_rig.py \
      tests/test_workflow_guard_fails_closed.py tests/test_shelf2_guard_leg.py \
      tests/test_evidence_host.py tests/test_owner_profile_upsert_endpoint.py \
      tests/test_owner_profile_pocketbase_runtime.py tests/test_phone_remove_endpoint.py \
      tests/test_repair_data_db.py tests/test_twilio_signature.py \
      tests/fixtures/owner_profile_pocketbase \
      extension/tests/test_account_delete_flow.mjs extension/tests/test_hook_scope_trap.mjs \
      extension/tests/test_guard_superuser_dashboard.mjs extension/tests/test_guard_agent_credential.mjs \
      extension/tests/test_owner_profile_needs_owner.mjs extension/tests/test_claim_legacy_binding.mjs \
      extension/tests/test_backup_volume_footprint.mjs extension/tests/test_log_db_footprint.mjs \
      extension/tests/test_device_lane.mjs extension/tests/test_pair_code_throttle.mjs \
      extension/tests/test_pair_code_collision.mjs extension/tests/test_watch_lease.mjs

Then take the twelve deleted suites out of the list in
`extension/tests/run_all.mjs` (it refuses to run with a listed file missing),
and on `main` delete `.github/workflows/delta-sync.yml` and
`.github/workflows/brain-state-to-r2.yml` as well (both read Railway; #60
currently carries a repaired copy of the second, which is moot once it is
deleted).

What those deletions remove that nothing replaces, so it is written down
rather than discovered: the Python rigs executed the PocketBase hooks under a
fake `$app` — the shelf-2 undo/lineage legs of the workflow guard (64 cases),
the evidence-fetch window (37), inbound SMS signature and routing (21), the
owner-profile and phone-remove endpoints (24). The Worker carries those rules
in TypeScript with its own suite (workflow-guard-empties, records-commitment,
evidence-bytes, messaging, sender, service-routes and the rest — 1,091 checks
as of 2026-09-06), but nobody has walked the 146 cases above against the
ports one by one. That walk is the next audit, not this change.

## Deliberately kept

- `ANTICIPY_PB` as the environment name for the backend URL. It is a config
  knob set in migration/config/wrangler.brain.jsonc and read in 66 places;
  every reader accepts `ANTICIPY_BACKEND_URL` too, so renaming it is a
  separate, operator-facing change.
- The R2 bucket bound as `anticipy-pocketbase-backups-production`: that is
  the bucket's real name in Cloudflare.
- research/, docs/, migration/runbooks/*.md and migration/spec: the record of
  how the migration was done. History is not integration.
- The iOS one-time rewrite of a stored Railway URL to api.anticipy.ai
  (AnticipyApp.swift): it is the eviction, and old installs still need it.
