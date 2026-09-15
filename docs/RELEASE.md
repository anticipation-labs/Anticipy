# Release runbook

One ordered path for one release. Every step names the instrument that proves
it; a green workflow tick proves only that the workflow ran.

## 0. Before anything

- Branch `cloudflare-backend`, up to date. `main` is never pushed to.
- Every suite green offline ([TESTING.md](TESTING.md)).
- `git status --short` shows only your paths. Stage by name; commit with
  `git commit -- <paths>` ([CONTRIBUTING.md](../CONTRIBUTING.md)).

## 1. Extension package

If anything under `extension/` changed:

1. Move the version in lockstep: `version` in `extension/manifest.json`,
   `ENGINE_BUILD` in `extension/background.js`, `expectedExtensionVersion`
   in `app/ios/Anticipy/AnticipyApp.swift`, and `expected` in
   `app/ios/Tests/StaleExtensionTests.swift`.
2. `sh extension/build-zip.sh` — derives the package from the manifest's
   entry points, normalises timestamps so identical source gives an identical
   SHA-256, writes
   `migration/workers/public/anticipy-claude-version-extension.zip`, and
   copies the same bytes to `anticipy-extension.zip` and
   `anticipy-codex-version-extension.zip`. All three aliases are committed;
   rename none of them.
3. `python3 proof/audit/check_extension_package.py` — prints the shared hash.
   Keep it; step 5 compares the live download against it.

A new ZIP does not update an already-installed unpacked extension
([extension/README.md](../extension/README.md)).

## 2. Pull request into `cloudflare-backend`

Open the PR with the template. CI on a PR: `system-invariants.yml` (the
Python, extension, Worker, brain Worker and Mac suites plus an unsigned Mac
build, for the paths it watches) and `ios-candidate.yml` (the iOS logic gate
plus a simulator compile, for `app/ios/**`). Do not put `[ship]` in the PR
title unless a TestFlight upload is intended: a squash-merge takes its commit
subject from the title.

## 3. Merge

A merge publishes nothing by itself. The API, the extension downloads, the
brain, and the apps each change only through the steps below.

## 4. API deploy

Dispatch `brain-deploy.yml` with `component=api` and `confirm=DEPLOY` on
`cloudflare-backend`. The `api` job, in order:

1. `npm ci && npm test && npm run typecheck` in `migration/workers`;
2. `python ../../proof/audit/check_extension_package.py`;
3. the two rerunnable `CREATE ... IF NOT EXISTS` migrations, applied by file;
4. `python3 -m proof.audit.d1_additive <migration> --apply` for each
   column-adding migration (applies only what is missing, verifies after);
5. `python3 -m proof.audit.d1_connector_readiness` — refuses the deploy if
   the deployed database cannot carry it;
6. `wrangler deploy --config wrangler.jsonc --keep-vars --tag "$GITHUB_SHA"`;
7. `python proof/audit/live_api_release.py --base https://api.anticipy.ai --verify-deployment`,
   which creates and removes only its own phone-less probe accounts.

Migrations run **before** the Worker on purpose; the comment block in the
workflow records the failure that ordering prevents.

## 5. Live verification (never the workflow exit code alone)

```sh
curl -sI https://api.anticipy.ai/api/health | grep -i x-anticipy-revision
```

The header carries the deploy tag, which is the commit SHA the job deployed
(`migration/workers/src/index.ts` sets it from the Worker's version
metadata). It must be the SHA you merged. Then the download:

```sh
curl -s https://api.anticipy.ai/anticipy-extension.zip | shasum -a 256
curl -s https://api.anticipy.ai/anticipy-claude-version-extension.zip | shasum -a 256
curl -s https://api.anticipy.ai/anticipy-codex-version-extension.zip | shasum -a 256
```

All three must equal the hash from step 1. `python3 overnight/is_it_live.py`
makes the same source-against-live comparison; it reads a root `.env.local`
if one exists, so read [TESTING.md](TESTING.md) first.

## 6. Brain deploy

