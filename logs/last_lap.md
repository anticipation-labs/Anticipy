# Last lap: 20260613T022002Z (build - dev_v2 imperative note commands)

## What changed
- Added `shared/note_task.py`, a narrow matcher for imperative note-creation
  commands only.
- Room 2 now treats imperative note creation as reversible note capture before
  soft-send wording is assessed, while hard money/delete/auth gates still outrank it.
- The deterministic planner and stub gateway now write the exact note text as one
  `write_memory` open-loop step.
- Added regression pins in `test_harmline.py`, `test_gateway.py`, and
  `test_owner_ingest_event.py`.
- Logged F38 and F39 in `logs/factory/FAILURE_MODES.md`.

## Failed attempt ripped out
- A context-backed no-clock pickup-alarm adjustment retry was tried first. Official
  dev_v2 scoring produced `false_action_count=1`, so the code and tests were removed.
  Do not retry that family again without a new owner/foreman product rule.

## Eval numbers seen
- Official TARGET v9 lane: `ANTICIPY_OWNER_INGEST=1`, bank `factory/personas/dev_v2`,
  tier `stub`, lap `20260613T022002Z-pre`.
- dev_v2 score: catch 0.8413, catch_worst 0.6667, false 0, harm 0, interrupt
  1.0/2.0, e2e 0.75, correct 0.8611, recall_worst 0.5, worst_persona
  `freelancer_nora`.
- Previous kept score from lap `20260613T020216Z-pre`: catch 0.8413,
  catch_worst 0.6667, false 0, harm 0, interrupt 1.0/2.0, e2e 0.6945,
  correct 0.8055, recall_worst 0.5.
- Legacy contract smoke, bank `factory/personas/dev`, lap `20260613T022002Z-pre-dev`:
  catch 1.0/1.0, false 0, harm 0, interrupt 0.625/1.0, e2e 0.6483, correct 0.8475,
  recall 1.0.
- `bash scripts/run_suite.sh`: 46/46 GREEN.

## Gate status
- `factory/config/owner_phone.confirmed` is absent, so `gate_P3.sh` live calls/SMS are
  still banned and were not attempted.
- This builder ran under the active Factory loop lock for this lap id. No competing
  lock owner was observed.

## What's next
- The remaining official v2 floor is still `freelancer_nora`. The biggest honest
  gaps are unresolved browser-cart tasks and communication-boundary misses. Do not
  invent store URLs, weaken no-purchase rules, or retry no-clock pickup-alarm changes
  without a new product law and a zero-false eval.
