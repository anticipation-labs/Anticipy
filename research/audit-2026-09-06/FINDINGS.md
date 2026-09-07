# Findings under investigation

This is an active audit ledger. Source observations are not reproduced runtime
defects until their experiment is recorded. No release verdict has been issued.

| Finding | Evidence so far | State / next experiment |
| --- | --- | --- |
| Account deletion omits connection and password-reset records | Original handler listed nine tables. Real-schema synthetic fixtures retained connection state and password-reset hashes after HTTP 200. Schema census also found `connect_codes`. | Reproduced and repaired locally: all 15 product-owned tables now enumerated; provider cleanup precedes row removal. Not deployed. |
| Claimed legacy identity deletes another owner's legacy-keyed rows | A synthetic account declaring legacy_uuid equal to another account's ID deleted the other account's profile and jobs through its own authenticated deletion request. | Reproduced and repaired locally: canonical owner_ref wins; supplied UUID never authorizes a delete, including unclaimed historical rows. Not deployed. |
| Cloudflare memory purge has no consumer | Original supervisor never consumed the API purge queue. | Local implementation stops the owner container, persists a restart tombstone and removes per-owner objects; seven adversarial tests pass. Shared historical archives and actual Cloudflare behavior remain unresolved. |
| Evidence bytes outlive deleted metadata | Synthetic R2 fixture retained picture after successful row/account deletion. | Reproduced and repaired locally: delete bytes before losing handles; bucket failures preserve retryable account/metadata. Concurrent-write erasure remains to test. |
| Location is inferred from a time-zone name | Model input asserted Los Angeles solely from America/Los_Angeles. Existing tests incorrectly pinned that claim as correct. | Reproduced and repaired locally: use explicit contextual place evidence; timezone is a clock. 14 focused context tests pass; model-backed behavior remains to run. |
| Ordinary iOS push does not compile the app | Workflow ran logic suites and xcodegen, but xcodebuild archive/export were conditioned on an upload request. | Source repair: unconditional unsigned simulator compile of the committed project. Workflow execution still pending. |
| Existing full-chain proof depends on another machine's temporary path | `proof/e2e_cloudflare.py` defaults its browser arm to a missing `/private/tmp/claude-501/...` script. | Source confirmed; restore a portable executable browser harness and run it. |
| Standing meaning heuristics remain | Five entries in HARNESS-LAWS and tape registry; wider historical audit reports more. | Existing measured failure; map live callers and replace through context/model judgments, preserving regression cases. |
| Connection listing silently truncates paginated provider results | Adapter read one `/connected_accounts` page; official Composio v3.1 contract exposes cursor/next_cursor. | Local repair walks pages with owner checks on every page and rejects page failures/repeated cursors. Four new provider tests pass. Live pagination remains to verify. |
| Generic account-record DELETE bypasses erasure | Actual local HTTP returned 204 and left an orphan profile. | Reproduced; generic owner DELETE now returns 405 for every principal and directs callers through confirmed lifecycle erasure. Regression failed before repair, passes after; live verification pending. |

## Current verification

- Original five erasure regressions all failed before repair, with fixture-shape
  errors corrected before recording the baseline.
- Eleven erasure checks now pass, including schema census, another owner's
  survival, bucket/provider failures, unclaimed historical rows and rollback of
  the account/row/purge transaction together.
- Full Worker suite passes (including the new erasure and boundary files),
  and TypeScript typechecking passes. Connection provider suite now has 202 cases.
- Actual local workerd service/account script passes; its deletion portion runs
  four HTTP tests, including authenticated signup/sign-in/deletion.
- Account cleanup is not yet complete across all systems: active containers,
  R2 memory/history, in-flight writes/consents and deployed behavior remain open.
- Composio dashboard: `omar_workspace/anticipy_two_hands`; only listed user is
  the existing synthetic probe, with one expired Google Calendar account.
  Existing project API key is masked and absent from the recovered vault.
  Temporary scoped key is prepared, not created, awaiting explicit approval
  required by the browser tool's new-credential confirmation rule.

Baseline rerun before source edits: all iOS suites passed, source build 158.
Private full log: `~/Library/Logs/Anticipy/audit-2026-09-06/ios-before.log`.
Wrangler currently has no login on this fresh Mac environment. GitHub has the
Cloudflare deploy secrets; local deployment access still needs verification.
Paid testing is underway; exact usage and unresolved reservations are recorded
in the private durable ledger `work/audit/spend.json` (under $1 at this checkpoint).

