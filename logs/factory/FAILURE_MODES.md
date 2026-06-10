# FAILURE MODES LEDGER — the living list

Rule: every failure mode anyone (foreman, builder lap, judge, auditor, Omar) finds gets an
entry here with a status. "Next to zero failure" is not a promise — it is this list trending
toward 100% PREVENTED/CONTAINED, with every new entry getting a regression check. Statuses:
PREVENTED (can't happen) / CONTAINED (auto-detected + auto-recovered) / ACCEPTED (known,
bounded, documented) / REFUTED (claimed but disproven by test) / OPEN (fix pending).

## Class A — work destruction
- A1 Foreman commits during a running lap land in the lap's diff scan; revert (`reset --hard base`)
  destroys them. CONTAINED: no-commit-while-`factory/.lock` rule in CLAUDE.md; loop refuses to
  start over a dirty product tree (guard added 2026-06-10). Observed live once; lap stopped, no loss.
- A2 `reset --hard` wipes uncommitted tracked edits (incl. tracked files under logs/). CONTAINED:
  loop journal is untracked; foreman state edits forbidden mid-lap (A1 rule); revert saves
  `reverted.patch` first. Verified by scratch-repo test.
- A3 Crash between build and verify leaves unverified commits as the next lap's base. CONTAINED
  (2026-06-10): lap writes `base` file at start + `.lap_in_progress` marker; loop start rolls an
  orphaned lap back to its recorded base and journals it.
- A4 Single-Mac disk loss = total project loss. CONTAINED (partial): nightly `git bundle` backup to
  ~/Anticipy-backups (last 7 kept). OPEN question to Omar: also auto-push factory/build to the
  private GitHub origin for true off-site backup?
- A5 git exclude-pathspec (`':!logs'`) misbehaving would let lap cleanup wipe loop state. REFUTED:
  tested in a scratch repo — exclusion works; logs preserved, code reverted.

## Class B — real-world side-effect leaks
- B1 gate_P1 creates a REAL calendar event per run with no cleanup; post-P1 it would also SMS the
  owner — per lap, nightly (~16 texts/night). PREVENTED (2026-06-10): phase gates run only when the
  builder's manifest sets `attempt_gate_close: true` (or foreman forces); gate_P1 deletes its test
  event after verification; S2 poll capped.
- B2 Persona engines reaching real services. PREVENTED: explicit env pins (hands/channels/Twilio
  mock, bridge off) override .env.local because the engine's dotenv never overrides existing env.
- B3 Builder laps causing third-party effects. PREVENTED by prompt contract + the engine's own
  money/ask gates + judge review; test artifacts must be `[Anticipy test]`-labeled and reversible.

## Class C — measurement lies
- C1 Seeds embedded with stub embedder while engine runs live embedder → memory retrieval scores
  garbage in tier=live. PREVENTED (2026-06-10): persona_run passes the tier's ANTICIPY_MEMORY_MODE
  into seed_memory.
- C2 source_lines prior lifts any same-line event to "caught" with zero token match. PREVENTED
  (2026-06-10): prior now only applies when token ratio ≥ 0.3 (tiebreaker, not bypass).
- C3 An ACT on an expected-ASK item counted as both caught and false action (double accounting).
  PREVENTED (2026-06-10): counts as false action only; selftest extended to pin this.
- C4 A failed persona day silently vanishes from scoring (lap looks better than reality).
  PREVENTED (2026-06-10): any day error fails the whole persona run → verify gate fails the lap.
- C5 Missing/crashed metrics.json scored as vacuous pass. PREVENTED (2026-06-10): scoreboard exits
  hard if metrics absent; loop halts the line on scoreboard failure (measurement broke = stop).
- C6 Ratchet poisoning by one lucky run locks the bar too high. ACCEPTED: best-ever only updates
  from kept laps; judge recomputes scores on phase closes; foreman may reset RATCHET.json with a
  journaled rationale.
- C7 memory_recall trivially 1.0 if a bank has no requires_memory items. ACCEPTED: bank authoring
  requirement (each persona ≥1 memory-dependent item — currently true for all 12); judge can verify.
- C8 interrupt_cost is per-day average by definition (not total). ACCEPTED: documented metric.
- C9 Delta column shows raw difference (negative = improvement for count metrics). FIXED cosmetically
  (direction-adjusted display).
- C10 Builder gaming the scorer (token stuffing). CONTAINED: judge recomputes 2 random personas from
  raw runs on judged laps; personas/ frozen + scan-forbidden; SUITE_HASH stamped per row.
