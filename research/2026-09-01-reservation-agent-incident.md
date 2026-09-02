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

## Verification record

- Backend/Python suite: 2,429 passed after the final implementation. A first rerun
  failed because the host disk had 116 MB free and pytest could not create temporary
  files; deleting generated pytest/Xcode temp caches restored the test environment.
- Extension suite: all 70 suites passed against the final source.
- Extension package: built as 0.11.2 and copied to all three backend download names.
- Loaded Chrome folder: source synchronized to the existing unpacked install at
  `/Users/omarebrahim/Documents/Anticipy Browser Agent`.
- Live deploy and live gate: pending at the time this record was created. Law 3
  requires the production download and worker behavior to be checked after deploy.

## Known conditions outside this incident

The repository scoreboards already identify two broader release conditions that this
repair does not pretend to solve: the speaker-tagger package is not linked in the iOS
target, and no cold stranger has completed a full independent day. The standing tape
gate is also red by design while registered legacy tape exists. They remain separate
work, not hidden under this incident's green unit suites.
