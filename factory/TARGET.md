# TARGET v1
updated: 2026-06-09T00:00:00Z by foreman (initial bootstrap)
north_star: A person's messy day in -> the right tasks caught, done for real, proven; wrong ones never done.
current_phase: P0-floor
primary_metric: catch_rate_worst
guards: false_action_count==0 silent_harm_count==0
phase_gate: factory/gates/gate_P0_floor.sh
eval_tier: stub
budget_week_usd: 200
allowed_strategies: |
  P0: build and prove the Factory itself (persona harness, scorer selftest, scoreboard,
  lap machinery). After P0 closes, the foreman flips this file to P1 (one-person closed
  loop: scheduler for trigger_tick, due-time grounding, real channel worker, live hands,
  real typed input in the mac app).
banned_work: |
  New per-store DOM recipes in agent/webvoyager.py. UI polish. Status surfaces.
  Onboarding cosmetics. example.com / localhost / fixture pages as task targets.
  Typing whole tasks into search bars. Anything not aimed at primary_metric or phase_gate.
notes: |
  Bootstrap target. The builder must read this file at the top of every lap and aim
  exclusively at primary_metric or phase_gate. Strategy questions go to ESCALATION.md,
  never silently resolved.