- C11 Holdout scan flagged MENTIONS of the holdout path (CLAUDE.md/STATE.md reference it) as
  violations — falsely reverted the first real lap 20260610T045550Z, which had correctly built
  the P1 due-time slice. PREVENTED (2026-06-10): scan_holdout.py parses tool_use INPUTS for
  paths reaching INTO holdout dirs; regression-verified both directions (old stream now PASS,
  synthetic real read FAIL). The reverted work is preserved in the lap's reverted.patch.
  Lesson: the fail-closed design worked — wrong verdict, zero data loss, full forensics.

## Class D — process/ops failures
- D1 launchd PATH could not find `claude` (lives in ~/.local/bin) — nightly would fail 100%.
  PREVENTED (2026-06-10): plist PATH fixed + verified; CLAUDE_BIN resolved in factory.conf.
- D2 Mac asleep at 22:30. CONTAINED: launchd runs missed StartCalendarInterval jobs on wake;
  caffeinate -i prevents idle sleep mid-run. Residual: powered-off Mac = skipped night (ACCEPTED,
  visible as a missing journal line).
- D3 Watchdog `pkill -P $$` misses grandchildren of the claude process. PREVENTED (2026-06-10):
  lap scripts capture the claude PID, kill PID + its process subtree on timeout.
- D4 gate engines (uvicorn) leaking after kill. CONTAINED (2026-06-10): port-based sweep
  (`lsof -ti :PORT`) after kill in gate_P1 + stale persona-port sweep at loop start.
- D5 BUILD failure (rc≠0) with partial commits could be kept if evals happen to pass.
  PREVENTED (2026-06-10): nonzero build rc with commits forces gate FAIL → revert.
- D6 verify_gate can hang forever (no timeout). PREVENTED (2026-06-10): watchdog wall-cap.
- D7 PHASE_CLOSED True/False string comparison fragility between python repr and bash.
  PREVENTED (2026-06-10): JSON-lowercase emitted and compared.
- D8 Stale lock with recycled PID blocks the loop forever. CONTAINED (2026-06-10): lock older
  than 24h is reclaimed regardless of PID liveness.
- D9 scoreboard/spend failures swallowed by `|| true`. PREVENTED (2026-06-10): scoreboard failure
  halts the line with a notification; spend failure journals loudly.
- D10 runs/ and laps/ disk growth. CONTAINED (2026-06-10): loop start prunes runs/ older than 7 days.
- D11 Claude subscription rate limits overnight → laps fail. ACCEPTED: laps fail honestly, treadmill
  escalates to a visible halt + Mac notification if persistent (that visibility is the feature).
- D12 claude CLI auto-update changing flags mid-operation. ACCEPTED: laps fail honestly; foreman
  fixes flags next session.
- D13 fd "leak" in one-shot python -c calls. REFUTED: processes exit per lap; nothing accumulates.
- D14 Nightly window string comparison at 06:59/07:01 boundary. REFUTED: walked the truth table;
  zero-padded HH:MM string compare is correct for this window.
- D15 Concurrent spend.csv writes corrupting budget data. ACCEPTED: single-loop lock makes
  concurrency impossible in practice; CSV appends are line-atomic at these sizes.
- D16 Engine restart double-fires reminders (TriggerWatcher._fired is in-memory). OPEN: P1 work
  item — persist fired-state on the loop record (e.g. fields["fired_at"]).

## Class E — context/continuity failures
- E1 Session compaction loses operating knowledge. PREVENTED: autoCompactEnabled=true (was false!);
  CLAUDE.md auto-loads the router into every session; STATE.md + FOREMAN_STATE.md + TARGET.md +
  this ledger carry the durable truth; persistent memory dir written.
- E2 A fresh session not knowing a lap is mid-flight. CONTAINED: factory/.lock + .lap_in_progress
  on disk; CLAUDE.md instructs checking before committing.
- E3 The plan living only in conversation. PREVENTED: approved plan at
  ~/.claude/plans/oh-my-god-everybody-iterative-puffin.md; phases mirrored in factory/PHASES.yaml.

## Standing rules that keep this list honest
1. Every new failure found → entry here (builders and judges are instructed to append; this file
   lives under logs/ so lap roles may edit it).
2. Every PREVENTED/CONTAINED entry needs a regression check (gate, scan, selftest, or smoke) —
   no fix without a tripwire that notices its return.
3. REFUTED entries stay listed so the same false alarm isn't re-investigated.
4. The foreman re-runs an adversarial audit pass at every phase boundary.
