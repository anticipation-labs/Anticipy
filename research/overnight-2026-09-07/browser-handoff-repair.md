# Browser task pickup and clicking: 0.17.0 repair

Inspected from `a492703512881a935962e62e61b0d019a83b355a`, 2026-09-07.
No Mac source, iOS source, Worker routes, personal browser session, or paid model
was touched by this subtask. No commit, deployment, or extension installation was
performed by this agent.

## What was actually broken

**Click coordinates could be measured before scrolling finished.** The existing
`window.__anticipyCenter` in `extension/page_map.js` used the default
`scrollIntoView` behavior, then immediately measured the target. CSS
`scroll-behavior: smooth` makes that scroll asynchronous. In real isolated Chrome,
the production mapper returned `y=2452` for a button on a 700-pixel-high viewport.
The CDP click missed. This happened on both a smoothly scrolling document and a
nested scrolling container. A removed target also returned `(0,0)` instead of
being rejected.

**A stalled backend request could monopolize task pickup.** The background
worker awaited unbounded `fetch` calls while holding its poll lock
(`extension/background.js:1909`). The existing rescue ceiling is twelve minutes.
Registration, heartbeat, claim, and result requests all used that transport. A
connection which stops returning headers or finishes only half a JSON body is
not an empty queue; without a deadline it can prevent later work from starting.
This is a reproduced transport failure condition, not a claim that a particular
customer incident was traced to that network condition.

## Changes

- `extension/page_map.js:699`: reject disconnected or non-rendered mapped
  elements; complete the scroll instantly before measuring the point. This
  changes geometry only. No website names or task wording decide behavior.
- `extension/backend_transport.js`: give each background request a 20-second
  `AbortSignal` deadline, including response-body consumption. Preserve an
  earlier caller cancellation. Do not automatically retry a timed-out POST/PATCH.
  The server may already have accepted a write; existing lease and uncertain-
  effect recovery remain responsible for it.
- `extension/background.js:15`: all existing background `fetch` calls use that
  shared transport. Existing model request deadlines are separate and unchanged.
- Manifest and engine marker advance together to **0.17.0**. All three published
  zip aliases were rebuilt from the import graph and contain the new module.

## Proof

`node proof/audit/check_browser_click_geometry.mjs` uses actual Chrome, injects
the production page mapper, and dispatches CDP mouse events to the point it
returns. Every page and button is synthetic; all network requests are blocked.
This exercises the geometric click path, not model judgment.

| Fixture | Before | After |
|---|---|---|
| Smooth document scroll | Target point off screen; zero clicks | Visible point `(120,350)`; exactly one click |
| Smooth nested scroll | Target point off screen; zero clicks | Visible point `(120,270)`; exactly one click |
| Removed mapped target, both pages | Incorrect `(0,0)` target | `null`; no coordinate to click |

`node extension/tests/test_backend_deadline.mjs` runs a real local HTTP server
which deliberately withholds headers and stalls mid-body. Both requests abort.
It also proves no POST replay, preserved caller cancellation, and successful
recovery on the next healthy request. The suite is registered in `run_all.mjs`.

`node extension/tests/run_all.mjs`: **all 83 suites passed**, 79.04 seconds,
eight isolated test processes at a time. This includes the new network test and
existing registration, claim, lease, cancellation, recovery, and model-contract
checks. Scripted model answers in those existing suites are not live-model proof.

The rebuilt aliases have identical SHA-256:

`2e36a5de26fd89dd02336b6e3faa4f6b2523625b4fd9ec9f50ed8a0d22caaae7`

Every packaged module matches current source byte-for-byte. The aliases are:

- `migration/workers/public/anticipy-extension.zip`
- `migration/workers/public/anticipy-claude-version-extension.zip`
- `migration/workers/public/anticipy-codex-version-extension.zip`

Structured results and source hashes:
[`browser-handoff-repair-evidence.json`](browser-handoff-repair-evidence.json).
Local logs are `work/audit/browser-handoff-extension-tests.log`,
`work/audit/browser-click-geometry-before.log`, and
`work/audit/browser-click-geometry-after.log`. Screenshots are under
`output/playwright/browser-click-geometry/` and were not staged with private
historical UI artifacts.

## Deployment and installed-version limits

At inspection, the live public downloads all served **0.16.0** with SHA
`93c3a2d8c29e97031c7c81707a2fb086c01564b3d201b546e2ec1b18aa0a9ba9`.
Seven modules differed in bytes from the migration-updated checkout. The
inspected differences in `background.js`, `agent_loop.js`, and `config.js` were
comments renaming removed PocketBase paths, not a functional stale-code finding.
Do not cite those byte differences alone as the cause of failed work.

The owner’s installed extension was not inspected here. The earlier audit
recorded 0.15; that is historical evidence, not a fresh observation. Shipping a
zip does not reload an already-installed unpacked extension. After deployment,
verify the live zip bytes, installed version, and heartbeat engine marker, then
run an owned synthetic task through the actual queue and installed extension.

This repair does not establish that all browser work succeeds. Arbitrary sites,
cross-origin frames, login state, task routing, API authorization, and the
quality of model decisions still need their own evidence. Existing semantic
wording rules in `agent_loop.js` were not extended or removed by these two
mechanical fixes; zero-hardcoding compliance is not claimed.
