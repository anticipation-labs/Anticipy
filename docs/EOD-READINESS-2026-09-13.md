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
| iPhone distribution | [iOS release](https://github.com/anticipation-labs/Anticipy/actions/runs/34743959115): 1.1.1 (176), Apple VALID and in beta testing. [Audience assignment](https://github.com/anticipation-labs/Anticipy/actions/runs/34765221900) covered all existing testers. One owner subsequently confirmed installation of 176 and a greeting reply in-app and in Messages. | Other testers' installation, all message types, voice or connector tasks. Two invitations remain unaccepted; the final audience-readiness gate is red for that reason. |
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
| iPhone audio and messaging | One owner reports build 176 installed and a greeting replied to in-app and in Messages. Audio and broader delivery cases remain unproven. | Final words, pause/resume, interruption/background/offline recovery, account isolation, broader reply/delivery cases and redacted timing evidence. | Device owner + coordinator |
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

## 2026-09-14 addendum (continuity run)

Every line here is exactly one of `live-proven` / `deployed, unproven` /
`merged, not deployed` / `in review` / `not started`. "Ships" never means done.
Candidate branch: `codex/harness-transport-20260913` (base: the released tip of
`cloudflare-backend`). Nothing in this addendum changes the 2026-09-13 snapshot
above; it records what moved on the 14th and at which rung it sits.

| Surface / requirement | Change on the 14th | Rung now | Closes when |
| --- | --- | --- | --- |
| Browser pairing and reconnect | Unpaired-row release shape fixed (`stampLastSeen`); 11 review findings fixed red-first; 0.18.3 ZIPs rebuilt; installed-client rig 10/10 in real Chrome on loopback (`proof/audit/installed_extension/`). | `in review` | api dispatch lands (→ `deployed, unproven`), then the owner's journey on the live download: pair → errand → restart → release from the phone → "Not linked" → same-code re-pair → errand (→ `live-proven`). Residue: an install upgrading from 0.18.2 with `{ownerRef, paired:false}` in storage reads "Linked" for one heartbeat. |
| iPhone receipt (build 177, pins 0.18.3) | Receipt slice identical to the released tip; native gate green with the CLT SDK; transport assembler re-sync, dead code removed. | `in review` | TestFlight upload of the merged source (`ios-testflight.yml` dispatch, AFTER the api dispatch — 177 pins 0.18.3), `asc-query.yml ASSIGN_EXISTING`, then one owner sees a receipt on the phone. |
| Connectors and initial codes | Refused sends (gap, ceilings, lost reservation, provider refusal) now draw a "No new code was sent" page; oracle for dead/spent/forged/phoneless tokens byte-identical; CONTRACT §6.12b. | `in review` | api dispatch (→ `deployed, unproven`); the designated account triggers a third resend on one link and sees the page (→ `live-proven`). The real Google/Meet start flow stays unproven. |
| In-app / API non-response | Connection-command recycle bounded to two API leases (600 s from the row's `created`): pending rows park for the factual notice, unreachable rows release to reasoning, both leave a countable `reply_diagnostic`; every API-reply replan refusal names its clause in the log. | `in review` | brain dispatch (`component=brain`, `cap=100`, preflight is the job's first step) (→ `deployed, unproven`); a live 202/503 shape observed through the metadata projection (→ `live-proven`, or stays UNPROVEN if the shape never occurs). The read-only projection script is not written yet (needs the owner's Cloudflare credentials to run). |
| Documentation for the public repository | README, ARCHITECTURE, TESTING, RELEASE, SECURITY, CONTRIBUTING + PR template, docs index, component READMEs, rig README, redaction note, MIT LICENSE, third-party notice. | `in review` (separate docs PR) | merged into `cloudflare-backend`; a follow-up redaction PR removes the personal paths/e-mails/phones the note lists. |
| Deferred on purpose today | Extra tally legs for transport counts (already pinned in `GapEngineTests`); the D3 projection script; the phone feed-window fix (D4) pending that projection; the em dash in the gap marker (SwiftUI-only consumer). | `not started` | Listed so nobody reads their absence as an oversight. |


### Adversarial review of this candidate (2026-09-14, HARNESS-LAWS Law 6)

Seven reviewers read the combined diff against the laws, the tests and the
recorded failures; each finding was then put to independent refutation. The
pass found real defects in the same day's work, and they were fixed before
commit, red-first:

- an **unreachable** connection route was released to ordinary reasoning, which
  would double-answer a plan the API may already have run — it now parks like a
  busy one, and only the diagnostic category tells the two apart;
- an event older than the bound was parked on its **first** verdict, against a
  lease that was seconds old — parking now also requires this process to have
  watched the stall;
- the browser's three-refusal liveness grace was a module global, so a run that
  ended on a refusal made the **next** errand die on one blip — it is per run;
- a wrong code typed on the "No new code was sent" page was answered with
  "enter the code from Anticipy's latest text" — the page carries its own state;
- `_flip_reply` had a **sixth** silent refusal, the conditional write's own;
- the proof rig carried a machine's home directory, a loopback guard that two
  subcommands walked past, and a process sweep matching a path substring;
- and `adoptLegacyHandBacks` stamped an untagged pre-0.18.3 hand-back with
  whoever holds the install NOW. Its premise — "before 0.18.3 an install had one
  owner" — is contradicted by the very defect this release fixes: the released
  0.18.2 rewrote `ownerRef` in place on a phone-driven owner change and cleared
  neither `handBacks` nor the owner's key and profile. An install that changed
  hands under 0.18.2 would therefore have handed owner A's parked page, and its
  URL, to owner B on B's first boot after the upgrade. The adoption is gone;
  untagged records stay invisible, which the badge, the popup snapshot and the
  closed-tab sweep already assumed. One pending notification is lost on upgrade
  for a single-owner install, and that is the whole of the cost.

**Reverted rather than shipped:** the BLE assembler re-sync. It fixes a real
stall and it introduced a way for two replayed packets to re-origin the stream
backward. Release day is the wrong day to trade a dormant defect for a live one.

**Recorded, not fixed** — open defects with a reason, not oversights:

| Open defect | Where | Why not here |
| --- | --- | --- |
| Two asks on one live link separate "the owner is textable" from every other condition, because the refusal legs sit below the phone lookup | `migration/workers/src/routes/connect_auth.ts` | The obvious repair makes the FIRST ask separate a live phoneless link from a dead one — a strictly stronger one-request oracle — and writes rate-limit rows for an owner who can never be texted. A mutant in the suite shows it breaking the oracle leg. The tell is now priced in the file header and in CONTRACT 6.12b, and a new test pins the behaviour actually claimed. |
| A pendant reboot can convert the re-origin distance into up to 32,767 "missing notifications"; a counter-corrupt stream can write a journal line and a feed marker per notification | `app/ios/Anticipy/BLE/` | Same root cause as the reverted re-sync: the wire format has no session epoch. Pendant capture is not live. |
| Two call sites build an owner scope from the unqueued default generation instead of `currentOwnerScope()` | `extension/background.js` | Narrow race, no observed failure; listed so it is not rediscovered as new. |
| A `created` stamp ahead of this host's clock is treated as unreadable — correct, but the try-backstop already covers that path, so no test can tell the guard from its absence | `brain/worker.py` | Kept for intent; its mutant survives, and that is recorded rather than hidden. |

Mutation evidence for what did ship: 30 mutants run across the four areas, 29
killed. The one survivor is the clock-skew guard above.

Order of operations for the release (each gated by the previous one's evidence):
PR checks green → owner merges → **owner dispatches api** (`brain-deploy.yml`,
`component=api`, `confirm=DEPLOY`; verify `x-anticipy-revision` on
`/api/health` and the three ZIP hashes, never the exit code) → iOS dispatch +
`ASSIGN_EXISTING` (build N read from the run log) → owner dispatches brain
(`cap=100`) → live checks → the owner's installed-client and phone journey.

