# Reservation agent incident — 2026-09-01

## What the owner observed

A request to find and make a restaurant reservation produced several overlapping
SMS/app conversations, repeated questions, multiple search tabs, and no confirmed
reservation. A browser tab reached a real reservation form and displayed available
times, but the agent never submitted it and no restaurant confirmation was found.

The production cleanup cancelled the five duplicate or stale workflows implicated in
the incident. They remain as cancelled records for auditability. This cleanup did not
cancel a real reservation because the evidence contained no completed external
reservation.

## Live evidence

- One currently paired Chrome agent was healthy enough to poll and had extension
  0.11.1. A retired agent identity continued receiving a deterministic 403 because
  refresh reused the rejected credential.
- Five live jobs represented variants of the same dinner plan. Four pointed at the
  same durable memory commitment; one older row carried contradictory details.
- The active browser contained an OpenTable/The Keg flow with party, date, time, and
  availability visible, plus abandoned search tabs. It contained no confirmation.
- The research provider returned HTTP 402 because its monthly plan limit was
  exhausted. The earlier result erased that operational reason behind a generic
  search failure.
- A search-field value was sent through the authored-message judge. It classified a
  navigation query as text composed on the owner's behalf and parked the browser run.
- Search fallback paths embedded Bing URLs, so retries created provider-specific tabs
  that looked like different agents fighting.

## Ownership of the failure

This was principally orchestration and browser-runtime code, not an inability to
understand the concept of a restaurant reservation.

The language model is responsible for interpreting the owner's goal, selecting the
destination or a provider-neutral discovery query, planning reversible steps, and
choosing a page action from the current page map. Code is responsible for durable
workflow identity, tenant scoping, transport truth, research availability, safety
ceilings, execution, and proof that a real-world effect occurred. The model produced
different but plausible paraphrases; code incorrectly allowed those paraphrases to
become separate workflows and then combined their replies.

The production tool chain in this path is:

1. PocketBase stores commitments, jobs, events, owners, and browser-agent claims.
2. The brain's clock/model turns an open commitment into a proposed workflow.
3. Twilio carries proactive questions and completion messages when the owner account
   has a reachable phone.
4. Brave supplies research before browser work when that gate requires it.
5. The Chrome extension uses the backend model, a structured DOM/page map, Chrome's
   search capability, and guarded click/type/select/navigation actions.
6. The job is complete only after the runtime records external evidence. An open form
   or an in-app card is not a reservation confirmation.

## Generic repairs (no restaurant exemplar or task vocabulary)

- **One promise, one live workflow.** A live job is now keyed to the exact durable
  `commitment_id`, not to word overlap. A later clock paraphrase is absorbed by the
  same workflow for every type of task.
- **The database owns the invariant.** The initial repair checked for an active
  commitment before creating. A follow-up audit found the remaining concurrency
  gap: two workers could both read "none" before either wrote. Jobs now carry a
  tenant-scoped `commitment_key`, and a partial SQLite unique index refuses a
  second active row even under that race. A database model hook clears this
  auxiliary key in the same write that makes a row terminal, so history stays
  available and an intentional retry remains possible.
- **Outreach must be reachable.** The clock does not compose or queue proactive work
  when an actual SMS transport exists but the owner account has no reachable phone.
- **Search is structural navigation.** Native/ARIA/form search controls are marked by
  page structure, so their contents do not pass through the authored-message safety
  judge. No query wording or restaurant name decides this.
- **Search provider belongs to the owner.** Discovery uses `chrome.search` and the
  browser's configured provider. Provider URLs are no longer embedded in the planner,
  initial route, retries, or ordinary fallbacks.
- **Retired browser identities self-retire honestly.** Three exact protocol-level
  credential rejections clear the false paired state and mint a fresh unpaired code.
  Generic 403s, timeouts, and infrastructure failures do not trigger that reset.
- **Research failure is legible.** A safe HTTP status such as 402 reaches the job
  result without the query, exception text, or API key.

