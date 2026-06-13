# Last lap: 20260613T012751Z (build - dev_v2 schedule-change calendar holds)

## What changed
- Added a shared schedule-change calendar-hold matcher for messy owner lines with all
  three anchors: schedule-change cue, explicit block/capture cue, and concrete time or
  daypart.
- Wired that matcher through Room 1 triage, Room 2 harm-line, and the stub planner so
  matched lines become one grounded `create_event` step with proof in owner-ingest runs.
- Narrowly scrubbed the harmless metaphor "my brain deletes it" from hard destructive
  delete detection while preserving real delete/remove/wipe hard stops.
- Added regression pins in `test_triage.py`, `test_harmline.py`, `test_gateway.py`, and
  `test_owner_ingest_event.py`.
- Logged F33 in `logs/factory/FAILURE_MODES.md`.

## Eval numbers seen
- Official TARGET v9 lane: `ANTICIPY_OWNER_INGEST=1`, bank `factory/personas/dev_v2`,
  tier `stub`, lap `20260613T012751Z-pre`.
- dev_v2 score: catch 0.8413, catch_worst 0.6667, false 0, harm 0, interrupt
  1.0/2.0, e2e 0.5833, correct 0.6945, recall_worst 0.5, worst_persona
  `freelancer_nora`.
- Baseline comparison from lap `20260613T011932Z-pre`: catch 0.6825, catch_worst 0.5,
  false 0, harm 0, interrupt 1.0/2.0, e2e 0.3778, correct 0.6222, recall_worst 0.5.
- Legacy contract smoke, bank `factory/personas/dev`, lap `20260613T012751Z-pre-dev`:
  catch 1.0/1.0, false 0, harm 0, interrupt 0.625/1.0, e2e 0.6483, correct 0.8475,
  recall 1.0.
- `bash scripts/run_suite.sh`: 46/46 GREEN.

## Gate status
- `factory/config/owner_phone.confirmed` is absent, so `gate_P3.sh` live calls/SMS are
  still banned and were not attempted.
- This builder ran under the active Factory loop lock for this lap id. No competing
  lock owner was observed.

## What's next
- The remaining official v2 floor is still `freelancer_nora`: inspect
  `logs/factory/runs/20260613T012751Z-pre/freelancer_nora/` before forming the next
  hypothesis. Known remaining families include memory-resolved cart/action recall and
  unnecessary owner asks; do not invent stores or weaken send/money confirmation to move
  the score.
