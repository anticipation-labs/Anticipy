# Anticipy app readiness

Backend last checked September 7, 2026, 6:24 PM Vancouver time.
Phone and installed-extension observations below retain their earlier timestamps.
This is a dated readiness check, not a promise that every user journey works.

## What is live

- iPhone build **170** is available to the owner's Internal TestFlight group.
  Apple availability was independently verified at 01:29:13 UTC on September 8
  by query 34176788640; the installed phone version was not read during this check.
  Build 170 updates the extension-version warning; build169 carries the earlier
  task-card and delivery-status repairs.
- API and brain source: `cb2010957877eec0a8c67138b57060dc1bef3110`.
  A direct production read at 01:24:55 UTC on September 8 returned HTTP 200,
  all eight workers running the exact source with current memory snapshots,
  and zero failed archive cleanups. API version:
  `af5a0a33-ab22-4cab-8d38-ecc108e3e343`.
- Extension **0.18.0** is published: all three downloads match committed bytes,
  SHA-256 `4e409dcec8fa01669fe07fb60e83ef14870bf6cd0327a9db7a65e346b2a4690a`.
- The overnight scheduled follow-up is **PAUSED**. The fixture API on 8788 and
  audit model gateway on 8790 are stopped; spend/evidence files are retained.
- [Reply-priority repair and evidence](../research/overnight-2026-09-07/reply-priority-repair.md):
  direct answers precede the speech backlog and retain earlier quoted context
  through task execution. 3,033 Python tests (2 skips), 83 browser suites and
  the iOS checks passed. Real-model lost-links and fiction cases passed;
  isolated Chrome read the retained URLs and returned both fixture prices.
  [Live release receipt](../research/overnight-2026-09-07/reply-priority-release.json).

## Latest backend repairs and synthetic lab

Fifteen fictional owners exercised transcripts, separate SQLite memories,
short replies and task persistence. The lab repaired lost text-task context,
premature API-read completion, misleading amendment replies, malformed connection
decisions and invented memories. Seven real Chrome fixture cases, five connection
dispatcher cases and 24 API fault checks passed. The full Python suite passed
3,024 tests with two skips; the Worker suite and typecheck passed.

These are simulated provider/texting and isolated Chrome proofs. They do not
establish the owner's installed browser, real OAuth or carrier delivery.
See the [complete lab report](../research/overnight-2026-09-07/persona-lab-status.md)
and [live release receipt](../research/overnight-2026-09-07/persona-lab-release.json).

## What the user should experience

The intended flow is: **say or type something → understand it with context →
ask for what is missing → get any required connection/approval → do the work →
verify the result → show the same outcome in the app and text conversation.**

Build 169 repairs discarded task questions, partial-answer retention, stale
approvals, incompatible research routing, and task-specific text status. The
live dinner task now asks for its missing time and has no execution approval.
Its matching notification record says the daily outreach limit paused texting.
That limit remains enabled; the repair exposes the reason rather than changing
notification preferences silently.

## What still prevents a complete readiness claim

| Area | Evidence | Required next proof |
|---|---|---|
| Installed browser | The owner's paired Chrome agent reported **0.15.0** at 22:49:54 UTC. The published ZIP now contains **0.18.0**, verified byte-for-byte above. | Load the repaired extension, verify its new heartbeat, and complete a harmless task through that installed extension's queue and result receipt. Updating TestFlight does not update Chrome. |
| Browser execution | Earlier live-model synthetic-page tests passed comparison, appointment form, login handoff, capacity and hostile-content cases. One comparison traversed the live queue with adapted extension plumbing. Geometry fixes were separately tested in real Chrome. | Those proofs do not establish arbitrary bookings or task completion in the owner's installed browser. |
| API connections | Earlier live stored-event tests passed app listing, link creation, contextual acceptance, quoted-command rejection and task-card routing. | Complete real provider authorization, read an agreed record, and resume the original task. A connection link or catalog match alone does not prove these steps. |
| Proactive understanding | Conversation-led discovery is wired. The whole-conversation sorter remains non-acting; several other signal collectors have no production input callers. Registered legacy semantic heuristics remain. | Complete those integration paths using contextual model decisions and test against both actionable and non-actionable conversations. Global absence of word-based reasoning is not established. |
| Listening speed | The earlier incident measured a substantial speech-processing backlog. Reply scheduling is now repaired and verified in a simulated-clock main-loop test. | Measure fresh phone transcript-to-question/result latency. An in-flight decision, import or other serial duty can still delay replies; worker health does not prove fast listening. |

Direct inspection or modification of Chrome's extension settings was blocked by
the browser tool's URL security policy. No alternate browser-control route was
used to bypass it. The extension version above comes from Anticipy's server-side
heartbeat, not from a claim to have inspected or updated Chrome's settings.

## Evidence to read

- [Latest task/text repair and release receipts](../research/overnight-2026-09-07/task-question-repair.md)
- [Repository wiring and integration audit](../research/overnight-2026-09-07/repository-integration-audit.md) — earlier snapshot; current component versions are above.
- [Browser repair and test boundaries](../research/overnight-2026-09-07/browser-handoff-repair.md)
- [Live browser cases](../research/overnight-2026-09-07/browser-production-results.json)
- [Live queue case](../research/overnight-2026-09-07/browser-queue-results.json)
- [Live connection-command cases](../research/overnight-2026-09-07/connection-live-results.json)

The release is usable for further development and testing. The evidence does
not yet support calling it an entirely reliable, investor-ready product.
