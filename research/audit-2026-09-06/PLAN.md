# Anticipy audit, repair, and fresh-user release

Requested by the owner on 2026-09-06. This is ongoing work, not a completion claim.

## Scope and constraints

- Audit current `cloudflare-backend`: every route, connection, documentation file,
  and backend component, with explicit coverage and remaining uncertainty.
- Research harnesses, general agent workflows, and memory from primary sources.
- Create 50 distinct fictional people with contacts, histories, permissions,
  transcripts, cross-application tasks, and observable expected outcomes.
- Exercise actual brain code with model-backed transcripts and browser/API
  simulations; separately verify real Composio and messaging behavior.
- Repair reproduced defects and test the repairs adversarially.
- Produce a PDF report plus reproducible repository evidence.
- Paid model and live integration testing: **US$50 maximum total**. Record usage;
  stop paid requests before crossing the cap. Provider unavailability is not a
  passing test. Paid runs are underway; the private durable spend ledger is
  `work/audit/spend.json`; current totals are in the handoff status below.
- Synthetic contacts and users belong to isolated test environments. Live test
  messages may go only to the phone the owner specified, never invented people
  or unrelated real contacts.
- After the audit and repairs, erase the owner's explicitly identified product
  account data, verify the fresh-user state, and deliver through CI/TestFlight.
  Exact identifiers and private production evidence stay in ignored `work/audit/`.
- Stage and commit exact paths. Maintain synchronized iOS build numbers with
  source changes; no laptop uploads. Check Apple's actual build verdict.
- Do not promise literal perfection: report observed behavior and untested
  conditions plainly, without opaque test-stage labels.

The update_plan tool is unavailable in this session; this file is the durable
plan. Exactly one top-level phase is marked in progress.

## Current handoff status — 06:37 UTC, 7 September 2026

The requested outcome is an audited, repaired app on the owner's phone with a
verified fresh product account. **That outcome has not been delivered.**
Backend fixes and a PDF are completed parts of the work, not the final handoff.

| Deliverable | Verified state | Remaining work |
| --- | --- | --- |
| Mac workspace | Correct branch; tools, simulator and isolated API prepared | Keep existing checkout and explicit-path commits |
| iOS availability | TestFlight 159 is valid and in beta; app/ios tree matches the source used for that upload | Installation and fresh-user handset observation |
| Backend deployment | API and all eight brain runtimes at source 1682d69; running processes and current durable snapshots verified | Repair remaining material decision-rule defects and expand authenticated integration coverage |
| Consent behavior | 18 real-model cases and 18 complete model/HTTP/database paths passed; live API rejects stale approval | Other approval/execution paths remain in the wider audit |
| Research and examples | Primary-source research, 50 fictional people, 101 contacts, all transcript observations and five browser simulations recorded | These are not 50 completed real-provider tasks |
| Google Calendar | Connection-link/code delivery observed | Google authorization and a verified provider operation; the previous connection browser tab is now closed |
| Owner erasure | Live public/operator cleanup verified on synthetic accounts; historical DB recovery cross-checked | Selective historical cleanup and deletion of the actual owner's product account, after audit/repair readiness |
| Audit report | Current 14-page PDF and repository evidence committed at 4773267 | Complete the remaining coverage and fresh-user handoff |

Current source release evidence: API run 34090499964 (29 live checks), brain run
34090592279 (all eight sources/processes/snapshots), CI run 34090500689 (3,017
Python tests passed, seven skipped, all 94 browser suites and Worker checks).
See BACKEND-CONSENT-REPAIR.md and verification.json for exact evidence.

Paid audit usage: **US$2.548762**, zero unresolved model reservations; the gateway
is stopped. The authorized maximum remains US$50. No iOS source was changed and
no redundant Apple upload is needed for the current source. No real owner data
has been erased. No complete-audit or production-perfection verdict is issued.

## Execution order

1. **IN PROGRESS:** close the remaining material backend behavior and integration
   failures, with concrete persisted outcomes and live source/behavior evidence.
2. Prepare and verify selective real-account erasure across current and historical
   product stores, preserving unrelated people and company/source archives.
3. Once readiness is established, execute the already-authorized product reset,
   verify that the old identity and data are gone, and complete fresh-phone testing
   on the current TestFlight build.

The calendar UI is one unfinished dependency; it is not an explanation for all
remaining backend work. The exhaustive audit remains incomplete. Do not silently
reduce the user's required audit-before-reset order to obtain a quicker handoff.
Do not produce another partial report as though it completes the requested job.

## Evidence standard

