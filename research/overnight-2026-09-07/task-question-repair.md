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
- Full iOS logic suite passed before integration. Simulator build passed; the
  merged build 169 and release checks are recorded in the release receipt below.
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
- The existing live dinner record can be corrected with the version-checked,
  dry-run-by-default `proof/audit/repair_dropped_requirements.py`. It restores
  already declared questions and removes stale approval; it never books anything.

## Integration and limits

The Mac developer's PR #62 was merged while this work was in progress. It already
used build 168. Its changes were retained; this iPhone repair uses build 169 in
both project files. A path-limited stash kept a recovery copy, and every repair
file outside those project files was compared byte for byte after integration.

This is a bounded repair, not a claim that all of Anticipy is proven. The measured
speech backlog, recognition fragments, installed browser extension version,
and full real-world booking completion remain separate concerns. No new
third-party booking or unsolicited message was used as a release test.

Runtime deployment, current-account repair, and TestFlight availability must be
verified separately; an uploaded source commit alone is not a release receipt.

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

At 22:03 UTC Apple independently reported build 169 VALID and IN_BETA_TESTING
for the Internal group, including the owner's iCloud tester account. The backend
source readback reported all eight children running the expected source hash,
but its fleet observation subsequently became stale. That operational check
remains open until fresh snapshot and fleet observations are obtained.

The expanded live fixture also found that Cloudflare compression changed a job's
strong ETag into `W/"..."`, which the API correctly refused for a conditional
write. The same GET with identity encoding returned the strong token. Job detail
responses now include `private, no-store, no-transform`, preserving the token
without weakening stale-write protection. This applies to every job and client,
including iPhone requests. Cloudflare documents this behavior in its
[compression documentation](https://developers.cloudflare.com/speed/optimization/content/compression/).
