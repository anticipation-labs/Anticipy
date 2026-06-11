# Last Lap

Lap: 20260611T043446Z
Date: 2026-06-11
Phase: P2-brain CLOSED (lap 20260611T041654Z, judge REAL) -> TARGET v6 STAGE B item 1
Slice: GROUNDWORK — owner-path honesty wiring, engine side. The owner lane (POST
/owner/ingest cards) is now measurable by the UNCHANGED factory instrument
(persona_run + persona_score + the same expected.json keys), with worst-persona
honesty, in one command:
  ANTICIPY_OWNER_INGEST=1 engine/.venv/bin/python factory/bin/persona_run.py \
    --bank factory/personas/dev --lap <LAP>-owner --tier stub

What changed:
- engine/anticipy_engine/core/control_core.py: env-gated seam in feed() — with
  ANTICIPY_OWNER_INGEST=1, /event routes through new owner_event() -> owner_ingest()
  and answers in the proactive shape {decision, goal_id, ask_id}. Mapping fails
  toward ask: ask/blocked -> "ask", do -> "act", remember -> "remember", no card ->
  "ignore". Cards do NOT execute (that is STAGE B item 2), so e2e shows an honest 0.
  Recursion guard: meta.owner_ingest_execute keeps execute_actions card feeds on the
  proactive path. Every owner card now persists a goal-shaped durable record
  (id/intent/steps/state, state "open" — never fake-done) under <data>/owner_cards/,
  which persona_run's collect_goals already harvests (verified: parent_dana 14,
  founder_jin 5 records in goals.json).
- engine/anticipy_engine/owner_mode.py: C22 product side — deleted the judge-named
  eval-tuned routing literals (_BROWSER "water[- ]?table", "that .* thing"; _SEND
  "decking|deck|new version|revised") plus two same-class deny-side literals
  (_VENT_OR_JOKE "clone myself", "that'?ll fix" — 4-gram shingle matches of
  parent_dana day01's vent). Manifest was amended BEFORE this change (amendment_1).
- engine/scripts/test_owner_ingest_event.py (new, registered in run_suite.sh):
  pins the decision mapping, the response contract, the goal-shaped record
  read-back (state open, memory_write + card_record proof), default-path purity
  (no env var -> no owner_lane, no owner_cards dir), and the recursion guard.

Eval numbers I saw (verify_gate recomputes the official ones):
- Suite: 39/39 green (38 + owner_ingest_event), after every change.
- Default path, stub full bank, at final HEAD (runs -pre AND -pre2): BIT-IDENTICAL
  to ratchet bests — catch 1.0 / worst 1.0, false 0, harm 0, interrupt 0.625 / 1.0,
  recall_worst 1.0, correct 0.6788, e2e 0.3427, worst contractor_luis. The seam is
  provably inert without the env var; the official scoreboard must not move.
- OWNER LANE, first honest read (run -owner-c22, untuned regexes, metrics.json in
  the run dir): catch 0.5054 / worst 0.2222 (founder_jin 2/9), false_action_count 15,
  silent_harm 0, interrupt 0.6875 / 1.5 (contractor_luis, parent_dana),
  recall_worst 0.25, e2e 0.0. Pre-C22-removal run (-owner) read catch 0.5054 /
  false 17: removing the tuned literals changed ZERO catches and removed 2 false
  actions — the tuning was hurting, not helping.
- Zero model calls; spend 0; stub/mock everywhere; no real-world artifacts.

Honest counting:
- This lap moves NO scoreboard metric and closes NO gate (P2 closed last lap; the
  scoreboard's catch_rate_worst stays at the saturated dev 1.0). It is groundwork,
  pre-registered as such; it enables STAGE B item 2 (card execution through
  orchestrator/ApiHand with proof write-back) to be BUILT AGAINST this instrument.
- The owner-lane numbers are dev-bank, builder-visible, post-C22-cleanup — still not
  gate-grade (only the judge's holdout is). F17 (new): the owner doors currently
  ship a second, weaker brain (0.22 worst vs 1.0); the fix direction is routing owner
  cards through the proven triage/decider/harm-line spine or the hybrid extractor
  (OWNER_ACTION_ENGINE item 4), NOT more regex (F15 falsified lexicon-chasing).
- C22's mechanical shingle SCAN is factory/-side and remains OPEN for the foreman.

Next:
- STAGE B item 2 (build): act-route cards execute through the existing
  orchestrator/ApiHand with proof written back onto the card record (the record file
  + state field are already the landing spot); ask_required cards into /pending +
  YES/NO; money cards never execute. Score it with this instrument before/after.
- Foreman calls: F17 fix direction (one brain, not two); C22 shingle scan; whether
  owner-lane thresholds enter a gate.
- Carried unblocked: F6, B6, D16 sibling (self.pending in-memory), F7 last residual
  (real-429 storm observation), F16 (only if a judge count names it).
