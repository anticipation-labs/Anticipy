# Anticipy: release evidence and remaining-work board

Snapshot: 2026-09-13. This is a work board, **not an end-to-end acceptance certificate**.
Source of record: `cloudflare-backend`; released source:
[`a29bcea66565e8efe2d1710f0ba451d6af9a2548`](https://github.com/anticipation-labs/Anticipy/commit/a29bcea66565e8efe2d1710f0ba451d6af9a2548).
Later work must record its own source, tests and deployment evidence.

## What is actually released

Reviewed connector, browser, receipt and migration repairs landed in
[PR 63](https://github.com/anticipation-labs/Anticipy/pull/63) and
[PR 64](https://github.com/anticipation-labs/Anticipy/pull/64).
`main` was not changed. The following are separate evidence levels:

| Surface | Evidence at this snapshot | Does not prove |
| --- | --- | --- |
| Source and automated gates | [System invariants](https://github.com/anticipation-labs/Anticipy/actions/runs/34743341295): 4,047 Python tests, 88 extension suites, API/brain tests and types; three explicit Python skips. Separate real-Wrangler local regression passed. | Real customer journeys, all providers, or comparative model quality. |
| Cloudflare API | [Release and live checks](https://github.com/anticipation-labs/Anticipy/actions/runs/34743554858), 06:47 UTC: semantic schema readiness and 37 live API checks passed. Synthetic probe accounts were cleaned up. | Real Google OAuth, phone delivery, or browser task completion. |
| Cloudflare brain | [Release and fleet proof](https://github.com/anticipation-labs/Anticipy/actions/runs/34743739035), 06:54 UTC; independent full proof at 06:55 UTC. Expected running source/models and current snapshots passed. | An arbitrary user task succeeded, acceptable latency, or a full clean day. |
| Deployment identity refresh | 15:25 UTC: API and brain still tagged to the release at 100%; API health returned 200. | A rerun of the complete earlier fleet or task proof. |
| Browser download | Extension 0.18.2; all three public ZIP aliases matched the reviewed archive. | Installation in anyone's Chrome, reconnection after restart, or clicks on actual customer sites. |
| iPhone distribution | [iOS release](https://github.com/anticipation-labs/Anticipy/actions/runs/34743959115): 1.1.1 (176), Apple VALID and in beta testing. [Audience assignment](https://github.com/anticipation-labs/Anticipy/actions/runs/34765221900) covered all existing testers. | Installation or notification delivery. Two invitations remain unaccepted; the final audience-readiness gate is red for that reason. |
| Mac | Unsigned universal compilation passed in CI. Public ZIP rechecked at 16:31 UTC: bytes match the checked-in package whose Info.plist reports build 171. | A current signed/notarized distribution; approved Developer ID signing material is still needed. |

The first API attempt failed safely before the new migration/deploy because
Wrangler parsed a leading SQL comment as an option. PR 64 preserved SQL bytes
and repaired argument transport; it did not bypass readiness. Historical
uncertain effects and inactive malformed metadata were preserved, not erased
to manufacture a passing result.

The public [Mac archive](https://api.anticipy.ai/mac/Anticipy-for-Mac.zip) and
checked-in archive both hashed to
`c27dd01e3257e2d8df99e2f5ff1a80f943b53eab01a5d9ab8431bed8186e1cbb`.
The successful curl/hash check used pipeline failure propagation; archive metadata
was read without executing the app. A preceding Python HTTP fetch returned 403,
so that attempt did not establish availability or inspect the archive.

## Team and work order

The coordinator owns integration, exact-path commits and release decisions.
Ben owns the local reconciliation and bounded audio transport repair. Waterloo
owns browser recovery and connector evidence. The independent **CEO review**
role challenges tests, privacy, source/deployment identity and completion claims;
it does not approve its own implementation. These are engineering roles, not
company titles. Omar owns the physical firmware collaboration lane.

Order: repair observed transport defects → run adversarial regressions → publish
reviewed source and docs → verify exact build/deployment → exercise installed
clients and real selected connectors → extend onboarding/memory → accumulate
unscripted acceptance. Work may run in parallel only with disjoint file ownership.

| Requirement | Current status / next action | Evidence needed to close it | Owner |
| --- | --- | --- | --- |
| Honest typed and proactive task execution | Partial. Existing ask/act/ignore, owned lanes and receipts need broader task acceptance. Unsupported API writes remain disabled. | Typed and consented speech reach the same owned workflow; real result proof, correct quiet/ask behavior, cancellation, retry and outage cases; report latency and cost separately. | Coordinator + CEO review |
| Browser pairing and reconnect | New audit reproduced a legacy credential state that can falsely appear linked. Repair in progress, not yet shipped in 0.18.2. | Actual handler regressions plus installed Chrome pairing, restart, lost heartbeat, rejection, transient outage, owner separation and one successful resumed task. | Waterloo |
| Browser action quality | Earlier frame geometry and hit-testing repairs released. | Real nested/covered/changed-page targets; refresh observations after navigation; cancel/lease fencing; no blind retry of an uncertain effect. | Waterloo + CEO review |
| Connectors and initial codes | Recovery/account/scope repairs released, real initial Google/Meet flow still unproven. | Request → provider acceptance → device receipt → redemption/OAuth → selected-account harmless read; expiry/resend/Skip/revoke and two-account tests. A badge alone is not success. | Waterloo + account owner |
| API actions that change external state | Deliberately unavailable without a durable effect ledger. | Exact approved plan/account/scope bound to execution, idempotency, crash reconciliation, uncertain outcomes and final provider evidence before enabling a write. | Coordinator + CEO review |
| iPhone audio and messaging | Build 176 available; no new physical-device acceptance claimed. | Installed build, final words, pause/resume, interruption/background/offline recovery, account isolation, one visible reply, and separately a delivered SMS. | Device owner + coordinator |
| Pendant → phone → brain | Incomplete: current app discards Opus frames; transport audit also found missing-boundary/duplicate-sequence defects. | Repaired assembler, local Opus decode, supported on-device transcription, consent and continuity, actual hardware capture and verified result. See firmware handoff. | Ben + Omar + coordinator |
| Source-selective onboarding and memory | Proposed, not integrated. No new mailbox/Messages/Notes bulk scanner is shipped. | Per-source opt-in, bounded preview/read, provenance, review/correct/delete, revoke-in-flight, restart safety, account separation, prompt-injection resistance and explicit local/cloud destination. | Coordinator + CEO review |
| Local-first / overnight | New local-source runtime and scheduling integration are not built. | Same task engine and permission ledger; bounded execution/energy/cost, cancellation and restart. A powered-off Mac cannot compute locally; cloud continuation needs separately permitted data/tools. | Coordinator |
| Mac distribution | Source compiles; signed current package unavailable. | Approved signing identity, exact-source archive, notarization/stapling, live hash, clean install, recorder/queue/restart and visible task result. | Signing owner + coordinator |
| GitHub collaboration | Released code reconciled; fresh public-safe documentation replaces bulk publication of local operational notes. | Reviewed named-path commit/PR, remote SHA, no secrets, no held changes swept in. See workspace reconciliation. | Ben + coordinator + CEO review |
| Whole-product acceptance | **Not achieved.** | Cold onboarding and an unscripted clean week as described in the product brief. A same-day test pass cannot certify a week. | Product/test owners |

## Onboarding and reference-product boundaries

The requirement is an original Anticipy experience: choose sources individually,
review what was learned with source quotes, correct or forget it, and let that
context inform the existing proactive harness. Facts, ongoing work and permission
to act must remain separate. Source text is untrusted data, never an instruction
or approval. Revocation must fence delayed reads, model completions and uploads.

“Sapient” remains unidentified. Sentient research did not integrate code or
models. Instinct parity has not been established by hands-on comparison. Do not
substitute similarly named repositories, copy third-party code without a license
review, or represent a synthetic onboarding demonstration as connected inboxes.
Native connectors and the real local-memory bridge remain actual work, not items
closed by writing this document.

## Verification and release discipline

1. Preserve the original dirty checkout. Use an isolated branch based on
   `cloudflare-backend`; never merge unrelated `main` history into it.
2. Reproduce the failure against actual source, then change the smallest correct
   contract. Run relevant regression suites and an independent adversarial pass.
   Do not reduce a gate to make it green.
3. Update native build numbers in both project representations with iOS changes.
   Keep extension manifest, runtime, expected client version, tests and shipped
   ZIPs aligned. A source fix is not an installed-client update.
4. Stage and commit explicit paths only. Inspect workflow triggers. A push/PR is
   not a backend deployment; native upload and Mac signing are separate actions.
5. Before a backend release, preserve capacity, validate schema and snapshots,
   check for active effects, and retain rollback evidence. Never clear user work
   or uncertain effects to unblock deployment.
6. Verify the live source/package and then the affected behavior. Keep source,
   local tests, CI, deployment, installation and customer acceptance separate.

Legacy overnight gates may load credentials or call paid/live services. Read a
gate before running it. Offline synthetic tests must disable dotenv loading and
deny external network where practical. No new paid calls or personal-source scans
are implied by this board. Do not run `deploy.sh` or commit env files, tokens,
phone numbers, account contents, invite links or private operational logs.

## Immediate acceptance session

Use one designated test account. Record versions and timestamps, not secrets.
Confirm TestFlight 176 is installed; send one harmless in-app greeting. Next test
phone listening with a harmless complete sentence, pause/resume and interruption.
Then install/reload the reviewed extension, pair it and test a harmless browser
task plus reconnect. Finally connect a chosen test Google account and verify a
read on that exact account before attempting any approved write.

Record expected result, observed result, source/build, elapsed time, effect receipt
and redacted failure for each case. Do not repeatedly submit a consequential task
when its first outcome is unknown. A failure reopens its row above.
