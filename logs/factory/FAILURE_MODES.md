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
- B4 gate_P1's S1 cleanup NEVER fires: it reads `proof.id`/`proof.event.id`, but the orchestrator
  writes step-keyed proofs (`proof["0:create_event"].id`) — so B1's "deletes its test event" has
  never been true on a live run; every live gate run stranded a real calendar event. CONTAINED
  (2026-06-10, lap 20260610T052102Z): builder enumerated goal proofs across all gatep1-* run dirs,
  deleted 4 stray events via Arcade, verified gone by ListEvents read-back. OPEN for the real fix
  (foreman-only: gate_P1.sh must extract ids from step-keyed proof values). Regression check:
  after any live gate run, ListEvents over the window must show no gate-created ids.
- B5 the live S2 leg ("remind me to ... at <time>") ALSO creates a real calendar event through the
  harm-line calendar_hold ACT path — a second per-run artifact the gate never attempts to clean.
  CONTAINED with B4 (deleted + read-back). OPEN: gate cleanup must cover S2's goal proof too.
- B6 the deterministic calendar planner DROPS the quoted event title: the S1 artifact lands in the
  real calendar as generic "Calendar event", not "[Anticipy test] gate-P1 <lap>" — a semantically
  wrong real artifact that also breaks the B3 label convention, and it makes B4's strays unlabeled
  and hard to attribute. OPEN: next P1 slice — quoted-title extraction in the orchestrator's
  calendar pre-plan + a test pinning the summary.

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
- C12 Holdout scan v2 still false-positived on FREE-TEXT tool inputs: the builder's Workflow
  script PROHIBITING holdout access mentioned the path and reverted lap 20260610T052102Z —
  a lap whose P1 slice had legitimately PASSED gate_P1 (S1-S4) live. PREVENTED (2026-06-10):
  scan v3 inspects only operational fields of file/exec tools (Read/Write/Edit paths,
  Glob/Grep path+pattern, Bash command); free-text prompt/script fields are exempt.
  Regression: both real lap streams PASS, synthetic Read and Bash violations FAIL.
  Residual (ACCEPTED + documented): a builder could delegate holdout reads to a subagent
  whose tool calls don't appear in the parent stream — mitigated by prompt prohibition,
  judge metric recomputation from raw runs, and holdout being judge-run data anyway.
- C13 scans.sh `|| echo` wiring appended a second line to the scan value, producing invalid
  scans.json → gate_results.json never written (cascading instrument failure). PREVENTED
  (2026-06-10): rc captured via PIPESTATUS, value sanitized to one line.

## Class B addendum
- B4 gate_P1's S1 created a real calendar event whose id the cleanup failed to extract
  (proof nests step results as {"0:create_event": {id}}); cleanup silently skipped and a
  stray event reached the owner's real calendar. CONTAINED: event found and deleted with
  read-back confirmation same night. PREVENTED going forward: recursive proof-walk
  extraction + S1_cleanup is ALWAYS written (silent-skip impossible).

