# Last lap: 20260613T023948Z (build - dev_v2 derivable-store cart-only commands)

## What changed
- Added the narrow derivable-store cart-only path: Room 1 now survives verb-style
  "cart one ..." clauses, Room 2 strips no-buy/no-checkout language only when memory
  resolves a product-shaped item plus a derivable store URL, and owner shaping treats
  `no buying` / `no checkout` as no-purchase bounds.
- Extended the deterministic browser resolver to handle cart-verb action lines and to
  prefer explicit "liked/preferred the ..." item memory before broader shopping-category
  text.
- Added regression coverage in `test_triage.py`, `test_harmline.py`,
  `test_orchestrator.py`, and `test_owner_ingest_event.py`, including non-derivable
  store denial so no site is invented.
- Logged F40, F41, and the F42 ops listing mistake in `logs/factory/FAILURE_MODES.md`.

## Failed attempt ripped out
- A named-follow-up note-capture expansion was tried first. Official dev_v2 scoring
  produced `false_action_count=1` and no e2e gain, so the matcher and tests were removed.
  Do not retry non-imperative note capture without a new product law and a zero-false eval.
- Ops note: a broad `git status --ignored` printed ignored `.anticipy-data` filenames.
  It did not print contents, but it repeated the local-state listing mistake; the lesson
  and failure ledger now forbid ignored-status listings in builder laps.

## Eval numbers seen
- Official TARGET v9 lane: `ANTICIPY_OWNER_INGEST=1`, bank `factory/personas/dev_v2`,
  tier `stub`, lap `20260613T023948Z-pre`.
- dev_v2 score: catch 0.8889, catch_worst 0.6667, false 0, harm 0, interrupt
  1.0/2.0, e2e 0.7579, correct 0.8611, recall_worst 0.5, worst_persona
  `freelancer_nora`.
- Previous kept score from lap `20260613T022002Z-pre`: catch 0.8413,
  catch_worst 0.6667, false 0, harm 0, interrupt 1.0/2.0, e2e 0.75,
  correct 0.8611, recall_worst 0.5.
- Legacy contract smoke, bank `factory/personas/dev`, lap `20260613T023948Z-pre-dev`:
  catch 1.0/1.0, false 0, harm 0, interrupt 0.625/1.0, e2e 0.6483, correct 0.8475,
  recall 1.0.
- `bash scripts/run_suite.sh`: 46/46 GREEN.

## Gate status
- `factory/config/owner_phone.confirmed` is absent, so `gate_P3.sh` live calls/SMS are
  still banned and were not attempted.
- This builder ran under the active Factory loop lock for this lap id. No competing
  lock owner was observed.

## What's next
- Remaining official v2 floor is still `freelancer_nora`. Do not retry no-clock
  pickup-alarm changes or non-imperative note capture without a new product law. The
  remaining Nora browser gap is non-derivable B&H memory; do not invent a store URL or
  add per-store recipes to force it.
