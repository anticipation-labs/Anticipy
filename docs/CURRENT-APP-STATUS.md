# Anticipy app readiness

Backend last checked September 7, 2026, 5:14 PM Vancouver time.
Phone and installed-extension observations below retain their earlier timestamps.
This is a dated readiness check, not a promise that every user journey works.

## What is live

- iPhone build **169** is available to the owner's Internal TestFlight group.
  Apple availability was independently verified; the installed phone version was
  not read during this check.
- API and brain source: `61db0e7dc7ca8c2cb7bad11bfa7f36d73aecc2ea`.
  A direct production read at 00:14:24 UTC on September 8 returned HTTP 200,
  eight running served workers with matching source and current memory snapshots,
  and zero failed archive cleanups. The API URL serves the same commit and
  version `f1e83a35-63a2-421a-ab9c-880239650d08`.
- That repair commit was pushed to `cloudflare-backend`; the lab/report commit
  adds reproducible evidence without changing the deployed runtime source.

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
| Installed browser | The owner's paired Chrome agent reported **0.15.0** at 22:49:54 UTC. The public ZIP was freshly checked and contains **0.17.0**, SHA-256 `2e36a5de26fd89dd02336b6e3faa4f6b2523625b4fd9ec9f50ed8a0d22caaae7`. | Load the repaired extension, verify its new heartbeat, and complete a harmless task through that installed extension's queue and result receipt. Updating TestFlight does not update Chrome. |
| Browser execution | Earlier live-model synthetic-page tests passed comparison, appointment form, login handoff, capacity and hostile-content cases. One comparison traversed the live queue with adapted extension plumbing. Geometry fixes were separately tested in real Chrome. | Those proofs do not establish arbitrary bookings or task completion in the owner's installed browser. |
| API connections | Earlier live stored-event tests passed app listing, link creation, contextual acceptance, quoted-command rejection and task-card routing. | Complete real provider authorization, read an agreed record, and resume the original task. A connection link or catalog match alone does not prove these steps. |
| Proactive understanding | Conversation-led discovery is wired. The whole-conversation sorter remains non-acting; several other signal collectors have no production input callers. Registered legacy semantic heuristics remain. | Complete those integration paths using contextual model decisions and test against both actionable and non-actionable conversations. Global absence of word-based reasoning is not established. |
| Listening speed | The earlier incident measured a substantial speech-processing backlog. | Repair the bottleneck and measure fresh transcript-to-question/result latency. Worker health does not prove fast listening. |

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
