# Last lap: 20260613T031441Z (build - note-bearing cart false-action guard)

## What changed
- Pre-registered and tried a narrow first-person follow-up-note auto-capture
  hypothesis. Official dev_v2 scoring returned `false_action_count=1`, so the
  matcher and owner-ingest proof test were removed before the kept run.
- Kept only the failure-mode fix found during focused testing: Room 2's generic
  reversible `add ... cart` / `put ... cart` regex now refuses clauses with a
  nearby `note`, so note-bearing follow-up lines cannot become ungrounded cart
  actions by falling through to the cart rule.
- Added the regression to `test_harmline.py`.
- Logged F44 fixed and F45 avoided in `logs/factory/FAILURE_MODES.md`.

## Eval numbers seen
- Official TARGET v9 lane: `ANTICIPY_OWNER_INGEST=1`, bank
  `factory/personas/dev_v2`, tier `stub`, lap `20260613T031441Z-pre`.
- First attempt score, rejected and removed: false 1 on `freelancer_nora`.
- Final dev_v2 score: catch 0.8889, catch_worst 0.6667, false 0, harm 0,
  interrupt 1.0/2.0, e2e 0.8135, correct 0.9167, recall_worst 0.5,
  worst_persona `freelancer_nora`.
- Previous kept score from lap `20260613T025806Z-pre`: catch 0.8889,
  catch_worst 0.6667, false 0, harm 0, interrupt 1.0/2.0, e2e 0.8135,
  correct 0.9167, recall_worst 0.5.
- Legacy contract smoke, bank `factory/personas/dev`, lap
  `20260613T031441Z-pre-dev`: catch 1.0/1.0, false 0, harm 0, interrupt
  0.625/1.0, e2e 0.6483, correct 0.8475, recall 1.0.
- `bash scripts/run_suite.sh`: 46/46 GREEN.

## Gate status
- `factory/config/owner_phone.confirmed` is absent, so `gate_P3.sh` live calls/SMS
  are still banned and were not attempted.

## What's next
- Do not retry first-person follow-up note auto-capture without a new product law;
  the stricter explicit-note hypothesis still scored as a false action.
- Remaining official v2 floor is still `freelancer_nora`. Avoid the B&H cart path
  unless memory resolves a derivable store without adding a new hostname literal or
  recipe.
