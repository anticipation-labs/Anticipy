# Browser queue ownership — 8 September 2026

Inspected at `cloudflare-backend` commit `7f319726`. The changes below are local
source changes, not a deployment or proof about the owner's installed browser.

## Reproduced failures

1. **Phone tasks could starve Chrome's queue.** `claimJob()` reads the oldest ten
   queued workflow rows. `BROWSER_LANE` excluded research and API work but still
   included `device_calendar`. Ten calendar rows filled that page; the server
   refused all ten claims, and the browser row behind them was never reached.
   The same filter also controlled the stale-job sweep, which could attempt to
   recover work belonging to the phone. Supervised reads were excluded only by
   their normally empty workflow ID; workflow metadata on such a row made it
   eligible for the general action runner.
2. **A lost claim could look like a running browser.** The popup's current-job
   mirror was written before the claim PATCH. A guard rejection or another
   browser winning the lease left "picking this up" on screen for a task this
   browser would never start, sometimes replacing a valid previous result.

## Changes

`extension/background.js` now excludes the device-calendar and supervised-read
lanes in the same shared filter used by claiming and recovery. Supervised reads
retain their separate watched-reader claim path. The current-job mirror is now
published only after the returned claimant, running state and lease token prove
that this browser owns the task, still before model calls or tab creation.

These checks compare stored lanes and lease identity. They add no natural
language classification, model calls, auto-approval, or replay of a write.

## Local evidence

`node extension/tests/test_browser_queue_ownership.mjs` runs the production
filter compiler over the production SQLite schema and drives the real
`claimJob()` function. Its PATCH boundary supplies deterministic claim refusals
and competing lease winners. Four of five scenarios failed before the changes;
all five pass afterward:

- Ten phone jobs followed by one browser job: only the browser row is claimed.
- A supervised-read row carrying a workflow: the action runner does not claim it.
- A refused claim preserves the previous completed result.
- A competing lease winner leaves no false picking-up card.
- A competing lease winner does not prevent claiming the next runnable row.

The existing `test_api_lane_is_not_browser_work.mjs` additionally drives both
the queue poll and the alarm-triggered sweep through that same compiler and
schema. Browser work stays visible; research, API, phone and supervised-read
work stay excluded. The server-side `api-lane-claim.test.ts` remains green:
24 checks passed, 0 failed.

`node extension/tests/run_all.mjs`: **84 suites passed**, exit 0, 74.28 seconds.
The new suite is registered in the runner. `git diff --check -- extension`
passed. Scripted model replies elsewhere in those suites prove wiring and
guards, not the quality of a live model's judgment.

## Handoff diagnosis and remaining proof

The earlier `research/2026-09-07-browser-hand-gets-no-job.md` records a different
failure: the brain stamped an `act` decision but produced no jobs row. Chrome
polling cannot recover an instruction that was never queued. Current source
runs the direct act branch through `brain/anticipy_core.py`'s `_queue_job()`;
the worker subsequently stamps the returned decision. That stamp alone is not
evidence of a successful mint. A historical `act`/no-row observation does not
identify which dedupe, refusal or failed-write path was taken.

The layer audit also identifies the brain's connections read as unavailable;
the API route and its owner boundary need their own fix and proof. Neither that
route nor brain behavior was changed by this extension subtask.

This change removes one concrete cause of queue starvation. Ten malformed
browser-lane workflow rows can still occupy the first page; general pagination
around permanent poison rows is separate remaining work. The existing code
accounts for malformed rows in the popup, but does not paginate past ten.

No production request, owner's Chrome profile, paid model, extension install,
version bump, zip rebuild, push or deployment was performed by this subtask.
Before a release claim, build the extension artifact from the reviewed source,
verify served bytes and the installed version, and run an approved synthetic
task from the real queue through that installed extension. Law 3 remains
unproven until that live evidence exists.

## Release preparation, inspected but not performed

Four pins must advance together from 0.18.0: `extension/manifest.json` version,
`extension/background.js` ENGINE_BUILD,
`app/ios/Anticipy/AnticipyApp.swift` expectedExtensionVersion, and
`app/ios/Tests/StaleExtensionTests.swift` expected. A patch release can use
0.18.1; no pin was changed in this subtask.

`sh extension/build-zip.sh` derives the Chrome module graph, normalizes archive
timestamps/order, and rebuilds all three aliases in `migration/workers/public`.
It verifies the packed version and module graph. Also run
`tests/test_extension_version_pin.py`,
`app/ios/Tests/run_stale_extension_tests.sh`, and the extension suite, then
compare every packaged module with source and all three SHA-256 values.

The current API Worker's `npm run deploy` directly invokes Wrangler; it does
**not** rebuild or stage the extension. Earlier handoffs mentioning an automatic
`stage:assets` step are obsolete. The committed `migration/workers/public`
directory is now the configured static-asset source. Publishing therefore
requires the freshly reviewed archive to be present before an authorized API
Worker deployment, followed by live-byte and installed-version checks.

The Python cross-layer contract in `tests/test_api_lane.py` was also updated
to require the exact five conjunction clauses without depending on their
order. The API-lane and extension-version-pin tests passed together: 25 tests.
