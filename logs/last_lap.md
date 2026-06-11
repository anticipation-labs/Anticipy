# Last Lap

Lap: 20260611T095522Z (build, TARGET v7 item 1 — e2e_completion_rate)

## What changed
- `engine/anticipy_engine/hands/browser_hand.py`: BrowserHand gets an explicit
  `mode` (class default LIVE). Mock mode (ledger F26) applies the live path's own
  deterministic gates FIRST — an action-shaped task with no resolved real site
  fails with the identical live refusal (no search dumping) — then returns a
  loudly-labeled proof artifact (`{"id": "mock-…", "mock": true, "url": …,
  "screenshot": "mock://…"}`) instead of touching a browser. New unit pins.
- `engine/anticipy_engine/core/control_core.py`: wires `mode` from the SAME
  `ANTICIPY_HANDS_MODE` env ApiHand follows (mock default, live explicit);
  `ANTICIPY_BROWSER_HAND_MODE` narrows the knob for integrations that need the
  real-WS browser leg while the API hand stays mock.
- `scripts/hands_loop.sh`: declares its browser leg live (the test's purpose is
  the reroute reaching the REAL WS with a simulated extension; under mock the
  hand would answer the reroute itself — and its no-url post job was only ever
  "succeeding" because the simulated extension blind-succeeds what the real
  extension dead-ends; F25 lesson applied: pin re-derived, not papered).
- Ledger: F26 FIXED, F27 OPEN (see below). Manifest pre-registered; results match.

## Numbers I saw (builder-side, stub, dev bank)
- OFFICIAL owner lane (ANTICIPY_OWNER_INGEST=1): e2e_completion_rate
  0.4618 -> 0.4797 (+0.0179). Catch 1.0/1.0, false 0, harm 0, interrupt
  1.125/1.5, correct 0.6788, recall_worst 1.0 — all EXACTLY unchanged.
- Default lane: e2e equally 0.4618 -> 0.4797 (shared hand plumbing, disclosed);
  interrupt 0.625/1.0 and everything else bit-identical to ratchet bests.
- Per-line decisions: ZERO diffs across 493 lines x 16 persona-days in BOTH
  lanes (execution-layer change only; decisions precede execution).
- Suite 42/42. Selftest PASS. Zero spend, zero real-world artifacts.

## Exactly which items moved (scorer-replica diagnostic, runs/-pre vs -post)
- COMPLETED 26 -> 27: contractor_luis day02 "cabinet delivery monday 8" — its
  goal's only step ("open the page", junk-planted by the disclosed "on site"
  stub trigger) is live-navigable (search-fallback navigate + screenshot =
  exactly what the real extension would do), so mock completes it. F27 OPEN:
  the semantically right artifact is a calendar block; the stub planner lacks a
  "block <time range>" trigger — that is the named next plumbing slice.
- ACT_STALLED 2 -> 1: doctor_amara day01 "hoka shoes wide cart" now FAILS
  honestly (whole-prompt cart dump, no resolved site — the identical live
  refusal) instead of parking at "waiting". Cannot complete honestly until the
  product resolves a real site (memory has the item, no store; P4 territory).
- Remaining e2e gap on this bank is NOT plumbing: 16 expected-ask items the
  scorer never counts complete + 12 expected-acts the spine decides ASK on
  (decider/harm-line, holdout-risky — foreman territory, per the F23 queue).

## What's next
1. F27: stub-planner calendar trigger for time-anchored "block X to Y" (the F24
   "set up" precedent — product fix, the stub is the keyless default planner).
2. F23 (TARGET item 2): money pre-gate interrupt delta (1.125 vs 0.625) —
   foreman call queued on letting the spine rule money-shaped vents while
   keeping never-pending/never-execute.
3. P3 live gate still waits ONLY on OWNER_PHONE confirmation (PENDING_FOR_OMAR).
   Note: factory/gates/gate_P3.sh does not exist yet (TARGET names it as the
   phase gate; foreman item — a builder may not create control-plane gates).
