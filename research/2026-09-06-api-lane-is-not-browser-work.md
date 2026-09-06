# The api lane is not browser work — 2026-09-06

Adversarial pass over the two-hands wire (brain/hands.py router,
migration/workers/src/routes/hands_api.ts, brain/worker.py `run_api_jobs`),
one defect, reproduced before it was touched. Nothing here is deployed.

## The defect, measured

The extension polled `workflow_id!="" && lane!="research"`
(extension/background.js `BROWSER_LANE`). Two things about that string:

1. It NAMES `lane`, so the Worker's research_lane leg 1 — which appends
   `lane != research/supervised_read/device_calendar` to a queued poll that
   does not mention lane — appended nothing to it.
2. It excluded ONLY research. The claim leg (leg 5) had no api rule at all.

So an api-lane row (the row the brain mints from an `api` verdict and
`run_api_jobs` claims for `/hands/api/run`) was listed by every shipped
extension, and the extension's claim PATCH was **accepted**. Reproduced end
to end through the real Worker (`guard → ownerProfileOwner → researchLane →
workflowGuard → records`, real schema in SQLite) before any change:

    PATCH /api/collections/jobs/records/<api row>  (agent credential)
    → 200, row now status=running claimed_by=agent-1

A browser that polled before the brain won the row and ran an api errand
through the browser vocabulary. The api hand was bypassed every time a
browser was awake. What kept two hands off one row was the workflow lease,
not any lane rule; what it cost was the wrong hand.

## The fix, two layers, tested independently

**The floor is the server.** `migration/workers/src/policy/research_lane.ts`:
`API_LANE = "api"` joins `EXCLUDED_LANES` (so a 0.2.3-style poll that never
named lane is protected too), and leg 5 refuses a non-worker claim on lane
api. The refusal keys on the worker marker (`X-Anticipy-Worker` + the service
token), never on what the body calls itself — a browser can type
`worker-api` as easily as anything. The sweep's requeue (`claimed_by: ""`)
is a claim-shaped write and is refused alike; `release_stranded_api` does
that job under the marker.

**The courtesy is the extension.** `BROWSER_LANE` now reads
`workflow_id!="" && lane!="research" && lane!="api"`, and because the claim
poll and the stale sweep share that one definition (test_hunt_round2.mjs),
both stop seeing api rows.

Proofs:

- `migration/workers/test/api-lane-claim.test.ts` — 24 checks. Direct legs
  over the policy with a real D1 row; end-to-end legs through `worker.fetch`;
  the extension's `BROWSER_LANE` read out of its source and listed with, so
  the server proof measures the extension that exists.
- `extension/tests/test_api_lane_is_not_browser_work.mjs` — 9 checks. The
  exact filter strings `claimJob` and the alarm-driven sweep send, parsed by
  the server's own filter DSL and run over the server's own schema in
  SQLite. The 2026-09-06 filter is held as a literal and proven to still
  list the api row through the same pipe (the reproduction, kept).

Every refusal has a control: the same claim on the browser lane lands; the
same claim from the worker lands; a non-claim write by an agent on an api
row is not this leg's to refuse; research is still refused (the neighbour
leg survived).

## Mutations run (each literal asserted to occur EXACTLY ONCE)

| mutation | what went red |
|---|---|
| M1 `API_LANE` leaves `EXCLUDED_LANES` | leg-1 direct, leg-1 E2E (0.2.3 poll lists the api row), the once-pin — 3/24 |
| M2 the `lane === API_LANE` leg deleted | every floor leg incl. the E2E 403 — 8/24 |
| M3 the leg keys on `claimed_by !== "worker-api"` (the research leg's shape) | "the name is not a credential", "service token alone", the once-pin — 3/24 |
| E1 `BROWSER_LANE` reverted to the 2026-09-06 literal | claim poll lists api, sweep lists api, the once-pin — 3/9; test_hunt_round2 red too |
| E2 a second `lane!="api"` clause elsewhere in background.js | the once-pin — 1/9; test_hunt_round2 stays GREEN (it forbids a second `research` clause, not a second `api` one) |

Files restored byte-identically after each (`cmp`).

Suites: worker `npm test` chain passes through `connections-endtoend`
(hands-api 39/39 once the index dispatch landed); extension
`run_all.mjs` 94/94.

## Still open — in the order it bites

1. **Not registered in CI.** `migration/workers/package.json` `test` must gain
   `&& node --experimental-strip-types test/api-lane-claim.test.ts`. That
   file was mid-edit by another agent during this pass and is not mine;
   until the line is added, CI runs the extension proof and not the server
   proof.
2. **`tests/test_api_lane.py::test_the_measured_hole_in_the_extensions_claim_filter_is_recorded`
   is RED, by its own design** ("goes red the day either file changes"). Its
   new measurement is: `BROWSER_LANE` ends `&& lane!="api"`;
   `EXCLUDED_LANES = ["research", SUPERVISED_LANE, DEVICE_LANE, API_LANE]`;
   the `'"api"' not in hook` assertion goes (the hook now defines
   `API_LANE = "api"`); and brain/hands.py's docstring paragraph "THE
   EXTENSION'S CLAIM FILTER, measured 2026-09-06" is rewritten to say the
   hole is closed on both layers. Both files are another agent's.
3. **Law 3.** Nothing is deployed. After `wrangler deploy`: an agent-credential
   claim on a live api row must answer 403 against api.anticipy.ai, and
   `proof/e2e_cloudflare.py --owner qeuy6sv1raof9rw` must still exit 0.
   After the extension ships: the popup must not list an api errand.
4. **Until the extension is redeployed**, 0.15.0 installs still list api
   rows and are refused on claim (harmless: `could not claim` warn, next
   row) — but `setCurrentJob` runs before the claim, so the popup can flash
   "Picking this up: <api errand>" for a row this browser will never run.
5. **Measured, not fixed:** the extension's filter still lists a
   `device_calendar` row that carries a plan; the server refuses that claim
   ("a calendar errand happens on your phone"). Pinned in the extension twin
   as a measurement, not an endorsement.
6. **Measured, not fixed:** research_lane.ts leg 5 lets a non-worker claim a
   research row by naming itself `worker-research` (ported as written from
   research_lane.pb.js:649). Pinned in the server suite; the api leg does not
   copy that shape.
7. `noteResearchWaiting` explains "nothing here to do" by looking at the
   research lane only; a queued api row waiting on a stalled brain presents
   as a dead Chrome the same way research used to.
8. The retired PocketBase hook (backend/pb_hooks/research_lane.pb.js) was not
   touched; it has no api rule. Nothing points at it any more.

## Law 1

No pattern-match over natural language was added. Both new checks are
structure: equality on a `lane` column the brain stamps from a model verdict
(`lane_for`), and a filter clause naming a lane — which hand runs an errand,
not what anyone's words mean. The only string checks in the tests are source
pins, the gates-and-evals carve-out. No tape, no `TAPE:` comment, nothing for
tape_gate.py.
