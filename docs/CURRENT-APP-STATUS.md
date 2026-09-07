# Anticipy app readiness

Last checked September 7, 2026, approximately 3:50 PM Vancouver time.
This is a dated readiness check, not a promise that every user journey works.

## What is live

- iPhone build **169** is available to the owner's Internal TestFlight group.
  Apple availability was independently verified; the installed phone version was
  not read during this check.
- API source: `057b293d1e1ae4e9ac33ad26b3359f760e4f429c`.
- Brain control plane: `7aee24c621bd23233162263c034f816c93e18770`.
  A fresh production status read at 22:48:48 UTC returned HTTP 200, eight served
  workers, no failed workers, and current memory snapshots for all eight.
- Local source and GitHub `cloudflare-backend` both pointed to `c67136a9` before
  this status document was added. The different runtime commits above reflect
  separately deployed components, not missing merges.

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