These changes obey the Harness Laws: durable IDs and declared control/effect
structure make the decisions; no regex, vocabulary list, restaurant path, or example
decides the meaning of the owner's request.

The release branch now also runs `.github/workflows/system-invariants.yml` for
every brain, backend, browser, test, or gate change. It executes the complete
Python and extension suites, including a storage-level race reproduction and
the existing provider/domain hard-coding guards. A future wording-based repair
to this incident path therefore has to break a red gate rather than quietly ship.

## Verification record

- Backend/Python suite: 2,434 passed after the final implementation. A first rerun
  failed because the host disk had 116 MB free and pytest could not create temporary
  files; deleting generated pytest/Xcode temp caches restored the test environment.
- Extension suite: all 70 suites passed against the final source.
- PocketBase 0.30.4 integration: all migrations applied to a fresh real
  database; the first active job returned 200, a concurrent duplicate returned
  400, a terminal transition returned 200 and cleared `commitment_key`, and a
  deliberate retry returned 200.
- Extension package: built as 0.11.2 and copied to all three backend download names.
- Loaded Chrome folder: source synchronized to the existing unpacked install at
  `/Users/omarebrahim/Documents/Anticipy Browser Agent`.
- Git release: commit `3014699e` is pushed to `origin/jose_anticipy_system`.
- Backend deploy `d5d6b635-2953-4782-a35d-232724d4a37b`: SUCCESS. Production
  health is HTTP 200; the served 0.11.2 ZIP is 277,549 bytes and its SHA-256
  equals the committed artifact.
- Worker deploy `dbbb4652-7dd0-42e8-9a6e-c84eaf48b6d7`: SUCCESS. Its startup
  log reports brain fingerprint `816549dbf2b5`, equal to the final tree, and
  the live-brain behavioral gate passes.
- Commitment-identity backend deploy `0829e150-da74-4ce7-84d2-b48a1e75f65b`:
  SUCCESS. Health and authenticated jobs reads return 200 and live rows expose
  `commitment_key`. A production probe measured first create 200, concurrent
  duplicate 400, terminal release 200 with an empty key, and retry 200; both
  probe rows were deleted. An earlier attempt
  `35095ce3-fd2f-4a87-874a-b66a3e3d94a4` was correctly withheld from the
  worker after its raw log revealed PocketBase rejected the first index shape.
- Commitment-identity worker deploy `697ff321-6e03-4f1b-ac7c-ee48f7e10b8e`:
  SUCCESS. The startup fingerprint `0e40c03f9fe7` exactly equals the release
  tree's brain fingerprint, and `overnight/is_the_brain_live.py --hours 2`
  passes against production.
- Independent CI: GitHub Actions run `33589980000` passed the complete 2,434
  Python tests and all 70 browser suites on a clean Ubuntu runner. Product code
  is commit `84acbdcc`; commits `c94cb19d` and `24d36c54` only declare the two
  test-runner dependencies uncovered while making that new gate self-contained.
- Live release gates: `overnight/is_it_live.py`,
  `overnight/is_the_brain_live.py`, and all nine machine-checkable
  `overnight/stranger_gate.py` prerequisites pass.
- Production cleanup recheck: zero active workflows remain for the incident
  owner after the worker restart.
- TestFlight: GitHub Actions run `33580491900` uploaded build 121, received
  Apple's literal `UPLOAD SUCCEEDED` response, and waited until App Store
  Connect reported the build `VALID`.
- Local unpacked Chrome activation: the exact 0.11.2 source is synchronized to
  the one enabled Anticipy folder, but the already-running agent heartbeat still
  reports 0.11.1 until Chrome's protected Extensions page Reload button is
  pressed. Both available UI automation channels refused that protected page,
  so this one local click is recorded as pending rather than claimed.

## Known conditions outside this incident

The repository scoreboards already identify two broader release conditions that this
repair does not pretend to solve: the speaker-tagger package is not linked in the iOS
target, and no cold stranger has completed a full independent day. The standing tape
gate is also red by design while registered legacy tape exists. They remain separate
work, not hidden under this incident's green unit suites.