Track each route and component as not reviewed, source reviewed, locally
exercised, live exercised, failed, or blocked, with evidence references. A stubbed
provider proves local orchestration, not a provider integration. A fake browser
response is not a browser interaction. A mock success body is not proof of a
persisted effect. Deterministic controls must demonstrate that the checker fails
on a broken result, and semantic judgments must be separated from mechanical
assertions. Test cases are examples, not product-specific decision rules.

Primary research lanes: official agent/harness documentation and original
evaluation papers; memory architectures and original memory benchmarks;
official Composio and messaging integration documentation. Research agents are
limited to evidence gathering and do not edit or deploy the project.

## Historical September 7 checkpoints (superseded by current status above)

The owner imposed 3-, 6- and 10-minute self-checks to accelerate the full task.
A partial handoff was incorrectly treated as completion; the owner explicitly
rejected that on September 7. The full audit, repair, reset and phone delivery
remain active. Finish deployment and live verification dependencies before
expanding the research. The elapsed timer automation has been paused.

Latest verification: all 50 transcript cases have observations, including ten
held-out cases; five actual-extension/real-model browser simulations completed.
The API at ec42707 passed 22 live checks. SMS delivery is visible in the owner's
screenshot, but Google consent is pending owner interaction. All eight brain
images now pass source/process/snapshot/model checks in release 34086177008 at
ebbac06. A graceful recovery resolved the stale runtimes. The 13-page PDF is
updated and rendered. Apple confirms build 159 is available internally and its
entire iOS tree matches the current checkout. No additional upload is needed for
the current iOS source. The real account reset has not been executed.

Reset preparation found both scoped worker ZIPs and shared historical PocketBase
archives. The latest old PocketBase database is already corrupt, including an
agents-table scan, so rewriting it without losing unrelated records requires
further work. Read-only local copies are private and must also be erased with
the product data. Source/git/company archives are outside product-account scope.

Primary-source research is integrated in RESEARCH.md. Inventory candidates cover
2,518 tracked files and 365 documents; this is enumeration, not complete review.
The frozen corpus contains 50 fictional people and 101 contacts. All ten held-out
cases were observed after development repairs without tuning to those results.
Five simulated browser read tasks completed with real models; actual connected
provider operations and broader multi-turn cancellation/restart coverage remain
unfinished. Both API and brain repairs are deployed and verified as described
above. The paid gateway is stopped at US$2.017588. No real owner data has been
erased and no complete-audit verdict has been issued.

## Initial source baseline

`d93682f80b14c40d5d4ba445ea6333e4a5a58e33` plus local setup-documentation commit
`fe04ee5`. No remote advance at the start of this audit. App source version:
1.1.1, build 158. Prior setup evidence is in
`research/2026-09-06-mac-development-setup.md`; it is a starting measurement,
not evidence that this audit is complete.

## Memory and voice repair, 05:49 UTC September 7

Reproduced and removed the deterministic fact-merge, veto-coverage and
commitment-resolution shortcuts. Stronger contextual judgments passed all
16 real-model memory cases. Historical/veto uncertainty defers writes rather
than inferring permission; retired notes cannot be resurrected by an unknown
judgment. Full Python suite: 3,003 passed, two skipped. Subsequent voice changes
passed 46 focused checks and 12 real-model compositions, reviewed in
voice-state-repair-results.json. Correct assistant identity and persisted
execution status reach the stronger composer. Runtime deployment is next.
Paid observed/reserved spend is US$2.339278.
The earlier report is a checkpoint; erasure, real connected-provider tests and
the wider legacy meaning audit remain incomplete. No real account reset has
been executed.

Live verification completed: deployment 34088232090 at 272a3e3 passed
source/process/snapshot checks on all eight workers. System invariants run
34088225993 passed (2,999 Python cases, seven environment-specific skips; all
94 browser suites in 72.91 seconds; Worker checks passed). No iOS source changed.

Calendar continuation: a new link was minted without an extra link SMS; the
code was requested through the real page and delivery was observed in Messages.
Chrome refused code entry because another extension UI is open. Native Chrome
control also reported a concurrent user app change. No bypass was attempted.
The user has been asked to dismiss that popup and reply continue. Google
consent and actual connected-calendar execution are still unverified.

Historical data: local SQLite recovery preserves all 112 schema objects and
every row from 45 readable original tables. The damaged agents table yields
489 rows, identical in two independently recovered dated backups. Both recovered
databases pass integrity checks; foreign-key checks have no violations. These
are private local review copies, not remote rewrites or completed account erasure.