## Class D — process/ops failures
- D17 macOS TCC blocked the 22:30 launchd run outright ("Operation not permitted"): the repo
  lives on ~/Desktop, a privacy-protected folder background jobs cannot read. Found live at
  first nightly fire 2026-06-09 22:30 PDT. CONTAINED tonight: loop started manually from the
  TCC-blessed interactive context (caffeinate+nohup). RESOLVED 2026-06-10 ~23:10 PDT: repo moved to ~/Anticipy (option b), proven by launchctl kickstart writing the journal with an empty error log. Original options were:
  (a) 30-sec System Settings grant — Privacy & Security → Full Disk Access → add
  /usr/bin/caffeinate (the LaunchAgent's responsible binary), or (b) move the repo out of
  ~/Desktop (structural, ~15 min, requires path updates + session restart). Verify either by
  `launchctl kickstart gui/$UID/com.anticipy.factory` and reading logs/factory/launchd.err.log.
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

## Class F — product decision failures (the gate caught these; they are why the gate exists)
- F1 Hedge-nonspecific vent lines ("ugh, I should really call my landlord someday") survived triage
  (positive "i should"/"call" cues) and the harm-line's unclassified branch fail-safed them to ASK —
  an interruption on a vent (gate_P1 S3 red; also feeds interrupt_cost). PREVENTED (2026-06-10, lap
  20260610T052102Z): triage drops hedge words (someday/eventually/at some point/one of these days/
  when-I-get-a-chance) when no concrete time anchor cancels the hedge; capture still remembers the
  line. Regression checks: vent cases in engine/scripts/test_triage.py + gate_P1 S3.

## Standing rules that keep this list honest
1. Every new failure found → entry here (builders and judges are instructed to append; this file
   lives under logs/ so lap roles may edit it).
2. Every PREVENTED/CONTAINED entry needs a regression check (gate, scan, selftest, or smoke) —
   no fix without a tripwire that notices its return.
3. REFUTED entries stay listed so the same false alarm isn't re-investigated.
4. The foreman re-runs an adversarial audit pass at every phase boundary.

## Class D addendum (night of 2026-06-09/10)
- D18 OpenRouter unfunded blocked all live engine model calls (the old loop's killer).
  PREVENTED (2026-06-10): the gateway's OpenAI-compatible path is now URL/key-configurable
  (ANTICIPY_OPENAI_BASE_URL / ANTICIPY_MODEL_API_KEY); .env.local points it at Gemini's
  free-tier OpenAI endpoint using the GEMINI_API_KEY that already existed. Verified live
  through the engine gateway (cheap + smart both answered); suite green. Groq also verified
  as a fallback provider; Cerebras 404'd on the tested model name.
- D19 Foreman killed a mid-build lap (20260610T055231Z) to supersede it; its uncommitted
  WIP was saved to the lap dir (killed_wip.patch) and the tree restored — but its UNTRACKED
  new files survived the checkout and blocked the patch apply until removed. CONTAINED:
  documented here; loop's own cleanup never hits this (builders commit); foreman kills must
  also `git clean` check untracked product files.

## Class B addendum (lap 20260610T060701Z)
- B7 gate_P1's S1 cleanup (fixed for id-extraction in a6ce4a3) reads ARCADE_API_KEY/ARCADE_USER_ID
  from the GATE SHELL env, but the production chain (launchd -> loop.sh -> verify_gate.sh ->
  gate_P1.sh) exports only PATH + factory.conf caps and nothing sources .env.local — so on every
  mechanical verify_gate run the cleanup raises and S1's real event strands with
  "MANUAL CLEANUP NEEDED: <id>" in S1_cleanup. Builder-side proof both ways (2026-06-10, lap
  20260610T060701Z): with .env.local exported the cleanup deleted its event (S1_cleanup.deleted=
  inkiukb899odvrethklgs5n5hc, ListEvents read-back clean); launchd plist confirmed to set only PATH.
  OPEN (foreman-only fix: gate_P1.sh or verify_gate.sh must export .env.local before the heredoc).
  Regression check: any verify_gate-run gatep1-*/gate_p1_results.json must show S1_cleanup.deleted
  as an event id; an S1_cleanup.error / "MANUAL CLEANUP NEEDED" note is the tripwire.
- B8 gate_P1's S5 leg derives twilio_live from the GATE SHELL env, not engine reality: with
  .env.local exported it reports skipped:false (TWILIO_MOCK=false in env) even though the engine's
  channel path sent ask+notify to placeholder +10000000000 (real ChannelWorker/OWNER_PHONE wiring is
  TARGET item 4, unbuilt) and the leg implements no actual SMS-SID check (its note is aspirational)
  and writes no pass key. Harmless to the verdict today (ok_core is S1-S4), but when Twilio goes
  live this leg would claim live coverage without checking anything. OPEN (foreman-only): S5 must
  read the engine's channel audit + Twilio REST, keyed off the ENGINE's effective config. Related:
  the channel stub logs {"sent": true, "to": "+10000000000"} — an audit line that could be mistaken
  for a real send; the real ChannelWorker should mark mock sends as mock.
