# Last lap: 20260613T032644Z (build - seeded ampersand-store cart resolution)

## What changed
- Inspected the latest official dev_v2 run for `freelancer_nora`. The only
  remaining expected act that was not a do-not-retry family was the B&H cart-prep
  task; the Northstar follow-up note and no-clock pickup alarm families were not
  retried.
- Added seed-host-only ampersand alias resolution in `shared/storesite.py`.
  A spoken alias such as `B&H Photo` now resolves only when its normalized form
  uniquely prefixes an already-packaged verified `site_hints_seed.json` host.
  Bare `B&H` and unseeded aliases still fail closed.
- Narrowed Room 1's countermand rule so cart-only no-purchase phrases like
  `put it in the cart ... don't buy it` reach the harm-line, while bare
  `do not buy` lines still stay silent.
- Updated focused regression coverage in storesite, triage, harm-line,
  orchestrator, and owner-ingest tests. Logged F46 in
  `logs/factory/FAILURE_MODES.md`.

## Eval numbers seen
- Official TARGET v9 lane: `ANTICIPY_OWNER_INGEST=1`, bank
  `factory/personas/dev_v2`, tier `stub`, lap `20260613T032644Z-pre`.
- First attempt, resolver only, was unchanged at e2e 0.8135 because triage still
  silenced the no-buy cart line.
- Final dev_v2 score: catch 0.9444, catch_worst 0.8333, false 0, harm 0,
  interrupt 1.0/2.0, e2e 0.8301, correct 0.9333, recall_worst 1.0,
  worst_persona `freelancer_nora`.
- Previous kept score from lap `20260613T031441Z-pre`: catch 0.8889,
  catch_worst 0.6667, false 0, harm 0, interrupt 1.0/2.0, e2e 0.8135,
  correct 0.9167, recall_worst 0.5.
- Legacy contract smoke, bank `factory/personas/dev`, lap
  `20260613T032644Z-pre-dev`: catch 1.0/1.0, false 0, harm 0, interrupt
  0.625/1.0, e2e 0.6483, correct 0.8475, recall 1.0.
- `bash scripts/run_suite.sh`: 46/46 GREEN.

## Gate status
- `factory/config/owner_phone.confirmed` is absent, so `gate_P3.sh` live calls/SMS
  are still banned and were not attempted.

## What's next
- Nora still has one expected ask gap, the Northstar invoice draft ask. A pure
  ask catch may lower the primary e2e denominator, so do not chase it unless the
  product change also completes another act or the foreman changes the metric.
- Do not retry first-person follow-up note auto-capture or no-clock pickup/dropoff
  alarm adjustment without a new owner/foreman product law.
