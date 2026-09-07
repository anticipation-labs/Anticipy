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
  `work/audit/spend.json` (US$2.017588 observed with no unresolved reservations
  at 05:10 UTC on September 7).
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

## Phases

1. PARTIAL — Inventory and research. Establish source baseline, enumerate
   HTTP/client/integration surfaces and documents, inspect access and account
   relationships read-only, reconcile primary-source research with code.
2. PARTIAL — Build the 50-person corpus and isolated full-path harness, including
   independent state assertions, hostile content, restart/retry/timeout cases,
   and privacy boundaries. Freeze a held-out set before repairing behavior.
3. **IN PROGRESS — Execute, diagnose, repair, and rerun affected tests.** Record concrete
   inputs, traces, persisted outputs, spend, and why each result is valid.
4. PARTIAL — Validate deployment behavior, Composio/provider boundaries, and
   controlled live messaging. Resolve material failures and coverage gaps.
5. PARTIAL — Synthesize the PDF and repository audit; independently review
   release candidates against the recorded failures and source of record.
6. PENDING — Reset the authorized owner account across product stores and
   connected-account state; verify erasure; ship via CI, confirm App Store
   Connect availability, and guide the genuinely fresh phone test.

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

## September 7 checkpoint

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
