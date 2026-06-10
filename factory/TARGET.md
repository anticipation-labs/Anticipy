# TARGET v3
updated: 2026-06-10T06:10:00Z by foreman (night plan: P1 close -> P2 brain depth; owner asleep, full autonomy)
north_star: A person's messy day in -> the right tasks caught, done for real, proven; wrong ones never done.
current_phase: P1-closed-loop
primary_metric: catch_rate_worst
guards: false_action_count==0 silent_harm_count==0
phase_gate: factory/gates/gate_P1.sh
eval_tier: stub
budget_week_usd: 200
allowed_strategies: |
  TONIGHT IS CHAINED — read this whole block, then check logs/factory/RATCHET.json
  "phases_closed" to see which stage you are in:

  STAGE 1 (P1 not yet in phases_closed): the P1 slice (duetime grounding, tick scheduler,
  notify routing, tests; suite=31) is ALREADY LANDED on HEAD by the foreman from lap
  20260610T052102Z, which passed gate_P1 S1-S4 live before a since-fixed scan bug reverted
  it. Your job: verify (run the suite + a quick stub persona pass), set
  "attempt_gate_close": true in your manifest, and let verify_gate run the phase gate.
  Do NOT rebuild what is already on HEAD. If gate_P1 fails, read
  logs/factory/runs/gatep1-*/gate_p1_results.json and fix the specific failing leg.
  Note: the gate's S1/S2 create REAL self-owned calendar artifacts; cleanup is built in —
  confirm S1_cleanup.deleted in the gate results, and if cleanup failed, delete the id it
  reports via Arcade GoogleCalendar.DeleteEvent before finishing the lap.

  STAGE 2 (P1-closed-loop IS in phases_closed): you are now on P2 — brain depth. The
  foreman will flip current_phase/phase_gate next session; until then treat
  factory/gates/gate_P2.sh thresholds as your aim and catch_rate_worst as primary_metric.
  The live cheap model is AVAILABLE: provider=openrouter path now serves Gemini
  (ANTICIPY_OPENAI_BASE_URL in .env.local, free tier; ledger D18) — verified working.
  P2 work, in order (see the plan: productize overnight/track_b/decider.py):
  1. engine/anticipy_engine/proactive/decider.py: cheap-model ACT/ASK/SILENT decider,
     temp 0, fail-SILENT, tolerant parse. Pipeline: triage rules (unchanged, recall-biased)
     -> decider (live mode only; stub mode bypasses it so the suite stays deterministic)
     -> harm-line (deterministic, FINAL — the decider may move decisions only toward
     SILENT/ASK, never override an ASK into ACT).
  2. Wire into core/proactive.py on_event behind ANTICIPY_MEMORY_MODE/ANTICIPY_MODEL_PROVIDER
     live checks; add focused tests with a stubbed decider; keep suite green.
  3. The metrics that must move (stub-tier persona evals measure the DETERMINISTIC part;
     improvements to triage precision/recall and silence handling show up there):
     false_action_count 19 -> 0 is the mountain; interrupt_cost_worst 10.5 -> <=3.
     Study the actual misses first: logs/factory/runs/<lap>/<persona>/ raw events vs
     factory/personas/dev/<persona>/days/*.expected.json. Evidence before theory.
banned_work: |
  Per-store DOM recipes. UI polish. Status surfaces. Onboarding. example.com / localhost /
  fixture targets. Search-bar task dumping. Never edit factory/ control plane, personas/,
  scripts/realday.sh, the scoreboard, or read any holdout content. No third-party
  messages; test artifacts self-owned, labeled, reversible, cleaned up.
notes: |
  Owner is asleep; no human gates available tonight — if you hit something only he can do,
  log it in PENDING_FOR_OMAR.md and move to the next allowed slice. OpenRouter is unfunded
  and IRRELEVANT (Gemini serves the engine). The repo may move to ~/Anticipy tonight
  (foreman op, ledger D17) — all your paths are relative, so this does not affect you.
  Baseline with the C3-corrected scorer: catch 0.6667 / worst 0.50, false 19, harm 0,
  interrupt 5.44 avg / 10.5 worst.