## Additional measured findings

- A valid account JWT with an invalid-base64 signature produced HTTP 500 on
  local workerd. Decoding is now inside the authentication refusal boundary.
  A valid-token positive control and three malformed signatures pass.
- Concurrent snapshots in the same container could upload an older SQLite
  revision last. A blocked-first-upload experiment failed before repair; a lock
  spanning both copy and upload now passes. This does not establish fencing
  between container incarnations or eliminate the 60-second durability window.
- Read-only inspection recognized all 13 backup ZIPs, containing 108 memory.db
  entries in total. Eight archives contain paths matching the authorized reset
  subject. Private member names and account identifiers are under work/audit.
- The reset subject has one profile matching BOTH the supplied email and phone.
  The canonical account IS present in /worker/owners (37/37 rows returned).
  Process correction: the generic owners API hides rows from service credentials,
  so its 404/empty page was initially misread as account absence. That inference
  was wrong and was corrected against the dedicated discovery endpoint. No reset
  was executed here.
- Latest successful brain CI deployment observed: source 0b791d69df8d991edebdd619243291fa335d293a,
  capacity 8. Local source changes in this audit are not deployed.

## Harness work

The 50-person/101-contact corpus is authored, not a completed execution claim.
The first local transcript lane uses the production brain.worker entry point,
actual workerd HTTP, real paid model transport, per-run account IDs and memory
files. The worker has no vendor credentials and a network boundary that rejects
non-loopback destinations. Its model endpoint is a separate audited proxy.
Browser/provider completion is explicitly outside this lane's verdict.

The spend proxy passed 11 negative-control checks, including concurrent
reservations, recovery after crashes, absent usage costs and paid-add-on refusal.
It reserves a full model context before every request; uncertain requests keep
that reservation. Its working ceiling is $25 inside the owner's $50 total,
leaving funded balance for other verification. Current usage is recorded in
ignored work/audit/spend.json, not estimated from passing test counts.

Full Worker suite passed again after the generic DELETE/auth repairs; TypeScript
checks pass. Full Python baseline was 2,960 passed, two skipped and one stale
city-from-timezone assertion; the assertion was corrected and its focused
19-test group passed. A fresh full Python run remains due after later changes.

The local unauthenticated route sweep observed 131 HTTP requests. It initially
found one 500: an empty anonymous agent-record POST reached a required agent_id
SQL constraint. Known input constraints now return 400, while infrastructure
faults still propagate. The repeat sweep has no 500 responses. Its candidate
method extraction still needs refinement; it is not a substitute for authorized
happy-path/effect checks.

## September 7 repair and behavior checkpoint

- Generic account signup accepted a caller-chosen canonical ID. Anonymous
  creation now refuses that field, preventing reuse of a previously erased
  identity. Required-field and conflicting-update tests preserve original rows.
- A connection permission update could resurrect a connection deleted between
  read and write, or overwrite a newer expiration state. A conditional batch
  update now changes only write permission and returns a conflict if any target
  vanished. Both interleaving regressions failed before repair and pass after.
- Memory restore accepted corrupt bytes and could replace memory.db before a
  second download failed. Downloads now stage together, validate SQLite and
  clock JSON, and only then replace local state. Four restore cases pass;
  cross-object remote generation atomicity remains unresolved.
- Shared legacy ZIP archives contain more than one owner's memories. The purge
  consumer now leaves a purge pending when such archives exist, rather than
  claiming full erasure after deleting only per-owner prefixes. Selective archive
  redaction and live verification remain required.
- Live Composio catalog requests through the existing backend credential returned
  49 Calendar, 63 Gmail, 56 Notion, and 167 Slack tools (335 total). This proves
  catalog connectivity only; authenticated tool execution is not established.
- Real-model transcript runs reproduced unsupported progress claims: a reply
  said it had pulled documents/calendar when the job was only awaiting approval;
  another said a reminder was set while its job was awaiting approval. A pilot
  clarification correctly asked which Alex, but also claimed notes were ready
  without evidence. These are failures, not completed task results. Trace-based
  context repair and repeat model tests are next.

