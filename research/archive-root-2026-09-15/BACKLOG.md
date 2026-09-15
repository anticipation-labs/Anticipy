# BACKLOG — one line each. Touched only if it breaks the Week A → spike → Week B chain.

## From the wire verifier, 2026-09-06 (all LOW, none blocks the chain)
- ~~DONE 2026-09-06~~ worker.py:2061 release_stranded_api parks/requeues from the DECLARED effect; the route executes the TIGHTENED one, so a stranded write declared as a read can be re-run. Fix: sweep reads the effect the route wrote back onto the row.
- ~~DONE 2026-09-06~~ worker.py:2221 `code in (401, 404)` conflates the route's own 404 "no such job" (row vanished between claim and POST) with "route not deployed"; releases a dead row and pauses the lane 300s.
- ~~DONE 2026-09-06~~ hands-api.test.ts:611 auth-failure leg always sends body owner == row owner, so feeding the body's owner to markNeedsReconnect would keep 39/39 green (M10 survived).
- research_lane.ts:44 a shipped extension can claim lane="api" (EXCLUDED_LANES has no "api"); grip round is fixing.
- hands.py:153 no planner names a tool; every api job refused tool_required → browser lane; grip round is fixing.
- HARNESS-LAWS Law 4: the two holes above are recorded in docstrings/tests only, no research/ note.

## From the wire builder
- system-invariants.yml runs pytest + extension only; migration/workers `npm test` (1091 checks) runs in no CI. Grip round is adding the job.
- run_research_jobs' no-key handback PATCH {"lane": ""} is refused by research_lane.ts LEG 2 on Cloudflare; the api route does handbacks by direct D1 write instead. Pre-existing.

## From the iOS-complete round
- mail_hosts is empty on every catalog row (measured: the vendor publishes no MX-shaped field; Google/Microsoft exchangers cannot be derived without a public-suffix list). MX seeding pre-ticks nothing until an honest path exists.
- ConnectOnboardingPolicy.serverRecordsTheSoftSnooze is false because nudge.ts recordSkip still reaches recordDecline (real level-1 decline) on an onboarding skip; the migration is applied, the WRITE is not. Week B — frozen.

## From the grip verifier, 2026-09-06 (planner + claim floor + CI job)
- hands_api_tools.ts: the planner's catalog route was MISSING on the Worker (HIGH) — built and deployed 7c302a49 the same hour; leg to watch: GET /hands/api/tools -> 401 no-token, 200 with token.
- api-lane-claim.test.ts was not in `npm test` — added before the end-to-end leg, same deploy.
- system-invariants.yml `worker` job has no in-repo pin; deleting it is silent (Law 4).
- ~~DONE 2026-09-06~~ test_api_lane.py:361 pins the OLD BROWSER_LANE literal by design and is red in CI; either flip it or mark it expired.
- research_lane.ts:162 claim leg keys on the claimant NAME; a browser that types `worker-api` passes. Pre-existing, pinned, not fixed.
- hands.py:696 a hint-less vendor row keeps the model's declared effect; a hint-less write declared "read" runs as a read. Measured: none of the 3 toolkits probed have hint-less write tools.
