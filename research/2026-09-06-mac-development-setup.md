# Mac development setup — 2026-09-06

Scope: import and understand the iOS/Cloudflare branch, prepare the Mac, and
record an honest local baseline. No feature implementation or deployment.

Source baseline: `anticipation-labs/Anticipy`, `cloudflare-backend`, commit
`d93682f80b14c40d5d4ba445ea6333e4a5a58e33`. Fresh, non-shallow partial clone at
`/Users/omarebrahim/Anticipy`; all 2,516 tracked baseline files checked out and
inventoried. Older blobs remain available on demand. Governing files were read
before changes, and `sh app/ios/Tests/run_all.sh` was started against the
untouched source before environment work. No iOS or Worker production source
was changed during setup.

## Measured results

| Check | Result |
|---|---|
| Required iOS gate | Exit 0; all 63 registered legs reached; build 158 still identifies the source |
| iOS simulator build | Exit 0, `BUILD SUCCEEDED`; direct build of committed project, signing disabled |
| Simulator launch | iPhone 17 Pro / iOS 26.5; signed-out onboarding visually inspected |
| Source and binary version | 1.1.1 / 158 |
| Worker dependency install | `npm ci` succeeded from committed lockfile; Wrangler 4.129.0 |
| Worker unit suites | `npm test` exit 0; all 30 chained test files reached |
| Worker TypeScript | `npm run typecheck` exit 0 |
| Worker runtime wire test | Exit 0; 22 passed, 306 deselected; real local workerd with a fake provider |
| Browser extension | Exit 0; all 94 registered offline suites passed |
| Python initial run | 2,958 passed, 4 skipped, 1 pre-existing escape-sequence warning; exit 0 |
| Python local D1 follow-up | Both skipped D1 tests passed after resolving root-level Wrangler discovery; 2 passed / 125 deselected |
| Remaining Python omissions | Two explicitly opt-in live-model hand-router probes; not attempted |
| Local Worker | `/api/health` HTTP 200 at `127.0.0.1:8787`; dedicated local schema initialized |
| Staged assets | Four ZIPs byte-identical to `backend/pb_public/`; extension ZIPs report 0.15.0 |
| Tape gate | Exit 1: expected legacy tape only; every other ledger/census/closure leg passed |

The wire suite reports two pytest fixture deprecation warnings. Together with
the initial Python escape-sequence warning, these are recorded warnings, not
silently treated as failed or skipped checks. Local setup added no test bypass.

## App Store Connect was queried, not inferred

Dispatched only `asc-query.yml`, with `build=158`, all invitation inputs blank.
Run [34075480216](https://github.com/anticipation-labs/Anticipy/actions/runs/34075480216),
at the baseline SHA, reported at 2026-09-07 02:12 UTC:

- Build 158: `processingState=VALID`, `expired=False`.
- Internal tester state: `IN_BETA_TESTING`.
- Apple's recent-build list also contains build 159, `VALID`.

This does not make source build 158 into 159 or establish who can install 159.
The release workflow can choose a higher upload number when Apple already holds
the source number. No upload, tester invitation, or production mutation was
performed by this setup.

## What changed on the Mac

Python 3.11.12 virtual environment and CI test dependencies, Node 24.20.0 under
the existing NVM directory, the locked Worker dependency tree, and a local
`node_modules` symlink for repo-root Wrangler consumers. Global shell/npm
configuration was preserved despite its mixed Node/npm paths and NVM prefix
conflict. The project-specific environment handles that mismatch.

Created ignored `work/mac-dev/` configuration, launchers, and local storage;
created the dedicated Anticipy Development simulator and an ignored Anticipy
Local user scheme; opened Xcode and Simulator. Local Worker configuration has
no real provider keys, routes, cron schedule, or remote bindings. It uses its
own database identity and development-only auth values. The simulator launch
uses the app's existing backendURL override.

Git has local fast-forward-only pulls. Generated Wrangler directories, staged
assets, and the local dependency symlink are excluded through `.git/info/exclude`.
Old archives and the credential vault were left in their existing locations;
the ongoing archive transfer was not interrupted.

## Findings to carry forward

1. **CI's non-ship summary overstates what ran.** In the current
   `.github/workflows/ios-testflight.yml`, the logic gate and XcodeGen run on a
   qualifying ordinary push, but archive/export `xcodebuild` commands require
   `ship=yes`. There is no separate non-ship simulator build step. Its final
   “Built and tested only” line is not compile evidence. No workflow was changed
   during this environment task.
2. **Documentation has multiple historical topologies.** The root README's old
   PocketBase quick start was replaced by the current Mac guide. Older intake,
   iOS README, and cutover notes still contain obsolete branch names, generator
   advice, version numbers, and laptop release steps. The current source,
   governing rules, explicit owner instruction, and dated measurement take
   precedence over those old operational examples.
3. **Five registered Law-1 exceptions remain.** The tape gate names the
   read-only regex, compute fallback, thin-shard threshold, third-person drop,
   and anaphoric link heuristic. These are pre-existing, not setup failures.
   Replace them through senses → context → examples → model tier → structural
   effect-channel checks; do not extend or quiet their expiry gate.
4. **Local readiness is bounded.** No real speech capture, pendant flash,
   background-device soak, provider connection, browser action, or live
   model-backed conversation was established. The local Worker has test auth
   values and empty development data; no production brain was started here.
5. **Hardware tooling is separate.** This task prepared iOS and the API Worker.
   It did not install a full Zephyr/pendant toolchain or prove a firmware build.

## Evidence locations

All raw logs are local, under
`/Users/omarebrahim/Library/Logs/Anticipy/setup-2026-09-06/`:
`ios-gate.log`, `ios-build.log`, `python-tests.log`, `d1-tests.log`,
`worker-install.log`, `worker-tests.log`, `extension-tests.log`,
`worker-wire-tests.log`, `local-schema.log`, `local-worker.log`, `tape-gate.log`,
`asc-build-158.log`, and `simulator.png`. `tracked-files.txt` is the full original
tracked-file inventory. Raw ASC output stays outside Git because it includes
tester details. The usable commands and file map are in
[the Mac guide](../docs/LOCAL-DEVELOPMENT-MAC.md).
