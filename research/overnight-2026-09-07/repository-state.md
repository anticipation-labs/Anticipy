# Anticipy cloud/local codebase audit - September 7, 2026

ANTICIPY / REPOSITORY AUDIT / 01

The code is split.
The local copy is current.

The main checkout exactly matches GitHub. The larger problem is unfinished integration between branches, inconsistent runtime configuration, and tests that do not always exercise the deployed path.



Measured September 7, 2026, 11:14-11:24 AM Vancouver. Product source snapshot: a4f4871a. Read-only comparisons; no feature branch was merged or reset.

| Place | What is actually there |
| --- | --- |
| This Mac + cloudflare-backend | Same commit: a4f4871a. Zero commits ahead or behind. No tracked local modifications. Two untracked audit outputs are preserved. |
| GitHub default: main | Different history; no iOS app, brain, or migration directory. An ordinary default-branch clone leads developers to the wrong product. |
| issue-37-mac-ears / PR #59 | 11 branch-only commits; 49 current-app commits absent. A merge preview into current app source has no textual conflicts. Still needs integration tests. |
| retire-pocketbase / PR #61 | Stacked on the Mac branch, not current app source. 21 branch-only commits; 49 current-app commits absent. Direct integration has 12 conflicting files. |
| jose_anticipy_system | Older migration branch: 2 branch-only commits, 357 current-app commits absent. It is not an interchangeable development baseline. |

Why GitHub can look fine while developers collide

PR #61 is clean against its selected older base. That does not mean it is clean against the app branch. It changes 404 files and removes about 26,800 lines, including renames of modules that current repairs still edit. GitHub also reports cloudflare-backend as unprotected; discipline alone currently coordinates direct writers.

These counts describe divergence, not missing files or proof that someone lost work. No evidence of local tracked-code corruption was found.

ANTICIPY / REPOSITORY AUDIT / 02

One product. Three kinds of state.

The phone captures input. Cloudflare stores the record and runs the brain. The brain uses memory to decide what to prepare, ask, or do through connected tools.



| State | Owner and location | Collision boundary |
| --- | --- | --- |
| App records | Cloudflare D1: users, events, jobs, profiles, pairing and workflow state. API code: migration/workers/src/. | This is the migrated record store. A /api/collections URL does not mean PocketBase is still serving it. |
| Brain memory | Per-owner memory.db + clock_state.json in the container; snapshots in R2 under owners/<owner_ref>/. | One production Durable Object/container per owner is intended to be the single writer. A second laptop worker using that same live identity is unsafe. |
| Local test state | Wrangler local D1/R2/DO files plus a separate memory.db for each synthetic run. | Every developer/run needs its own state directory, ports and test identities. Sharing a SQLite file or fixture owner can collide. |

Where the code lives

iOS: app/ios/  |  Mac recorder: app/macos/  |  Brain: brain/  |  Browser: extension/  |  API: migration/workers/src/  |  Container control: migration/workers/brain/  |  Schema: migration/d1/

PocketBase names are still in current source: brain/pb.py is an HTTP wrapper; backend/pb_hooks is legacy code; backend/pb_public still supplies live static assets. PR #61 moves/renames these. Deleting backend/ before integrating its asset move would remove source the current deployment still uses.

ANTICIPY / REPOSITORY AUDIT / 03

Where it is failing

These are observed defects and concrete risks. Healthy infrastructure does not prove that the assistant understands a conversation or completes a task correctly.



| Finding | Impact / evidence | Status |
| --- | --- | --- |
| Migration work is not integrated | Mac source targets retired Railway (health: 404). Public /download serves the old 1.0.0 DMG (2.52 GB). The capture repair exists in PR #59; PocketBase removal is in separate PR #61. | Open integration work |
| Local server is not the current checkout | At audit start, port 8787 runs frozen worktree 998fca6. Its state is migration/workers/.wrangler/state. The local guide instead describes current source and work/mac-dev/state. | Wrong source |
| Documentation gives conflicting instructions | The migration checklist still says the brain is undeployed and PocketBase is online on Railway. Live Cloudflare status now shows 8 running owners with current snapshots. | Docs stale |
| Configuration diverges outside Git | SendBlue inbound secret differed from the Worker. Brain outgoing replies returned HTTP 403. Secrets were aligned and the verified sender configured on API and brain; a real text question and draft then completed. | Targeted path verified |
| Meaning was decided by wording rules | Fluent volunteer planning was suppressed as machine dictation. Contextual classification replaced those overrides; 30/30 model contrasts and 12/12 local planning outcomes pass. | Deployed; ambient live task still unproven |
| Task quality and delay remain | Previous live private artifact took 82.84 seconds. A queue entry or model acknowledgement is not a completed task. Browser pairing on the personal installation remains unproven. | Open product work |
| Memory correctness is not availability | Current snapshots show persistence is running. They do not prove correct recall, no conflicting facts, or 20 days of reliable behavior. No current cross-owner corruption was demonstrated in this audit. | Further behavior proof needed |

The new brain release a4f4871a is live: 8/8 owners, running source matches, snapshots current, deployment workflow 34150343842 passed. iOS remains build 165 from commit 844c8a38. A backend deployment does not create a new phone build.

ANTICIPY / REPOSITORY AUDIT / 04

Clean it without losing anyone's work

Reconcile the team around one integration history and one development recipe. Preserve working branches and databases while doing it.



1. Freeze the comparison, not everyone's work.

Record current remote SHAs and each developer's branch. Use cloudflare-backend as the product base. Give each change its own checkout/worktree and commit exact file paths. Do not reset, force-push, or combine unrelated main history.

2. Fix the local runtime mismatch.

Stop only the audit-owned frozen server after confirming no tests are using it. Start the prepared current-source launcher with its own work/mac-dev/state. Keep the old state as evidence; do not delete or point another worker at production memory.

3. Integrate Mac capture first.

PR #59 has a conflict-free textual preview, but must be checked on a fresh integration worktree against the current iOS build, auth flow and live capture route. Preserve build 165 and increment correctly if iOS source changes.

4. Restack the PocketBase removal.

Rebase or reconstruct PR #61 on the tested integration result in a new branch. Resolve the 12 conflicts against current behavior, including the brain, messaging, API entry point and both version files. Preserve renames and recent repairs; do not choose an entire side blindly.

5. Prove the shipped path and then tidy.

Run the maintained tests against the Worker, verify the deployed commit and memory snapshots, then exercise capture -> question -> reply -> actual result. Remove obsolete launch instructions only with working replacements. Branch protection/default-branch changes need a coordinated repository decision.

What I did during this check

Fetched the actual cloud branches, compared ancestry and commits, ran non-mutating merge previews, inspected the running local process and its working directory, read the storage/deployment code, and checked current live fleet health. No branches were merged, no developers' files were reset, and no memory was deleted. The existing runtime mismatch is documented, not silently erased.

Reproducible evidence

research/overnight-2026-09-07/repository-state-evidence.json contains the branch comparison, exact conflicts, route observations and sanitized live status. Related PRs: github.com/anticipation-labs/Anticipy/pull/59 and /pull/61. This report is a current-state map, not a claim that all product failures are repaired.