The reply composer now receives persisted job status and an explicit empty set
of verified results at task creation. Prompt examples distinguish plans, queued
requests, and running work from completed artifacts. The fallback no longer
claims a draft is ready. Six receipt/fallback checks and 82 adjacent checks pass;
real-model replay is underway, so behavioral repair is not yet established.

The no-credential LLM path formerly ran a nine-pattern intent classifier and
returned act/ask/ignore as though a model had answered. That path is removed;
missing transport raises ConnectionError, which the worker already treats as
retryable unavailability. Four before/after checks and the focused transport,
outage and meeting group pass (65 tests). The meeting tests had depended on the
implicit classifier and one only passed because its fake response lacked
raise_for_status, preventing a job. Explicit decisions and a positive held-work
assertion now ensure the meeting test actually exercises the behavior it names.

The full Python run reached 2,981 passed, two skipped and five failures: one
changed fallback expectation, one pre-existing clock-prefix expectation despite
grounding now being a suffix, and three failures from an unclassified extensionless
corpus checksum file. The checksum now has a .txt extension, and the corrected
expectations plus both registry groups pass (142 focused tests). No test's
meaning-heuristic removal condition was weakened.

Composer replay evidence: `voice-replay-evidence.json` preserves both rounds.
The first 15 new replies still included an invented marketing contact and a
promise to deliver an unapproved reminder. Supplying known contacts and explaining
why that future promise is misleading produced 15 further replies; manual review
found neither invented identities nor unsupported progress/completion claims in
those 15. This is a small development replay, not a general reliability estimate.
The full HTTP/worker path is now repeating the three affected scenarios to check
that actual persisted memory, rather than replay-supplied contacts, reaches the
composer.

## Timeboxed delivery checkpoint

At the owner's explicit speed correction, new scope expansion stopped. The final
full local Python run passed 2,986 tests with two skips. All 34 chained Worker
test files passed under the configured Node 24 runtime; API and brain typechecks
passed. An earlier command missed the project environment and ran a different
Node/SQLite runtime, whose existing ALTER TABLE test failed even against the
pre-change schema. Re-running under the configured runtime resolved that tooling
failure; production code was not changed to accommodate it.

The late-write erasure failures are reproduced and locally repaired with a
permanent purge-backed SQL fence. The handler checks all 32 required triggers
before cleanup, registers the purge first, and leaves the fence after partial
failure or deletion. The migration was applied only to isolated local D1.
Fifteen account-erasure tests pass, including absence of the migration, ownership
reassignment, ID resurrection, late pictures and stale transcript writes. This
supersedes the earlier assertion that a failed final account DELETE rolls back
the purge request: the request now intentionally survives to block late writes.
Late remote OAuth grants and R2 upload failure reconciliation remain unverified.

Three repeat full-path transcript runs (Ana, Clara, Ken) completed with real
models and persisted memory. Manual review found the final replies truthful
about unstarted work and missing identity. Fourteen distinct corpus people have
been exercised in the transcript lane; zero complete 50-person browser/provider
execution certification is claimed. Model cost at delivery: approximately $0.54,
with no unresolved reservations. The PDF is an audit checkpoint, not a release
certificate. No production deployment, owner reset, or new phone release occurred.

Actual local workerd/D1 verification also passed after the fence migration:
signup and event creation 200, confirmed account deletion 200, stale service
event insertion 409 (`local-erasure-wire.json`). The paid model gateway was
stopped at $0.537237884 observed, with no unresolved reservations. The PDF's
12 pages were rendered; every page was checked in the overview and the opening
page at larger scale, with all 50 case numbers and text extraction verified.


## Resumed delivery: deploy verification

The premature partial handoff was a process failure; the owner requested the
complete original outcome. The backend workflow now has a separate API deployment
choice with its own tests, the non-destructive erasure migration, and live account
and ownership checks. Deployments preserve separately configured provider variables.
The health response retains its client contract and adds immutable Cloudflare
version metadata; the verifier compares both the active deployment and the exact
workflow commit. Local HTTP proof passed 14 checks, including cross-account
read/write refusal, account cleanup, invalid tokens and revoked login. This is
local evidence until the deployment runs. Source: Cloudflare
[version metadata binding](https://developers.cloudflare.com/workers/runtime-apis/bindings/version-metadata/)
and [deployments API](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/deployments/).
