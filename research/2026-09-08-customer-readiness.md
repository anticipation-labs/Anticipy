# Customer-journey readiness — replacement brief

Date: 2026-09-08. Branch `cloudflare-backend`; starting HEAD and remote tip
`7f319726fb0c71a38c004fdd3ae0fea2756f2170`. No main merge/switch. Existing
untracked `.wrangler/`, `desktop/`, and `engine/` are not part of this patch.

Latest follow-up: the tester confirmed iPhone **1.1.1 (172)** installation.
The [audio-to-agent harness audit](2026-09-08-audio-harness.md) records new
capture-lifecycle findings and the build-173 candidate. Whole-journey status
remains UNPROVEN; current brain deployment metadata still declares the older
`cb201095` source. The historical checks below do not supersede those findings.

## Acceptance source and evidence boundary

The team replacement brief asks for real iPhone-led customer journeys, not
timed points or replayed scripted examples. The full guide and all 100
fictional exemplars were read. Local PDF and the repository's
`output/pdf/Anticipy-in-real-life-100-conversation-exemplars.pdf` have identical
SHA-256 `d683e276bc846f02a89360d31efee526433a46b460eb512cdb923e15a202d9db`.
Representative rendered pages 5/55 were inspected; editable sources are
`docs/100-lived-exemplars-2026-09-07/`. These are requirements/inspiration,
not a record of 100 completed real tests.

The tester supplied a Mac TestFlight screenshot showing 1.1.1 (169), then
confirmed the iPhone also remains on build 169. The tester supplied their own
email in the conversation as the intended test-account identifier; it is not
repeated in this commit-bound document. A subsequent exact-email lookup
returned exactly one canonical account, created on 2026-09-08. Actual client
sign-in and customer journeys have not yet been observed.
No phone capture, OAuth grant, real text, calendar operation, or installed
extension task has been fabricated to fill that gap.

### Follow-up: exact-account diagnostic access

A single read-only Cloudflare D1 query was attempted against the configured
`anticipy-backend` database: select only `id, created, verified` from `owners`,
filtering by the tester-supplied exact normalized email, with `LIMIT 2`.
Cloudflare refused it with API error **7403** (account not valid or not
authorized to access the service). The command exited 1; no account rows were
returned. This is an access failure, not evidence the account does not exist.
No alternative account, credential, broad owner list, or write was attempted.

The generic service-authenticated owners API intentionally denies owner-list
reads, and `/worker/owners` has no email filter and returns all owners. Neither
is an acceptable substitute. The fleet diagnostic is read-only but also
returns all owners, so it was not called. Scoped diagnostics require approved
read access or the tester's own authenticated customer flow; no password or
session token should be pasted into chat. The supplied email is not consent
to erase/reset existing data or to send messages or perform external effects.

Independent source inspection of build 169 (`6ea3e908`) found no reachable
canonical account-ID display/copy. A legacy support template's `ownerID` is a
device UUID, not the account row ID. Do not substitute it or mutable profile
email. An authorized team operator can perform the exact-email lookup or
grant the needed scoped diagnostic access. In-app visual checks remain
possible, but "Refresh diagnostics" is not read-only: it invokes the normal
refresh path, which can flush pending input and run already-approved device
work. Do not use it merely to resolve account identity.

Resolution after the tester clarified they are Super Admin: `wrangler whoami
--account 114587b715e702461766369b01d42fc7` reported the correct signed-in
tester and included `Super Administrator - All Privileges` in that account's
membership roles. Its OAuth token already includes `d1:write`. Exact database
metadata confirmed the configured `anticipy-backend` UUID belongs to this
account. A constant `SELECT 1` then succeeded with zero rows read/written,
and the original exact-email projection subsequently returned exactly one
account with zero writes (`changed_db=false`). No role, token, configuration,
or secret was changed by this agent, and no broader credential was tried.
The earlier 7403 failure is no longer reproducible; its transient cause has
not been established. Requesting broader permissions is no longer indicated.
Only the tester's account identity/creation/verification metadata was returned;
no transcripts, jobs, provider records, or other customers' rows were returned.

## Source path inventories

- [Every actual iOS path and source gaps](2026-09-08-ios-journey-map.md)
- [Service, delivery, approvals, OAuth, API and calendar](2026-09-08-service-journey-map.md)
- [Browser handoff, recovery, gate safety and human acceptance](2026-09-08-browser-customer-journey.md)
- [Earlier local browser/backend/memory repairs](2026-09-08-vc-browser-readiness.md)

## Environment and release metadata

The parent `.env` was initially empty, then the user saved it during this
session. Final presence check: private regular file, mode 0600, valid simple
dotenv, no duplicate assignments. No value has been printed or sourced. Both
backend settings name the current **LIVE** API. Keep it outside Git, not in
autoloaded `.env.local`; default owner values are deliberately ignored.

