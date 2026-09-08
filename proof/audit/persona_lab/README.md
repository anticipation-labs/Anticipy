# Fifteen-owner brain lab

Run from `cloudflare-backend`. Read the repository's harness laws first.
The models decide what the fictional people mean. The fixture layer supplies
transcripts, stored facts, available tools, web pages and provider failures.
Rubrics and expected answers do not enter the brain's prompts.

## What is exercised

- `run.py`: real `Anticipy.hear`, memory ingestion/retrieval, `Conversation`,
  `TaskDelivery`, durable `ReplyDelivery`, and local Worker storage. One process,
  account and SQLite memory per owner; no real phone numbers. Microphone/STT,
  connection-command dispatch and the background scheduler are excluded here.
- `memory_probe.py`: real extraction and restart persistence across all 15.
- `api_faults.ts`: brain-selected API arguments through the real Composio parser,
  connection store, API hand and disposition. Eight injected transport/results
  conditions; no external provider account or OAuth token exists.
- `exercise_outcomes.py`: those API results through the real server composer and
  independent completion verifier. This is an executor handoff probe, not a
  claim to have run a production polling worker.
- `connection_probe.ts`: the actual stored-event dispatcher, live model, mock
  integration catalog, reply persistence and replay. No real OAuth redemption
  or carrier delivery.
- `../run_real_browser.mjs`: production page mapping/agent loop in actual Chrome
  with adapted extension plumbing and isolated fixture pages. A private-place
  consent test answers the actual generated question and retains its reference;
  it does not disable the consent check.

The original corpus contains 5,072 transcript words and 25 typed follow-ups.
Its first 12 cases were used for development and the last 3 initially held back.
Once a held-back failure informed a repair, its rerun became a regression case,
not an unseen evaluation. Nothing here simulates 20 days of real life.

## Reproduce

Use Node 24 (Node 22 lacks the SQLite interface used by the Worker tests), Python
with the repository dependencies, Chrome, and Playwright as described in the
parent audit runner. Do not disturb an already-running local API on port 8787.

1. Start the isolated API: `python3 -m proof.audit.persona_lab.start_api --node /path/to/node24`.
2. Start the existing capped model gateway (`python3 -m proof.audit.model_gateway --help`).
   Reuse the audit's existing spend ledger; do not reset or replace it. The
   gateway token belongs in ignored `work/audit/gateway-token`. Its configured
   operating ceiling plus other live-test ceilings must fit the user's budget.
3. Run cases with a fresh label:
   `python3 -m proof.audit.persona_lab.run --label new-run --ids mina,asha`.
   Add `--held-out` when including the final three corpus members. No IDs means
   all 15. Strong calls share a reservation lock. Run other paid probes only
   after this driver finishes; the gateway refuses excess reservations.
4. Run API faults on a resulting `result.json`, supplying a new output path and
   optionally `proof/audit/persona_lab/api_fixtures.json` as the fourth argument.
   Then run `exercise_outcomes` against that fault output.
5. Run a Chrome fixture:
   `node proof/audit/run_real_browser.mjs changed-prices new-browser-run --fixture proof/audit/persona_lab/browser_fixtures/changed-prices.json`.

Results and SQLite files stay under ignored `work/audit/persona-lab`; browser
screenshots and traces are under `output/playwright/overnight-<label>`. Every
completed owner run erases its local Worker account. A process killed by an
external timeout may need its exact fixture account removed using that run's
private identity record. Never erase unrelated owners.

## Evidence discipline

Runtime completion is not semantic correctness. Inspect `model_errors`, jobs,
answers, original sources, memory, provider calls and replay counters. A 402 from
the audit gateway is a budget-reservation failure, not an intelligence defect;
keep it and rerun serially with a new label. Keep unexpected results as evidence.

Do not commit identity-private files, shared model traces, real credentials or
unrelated browser output. The dated report exports only synthetic evidence and
distinguishes source fixes, deployed bytes, simulated behavior and untested live
account/phone journeys.
