# Repository integration audit — September 7, 2026

**Result: no additional merge is needed for the repairs already pushed.** Local `cloudflare-backend` and GitHub both point to `a216dae380ebe78ef2e1c20e90080295be2bc6a4`, with zero commits ahead or behind. Remaining product gaps concern execution wiring, client installation and release coordination; they are not explained by missing repair commits.

This audit changed no product code, deployed nothing and sent no messages. It added only this report, a tracked-file inventory and machine-readable evidence. Existing untracked `output/playwright/` and `proof/audit/live_stall_notice.py` were preserved. Other developers' remote branches were inspected without switching this checkout.

## What was checked

Inventoried all **2,648 tracked files**, compared all **15 remote branch heads**, inspected all **four open pull requests**, reviewed the recent integration history, and traced production entrypoints, configuration, important imports, schedules and packaged artifacts. This is a repository-wide integration audit, not a claim that every function or third-party operation was dynamically exercised.

Reproducible details: [branch/source evidence](repository-integration-evidence.json), [complete file inventory](repository-integration-inventory.tsv). Release observations below come from the earlier committed [release readback](repair-live-release.json), [text-delivery evidence](repair-live-text.json), and [repair status](repair-status-2026-09-07.md). This pass rechecked source equivalence and GitHub run metadata; it did not rerun the live end-to-end tests or spend model credits.

## What is already integrated

| Change | Current position | Integration decision |
|---|---|---|
| PR #59, Mac ears/source | Merged at `776cbab5`, ancestor of current HEAD | Already integrated; Mac packaging belongs to its developer |
| PR #61, retire PocketBase | Merged at `5ef2a96a`, ancestor of current HEAD | Already integrated; do not restore deleted PocketBase code |
| `03f0c7f4`, calendar/text/discovery/browser repair | On top of both merges | Already integrated |
| `1f2d8f67`, build 167/browser requirement | Ancestor of HEAD | Already integrated |
| `b9a388b2`, SendBlue receipt reconciliation | Ancestor of HEAD | Already integrated |
| `a216dae3`, verified repair report | HEAD | Documentation, not another runtime version |

The main repair changed iPhone EventKit execution and delivery status, brain reply persistence and connection dispatch, Worker discovery and SendBlue callbacks, extension transport/click geometry, and related tests. The next iOS commit aligned its minimum extension version with 0.17.0 and advanced both build-number declarations. The final brain change reconciles saved SendBlue provider receipts without resending the reply. Exact filenames are available with `git show --stat` on these commits.

The deployed components intentionally have different source commits:

| Component | Last recorded release | Source compared with HEAD now |
|---|---|---|
| API Worker | `03f0c7f4` | No differences in Worker source, public assets or deployment configuration |
| Python brain | `b9a388b2` | No differences under `brain/` |
| iPhone | Build 167, `1f2d8f67` | No differences under `app/ios/` |

Different component commit IDs therefore do not establish deployment drift. The earlier Apple readback recorded build 167 available for the owner and the external pilot group; that is availability, not evidence that every tester installed it.

## Where everything belongs

| Area | Files | Role and integration boundary |
|---|---:|---|
| `app/` | 301 | 276 iOS files and 25 Mac files. Native UI, listening, client state and device execution. Shared Xcode/build files require coordination. |
| `brain/` | 36 | Python orchestration, contextual decisions, memory, questions, text delivery and execution coordination. |
| `migration/` | 206 | Despite its name, contains the production API Worker, brain control plane and deployment configuration. |
| `extension/` | 115 | Paired browser executor, page observations, actions and tests. Installing the released package is separate from merging source. |
| `spike/` | 39 | Experimental code mixed with contracts that production imports. Cannot archive this entire directory safely. |
| `firmware/` | 250 | Hardware/firmware source, artifacts and historical receipts; requires a chosen device/protocol baseline. |
| `tests/` | 193 | Automated test sources. Python default collection is here. |
| `proof/` | 1,020 | Evidence, fixtures and manually invoked probes; 774 files are under `proof/ambient`. Not 1,020 automatically executed tests. |
| `research/` | 351 | Dated audits, experiments and historical design evidence. Older reports describe older states. |
| `docs/` | 30 | Runbooks and technical documentation, partly stale after migration. |
| `overnight/` | 44 | Investigation/evaluation assets; existence does not establish production execution. |
| `design/`, `output/`, `website/` | 18 / 9 / 1 | Design/report artifacts and a minimal website artifact in this lineage. Not the unrelated main-branch website tree. |
| `.github/`, `.agents/`, root files | 5 / 1 / 29 | CI, agent guidance, configuration and root documents/data. |

