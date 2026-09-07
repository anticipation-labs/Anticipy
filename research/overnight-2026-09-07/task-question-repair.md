# Task questions, approvals, and text delivery — repair record

## What failed

The dinner task was missing a time. `_required_from_missing` discarded questions
longer than four words, so the stored workflow had no required facts and offered
Approve. The task also declared an external effect but was routed to a read-only
research worker, which could not execute it and returned a generic account/device
blocker. These were Anticipy defects.

The original proactive text was subject to an already exhausted daily allowance.
The later text, sent after approval, was confirmed DELIVERED by SendBlue. Its
provider timestamps were about 1.7 seconds apart. The app's original caption did
not read that task's delivery receipt. The records do not support blaming that
incident on a SendBlue delivery outage. See [the incident evidence](dinner-delivery-incident.md).

## Changes

| Area | Repair | Protection |
|---|---|---|
| Missing information | Preserve every model-declared question as an opaque required key | No language, word-count, or field-name classifier decides which questions matter |
| Corrections | Model sees the existing task, constraints, and new conversation together | Missing/invalid verdict preserves the old plan; adopted details must remain in the executable goal |
| Several answers | Store partial answers in workflow facts before asking the remaining question | A later answer retains earlier facts; amendments invalidate stale approvals |
| Executor | Give the router the task's declared effect; reject research for external actions | Ask again or hold when there is no capable verdict; no invented connection request |
| Text questions | Use the same persistent message, outbox, provider handle, and receipt machinery as chat replies | Stable identity, fresh owner/version/status/question check, no blind resend after uncertain provider response |
| Pauses | Persist quiet-hours, ongoing-conversation, daily-limit, follow-up-limit, phone-unavailable, and policy-read failure reasons | UI distinguishes scheduling from delivery |
| iPhone | Match delivery metadata to the exact task version and question | Clear old captions when jobs change; missing evidence remains unknown |

The existing daily outreach limit remains in force. Its policy is now visible;
this release does not silently remove it or promise every proactive question
will arrive immediately.

## Evidence

- Full Python regression run: 3,021 passed, two optional live tests skipped.
- Full iOS logic suite passed again on the committed build 169 after integration.
  Its simulator build also passed.
- [Live model cases](task-revision-live-evidence.json): five synthetic cases,
  covering a location correction, acknowledgement without an answer, a
  manufacturing requirement, French context, and quoted hostile instructions.
  These exercise the production reconciliation prompt/parser with a live model,
  not the complete listening-to-execution path.
- [Live storage checks](task-delivery-live-evidence.json): a disposable account
  exercised persisted pause metadata, duplicate publication, signed-in metadata
  reads, and cancelled-question suppression. No phone number or provider send.
  The account and its records were deleted afterward.
- The first model run exposed an incomplete goal: new details were put only in
  facts. The prompt was corrected and all five cases were rerun. This finding
  is why mocked tests alone were insufficient.
- The existing live dinner record was corrected with the version-checked,
  dry-run-by-default `proof/audit/repair_dropped_requirements.py`. It restored
  the already declared time question and removed stale approval. The fresh
  readback is recorded in [current-task-repair-evidence.json](current-task-repair-evidence.json).
  No reservation was made.

## Integration and limits

The Mac developer's PR #62 was merged while this work was in progress. It already
used build 168. Its changes were retained; this iPhone repair uses build 169 in
both project files. A path-limited stash kept a recovery copy, and every repair
file outside those project files was compared byte for byte after integration.

This is a bounded repair, not a claim that all of Anticipy is proven. The measured
speech backlog, recognition fragments, installed browser extension version,
and full real-world booking completion remain separate concerns. No new
third-party booking or unsolicited message was used as a release test.

Runtime deployment, current-account repair, and TestFlight availability were
checked separately; their receipts appear below.

## Live repair exposed an API transition mismatch