`proof/audit/local_env_preflight.py` performs secret-free offline inspection;
its regression tests cover no value leakage/environment changes, shell input,
duplicate/malformed keys, bad URLs, nonprivate/symlink files and admission
against the opened descriptor. Exit 0 means file-format admission only.

Read-only names-only inspection confirmed release secrets in GitHub CI and
required messaging/auth/service/provider/storage names on the API and brain
Workers. Local absence of SendBlue/ASC private key/Cloudflare token is not a
production missing-secret finding. Keys have not been authenticated against
providers by this inspection, and no secret has been rotated, uploaded or
downloaded. The API public GET health returned 200; HEAD returns 404, so
HEAD alone is not a health verdict. No customer records were read.

Public GET response headers identify the still-live API as revision
`d52eaf38444d17adc410ac115636764f9807e89e`, Worker version
`194e352b-951c-482c-a852-6246b1fb78d2`. That is not this uncommitted patch.

Current machine: Node 24.20.0, virtualenv Python 3.11.16, macOS Command Line
Tools/Swift, Poppler. Full Xcode/Simulator absent; actual SwiftUI compilation
must run in CI or after Xcode installation. Updated developer guidance:
[Tejas Mac](../docs/LOCAL-DEVELOPMENT-TEJAS.md).

## Current patch and gates

| Area | Source work / local evidence | Live verdict |
| --- | --- | --- |
| Pre-edit iOS baseline | Full required suite passed, build 171 | Not an installed-device test |
| Home task controls / source permission recovery | Actual Home/detail task controls and declined-source reopening restored; 13 actual-screen checks pass | UNPROVEN |
| Input durability / retry | Owner-bound atomic staging, exact-identity reconciliation and honest failed-write/cleanup recovery; 101 outbox/race checks pass | UNPROVEN |
| SMS approval referent | Delivered presentation snapshot + separate contextual selection + exact conditional write; 80 focused Python checks and 22 Worker approval checks pass | UNPROVEN |
| Server-owned delivery evidence | Account clients cannot forge protected provider receipts or SMS origin; 46 guard/atomic SQL checks and 79 scoped presentation-route checks pass | UNPROVEN |
| Browser packaging | Source pins moved together to 0.18.1; all three 353,502-byte ZIP aliases match, SHA-256 `430518d8eb50186f0e3d6af4caf1b8754cd231e21899a997dc65984af7f97afc` | Not deployed or installed |
| iOS version | Source build 172 agrees in both project files; logic suite passed, full SwiftUI compile remains pending | No new upload/install |
| Release summary | CI now distinguishes failed run, upload, processing and tester verification; 7 local summary tests passed | Workflow not executed |
| Secret preflight | 9 local tests passed; no network/env activation | Presence only, no provider proof |

Source-only rows remain UNPROVEN live even after their unit tests pass.

Component checks completed while other component patches remained in progress:

- Extension 0.18.1: all 84 suites passed in 74.59 seconds, exit 0, with OS
  outbound networking denied except loopback. Initial all-outbound denial
  made the local HTTP timeout suite fail with `connect EPERM`; that exact
  failure was reproduced and corrected by allowing loopback only. No external
  access was enabled to turn it green.
- Brain fleet Worker: full tests and TypeScript check passed with external
  outbound networking denied for tests.
- API Wrangler dry-run built locally (769.35 KiB / gzip 196.39 KiB), exit 0.
  It warned that `anticipy.ai/c/*` can match assets; no `public/c` assets were
  introduced. No Worker was deployed. This precedes the final event-guard
  patch and must not stand in for its final test/typecheck/dry-run.
- Secret preflight, release summary and extension version pins: 22 tests
  passed together. These component results preceded the frozen-tree runs below.

Final component verification after the API source freeze:

- Full Python suite independently passed **3,155 tests, 2 skipped**, exit 0
  in 127.43 seconds, with external networking denied and npm resolution
  offline. Both skips are the intentional live model/tool probes in
  `tests/test_hands_router.py`; no additional local-D1 skip remains.
- API Worker full registered suite and TypeScript check passed independently
  under OS external-network denial (loopback allowed). All provider responses
  are fixtures, including deliberately refused and delayed responses.
- Final API dry-run passed under that same network restriction: 777.04 KiB /
  gzip 198.29 KiB. The existing asset-route warning remains. This produced only
  ignored local build output under `work/api-final-dry-run-2026-09-08/`.
- Mac full seven-suite gate passed, including the complete Mac app typecheck
  against the macOS SDK. This is distinct from the unavailable iOS SDK build.