The working path is: **phone/text input → API account/event state → owner brain with memory → required question/approval → API, browser or native-device executor → stored result and delivery receipt → app/text update.** Discovery can propose a connection; it does not itself authenticate an account or authorize an external action.

The same Worker also has live internal HQ/fellowship routes for people, tasks, notes, expenses and related operations. These are not unused merely because the iPhone does not call them. They share a deployment boundary with the app API and need their authentication contracts preserved.

## Concrete gaps and their consequences

### 1. Published source and installed clients can differ

The prior production heartbeat reported Chrome extension **0.15.0**, while the published and checked download was **0.17.0**. An old installed executor cannot benefit from new click/transport code. A successful pairing heartbeat alone is not proof that a task can execute.

The committed `migration/workers/public/mac/Anticipy-for-Mac.zip` contains **version 1.1.0, build 119**, inspected directly from its application plist. The recently merged Mac source should not be assumed present in that binary. Its developer must reconcile the source/build/package receipts and release it. No Mac changes were made here.

### 2. Some harness components still do not drive production work

The whole-conversation sorter is default-off. Even requesting `on` is explicitly demoted to shadow in [brain/worker.py](../../brain/worker.py), around lines 3660–3670, because the shared decision/authority/execution path has not been extracted. It observes but does not act. This is unfinished integration inside the current branch, not an absent merge.

Conversation-led app discovery now calls `recordUserSaidIt` in [discovery.ts](../../migration/workers/src/connections/discovery.ts). `recordObservedHost`, `recordSignUpDomain`, `recordLinksSeen` and `recordAnswerToAsk` still have definitions/wrappers/tests without production inputs found by the caller audit. In plain language: those collectors are empty inlet pipes. Do not promise that Anticipy learns from browser visits or email domains through them yet.

The Python import walk found `brain.links` outside the static production entrypoint graph. Treat this as a review candidate, not proof that deletion is safe. `brain.__init__` is implicit package machinery, not dead code. Markdown exemplars are documentation; the triage examples used by the model are embedded in `brain/orchestrator.py`, so editing the Markdown alone does not change that prompt.

The pendant path still lacks the phone-side decoder/consumer and physical proof described in [pendant-audio-status.md](pendant-audio-status.md). There is no pending audio callback queue to clear. Separately, registered legacy semantic rules remain in the harness; these repairs did not establish the requested global absence of word-based interpretation.

### 3. Production depends on a directory labelled as a prototype

There are **22 static import declarations** from Worker production source into `spike/two-hands/src` contracts: three runtime value imports and nineteen type imports. For example, `connections/discovery.ts`, `connections/dispatch.ts` and `routes/task_access.ts` import `ownerId`. Deleting `spike/` as cleanup would break the product/build. Move the shared contracts into an explicitly owned production module in one separate, behavior-preserving change, updating every consumer together.

### 4. Documentation describes a retired backend layout

[README.md](../../README.md), line 36, says `backend/pb_public/` remains the static asset source. That directory is gone; the real source is `migration/workers/public/`. [LOCAL-DEVELOPMENT-MAC.md](../../docs/LOCAL-DEVELOPMENT-MAC.md) repeats the old paths and tells developers to run removed `stage:assets` and `check:assets` scripts. Some container/config comments still describe earlier scaffolding as untested despite later deployment evidence.

This explains part of the team's setup confusion: code and instructions disagree. The normal local configuration correctly uses the new Worker source and asset path. Fix the current runbook and put dated reports behind one current-state index; preserve historical evidence with dates.

### 5. Code synchronization does not synchronize memory safely

PocketBase server code is retired. `brain/backend.py` is the current Cloudflare API client; compatibility names such as `ANTICIPY_PB` do not mean a PocketBase server still owns production state. Starting `brain.worker` directly without configuration defaults that variable to port 8090, whereas the current local API runs on 8787.

The state boundaries are D1 for shared API/account/job records, per-owner SQLite brain memory, R2 snapshots, and per-owner brain containers managed by the control plane. The local API configuration has neither production brain service bindings nor the paid provider configuration. It is not a full production replica. Snapshot serialization/restore safeguards exist in `brain/container_entry.py`; that is distinct from a guarantee of correct model recall.