The first attempt to repair the existing record was rejected before changing it.
The API's lane policy permitted only the older research handback, and its state
table did not allow a blocked task to return to an answer card. Python's workflow
merge supported that transition. This also affected partial answers to blocked
work; local Python tests could not establish API compatibility.

The API correction permits a held revision only with exactly one version advance,
the same owner and plan, no active lease/receipt/uncertain effect, and no retained
approval. Returning an incompatible research task to the browser additionally
requires the authenticated worker, a consequential external-effect declaration,
and the new browser hand declaration. Browser claimants cannot perform this
rewrite. Twenty-seven adverse-case policy checks, the complete Worker suite on
Node 24, and TypeScript checking pass. The live fixture now traverses creation,
approval, claim, pause, and revision before checking a repeated-write conflict.

The expanded live fixture also found that Cloudflare compression changed a job's
strong ETag into `W/"..."`, which the API correctly refused for a conditional
write. The same GET with identity encoding returned the strong token. Job detail
responses now include `private, no-store, no-transform`, preserving the token
without weakening stale-write protection. This applies to every job and client,
including iPhone requests. Cloudflare documents this behavior in its
[compression documentation](https://developers.cloudflare.com/speed/optimization/content/compression/).

## Release receipts — September 7, 2026

| Component | Published source | Independent result |
|---|---|---|
| iPhone 169 | `6ea3e90808ec0a896e33200416e7c9e573d62204` | [CI upload](https://github.com/anticipation-labs/Anticipy/actions/runs/34164572941) succeeded. [Apple query](https://github.com/anticipation-labs/Anticipy/actions/runs/34165311488) at 22:03 UTC returned VALID and IN_BETA_TESTING for Internal, including the owner's iCloud tester account. This proves availability, not installation of 169 on the phone. |
| API | `057b293d1e1ae4e9ac33ad26b3359f760e4f429c` | [Deployment](https://github.com/anticipation-labs/Anticipy/actions/runs/34166076544) verified the live revision. The complete disposable-account task lifecycle passed against production afterward; stale writes remained rejected. |
| Brain | `7aee24c621bd23233162263c034f816c93e18770` | [Deployment](https://github.com/anticipation-labs/Anticipy/actions/runs/34166553818) succeeded. Subsequent live observations are preserved in [fleet evidence](task-repair-fleet-evidence.json), including the temporary unhealthy observation instead of hiding it. |
| Current task | Version 3, draft | The only remaining required question is “What time should I schedule the dinner for?” The matching delivery event records `text_daily_limit`; build 169 can show that explanation. |

Deployment verification exposed an additional operational defect: fleet health
observations stopped refreshing. The warm health path used the container startup
helper even when the container was already running. It now reads the control
port directly for running containers, with a bounded request, while retaining
cold startup and the owner-erasure lock. Tests cover warm reads, cold starts,
read failures, and startup failures. A failed health read cannot restart a
running worker. The fleet, erasure, and status tests and TypeScript checks pass.

The first deployment's verification run was cancelled after its observation
stalled; cancellation did not stop the running backend. After the later rollout,
the status became fresh but some workers initially lacked a snapshot receipt.
Follow-up observations returned all eight workers healthy with current snapshots
and the expected Python source hash
`51a967420053e554c96e659d5b6e3ba77f28d2969c30a5e39d71b68c06acdca1`.
These are observations over minutes, not a long-duration reliability claim or
proof of the underlying provider's reason for the earlier interruption.

## Why this repair applies beyond the dinner example

Human meaning is reconciled by the model using the existing task, conversation,
constraints, and new evidence. Every declared question survives unchanged as a
required key; there is no dinner vocabulary, short-question cutoff, or keyword
rule deciding whether an answer counts. The five live cases span different
tasks and languages, and one exposed a defect that was corrected before release.

Code still enforces ownership, versions, leases, approvals, delivery identities,
and notification scheduling. Those checks govern authority and transport. They
do not interpret the meaning of a person's words. This repair removes the
identified semantic heuristics from this path; it is not a claim that every
semantic decision everywhere in the repository has now been audited.
