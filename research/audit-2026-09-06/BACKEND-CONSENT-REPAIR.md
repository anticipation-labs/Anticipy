# Spoken approval and concurrent task changes — 2026-09-07

The live brain's `_GO_AHEAD_RE` authorized a held task from sentence shape.
It selected the newest row and treated unreadable creation timestamps as now.
That violated HARNESS-LAWS.md and could authorize a different task from the one
the owner meant. A second race allowed a task amendment/cancellation made during
judgment to be overwritten by the old approval.

## Implemented

- Removed the approval regex and the conversation-word-count shortcut from this
  authorization path. A separate four-state model judgment receives the complete
  supplied conversation, owner utterance, speaker evidence, and every held task
  in the bounded candidate read. It selects an explicit task ID. No answer,
  refusal, ambiguity, changed conditions or unknown task IDs authorize release.
- Use the configured strong model with refreshed owner identity. Single-word yes
  and unfamiliar wording reach this judgment before legacy prose prefilters.
  SMS, known other speakers and an armed meeting retain their separate routing.
- Reject absent/future/expired timestamps, incomplete candidate pages, malformed
  parameters and missing tenant identity. Older cards stay visible to the model
  as ambiguity evidence; their age cannot by itself select a recent card.
- Re-read the selected row after judgment, retaining corrections and canonical
  workflow checks. Store the actual words and selected job in approval evidence.
- Job reads expose an ETag over authority fields. If-Match is enforced in the
  actual D1 UPDATE predicate, using the same row checked by the policy chain.
  Stale/repeated approvals return 412 and do not change the row. The brain refuses
  to release through an API that does not advertise this support.

## Evidence before deployment

- 18/18 real Gemini 3.1 Pro consent cases passed; all 18 paid calls returned.
  Includes French approval, older-task selection, refusal, conditions, changed
  recipient, quotation, sarcasm, a caller's agreement and malicious source text.
  `spoken-consent-results.json`; private raw provider receipts remain under work/.
- 48 focused Python checks; full Python run before the final three additional
  focused checks: 3,019 passed, 2 skipped. No iOS source changed.
- All 35 Worker suites passed; typecheck passed. Fourteen new SQLite checks cover
  recipient/scope changes, cancellation, ownership change, two interleaving writes,
  replay, malformed preconditions and tenant boundaries.
- Real local workerd API: 21 account/ownership/approval/erasure checks passed.
  The first attempt reached an uninitialized local database; the configured Mac
  workspace environment was then used and the complete proof passed.
- Total observed paid audit cost after this proof: US$2.460962; no unresolved
  reservations. The user-authorized ceiling remains US$50.

## Release order and remaining scope

Deploy and verify API first, then brain; verify every running brain source hash.
Live release evidence will be appended after those checks complete. This file
is not a claim that all legacy intent rules or integrations are production-ready.
Google Calendar authorization, the selective historical erasure of the real
account, the complete legacy meaning audit and fresh-phone verification remain.
The owner's production account has not been deleted.
