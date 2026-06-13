# Last lap: 20260613T014006Z (build - dev_v2 time-anchored forget holds)

## What changed
- Added a narrow Room 2 safe-hold rule for time-anchored `before I forget` lines,
  after hard money/send/delete/auth checks.
- Taught the stub planner to turn that same shape into one exact `write_memory`
  open-loop step, preserving the spoken goal text as proof-bearing memory.
- Added regression pins in `test_triage.py`, `test_harmline.py`, `test_gateway.py`,
  and `test_owner_ingest_event.py`.
- Logged F34 and F35 in `logs/factory/FAILURE_MODES.md`.

## Failed attempt ripped out
- A broader capture-to-visibility matcher was tried first and failed honestly:
  official dev_v2 scoring produced `false_action_count=2` with no aggregate e2e
  movement. That matcher and its pins were removed before the kept run.

## Eval numbers seen
- Official TARGET v9 lane: `ANTICIPY_OWNER_INGEST=1`, bank `factory/personas/dev_v2`,
  tier `stub`, lap `20260613T014006Z-pre`.
- dev_v2 score: catch 0.8413, catch_worst 0.6667, false 0, harm 0, interrupt
  1.0/2.0, e2e 0.6389, correct 0.75, recall_worst 0.5, worst_persona
  `freelancer_nora`.
- Previous kept score from lap `20260613T012751Z-pre`: catch 0.8413,
  catch_worst 0.6667, false 0, harm 0, interrupt 1.0/2.0, e2e 0.5833,
  correct 0.6945, recall_worst 0.5.
- Legacy contract smoke, bank `factory/personas/dev`, lap `20260613T014006Z-pre-dev`:
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
  gap remains memory-resolved cart execution for named-but-not-derivable stores and
  ask-first communication boundaries. Do not invent store hostnames or weaken send,
  money, or no-purchase rules to move the score.
