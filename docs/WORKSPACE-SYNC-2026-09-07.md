# Workspace sync — 7 September 2026

The main checkout at `/Users/omarebrahim/Anticipy` was fast-forwarded from
`5e5b3a7b` to GitHub's `cloudflare-backend` at
`776cbab5d92379fd2d31dea0db6425a9e3d489b8`. This includes the team's merge of
Mac PR #59. The Mac source now targets `https://api.anticipy.ai`.
No product source was authored by this sync. This note's commit follows that
source revision. Use the branch, not the unrelated default `main`.

## The running development environment

- The local API now runs **current source** from `migration/workers`, using
  `./work/mac-dev/start-worker.sh` and `work/mac-dev/wrangler.json`.
- API: `http://127.0.0.1:8787`; inspector: `127.0.0.1:9239`.
- D1/R2/DO state: `work/mac-dev/state`. Bindings are explicitly local, with
  development-only auth values and no provider credentials.
- The missing `connection_command_runs` table, index and two erasure triggers
  were installed using the committed `2026-09-07-connection-command-runs.sql`
  migration with `--local`. The prior local schema had no other missing tables
  or columns relative to `migration/d1/schema.sql`.
- A backup made before that migration is at
  `work/mac-dev/backups/sync-20260907-114450/development-state`.

The old audit API on port 8787, disposable UI brain and metered model gateway
on port 8790 were stopped after checking their process identities. No brain or
paid model process was started by this sync. The API alone does not generate
assistant replies; a separately configured synthetic brain is required for
that kind of test.

The frozen `/private/tmp/anticipy-overnight-998fca6` worktree and its state under
`migration/workers/.wrangler/state` remain available as audit evidence. They
are not the normal development server. Existing `output/playwright/` and
`proof/audit/live_stall_notice.py` untracked work was preserved.

## Verification

- Before the fast-forward: `sh app/ios/Tests/run_all.sh` passed. Log:
  `work/audit/sync-baseline-ios.log`.
- After the fast-forward: Mac `run_all.sh` passed; 118 Python tests in
  `test_ears_hear_the_mac.py` and `test_stranger_gate.py` passed. Logs:
  `work/audit/sync-macos-tests.log`, `work/audit/sync-mac-python-tests.log`.
- The post-sync iOS build-number check passed at 165. The merge changes Mac
  sources and project references, not iOS app source.
- Local `/api/health` returned HTTP 200. The connection retry table is present
  and SQLite `quick_check` returned `ok`: `work/audit/sync-local-schema.log`.
- The running Wrangler process's working directory and config were checked
  against the current checkout. Runtime log: `work/mac-dev/sync-worker.log`.

## Team coordination and remaining integration

PR #61 (`retire-pocketbase`) is now based on `cloudflare-backend`, but GitHub
reports it OPEN and CONFLICTING. It was not merged by this sync. Its migration
must be reconciled with current repairs in a separate integration checkout.
The earlier repository audit's statement that PR #59 was unmerged is now
historical; the audit was captured before the team's 18:32 UTC merge.

Use one process owner per local port and separate database/memory directories
for concurrent runs. Do not aim laptop brains at production owner memory.
Check the shared index before any commit and stage/commit exact paths.
The prepared launcher already owns port 8787; reuse it instead of starting a
second server. Stop it deliberately before changing its checkout.

No production data, secrets, deployments or TestFlight distribution changed in
this sync. Source synchronization does not prove installation of the Mac app
or completion of the remaining product repairs.
