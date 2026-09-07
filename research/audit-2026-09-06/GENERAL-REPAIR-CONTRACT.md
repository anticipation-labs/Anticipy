# General repair contract for interpretation and notification

Status: design and source review, not an implemented or deployed repair.
Follow-up to MISSING-TEXT-2026-09-07.md.

## Root causes

1. Interpretation permitted an assumption to change whether work was already
   completed or still needed. Missing execution details were then treated as
   the only uncertainty, even though the existence of a new task was unclear.
2. A persisted waiting task is visible independently of its notification.
   The initial question can be deferred by an in-memory policy path, while
   the worker's dedicated blocked-question sweep only selects `needs_user`.
   The reported task is `awaiting_confirm`, so that sweep cannot recover it.
3. UI text derives delivery expectations from phone validity. It has no
   receipt supporting the claim for the particular question.

The general problem is consistency between interpretation, task state, and
notification state. Removing the midnight condition alone does not solve it.

## Required behavior, independent of task wording and provider

- Determine whether the source describes completed work, a new intention,
  someone else's commitment, a hypothetical, or unresolved meaning using a
  model with the full relevant conversation. Unresolved meaning cannot
  silently become a new action. Clarification can precede creating a task.
- Each outstanding question has a durable identity tied to its owner, task,
  and the relevant task revision. Its pending state survives a worker restart.
- Every send path for the same question uses that identity. Simultaneous
  workers and retries cannot each send it. A materially changed question is
  represented by changed structured task state, not a word-overlap threshold.
- Keep queued, deferred with reason, attempted, provider accepted, delivery
  confirmed, failed, and outcome unknown distinct. A timeout after provider
  acceptance must not automatically produce a second message.
- Phone removal, account erasure, task cancellation, an answered question,
  and a newer revision invalidate stale pending delivery before the effect.
- Questions arising during active use need an explicit timing policy distinct
  from unsolicited scheduled suggestions. Any delay must be visible.
- Render actual per-question state in the app. Phone validity is a routing
  prerequisite, not an attempted or delivered message.

## Reuse and integration points inspected

`brain/worker.py` already implements `record_notification_status`,
`notification_was_attempted`, and `claim_notification_attempt` for completed
jobs. These use exact durable external event IDs and keep result persistence
separate from sending. Question delivery should share this underlying claim
and evidence discipline instead of adding another independent sender.

The current helpers are job-result-specific; they do not establish complete
question delivery or provider receipt reconciliation. `ask_about_stuck_jobs`
also retains word-overlap deduplication. Reusing its entire behavior unchanged
would preserve that Law-1 violation.

## Regression families required before calling the repair complete

| Family | Variations | Required outcome |
| --- | --- | --- |
| Meaning | Completed, unfinished, corrected, quoted, hypothetical, other person's promise; unrelated calendar/payment/document examples | No invented new obligation; relevant clarification or preparation |
| Context | Bare ambiguous phrase versus the same phrase resolved by earlier conversation | The context changes the verdict appropriately |
| Timing | Daytime, midnight active use, ongoing conversation, scheduled unsolicited suggestion | Explicit, observable timing; no lost question |
| Delivery | Missing/removed phone, provider refusal, acceptance without final receipt, timeout | Accurate state; no false delivery claim or blind duplicate |
| Recovery | Restart before claim, after claim, after provider acceptance, after receipt write failure | Durable state; ambiguous effects are reconciled |
| Concurrency | Two workers, duplicate webhook, app and text answers, task revision during send | One current question; no stale action or duplicate effect |
| Isolation | Different owners and tasks with similar wording | No cross-owner routing or word-based suppression |

These are acceptance requirements, not claims that these tests were run. The
prior incident's frozen-time reproduction and live readbacks remain the
evidence currently available. The owner's field trial should add examples to
these families; it must not be the first check for missing sends or invented
authorization.
