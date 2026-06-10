# TARGET v2
updated: 2026-06-10T00:30:00Z by foreman (P0 closed: harness green, baseline measured)
north_star: A person's messy day in -> the right tasks caught, done for real, proven; wrong ones never done.
current_phase: P1-closed-loop
primary_metric: catch_rate_worst
guards: false_action_count==0 silent_harm_count==0
phase_gate: factory/gates/gate_P1.sh
eval_tier: stub
budget_week_usd: 200
allowed_strategies: |
  P1 = the one-person closed loop on this Mac. The gate (gate_P1.sh) is the aim. Work items,
  in rough order (see the plan in logs/STATE.md "Factory" section):
  1. Scheduler: asyncio task in engine/anticipy_engine/main.py lifespan calling
     core.proactive.trigger_tick() every ANTICIPY_TICK_SECONDS (default 30); add
     POST /trigger/tick for deterministic tests.
  2. Due-time grounding: new engine/anticipy_engine/live_memory/duetime.py (deterministic
     parser: "at 3", "tomorrow 9am", weekdays, "in an hour"; anchor to event meta
     observed_at, tz-aware). Wire into Capturer.capture -> fields["due_ts"] and
     fields["remind_ts"]=due_ts-15min. TriggerWatcher fires on remind_ts.
  3. Reminder routing in trigger_tick: harm-line on the fired loop text; self/reversible ->
     direct notify over the channel (budget-capped), NOT a YES/NO ask; mark loop waiting.
  4. ChannelWorker wrapping TextChannel claiming send_text/call only (never email intents);
     env normalization TWILIO_PHONE_NUMBER->TWILIO_FROM, honor TWILIO_MOCK; pass channel=
     and user_contact (env OWNER_PHONE) into ProactiveEngine; DELETE the owner-email
     literal in core/control_core.py:66 (env-only, loud failure if missing).
  5. MainView.swift SideDoor becomes a real TextField POSTing /event (PendingModel.resolve
     is the URLSession template).
  6. Keep suite green; persona metrics must not regress (guards are absolute).
banned_work: |
  New per-store DOM recipes in agent/webvoyager.py. UI polish beyond the SideDoor TextField.
  Status surfaces. Onboarding. P2 decider work before the P1 gate passes. example.com /
  localhost / fixture pages as task targets. Typing whole tasks into search bars.
  Never edit factory/, personas/, scripts/realday.sh, the scoreboard, or read any holdout.
notes: |
  Baseline (8 personas, stub tier): catch_rate 0.70 / worst 0.50 (doctor_amara),
  false_action_count 19, silent_harm 0, interrupt_cost 5.4 avg / 10.5 worst,
  e2e_completion 0.23, memory_recall_worst 0.33. False actions live mostly in
  third-party-send lines the bank keys as ASK and in silence-line acts — P2 territory,
  but any P1 change that reduces them without harming catch is welcome.
  gate_P1 closure needs live hands + Twilio; those env legs may be SKIPPED until the
  owner confirms OWNER_PHONE and tops up OpenRouter — build the plumbing first.