Dispatch `brain-deploy.yml` with `component=brain`, `confirm=DEPLOY`, and
`cap` set to the **existing** fleet capacity (the input defaults to `1`). The
`deploy` job runs the brain Worker's tests and typecheck, then its own
preflight — `python3 -m proof.audit.brain_deploy_preflight`: complete eligible
fleet, current snapshot metadata, no active effects; a point-in-time
observation, not a drain lock, and never satisfied by cancelling jobs — then
`wrangler deploy --config migration/config/wrangler.brain.jsonc` with
`--containers-rollout immediate`, then
`python3 -m proof.audit.live_brain_release`. The rollout is immediate and may
restart active owner processes; do not describe it as gradual, and do not
dispatch it as a "check".

## 7. iOS

1. The build number moved with the source (rule below), and
   `sh app/ios/Tests/run_all.sh` is green including its last leg.
2. Upload is asked for, never automatic: dispatch `ios-testflight.yml` by
   hand, or land a commit whose **subject** contains the literal `[ship]`.
   A plain push to `cloudflare-backend` builds, runs the gate, and uploads
   nothing; the workflow's final step says which of the two happened. Space
   uploads apart; Apple throttles bursts on a rolling window.
3. Read back from App Store Connect, not from the tick: `asc-query.yml` with
   `build=<N>` and `confirm` blank is read-only and prints processing state,
   who can install, and the complete existing audience.
4. Assign the build to the existing testers: `asc-query.yml` with
   `build=<N>`, `confirm=ASSIGN_EXISTING`, `email` blank. No invitation is
   created. `INVITE` / `INVITE_EXTERNAL` with an `email` enroll a tester and
   are a separate decision; external groups need Beta App Review first.
5. A tester confirming installation of build N is the evidence. "VALID" is
   Apple's verdict on the bytes only.

## 8. Mac

`mac-release.yml` is dispatch-only with `confirm=RELEASE`. It runs
`sh app/macos/Tests/run_all.sh`, builds universal, signs with the Developer ID
identity held as repository secrets — or notarizes a reviewed, locally signed
archive supplied as a draft-release asset (`signed_candidate_tag` plus
`signed_candidate_sha256`) — notarizes, staples, and opens a PR that commits
`migration/workers/public/mac/Anticipy-for-Mac.zip`. Merging that PR and
running step 4 again is what changes the public download; hash it afterwards
the same way as in step 5.

## Rollback

Three different things, three different answers:

- **API code and static assets** (including the extension ZIPs): revert the
  source on `cloudflare-backend` (a path-limited revert commit, PR, merge) and
  run step 4 again. The deploy is tagged with the commit SHA, so step 5 tells
  you which source is live. No rollback step exists in this repository's
  workflows; the reverted source goes through the same job.
- **D1**: migrations are additive only (`proof/audit/d1_additive.py` refuses
  anything else) and are applied before the Worker on every run. A rolled-back
  Worker runs against a database that still has the newer columns, which is
  safe by construction. There is no down-migration; do not write one by hand
  against production.
- **Brain**: run step 6 from the reverted commit with the same `cap`. The
  preflight refuses a capacity change; the rollout is immediate.

## The iOS build-number rule

`CURRENT_PROJECT_VERSION` lives in **two files** and must move together, in
the **same commit** as the iOS or Mac source it describes:

- `app/ios/project.yml` — every `CURRENT_PROJECT_VERSION:` line (the app's
  settings and the Mac target's);
- `app/ios/Anticipy.xcodeproj/project.pbxproj` — all **four**
  `CURRENT_PROJECT_VERSION =` lines.

Edit both by hand; the committed `pbxproj` is what CI builds. The last leg of
`sh app/ios/Tests/run_all.sh` compares the working tree against the commit
where the number last changed, and `ios-testflight.yml` checks out full
history for the same reason. App Store Connect refuses a reused number, but
only at upload, days after the tree it should have described. Read the
current number from `app/ios/project.yml`; do not copy one from a document.