Each developer should use a separate worktree and isolated local database/memory directory. Do not merge memory databases, copy production memory into several live workers, or run competing local workers for one owner as a way of syncing code. The detached `/private/tmp/anticipy-overnight-998fca6` worktree is historical test state, not missing product commits; leave it until its owner agrees to cleanup.

### 6. Passing CI is narrower than full product proof

The recorded final backend CI run passed 3,001 Python checks (two skipped), 83 browser suites and Worker checks. `pytest.ini` collects `tests/`; it does not automatically execute every script under `proof/`. The iOS gate and release workflow are separate. The effective API schedules are daily maintenance plus hourly discovery; an older five-minute HQ handler is not scheduled. Do not enable old schedules as cleanup, because that could trigger real old work.

The brain Dockerfile also installs unpinned Python packages. Its source hash identifies repository code, not the entire resolved dependency environment. Pinning the tested runtime is useful release work, but it does not replace proving task completion on installed clients.

## Other pushed work: merge, port or leave separate?

`jose_anticipy_system` has two commits absent from this branch's ancestry: `db43db14` changes the iOS backend URL and `863d3d7b` adds a Railway-to-R2 migration workflow. Current iOS already defaults to `api.anticipy.ai` and migrates old URLs; the current brain already has R2/container deployment. Their intent is superseded. Do not reintroduce the retired migration workflow just to make the branch appear consumed.

Eleven of the fifteen remote branch heads, including `main`, have no common ancestor with `cloudflare-backend`. Their large ahead/behind counts are unrelated history, not a backlog to merge. The Mac workflow registration on main is needed for GitHub's dispatch discovery, but the corresponding workflow is already here; dispatch Mac releases with the intended `cloudflare-backend` ref, under that developer's ownership.

All currently open PRs target main:

| PR | Scope | Decision |
|---|---|---|
| [#22](https://github.com/anticipation-labs/Anticipy/pull/22) | 56 files: held XIAO investor-unit package | Hardware owner must select and physically validate it. It explicitly has no offline audio backlog. Port only the chosen package/interface later. |
| [#19](https://github.com/anticipation-labs/Anticipy/pull/19) | 44 files: custom PCB/manufacturing package | Separate hardware review; not an app/backend repair. |
| [#18](https://github.com/anticipation-labs/Anticipy/pull/18) | 32 files: alternate hardware/firmware plan | Includes a proposed offline-backlog design unlike #22. Resolve the product/protocol baseline before combining. |
| [#6](https://github.com/anticipation-labs/Anticipy/pull/6) | 23 files: older HQ frontend prototype | Compare with the website owner's current frontend and the already-live HQ APIs; do not merge the unrelated application lineage wholesale. |

Firmware receipts also describe different historical source/build states: an earlier built-but-not-flashed artifact, source-only packages, and an explicitly stale copied receipt. These cannot be combined into a claim that the current pendant end-to-end path is verified. A chosen source hash, build artifact, BLE contract and physical test receipt must agree.

## Recommended integration order

1. **Close installed-client gaps.** Verify the released extension is actually loaded, then run a bounded task from phone/text through its result receipt. Have the Mac owner reconcile and release its package separately.
2. **Complete the shared execution path.** Route contextual conversation decisions through the same authority, question and execution machinery; remove remaining semantic heuristics through model-led replacements. Validate multi-turn replies such as “yes” against their actual pending context.
3. **Wire discovery deliberately.** Add real, consented event sources to the unused collectors one at a time. Verify that the resulting connection offer opens the correct account flow and resumes the original task after authorization.
4. **Make concurrent development reproducible.** Separate worktrees/state per developer, coordinate shared build files, pin runtime dependencies, and record source → release → installed-client versions together.
5. **Reconcile structure and documentation.** Correct the live runbook and move production contracts out of `spike/` without behavior changes. These improve maintainability but should not displace the execution work above.
6. **Integrate hardware/HQ selectively under their owners.** No bulk merge from main, no repeated migration, no indiscriminate folder deletion, and no memory-file merging.

No extra merge or deployment was performed for this audit. Its central conclusion is that the code history is already reconciled; the remaining work is to complete and prove specific product paths and align each installed artifact with that code.
