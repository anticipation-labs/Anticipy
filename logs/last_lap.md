# Last lap: 20260613T033946Z (groundwork - dev_v2 metric/gate mismatch)

## What changed
- Inspected the latest official dev_v2 run dirs, especially
  `freelancer_nora`, before making any product-code edits.
- Confirmed P3 cannot be attempted because `factory/config/owner_phone.confirmed`
  is absent and `gate_P3.sh` correctly bans live calls/SMS without it.
- Confirmed the remaining Nora miss is the Northstar invoice-draft ASK. Catching
  it honestly would improve catch/correctness but lower the selected
  `v2_e2e_completion_rate`, because caught asks increase the denominator while
  only proof-bearing acts increase the numerator.
- Kept no product-code changes. Logged the metric/gate mismatch as F47 in
  `logs/factory/FAILURE_MODES.md`.

## Eval numbers seen
- Official TARGET v9 lane: `ANTICIPY_OWNER_INGEST=1`, bank
  `factory/personas/dev_v2`, tier `stub`, lap `20260613T033946Z-pre`.
- dev_v2 score reproduced the prior kept lap exactly: catch 0.9444,
  catch_worst 0.8333, false 0, harm 0, interrupt 1.0/2.0, e2e 0.8301,
  correct 0.9333, recall_worst 1.0, worst_persona `freelancer_nora`.
- Legacy contract smoke, bank `factory/personas/dev`, lap
  `20260613T033946Z-pre-dev`: catch 1.0/1.0, false 0, harm 0, interrupt
  0.625/1.0, e2e 0.6483, correct 0.8475, recall 1.0.
- `bash scripts/run_suite.sh`: 46/46 GREEN.

## Gate status
- `factory/config/owner_phone.confirmed` is absent, so `gate_P3.sh` live calls/SMS
  remain banned and were not attempted.

## What's next
- Foreman should either unlock P3 with the owner phone confirmation or retarget the
  instrument so catching required ASK work, such as Nora's Northstar invoice draft,
  is not punished by the primary metric.
- Do not retry first-person follow-up note auto-capture or no-clock pickup/dropoff
  alarm adjustment without a new owner/foreman product law.
