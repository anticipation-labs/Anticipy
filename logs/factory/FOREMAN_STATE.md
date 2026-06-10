# FOREMAN STATE — updated at the end of every foreman session

Last updated: 2026-06-10 (session: Factory bootstrap + P0 completion)

## Where things stand
- Factory P0 is COMPLETE and verified: persona harness (8 dev + 4 holdout), self-proving
  scorer, scoreboard+ratchet, treadmill halt (tested live, K=2 smoke), ESCALATION flow
  (tested), judge planted-fake selfcheck (REAL claude session ruled FAKE correctly),
  launchd nightly (22:30), auto-compaction enabled in ~/.claude/settings.json.
- Branch: factory/build. Old autopilot/ regime retired (read-only).
- BASELINE (frozen suite e0db2ed3d218, stub tier): catch 0.6984 / worst 0.50
  (doctor_amara), false_actions 19, silent_harm 0, interrupt 5.44/day avg / 10.5 worst,
  e2e 0.23, memory_recall_worst 0.33.
- TARGET v2 aims at P1 (closed loop): scheduler for trigger_tick, duetime.py grounding,
  reminder routing (notify-not-ask), ChannelWorker + Twilio env normalization + the
  control_core.py:66 owner-literal removal, MainView TextField. Gate: factory/gates/gate_P1.sh.
- A real autonomous test lap was launched this session (loop.sh --once) — check
  logs/factory/product_scoreboard.csv and logs/factory/laps/ for its outcome.

## Open questions for Omar (also in PENDING_FOR_OMAR.md)
- Holdout red-pen (~20 min), OWNER_PHONE confirmation, OpenRouter top-up (~$25),
  optional gmail.compose tap.

## Known weak spots to keep an eye on
- TriggerWatcher._fired is in-memory: engine restart can double-fire reminders — fix
  belongs in P1 item 1/3 (persist fired-state in the loop's fields, e.g. fields["fired_at"]).
- launchd fires only if the Mac is awake at 22:30; loop wrapped in caffeinate so it
  won't idle-sleep mid-run, but a sleeping Mac at 22:30 = skipped night (pmset wake
  schedule needs Omar's sudo, noted in PENDING if it becomes a problem).
- Persona bank v1 keys all third-party sends as ask-first (documented convention);
  Omar's red-pen may recalibrate. False_action_count 19 partly reflects this convention.
- Claude subscription rate limits could throttle heavy nightly lap usage; laps fail
  honestly (TIMEOUT/rc!=0) and the loop continues; escalate if it recurs.

## Session log
- 2026-06-09/10: plan approved → Factory built end-to-end → smoke bugs found+fixed
  (gate scratch isolation, log-safe revert, first-closure counting, set-u empty array,
  conf set-if-unset) → full bank authored → baseline measured → launchd installed →
  real test lap launched → compaction-proofing (CLAUDE.md, this file, memory dir,
  autoCompactEnabled=true) → research mandate added to BUILD.md.
