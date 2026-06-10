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

## Class B/C addendum (judge, lap 20260610T060701Z)
- B9 gate_P1.sh's verdict_pass contradicts the gate's own stated contract. The header (lines
  11-12) says "the gate cannot CLOSE with skipped live legs unless FACTORY_P1_ALLOW_MOCK=1",
  but the code computes verdict_pass = ok_core(S1-S4) and (live_hands or allow_mock) — S5
  skipped:true and S6 pass:null never block, and allow_mock is consulted only for live_hands,
  never for skips. PHASES.yaml's P1 close_when ("S1-S6 live ... real trigger-fired SMS ...
  MP3 day clean") is therefore broader than anything the gate enforces. Tonight's mechanical
  P1 close (lap 20260610T060701Z) proves S1-S4 live + the real scheduler — it does NOT prove
  live SMS (S5, owner-blocked: no OWNER_PHONE/Twilio) or the MP3/fixture day (S6, deferred;
  its substance is partially covered by the 16-day 8-persona evals each lap). TARGET v3
  STAGE 1 explicitly pre-authorized closure at this scope, so this is a foreman documentation/
  enforcement inconsistency, not builder gaming — but as written the ladder text and the gate
  disagree about what "P1 closed" means. OPEN (foreman-only): either amend PHASES.yaml P1
  close_when to the proven scope (SMS reality gates at P3, full-day reality at P5) or reopen
  P1 when Twilio creds land. Regression check: every phase close_when must list exactly the
  legs its gate hard-fails on; a gate header promising a rule its exit code doesn't implement
  is the tripwire.
- C12 scans.sh tree_clean WARNs on the loop's own marker file: the porcelain filter excludes
  `?? logs/`, `?? factory/.lock`, `?? .anticipy` but not `?? factory/.lap_in_progress`, which
  exists during every verify_gate run — so every nightly lap reports
  "WARN: uncommitted tracked changes" (a mislabel: it is an untracked loop-control file, not a
  tracked change). Confirmed on lap 20260610T060701Z: the WARN's only cause was
  .lap_in_progress; `git status --porcelain` minus the marker was clean. A permanent WARN is
  noise that trains everyone to ignore the one scan that would catch a genuinely dirty tree
  (e.g. a judge's uncommitted ledger append being measured into the next lap, or eaten by its
  revert). OPEN (foreman-only): add `factory/\.lap_in_progress` to the exclusion and rename
  the message to say what was actually found.