- Final full iOS logic suite independently passed on build 172 after the
  speaker assertion-runner repair, exit 0, under external-network denial.
  Local log: `work/ios-final-verification-2026-09-08.log`. The suite explicitly
  cannot compile the full iOS app without the missing iOS SDK.
- Final secret-file inspection passed without loading/authenticating values.
  All three extension aliases still match the exact source hash above.
- Local D1 tests now resolve the CI-matching locked Wrangler install through
  the ignored root `node_modules` symlink. They use isolated temporary local
  databases, not remote D1. Set `npm_config_offline=true` for this invocation.

Review found the speaker test runner was stripping `assert` with `swiftc -O`;
its earlier printed success did not prove the asserted race. The runner is
now explicitly `-Onone`. The active-assertion suite passed, and its temporary
no-epoch mutant failed the exact required ownership assertion. The existing
application generation fence already covers pre-tagging account switches;
no new application patch was needed for that interval. Normal Stop retains
its ordered tail. See the [iOS recovery evidence](2026-09-08-ios-outbox-recovery.md).

Independent final review accepted the changed SMS authority seams after 80
focused Python checks, 22 atomic approval checks, 13 dispatch checks, and nine
additional in-memory envelope/old-versus-new presentation probes. No live
model, actual delivery, or installed-device claim follows from those fixtures.

Final `git diff --check` passed. The work remains uncommitted on
`cloudflare-backend`; nothing was staged, pushed, deployed, or uploaded to
TestFlight. The prepared source versions are iOS build 172 and extension
0.18.1, not claims about the tester's installed versions. CI may require a
higher iOS upload number if Apple already holds 172. No local dev server was
started for this work; transient test processes have finished.

## Remaining product limitations (not waived by this patch)

- Verified connection does not yet re-plan an existing waiting browser task
  into the API lane. A fresh task can use available API reads; callback
  success alone does not establish original-task continuation.
- API writes have an intentionally closed maturity/authority gate despite a
  connection's writes switch. Do not remove that boundary just for a demo.
- Pendant audio has no live Opus decode/integration path; it is not working
  capture. Local notifications are not an APNs delivery implementation.
- Supervised-read fact veto currently lacks durable failure recovery.
- Both missing memory objects versus a genuinely new owner still need a
  durable initialization distinction; existing fail-closed snapshot repairs
  do not prove every storage-loss case.
- Legacy meaning heuristics remain registered red tape; no new prose-based
  shortcuts are permitted. Quiet/correction/short-answer judgment still needs
  varied real conversations with contextual model evidence.
- Full Xcode compilation, controlled TestFlight onboarding, real Chrome
  wake/pairing/task, OAuth/revocation, text delivery/callback, native calendar
  receipt and duplicate-effect counts remain required.

No blanket "perfect", "fully deployable", or "shipped" claim is justified
while those accepted paths lack evidence. Production release is not a way to
skip review or the tester's participation.

## Authorized release preparation (2026-09-08)

Subsequent commit, CI, API release and TestFlight observations are recorded in
the [build 172 release ledger](2026-09-08-release-172.md). Earlier frozen-tree
statements above describe the pre-release checkpoint, not current release status.

The user asked to proceed after discussing the reviewed branch, CI compile,
TestFlight upload, matching backend release and controlled iPhone verification.
The release remains on `cloudflare-backend`; `main` is out of scope. The
pre-edit iOS logic baseline passed again on source build 172 (local log
`work/ios-release-baseline-2026-09-08.log`). First push is compile/test only,
without a ship marker. Apple upload is a separate deliberate step after its
real iOS SDK compiler passes. Nothing in this paragraph establishes an upload.

The default backend workflow is not an acceptable owner-scoped test:
its API path creates synthetic accounts and invokes account reset; its brain
path reads every allowlisted owner's memory, defaults the serving cap to one,
and performs an immediate container rollout. Do not dispatch these defaults.
Preserve existing fleet settings and stop for any unapproved broader effect.

The automatic OAuth-to-original-task continuation repair is deferred from
build 172. It requires a durable task/access identity, verified connection
evidence and an atomic lane transition; a callback-only requeue is unsafe.
The iOS repairs are independently usable. Connect first, then create a new
read task for verification; cancel any earlier pending equivalent deliberately
before replacing it. Connecting an account does not claim the earlier task
resumed. API writes and automatic approval remain disabled by existing gates.

Release review found the iOS workflow automatically revoked all development
certificates named `Created via API`. The helper did not establish that these
were orphaned or belonged to this repository/run. The automatic revocation
step is removed; signing must succeed with the current pool or stop for a
certificate-specific cleanup decision. The temporary ASC key files are now
created with a private umask. No Apple certificate has been changed here.
