# The harness and two-day phone trial

Current handoff, 2026-09-07 UTC. This document supersedes earlier handoff-status
paragraphs for the account reset and TestFlight access. Technical evidence remains
in the adjacent JSON files; customer identifiers and raw deletion receipts are
private under work/audit.

## Product understanding

Anticipy is an ambient chief of staff: notice useful work in a person's day,
remember its source, ask at a useful moment, prepare or execute authorized work,
and report what actually happened. It should not require a perfectly worded
command for every useful moment. A quote is evidence, not permission. Another
person's promise must not silently become the owner's task.

The harness is the system around the model: capture, event transport, context,
memory, judgments, work records, permissions, execution hands and receipts.
Text is the common representation. Phone speech is transcribed on device; typed
lines, app replies and SMS replies arrive as events. Stored read evidence also
feeds context and memory with provenance. This is not a keyword-command bot.

## Source-verified architecture

- iOS `AnticipyBackend.pushEvent` posts text, capture times, source, speaker and
  idempotency identity to `/api/collections/events/records`. Raw microphone audio
  is not the payload of this path.
- A Cloudflare API Worker authenticates accounts and stores product rows in D1.
  The PocketBase-shaped HTTP contract is compatibility, not the current server.
- Per-owner Python processes in Cloudflare containers consume events and jobs.
  SQLite stores each owner's memory; R2 snapshots preserve it across replacement.
- Contextual models decide meaning. The repaired consent path uses a separate
  four-state question; unknown cannot authorize. Workflow records carry plan and
  source evidence. Database preconditions refuse stale approvals.
- Research, Composio APIs, a paired Chrome extension, and eligible device-local
  execution are separate hands. Receipt evidence must support the result.
- `hands.gather_context` currently sets `rung=NO_LEDGER_RUNG`. Its structural
  floors send connected-app writes toward the browser because the minimum write
  level is not available. This is a material phone-only limitation, not an OAuth
  success guarantee.
- OpenRouter transports brain model calls. The default source model is DeepSeek
  v3.2; current deployed stronger judgments were verified as Gemini 3.1 Pro preview.
  Apple Speech handles phone transcription; Sendblue/Twilio handle message paths;
  Composio supplies OAuth, catalogs and execution. CI/Apple handle iOS delivery.

## Concrete handoff

- App Store Connect run 34092989135 verified build 159 VALID and IN_BETA_TESTING.
  The exact supplied TestFlight email was already in Internal, state INSTALLED.
  The helper sent no duplicate invitation. This state does not identify which
  build is installed on the actual phone. The user subsequently confirmed
  "Build 159 and fresh signup are visible" on their iPhone.
- Existing upload 159 has the same iOS tree as this branch. No iOS source edit or
  duplicate upload was necessary for this handoff.
- The user renewed authorization for a blank slate. The verified operator reset
  returned HTTP 200 and account_deleted=true. It removed 244 events, 10 jobs,
  9 segments, one profile, one password-reset record, two connection codes and
  19 connection links. No provider-side revocation was reported as outstanding.
- The purge ledger subsequently confirmed current memory erasure complete. The old
  owner is absent from the serving fleet and live event/task/profile reads return
  zero rows. Full historical erasure is not yet certified;
  shared legacy backup review remains separate. Do not label this complete.
- Phone instructions: TestFlight > Anticipy > Update; check 1.1.1 (159). If the
  previous local account is visible, Settings > Privacy & Data > Forget me on this iPhone. Sign up
  again, choose capture permissions, reconnect apps and pair the browser anew.

## Trial and failure evidence

Day one: an ambient useful detail, a correction, someone else's promise and a
pause/resume. Day two: a task across two sources, one bounded action, a changed
mind, and the browser unavailable. Use ordinary situations, not only commands.

For an issue retain time, exact words, expected outcome, actual screen/state, and
whether the Mac/network/connection was available. Existing release UI exposes
Settings > Listening > Listening activity > Send me the whole
log. Investigate the first divergence in capture, context, judgment, authority,
execution and receipt, using source event IDs and job history.

## Evidence limits

The 18 consent cases used a real model and local HTTP/database, not real outgoing
contracts. Live API checks separately exercised stale approval rejection. Browser
experiments used the actual extension loop and real models with authored page
observations, not live provider effects. Fifty synthetic people and 101 contacts
are not fifty finished real-world tasks. Remaining meaning shortcuts are listed
in HARNESS-LAWS.md and the historical Law-1 audit; recent repairs do not certify
their wholesale removal. Physical phone capture, battery, interruptions and
speaker performance require device evidence. Do not claim perfection.

## Deliverables

`proof/audit/field_guide.py` builds the illustrated phone-sized PDF. The existing
FIFTY-EXEMPLARS.md is the full corpus with context and intended outcomes. The
narration explains the same architecture without claiming unexecuted effects.