## Class F addendum (builder lap 20260610T062952Z)
- F2 Triage classified by bag-of-words ANYWHERE-matching and inverted on speech-act shape:
  base-form word-boundary verbs missed explicit imperative commands phrased with inflections
  or idioms ("put that on my calendar", "Block Wednesday 5 to 6:30", "get those answers over
  to <colleague>", "someone needs to chase..."), while the SAME words in noun position passed
  triage as narration ("Pipeline review.", "Forecast draft:", "Lab report draft is at 60%")
  and the harm-line then ACTed on them via the draft/research reversible categories. Evidence:
  in run 20260610T060701Z-pre, 16/16 misses were decision=ignore on explicit commands and
  17/19 false actions were noun-position status narration. PREVENTED (2026-06-10, lap
  20260610T062952Z): triage rewritten to command-shape detection (clause-initial imperatives,
  calendar-put/block-time/cart/causative-get/delegation idioms) plus confident negatives
  (retraction/countermand, conditional vents, trailing hedges, already-handled, vocative
  asides); harm-line routes spoken calendar-puts to calendar_hold and delegated hand-offs to
  binding ask. Regression checks: pinned shape cases added to engine/scripts/test_triage.py
  (recall hard bar 1.000 now includes 7 command shapes; noise-drop includes status/retraction/
  conditional/trailing-hedge shapes) and test_harmline.py (delegated sends must ask, spoken
  calendar-puts must act); the 8-persona stub eval recomputes the full surface every lap.
- F3 The harm-line's casual-send downgrade (_recipient_casual) scans the WHOLE memory-context
  haystack for any casual token ("daughter", "friend", ...) instead of testing the actual
  RECIPIENT, so any send assessed with non-abstaining high-relevance memory that happens to
  contain a casual word anywhere downgrades to ACT. Observed live in this lap's first eval
  pass: 3 delegated work sends ("someone should ping the <vendor> folks", "get that letter
  drafted and over to <colleague>") cleared to act with category casual_send = 3 act-on-ask
  false actions. CONTAINED for delegation (this lap): _DELEGATED_SEND now returns binding-ask
  BEFORE the casual path can run (pinned in test_harmline.py). OPEN for first-person sends:
  "text <person> I'm running late" plus an unrelated casual token in recalled memory still
  downgrades to act on weak evidence. Fix candidate: extract the recipient phrase and test
  THAT against the casual list (or hand the gray middle to the P2 decider, which may only
  move decisions toward SILENT/ASK). Regression check when fixed: a battery case where the
  casual word is in memory context but the recipient is professional must ASK.

## Class F addendum (builder lap 20260610T070648Z)
- F4 The Track-B seed decider's tolerant parse (overnight/track_b/decider.py) tests
  `tok in raw` over a Python SET of {ACT, ASK, SILENT}: (a) it matches inside words —
  "multitasking" parses as ASK, so any model preamble containing such a word flips the
  verdict; (b) when a rambling reply names two verdicts ("I would ASK, not ACT"), set
  iteration order makes the result nondeterministic run-to-run. Harmless in Track B's
  offline scoring, but shipping it into the live pipeline would have made the safety
  filter itself flaky. PREVENTED (2026-06-10, this lap): the product decider
  (engine/anticipy_engine/proactive/decider.py) parses with a word-boundary regex and,
  when multiple verdicts are mentioned, deterministically picks the SAFEST
  (SILENT > ASK > ACT); no-match and every exception path return SILENT. Regression
  check: engine/scripts/test_decider.py pins "Multitasking is fun" -> SILENT,
  "I would ASK here, not ACT." -> ASK, "ACT or SILENT?" -> SILENT, raising/keyless
  gateways -> SILENT. The seed file is left as-is (overnight/ is read-only history).

## Class F addendum (builder lap 20260610T072358Z — first live-tier run)
- F5 The live decider (gemini-2.5-flash-lite, original Track-B prompt) read NARRATION as
  commitment: in the first live-tier dev-bank run (contractor_luis,
  logs/factory/runs/20260610T072358Z-live-smoke/), it returned ACT on banter/idiom lines
  ("Lunch truck burrito... Don't talk to me for eleven minutes", "Game's on. Suns by six.
  I'm calling it now"), future-schedule self-narration ("Early night. Texture crew at six",
  "Tomorrow: inspection prep..."), past-tense reports ("Swung by the Ramos lot..."), routine
  description ("Crew count, sweep, photos to Mrs. Chen"), and the F3 first-person casual
  send ("Telling Beto to try him") — producing 2 FALSE ACTIONS and interrupt 3.5/day at
  live tier vs 0 / 1.0 at stub (the lines reach the decider because live triage fails open,
  see F6). FIXED (this lap): the prompt was rewritten around the HANDOFF test — narration of
  one's own past/plans/social acts is never a task; a task exists only when the line
  delegates one (instruction/request, ownerless "someone should..." voicing, or unmistakable
  self-task). Self-authored 24-line probe (logs/factory/laps/20260610T072358Z/
  probe_decider.py, no bank content): 14/24 -> 24/24; live re-run on the same persona:
  false_action 2 -> 0, interrupt 3.5 -> 2.0, catch held 1.0. Regression checks:
  test_decider.py pins the prompt's F5 clauses; the probe script re-runs against any future
  cheap model; live-vs-stub persona compare is the standing method.
- F6 Triage's live-mode cheap-model tiebreak (proactive/triage.py _tiebreak) calls
  asyncio.get_event_loop().run_until_complete() INSIDE the engine's already-running event
  loop, which always raises (and leaves an un-awaited coroutine), so the except path fails
  OPEN — the model is NEVER consulted (verified: counting gateway shows 0 calls) and every
  ambiguous line passes triage at live tier. Net effect today: recall is preserved and the
  decider (Room 1.5) carries the precision burden alone, at one cheap call per ambiguous
  line. OPEN (deliberate defer: the fail direction is safe; fixing means making the triage
  path async — its own slice). Regression check when fixed: call actionable() under a
  running loop with a counting gateway and assert the tiebreak call actually happens and
  no RuntimeWarning is emitted.

## Class D addendum (builder lap 20260610T074854Z)
- D20 A bounded builder session that commits LAST can lose its whole lap: lap
  20260610T072358Z found F5/F6, fixed F5, and verified the fix live, but hit its session
  bound (num_turns=101, stop_reason=tool_use) before `git commit` — verify_gate captured
  the work to uncommitted.patch, warned tree_clean, recorded builder_commit=BASE, and the
  tree was reset; the fix was GONE from HEAD while the scoreboard row read kept=True.
  Only that lap's FAILURE_MODES entries (in the captured-but-unreset log files) flagged
  the loss. CONTAINED (this lap): the patch was recovered from the lap dir, independently
  re-verified (suite, live probe, live persona re-runs), and committed. Builder lesson
  (binding): commit the slice AS SOON AS it verifies, then keep polishing — never park
  verified product changes uncommitted. OPEN for the foreman: build_lap.sh could auto-WIP-
  commit at session end, or verify_gate could FAIL (not WARN) when uncommitted.patch
  touches engine/app/extension/macapp/shared. Regression check: any lap whose
  gate_results.json shows tree_clean WARN with product files in uncommitted.patch is this
  failure repeating.

## Class F addendum (builder lap 20260610T074854Z — F5 re-landed and extended)
- F5 (continued) The lost F5 fix was re-landed from lap 20260610T072358Z's
  uncommitted.patch, upgraded to that lap's authored-but-never-tested v4 variant (adds the
  "-ing"-openings-are-self-activity clause; probe 26/27 -> 27/27, the one v3 miss being
  present-progressive self-narration). Live re-verification then exposed ONE remaining
  live-tier false action, pre-existing under v3 (identical decision in the dead lap's
  unanalyzed live-full run): doctor_amara day02 self-personification self-talk
  ("...so morning-me has no excuses") — deterministic triage drops it in stub, but the
  F6 fail-open routes it to the decider at live tier, and the decider read the purpose-
  tail self-talk as a task. FIXED: two surgical prompt clauses (purpose tails don't make
  "-ing" self-activity an instruction; self-personification/self-talk is narration),
  verified on generic self-authored probes ("tomorrow-me"/"gym-me"/"future me" — no bank
  phrasing) with a same-domain imperative guard ("Remind me tonight to set out my running
  clothes..." must stay ACT): probe 31/31; live bank check contractor_luis + doctor_amara
  both false_action 0, catch 1.0, harm 0, interrupt 2.0/2.5 (<= 3.0). Residual (accepted,
  not a false action): "Reminder-me must exist" still draws decider ACT -> ask — it
  restates the prior line's already-captured reminder, so the cost is one redundant ask;
  that is ask-debounce/goal-dedupe territory, a different mechanism than the prompt.
  Regression checks: test_decider.py pins the '"-ing" openings' clause; the lap-dir probe
  re-runs all 31 lines against any future cheap model.

## Class D addendum (builder lap 20260610T091120Z)
- D21 A kept=False revert DESTROYS the uncommitted factory accounting of every PRIOR kept
  lap since the last foreman snapshot: loop.sh's revert is `git reset --hard $BEFORE`, and
  product_scoreboard.csv / RATCHET.json are TRACKED files that no lap ever commits (last
  snapshot: foreman commit ea08490). Lap 20260610T083047Z died at its session bound
  (empty build.json -> D5 forced revert despite green gates) and the reset rolled both
  files back to ea08490's snapshot: the P1 first-close record (lap 060701Z) vanished from
  phases_closed, the ratchet bests regressed from catch_worst 1.0 / false 0 /
  interrupt_worst 1.0 to the 051949Z snapshot (0.5 / 19 / 10.5), treadmill regressed
  4 -> 1, and the six scoreboard rows for laps 060701Z / 062952Z / 070648Z / 072358Z /
  074854Z / 080849Z were erased. scoreboard.py then wrote 083047Z's row AGAINST the
  regressed ratchet (that row's "+0.5000" delta and treadmill_count=2 are artifacts).
  Two compounding consequences: (1) the treadmill escalation that should have fired at 5
  on lap 083047Z was silently DEFEATED (counter reset under it), so the loop kept running
  without waking the foreman — the state loss disabled the very mechanism designed to
  catch nights going wrong; (2) every future kept=False lap repeats the destruction for
  rows written since, because the accounting stays uncommitted between foreman snapshots
  (loop.sh:12's comment shows the hazard was understood for loop_journal.md — made
  untracked — but the fix never reached the tracked accounting files).
  CONTAINED (this lap, builder-side): RATCHET's stage check honestly reads "P1 not
  closed", so per TARGET v3 STAGE 1 this lap re-verified HEAD (suite 33/33; stub bank
  catch 1.0/1.0 false 0 harm 0 interrupt 0.625/1.0 — identical to the lost bests) and
  re-ran gate_P1 live (precheck verdict_pass=TRUE rc=0, S1 cleanup proven, S2 stray
  cleaned with read-back), then set attempt_gate_close=true so verify_gate/scoreboard.py
  — the sole writers — re-record the P1 close mechanically. The six lost rows are NOT
  builder-reconstructable (forbidden files); every lost lap's metrics.json /
  gate_results.json / scoreboard.out SURVIVES under logs/factory/laps/<lap>/ (untracked
  files survive reset --hard) for foreman reconstruction.
  OPEN for the foreman (loop.sh is control plane; pick one): commit scoreboard/RATCHET
  immediately after every scoreboard.py write; or make the revert surgical
  (`git checkout $BEFORE -- engine/ app/ extension/ macapp/ shared/ scripts/ ...` instead
  of reset --hard); or untrack the accounting files the way loop_journal.md already is.
  Regression check: after any kept=False lap, RATCHET.phases_closed must remain a
  superset of the phases STATE.md records as closed, and the scoreboard must still
  contain every row that has a matching laps/<lap>/scoreboard.out — any mismatch is this
  failure repeating.
- B5 (recurred, contained) The live S2 reminder leg again created a second real calendar
  event (the planner books a calendar event for the reminder; the gate's built-in cleanup
  covers only S1). This lap's precheck stray (92vi6retu383hf8m72lu09l27o) was deleted via
  Arcade GoogleCalendar.DeleteEvent with ListEvents read-back (0 [Anticipy test] events
  remain in the -1/+2-day window). NOTE: verify_gate's mechanical gate run after this
  session will strand a fresh S1+S2 pair (B7: the launchd chain gives the gate shell no
  ARCADE_API_KEY, so even S1's built-in cleanup fails there) — morning foreman cleanup
  required until B7 is fixed; the stranded ids will be in
  logs/factory/runs/gatep1-20260610T091120Z/gate_p1_results.json.
