# Last lap: 20260613T020216Z (build - dev_v2 context-backed slot-choice booking)

## What changed
- Added a shared context-backed slot-choice resolver in `shared/slotbooking.py`.
- Room 2 now treats "book the <slot> one with <person>" as a safe calendar hold only
  when memory names the same person, slot, and an availability cue.
- The deterministic orchestrator uses the same resolver to plan one `create_event`
  step, keeping the act population aligned with proof-bearing execution.
- Added regression pins in `test_harmline.py` and `test_owner_ingest_event.py`.
- Logged F36 and F37 in `logs/factory/FAILURE_MODES.md`.

## Failed attempt ripped out
- A no-clock pickup/dropoff alarm adjustment auto-hold was tried first and failed:
  official dev_v2 scoring produced `false_action_count=1`. The code and tests for
  that attempt were removed before the kept run.

## Eval numbers seen
- Official TARGET v9 lane: `ANTICIPY_OWNER_INGEST=1`, bank `factory/personas/dev_v2`,
  tier `stub`, lap `20260613T020216Z-pre`.
- dev_v2 score: catch 0.8413, catch_worst 0.6667, false 0, harm 0, interrupt
  1.0/2.0, e2e 0.6945, correct 0.8055, recall_worst 0.5, worst_persona
  `freelancer_nora`.
- Previous kept score from lap `20260613T014006Z-pre`: catch 0.8413,
  catch_worst 0.6667, false 0, harm 0, interrupt 1.0/2.0, e2e 0.6389,
  correct 0.75, recall_worst 0.5.
- Legacy contract smoke, bank `factory/personas/dev`, lap `20260613T020216Z-pre-dev`:
  catch 1.0/1.0, false 0, harm 0, interrupt 0.625/1.0, e2e 0.6483, correct 0.8475,
  recall 1.0.
- `bash scripts/run_suite.sh`: 46/46 GREEN.

## Gate status
- `factory/config/owner_phone.confirmed` is absent, so `gate_P3.sh` live calls/SMS are
  still banned and were not attempted.
- This builder ran under the active Factory loop lock for this lap id. No competing
  lock owner was observed.

## What's next
- The remaining official v2 floor is still `freelancer_nora`. The largest honest
  gaps remain memory-resolved cart execution and communication boundaries. Do not
  invent stores, weaken send/money/no-purchase rules, or retry no-clock pickup-alarm
  holds without a new product law and a zero-false eval.
