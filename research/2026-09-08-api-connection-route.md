# Brain connection read — 8 September 2026

The layer audit reproduced a missing route: `brain/hands.py` read
`/api/collections/connections/records`, but the Worker does not expose that
collection. Every API verdict therefore lost its connection evidence and fell
back to the browser.

## Repair in this working tree

The brain now reads `GET /hands/api/connections?owner=<owner row id>` with its
existing service-token client. A dedicated read-only route was chosen over
adding a generic collection: connections uses `user_id`, has no PocketBase
record id, and its settings mutations already have purpose-specific handlers.
Adding it to the records allowlist would unnecessarily expose generic writes.

The new route checks the service token before querying storage, requires one
owner row id, and uses the existing `connectionsForOwner` store. That store
binds the owner in SQL and independently rejects mixed-owner results. The
reply projects only toolkit, alias, connection status and write-toggle state;
it carries an owner envelope and `Cache-Control: no-store`. Vendor account ids
and other metadata are not returned. A failure returns 503 without storage
details, never a successful empty list. No schema or database migration is
needed.

The Python reader rejects a missing/mismatched owner envelope, missing list or
malformed rows as UNKNOWN. The old reader could treat malformed successful
responses as an empty connection list; that distinction is now enforced.

## Evidence

- `node --experimental-strip-types test/hands-api-connections.test.ts`:
  **29 checks passed**, including the real Worker dispatcher over real local
  SQLite, separate owners, missing/wrong credentials, duplicate/invalid owner
  parameters, SQL-injection input, forbidden mutation methods, storage failure,
  missing schema, adversarial mixed-owner storage output, and more than 100
  connections without truncation.
- `.venv/bin/python -m pytest -q tests/test_hands_router.py`:
  **59 passed, 2 skipped**. The skipped tests require a live model.
- Existing neighboring suites: `hands-api` **51**, `connections-store` **58**,
  `connections-api` **118** checks passed.
- `connections-api-hand`: **74 checks passed**; Python API lane, live-gate
  unit tests and memory-handoff tests: **155 passed**.
- `npm run typecheck`: **passed**.

These checks used synthetic local rows and no network, credentials or customer
data. No backend was deployed. **Live remains UNPROVEN** until an authorized
service request for each of two test owners returns only the expected owner's
facts and a real model-produced API job reaches the connected hand.

## Related correction defect and repair

`Anticipy._merge_into` changes the embedded workflow goal, facts, source and
version but preserves `params._hand.tool` and `.args`. `handsApiRun` builds its
step from those old arguments without comparing the planning inputs to the
current workflow. A corrected held task can therefore execute the original
argument plan.

The planner now stamps `plan_input = {goal, source, owner_ref,
workflow_version}` alongside its arguments. Routing precedes creation of a new
workflow, so a fresh job binds version 1; a caller replanning an existing
workflow carries that workflow's actual version. Execution compares these
inputs with both the current job columns and embedded workflow before calling
the hand. Goal/source changes and fact-only revision bumps all invalidate the
old arguments. The comparison is structural identity, not a prose classifier.

A stale or missing binding produces `plan_stale` without even reading the
vendor catalog. The route clears the obsolete tool/arguments, releases the
claim and queues the current workflow on the browser lane. Current goal,
source, facts, version, approval scope and effect identity survive the handoff.
The existing attempt ceiling still stops work that has exhausted its retries.
Pre-binding/pre-workflow rows also refuse API execution; no legacy exception
can execute arguments whose revision is unknown. This deliberately does not
replan a correction onto the API lane: the browser works from the current
workflow. A later API-replanning feature must create a fresh binding.

The real API hand also runs a route-supplied authority check after its catalog
await and immediately before vendor execution. The query checks the original
params, goal, owner, lane, status, claimant, lease and workflow identity. A
correction or replacement lease arriving during the catalog request blocks
execute; a failed final authority read also blocks it. `_merge_into` rejects
running jobs, but that alone was insufficient because other same-lease/service
writers can change a running job.

The writeback compares the original params, goal and lease token as well as
status/claimant. If a newer revision arrives during the hand, the old result
cannot overwrite it. The current revision remains untouched when this compare
fails. There is still no distributed transaction between D1 and the vendor:
a correction after the final authority read/dispatch can overlap the external
request, and a request already sent cannot be retracted by these checks. The
fix does not claim to prevent that post-dispatch ambiguity.

The `hands-api` suite proves corrected and fact-only revised jobs cannot call
the API; the real vendor transport records zero calls on the corrected job.
It also proves that a fresh version-2 argument plan executes, the current
workflow survives browser handoff, old rows fail safely, corrections during
the catalog await make zero execute calls, and same-claim corrections or
replacement leases survive concurrent writeback. The route suite now has a
global fetch tripwire in addition to injected recording vendor transports, so
an accidentally unmocked call fails locally. **No live
execution or deployment was performed; both repairs remain UNPROVEN live.**
