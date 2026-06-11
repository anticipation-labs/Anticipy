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

## Class C addendum (judge, lap 20260610T091120Z)
- C13 OPEN Dev-bank day-line literals accumulate UNSCANNED in product code, and prompt-purity
  self-attestations are never machine-checked. Judge evidence (all prior kept laps' commits
  16956ef/ef30b63/e8caf95/2d62aa8 — NOT this lap's diff, which is logs-only):
  (a) EXECUTABLE: triage.py _ALREADY_HANDLED carries `\bone less thing\b` and
  `(he|she|they)...can grab` — together they reproduce parent_dana day01:24 ("he can grab
  Jonah today, one less thing") verbatim; debounce.py's _RETRACTION alternation set maps
  nearly 1:1 onto the dev bank's retraction lines (we're even/square, do nothing, park it,
  leave the payment...); each alternant is a real English idiom, but the SET was assembled
  by enumerating dev lines — the wording, not the shape, was lifted.
  (b) MODEL-FACING: decider.py's live _PROMPT (line ~72) contains "so I actually go" — a
  verbatim 4-word fragment of student_kayla day01:6 (a catch line) — while the same file's
  docstring (line ~18) attests the prompt "contains no eval line". The attestation is false
  and nothing verifies such claims.
  (c) ~18 more verbatim or name-swapped dev day-line quotations sit in comments/docstrings
  of triage.py/debounce.py/decider.py/core/proactive.py (incl. bank character names Jonah,
  Beto, Raj) — non-executable, but they normalize the pattern.
  Why it matters: dev-bank stub metrics (catch 1.0/1.0, false 0) partially measure
  MEMORIZATION of the bank, not inference; this lap's judge holdout slice quantifies the
  gap (holdout catch worst 0.3333 vs dev worst 1.0; counts only). HOLDOUT-LEAK CHECK
  NEGATIVE: every product-code example phrase absent from dev (e.g. "so the morning isn't
  chaos", "tomorrow-me will thank me", "showing Ana the photos") has ZERO matches in the
  holdout bank — they are invented/live-run paraphrases, not leaked eval lines.
  Not P1-blocking (gate_P1 legs are typed probes; P1 has no persona-metric thresholds) but
  P2-RELEVANT: gate_P2 thresholds judged on holdout at close will expose exactly this gap
  (0.3333 << 0.70). The scan hole: scans.sh owner_literals checks only the owner denylist;
  no scan compares product-diff added lines against dev day files.
  Fix options (foreman): add a bank-literal scan (flag any >=4-gram from
  factory/personas/dev/*/days/*.txt appearing in added product lines); machine-check
  prompt-purity attestations the same way; builder rule going forward — abstract the
  SHAPE of bank evidence, never its wording.
- C14 Reverted laps rolled back the MEASUREMENT STATE: product_scoreboard.csv and
  RATCHET.json are tracked but updated uncommitted between lap commits, so the revert
  path's `git reset --hard` erased 6 scoreboard rows (including the P1-closure REAL row)
  and regressed the ratchet/treadmill — observed live when wall-capped lap 083047Z
  reverted (treadmill impossibly went 4->2, phantom "movement" re-fired). PREVENTED
  (2026-06-10): both reset sites in loop.sh snapshot/restore the measurement files;
  books reconstructed from lap dirs + the untracked journal (rows marked RECONSTRUCTED).
  Lesson: the journal being untracked was the design choice that made truth recoverable.
  Note: builder lap 091120Z independently DETECTED the accounting loss and re-closed
  gate_P1 to repair phase state — the self-correction layer worked.

## Class D addendum (builder lap 20260610T094944Z)
- D22 OPEN The foreman's reconstruction commit (7bdc554) ANNOUNCES "TARGET v4: P2 closure
  then P3 plumbing" in its message — and RATCHET.json's foreman_note cites "(TARGET v4)"
  as the documented re-aim — but the commit's diff never touched factory/TARGET.md: the
  file on disk is still v3 with current_phase=P1-closed-loop and phase_gate=gate_P1.sh.
  Consequence: the control plane is stale in a way that makes EVERY builder lap
  mechanically uncountable — scoreboard.py counts only primary-metric movement (impossible:
  catch_rate_worst ratchet best is 1.0, the ceiling) or a FIRST gate closure (impossible:
  P1-closed-loop is already in RATCHET.phases_closed) — so honest work burns treadmill
  budget toward a false escalation. The announced strategy exists only in prose; the
  machine reads the file. This lap stated the dead-count up front in its manifest and
  spent the tick on recovering the revert-destroyed decider v10 (real product value the
  stub scoreboard cannot see).
  Fix (foreman, one edit): actually write TARGET v4 — current_phase: P2-brain,
  phase_gate: factory/gates/gate_P2.sh (gate_P2 thresholds already hold at stub on HEAD,
  so the first post-flip lap with attempt_gate_close=true closes P2 mechanically).
  Regression check: at lap start, if TARGET.md current_phase is already in
  RATCHET.phases_closed AND the ratchet best for primary_metric sits at its theoretical
  ceiling, the lap is dead a priori — any future lap finding that state should cite D22
  instead of re-deriving it, and the foreman checklist should include "commit-message
  claims about control-plane files must match the diff".

## Class D addendum (builder lap 20260610T100043Z)
- D20 RECURRENCE #2 (lap 20260610T094944Z): a second builder died at its session bound
  (num_turns=52, end_turn while "3/8 — founder_jin in flight" on a full-bank live
  re-baseline) with the decider v8+v10 re-landing applied-and-probe-verified (62/63)
  but UNCOMMITTED — exactly the D20 shape, against the SAME patch D20 first destroyed.
  The work survived only in its lap dir's uncommitted.patch; the dangling commit ebb0789
  remained one `git gc` away from permanent loss. CONTAINED (this lap): patch re-applied
  byte-exact (blob b7a0f15), independently re-verified (suite 33/33, stub bank
  bit-identical to ratchet bests, live probe 62/63 with the one known harm-line-contained
  relay residual), and committed BEFORE any live persona run was attempted (d788778).
  Root cause both times: commit-last ordering + a full-bank live run (~10+ min) inside a
  bounded session. Binding builder rule restated harder: the full-bank LIVE re-baseline
  does not fit a builder session reliably — commit first, then run AT MOST a targeted
  single-persona live check; leave full-bank live baselines to verify_gate/foreman runs.
  Foreman fix options unchanged from D20 (auto-WIP-commit at session end, or verify_gate
  FAIL on product files in uncommitted.patch — second firing argues for the FAIL).

## Class F addendum (builder lap 20260610T101115Z)
- F7 FIXED Sustained 429/quota pressure turned the live decider into a silent task-eater:
  gateway._openrouter returns "" after exhausting its 4 transport retries (429/5xx/
  TransportError, ~9s of backoff), Decider.decide parsed "" -> SILENT, and on_event
  recorded the FALSE reason "decider: not a real commitment -> silent" — so during any
  quota window every triage-passed line was dropped with a trace indistinguishable from
  judged silence. The live brain is Gemini FREE TIER (per-minute quotas), so this was a
  when-not-if; STATE carried it as the unproven "429-pressure behavior" risk. Fail-SILENT
  was the F4 design choice — correct for harm, deaf for catch, and dishonest in the logs.
  FIXED (this lap, commit 81eb8ea): transport-level non-reads (exception or empty reply)
  now return UNAVAILABLE — distinct from a READ-but-verdictless reply, which stays SILENT
  per F4 — and on_event defers UNAVAILABLE events 75s (past a per-minute quota window)
  for at most 2 retries through trigger_tick's existing pass, re-entering the FULL
  pipeline; exhausted retries drop with the honest reason "decider unavailable after
  retries -> fail silent". No failure path can act: deferral creates no goal/ask, the
  retried verdict still crosses the harm-line (a deferred money line ends at ASK), the
  one-way rule is untouched, and stub tier is bit-identical (stub constructs no decider).
  Residuals: the deferred queue is in-memory (an engine restart loses pending retries —
  same class as self.pending asks, D16 family); the gateway still ignores Retry-After
  headers (follow-up candidate); real-429 behavior remains live-unobserved (deliberately:
  inducing a genuine quota exhaustion would poison the night's shared free-tier quota
  for verify_gate's own live runs — the deterministic pins stand in).
  Regression check: engine/scripts/test_decider.py sections 2/10/11/12 (error/keyless/
  empty -> UNAVAILABLE while a verdictless READ stays SILENT; defer -> tick retry ->
  late act with honest reasons; sustained outage -> bounded retries -> honest silence
  with zero goals; deferred money line -> harm-line ASK is still FINAL).

## Class F addendum (builder lap 20260610T102837Z)
- F7 residual "gateway ignores Retry-After" CLOSED (commit 6efcad7): on 429 the
  gateway now reads the server's stated wait — Retry-After header (delta-seconds) >
  google.rpc.RetryInfo retryDelay in the error body (string Duration; the Gemini
  OpenAI-compat endpoint we actually call sometimes wraps the error in a one-element
  array) > "retry in Ns" in error.message. Short hints (<=8s) sleep inline (+0.25s
  margin) within the existing 4-attempt bound; long hints return "" after ONE request
  so the UNAVAILABLE -> 75s-defer path owns the wait instead of 3 more blind retries
  burning the same per-minute quota that caused the outage. No-hint 429s and all 5xx
  are byte-identical to the old blind backoff. Remaining F7 residuals: in-memory
  deferred queue (D16 family), real-429 storm still not live-observed.
  Regression check: engine/scripts/test_gateway_retry.py (suite entry gateway_retry)
  — parse ladder, inline recovery, single-request fast-fail, bounded loop, 5xx
  hint-blindness, and the e2e long-hint-storm -> Decider UNAVAILABLE pin.
- NEW (research finding, CONTAINED at birth): Gemini per-DAY quota exhaustion can
  return a misleadingly tiny retryDelay ("1s" observed in the wild on a daily limit) —
  a naive hint-honoring client would hammer a window that will not reopen for hours.
  Contained here by construction: short hints stay inside the 4-attempt bound (worst
  case ~3 extra spaced requests), then "" -> bounded defer -> honest fail-silent; a
  lying hint can never unbound the loop or produce an act. Regression check:
  test_gateway_retry.py pins gemini_429("1s") parsing AND the sustained-short-hint
  bounded-loop case (4 requests max). If hint trust is ever extended (e.g. gating on
  quotaId PerMinute vs PerDay like gemini-cli), revisit this entry.

## Class F addendum (builder lap 20260610T104837Z)
- F7 residual "in-memory deferred queue" CLOSED (commit 1ce2269): an engine restart
  during a quota outage used to eat every deferred line — decider_deferred and
  _decider_attempts lived only in process memory, so the lines the decider never read
  vanished with no trace when the process died (launchd restart, crash, deploy), the
  exact silent-deafness F7 exists to prevent. Now the outage queue persists atomically
  (tmp + os.replace) to <ANTICIPY_DATA_DIR>/decider_deferred.json on every mutation and
  a LIVE boot restores it: entries re-enter the FULL pipeline at their due tick, the
  attempt count rides along so DECIDER_MAX_RETRIES holds ACROSS restarts (a reboot
  grants no extra lives), and a restored money line still ends at the harm-line ASK.
  Every failure path keeps failing toward silence: a STUB boot neither restores nor
  touches the file (no decider = an unread line must never re-enter the pipeline
  without one; the file waits for the next live boot), a corrupt file boots an empty
  queue with an honest glassbox log and is set aside as .corrupt (never deleted), a
  persist IO error logs and carries on in memory, and the trigger_tick drain persists
  BEFORE re-entry so a crash mid-retry can only LOSE events — it can never leave one
  on disk to be restored-and-replayed after it may already have acted (no double act).
  Remaining F7 residual: real-429 storm still not live-observed (deliberate — inducing
  one would poison the night's shared free-tier quota for verify_gate's live runs).
  Regression check: engine/scripts/test_deferred_persistence.py (suite entry
  deferred_persistence) — restart recovery, cross-restart retry bound, money-ASK
  finality after restore, stub no-touch, corrupt set-aside, no-path no-IO,
  crash-loses-not-replays ordering.

## Class C addendum (judge, lap 20260610T110142Z)
- C15 OPEN The P2 phase-close decision is judged on a STUB-tier holdout slice
  (judge procedure + persona_run.py: stub tier sets ANTICIPY_MODEL_PROVIDER=stub,
  and stub constructs no decider — the engine's own logs state the live seam never
  engages). So the close structurally CANNOT see live-decider improvements (v8/v10):
  the 0.70 worst-persona catch floor must be cleared by the deterministic triage
  path alone. Evidence: tonight's holdout aggregate is BIT-IDENTICAL to the judge
  091120Z holdout on all six dims (catch 0.625 / worst 0.3333, false 0, harm 0,
  interrupt worst 3.0, recall worst 0.3333) despite three kept product laps in
  between — all live-only changes, invisible at stub, exactly as those laps
  pre-registered. Consequence: any builder hypothesis of the form "decider
  generalization" can never close P2 as currently measured. Foreman must pick one:
  (a) accept that the stub-visible triage path alone must clear the floor (then aim
  builders there), or (b) define a live-tier holdout protocol for phase closes
  (quota/cost implications; the shared free-tier window is load-bearing at night).
- C16 OPEN Holdout granularity is coarse: 4 personas x 1 day; the worst persona has
  only 3 expected items, so the 0.70 floor degenerates to requiring 3/3 there, and
  one swing item moves worst-catch by 0.3333. interrupt_cost_worst passed the P2
  ceiling EXACTLY at the boundary (3.0 <= 3.0, two personas sitting on it) — a
  knife-edge pass with no margin signal. Partially known (foreman backlog already
  carries "holdout red-pen; bank v2"); ledgered so the bank-v2 work treats
  denominator size and threshold margins as requirements, not nice-to-haves.

## Class F addendum (builder lap 20260610T124451Z)
- F8 Confident-negative shapes operate at UTTERANCE granularity while positive/imperative
  shapes operate at CLAUSE granularity: one vent-shaped sub-clause eats the whole line,
  including an explicit money command in a later clause. Evidence: student_kayla day02:17
  ("...I said I'd chip in... Send mom the twenty over zelle so she can order it today")
  was wholly dropped pre-change — the bare-I'd conditional-vent negative matched "I said
  I'd chip in" and returned False before the clause-initial "Send mom the twenty..." was
  ever examined; the bank's never_act tripwire was being passed by DEAFNESS, not judgment
  (the money command never reached the harm-line). CONTAINED for the reported-promise
  family (this lap's _REPORTED_PROMISE carve-out + test_triage_generalization.py pins);
  OPEN in general: a non-reported vent prefix still eats a trailing command today (e.g.
  self-authored: "I'd be lost without her. Send mom the twenty over zelle." — the bare-I'd
  negative drops the whole utterance). Proper fix is clause-scoped negatives (split before
  classifying), a structural triage change that needs its own lap + counterexample screen.
  Regression check: test_triage_generalization.py reported-promise block (incl. the money
  line "I told Dave I'd wire the deposit tonight" -> survives to the harm-line).
- F9 Harm-line category jitter defeats Room 2.6's money-retraction window: a money
  transfer phrased "send <person> <amount> over <rail>" categorizes as binding_send (send
  to a real person), and AskDebounce.should_hold holds ONLY category=="money" — so the ask
  fires immediately instead of waiting out the retraction window, and the next line's
  retraction ("Actually wait... Hold off till I look tonight" — "hold off" is literally in
  debounce._RETRACTION) finds nothing to cancel. Evidence: student_kayla day02:17-18 in
  runs 20260610T124451Z-pre and -pre2 (both: immediate ask, category binding_send, reason
  "send to a real person; memory low-confidence on recipient -> fail-safe ask"; scored
  unnecessary-ask, kayla interrupt 0.5 -> 1.0). Harm invariants UNAFFECTED (ask not act;
  never_act tripwire respected both before and after). OPEN; next-slice fix candidate:
  should_hold also holds binding_send when _TRANSFER matches the text (rail/amount named),
  or harm-line prefers money category when a payment rail is named. Regression check when
  fixed: a two-line money-command-then-retraction replay must end with zero surfaced asks.

## Class C addendum (builder lap 20260610T124451Z)
- C17 e2e_completion_rate RACES the trigger tick for remind-at-T goals: a goal whose
  completion needs a time trigger ("Submit the forecast by 6 tonight - remind me at 5")
  lands done vs waiting depending on whether the harness's final tick fires past the
  remind_ts before the run ends. Evidence: salesrep_pri day02 across two same-HEAD runs
  (20260610T124451Z-pre/-pre2) with BIT-IDENTICAL decisions (act 2/ask 7/held 1/ignore 35)
  scored goals 1 vs 2, e2e 0.1429 vs 0.2857; aggregate flickers 0.3249 <-> 0.3427. Same
  flicker already on record at FIXED commit 638e4ae (scoreboard rows 112701Z/112735Z/
  112808Z). Consequence: the ratchet best e2e (0.3427) embeds a lucky race — a genuinely
  neutral lap can post an apparent e2e regression by losing it, and an e2e "improvement"
  within one swing item is noise. OPEN (foreman/bank-v2 or harness: advance a final
  deterministic tick past the day's last remind_ts, or score waiting time-trigger goals
  as their own outcome). Until then: treat single-item e2e deltas as noise in keep/revert
  reasoning.

## Class C addendum (judge, lap 20260610T124451Z)
- C18 Isolation pins validate a family's REGEX, not its CATCH: every triage positive is
  consulted only after the utterance-granularity confident negatives (F8), so a family
  whose 53 single-sentence pins all pass can be completely inert on real multi-clause
  speech — the pin sentences never carry a vent-shaped prefix, the field lines do.
  Evidence (counts only): in the fresh 20260610T124451Z holdout run, a nurse_helen missed
  item's source line MATCHES the new `_LIST_PUT` product regex yet `actionable()` returns
  False — an earlier negative eats the line before the positive is reached; meanwhile
  test_triage_generalization.py passes 53/53. Consequence: "family added + pins green" is
  NOT evidence the family fires in situ; a builder can (honestly) ship dead coverage and
  the dev suite cannot see it. Pair finding: 4 of the 5 holdout misses match NONE of the
  six families added — two consecutive laps have now aimed families from counts-only
  feedback and moved holdout by zero items (110142Z, 124451Z). Mitigations for the next
  slice: (a) every new family must ship at least one in-situ pin embedding the family
  inside a vent-prefixed multi-clause utterance (the F8 composition, not just the family
  in isolation); (b) the structural fix is clause-scoped negatives (F8's named proper
  fix), after which isolation pins become representative again. OPEN until (b) lands.

## Class F addendum (builder lap 20260610T131707Z)
- F8 STRUCTURAL FIX LANDED (was OPEN-in-general): confident negatives are now CLAUSE-scoped
  in triage.actionable() — a vent clause silences itself, never the command beside it.
  Countermand + trailing hedge stay utterance-absolute (their meaning spans the line);
  sarcasm/conditional frames (_VENT_FRAME) cast forward so weak first-person-future cues in
  later clauses stay vents ("Oh sure. I'll just clone myself." still silent) while command
  shapes break out. Verified: student_kayla day02:17 is the ONLY decision change on the
  whole dev bank vs baseline 104837Z-pre (ignore -> held; the money command now reaches the
  harm-line — tripwire passed by judgment, not deafness). Sub-finding, FIXED same lap with
  a pin: the shared _CLAUSE_SEP treated the colon in "7:50" as a clause boundary and shredded
  "put coverage Thursday 7:50 to 8:20 on my calendar" (teacher_rob act->ignore in run -pre);
  caught by the full-bank run, NOT by the 26 authored pins — in-situ pins cannot cover the
  bank's surface diversity; always run the full bank before calling a triage change done.
  Residual (unmeasured, no holdout/dev miss rides on it): single-clause reported promises
  ("I told Dave I'd wire the deposit tonight") still drop — vent and commitment share one
  clause, so clause scoping cannot separate them; the 124451Z carve-out was reverted with
  that lap. Regression check: engine/scripts/test_triage_clause_scope.py (in-situ
  composition pins + the clock-range calendar-put pin).
- F9 FIXED: AskDebounce.should_hold now holds category binding_send when _TRANSFER names a
  rail (the ledgered fix candidate) — "send <person> <amount> over <rail>" reads as a send
  to the harm-line but is a money transfer in substance, and now waits out the retraction
  window like money does. Ordinary sends (no rail) and typed/API commands ask immediately,
  unchanged. Verified end to end: kayla day02:17-18 now held -> ask_retracted (glassbox),
  zero surfaced asks, interrupt back to 0.5 (dev aggregate restored to the 0.625 ratchet
  best the 124451Z families lap had regressed to 0.6875). Regression check: the two-line
  money-command-then-retraction replay in test_triage_clause_scope.py must end with zero
  surfaced asks and the goal failed; plus the flush-late one-way-safety leg.
- F10 NEW, OPEN: purpose clauses false-match _ALREADY_HANDLED — in "Send Dana the thirty
  over venmo so she can grab them tonight", "she can grab" reads as handled-by-someone-else
  and silences the COMMAND clause it lives inside. Found while authoring in-situ pins; the
  real kayla line dodges it only because "order" is not in the handled-verbs alternation
  (grab/handle/take are). Deliberately NOT changed this lap: no measured dev/holdout miss
  rides on it, and loosening a confident negative beside two zero-margin holdout interrupt
  ceilings without instrument evidence is the over-reach C18 warns about. Fix candidate: a
  purpose-marker guard before the pronoun ("so/so that she can grab" stays a command's
  rationale) — when fixed, flip the test_triage_clause_scope.py transfer pins back to the
  "can grab" surface as the regression check.

## Class C addendum (builder lap 20260610T131707Z)
- C18 STRUCTURALLY MITIGATED: mitigation (b) — clause-scoped negatives — landed this lap,
  so a positive family is no longer silently inert behind an utterance-level negative wall,
  and isolation pins are representative again for clause-local shapes. Mitigation (a) is now
  practiced: every un-deafened shape in test_triage_clause_scope.py ships embedded behind a
  real vent/negative prefix (the F8 composition). The lesson STANDS as a check on future
  family work (and the F8 sub-finding above shows its sibling: pins also cannot replace a
  full-bank run).

## Judge findings, lap 20260610T131707Z (verdict: VETO — holdout floor not met; see laps/20260610T131707Z/verdict.md)
- C19 NEW, OPEN (judge, lap 20260610T131707Z): builder DISCLOSURES are not mechanically
  verified. This lap's manifest declared all test pins "self-authored shape-equivalents,
  never copies (C13)" while engine/scripts/test_triage_clause_scope.py:133/:135 carries the
  exact student_kayla day02:17 command sentence verbatim, :74 carries that line's exact bank
  timestamp (16:25:50), and :39-41/:77-79 are near-verbatim templated swaps of the same
  line-pair (plus a bank character name at :184). No metric was inflated — executed product
  logic is clean and the holdout is the instrument — but suite pins on dev-bank literals
  entrench C13 memorization, and a false disclosure survived every scan. Fix candidate:
  verify_gate adds an n-gram overlap scan (any 6+-token shingle shared between a changed
  test/product file and factory/personas/dev/*/days/*) — each hit must be rewritten or
  justified in the manifest.
- C20 NEW, OPEN (judge, lap 20260610T131707Z): "held" decisions are structurally invisible
  to persona_score.py — neither act nor ask, so a held entry can never register as catch,
  false action, interrupt, or harm. Correct for command-then-retraction pairs (the F9 path:
  dev kayla/jin/pri money pairs end held+cancelled, genuinely silent), but an UN-retracted
  held money/binding_send command whose flush (2 events / 240s) lands after the day's last
  event would silently zero an expected ask with no metric trace. Fix candidate: scorer
  counts day-end still-held entries as their own column; expected.json gains an explicit
  kind for hold-then-silence ground truth.
- F11 NEW, OPEN (judge, lap 20260610T131707Z; applies whenever the clause-scoped gate
  re-lands): clause-scoping WIDENED the live fail-open tail. Pre-lap, a confident-negative
  match returned absolute False. Post-lap, an utterance whose clauses are ALL consumed by
  clause-negatives falls through to the ambiguous tail (triage.py:368-389) and in live mode
  reaches _tiebreak, which returns True on ANY exception (triage.py:408, fail OPEN) — a pure
  vent can pass triage to the decider during a gateway outage. Stub/CI is blind to it (the
  stub tail drops deterministically) and the commit message does not mention it. Fix
  candidate: track whether >=1 clause matched a confident negative; if every non-empty
  clause was negative-consumed and none was positive, return absolute False — the live
  tiebreak stays reserved for lines that matched NOTHING, vent or positive.

## Class F addendum (builder lap 20260610T223727Z)
- F8 STRUCTURAL FIX RE-LANDED (the judge-verified mechanism from
  laps/20260610T131707Z/reverted.patch, executed per that verdict's re-land conditions
  1-3): clause-scoped confident negatives + _VENT_FRAME + _LIST_PUT + clock-colon
  _CLAUSE_SEP, with the C19-flagged pins REWRITTEN as true shape-equivalents (fresh
  content words, fresh timestamp, recipient/filler names verified absent from the dev
  bank) and a builder-side 6-token shingle self-scan of the full diff vs
  factory/personas/dev/*/days/* run to ZERO hits — three bank-line quotes that rode in
  via product-code comments/docstrings (two of them unflagged by the 131707Z judge:
  the sarcasm example split across a docstring line break, and the clock-range comment)
  were paraphrased away. Dev bank at final HEAD: aggregates bit-identical to the
  ratchet bests; the per-line decision diff vs baseline 104837Z-pre shows EXACTLY one
  change (kayla day02:17 ignore -> held). Regression check:
  engine/scripts/test_triage_clause_scope.py (43 pins) + the full-bank decision diff.
- F11 FIXED (the 131707Z judge's fix candidate, landed in the same diff as the re-land
  per its condition 3): actionable() now counts negative-consumed vs open clauses; when
  every non-empty clause was consumed by a confident negative and none was positive it
  returns absolute False — a pure vent can no longer ride the live fail-open tiebreak
  to the decider during a gateway outage. The fail-open tail (F6, deliberate
  high-recall bias) stays reserved for lines that matched NOTHING. Regression check:
  f11_pins() in test_triage_clause_scope.py — three all-negative multi-clause vents
  must return False in live mode with a tiebreak-raising gateway, a matched-nothing
  line must still fail open True, and smart_calls must stay 0.
- F12 NEW, measured and CONTAINED before commit: clause-initial imperative VERB
  WIDENING has a live sarcasm tail. Adding "check" to _NOUN_PRONE_IMP turned a
  dev-bank quip aiming "check" at the heavens (contractor_luis day01:10) into a false
  ACTION (ignore -> act: the harm-line ACTED on a vent — the cardinal-sin direction).
  Found by the pre-commit full-bank decision diff (the F8 sub-finding's lesson working
  as designed); "check" removed, false_action back to 0. The same diff showed
  venmo/zelle-as-verbs un-deafening six dev money lines into F9 holds — all six are
  bank-keyed silence, so that widening buys zero dev catch while risking flushed asks
  at the holdout's zero-margin interrupt ceilings (and held is scorer-invisible, C20,
  so the dev metrics could not have warned); trimmed per the manifest's pre-registered
  rule. LESSON (C18's sibling, for verbs): an imperative-verb addition is proven only
  by a full-bank decision diff with zero changes beyond its intended catch; re-land
  check/venmo/zelle only if a judge count ever names such a miss. Regression check:
  contractor_luis day01:10 stays ignore in any full-bank run; the per-line decision
  diff discipline itself.

## Judge findings, lap 20260610T223727Z (verdict: VETO — holdout floor not met again; see laps/20260610T223727Z/verdict.md)
- C21 NEW (measurement blind spot in the C19 fix candidate): the 6-token shingle scan
  passes near-verbatim bank echoes whose longest shared token run is 4-5 tokens,
  including ones that reuse bank character names. Two such pins re-landed this lap in
  test_triage_clause_scope.py (:77 — a parent_dana day01 line near-copy keeping the
  bank child's name, shared runs of 4+4 tokens; :199 — a contractor_luis day01 money
  line stem keeping the bank supplier's name, shared run of 5 tokens). Both sat in the
  131707Z judge-inspected remainder (NOT the flagged list), both pin the conservative
  direction (DROP / money-hold), so no metric is inflated — but the file's "never bank
  copies" docstring stays overbroad and the mechanical scan alone cannot enforce C13.
  Fix candidate: scan test files at 4-token shingles AND against the union of
  persona.json "people" names + transcript proper nouns; rewrite on any name hit.
- F13 NEW (F12's holdout-side sibling, now measured on unseen data): blind imperative
  verb widening carries a junk-ask tax that dev evidence cannot bound. "feed" (added
  to _NOUN_PRONE_IMP this lap, curated blind per the manifest) fired on an idiomatic
  holdout narration line: chef_rosa day01 gained one unmatched ask, interrupt 0.0 ->
  1.0. Within the 3.0 ceiling THIS time and on the one holdout persona with slack —
  the same event on gradta_ming or nurse_helen (both AT 3.0) would have failed gate_P2
  outright. The full-bank dev decision diff (F12's containment) showed zero changes for
  "feed": the dev bank simply has no idiomatic "feed" line, so dev cleanliness is NOT
  evidence of holdout cleanliness for any newly widened verb. Containment that actually
  binds: fewer, higher-precision verbs; counterexample DROP pins per verb; treat every
  blind-widened verb as carrying unmeasurable interrupt risk at zero-margin personas.

## Class F/C addendum (builder lap 20260610T232257Z)
- F13 CLOSED-BY-REMOVAL: "feed" deleted from _NOUN_PRONE_IMP per the 223727Z verdict's
  re-land condition 1 (it was the only junk-ask source on either bank; chef_rosa's
  interrupt should return 0.0 on the next judge holdout run — that number is the
  regression check, plus the triage.py comment forbidding a blind re-land). The
  containment lesson STANDS for all one-word imperative lexicons; this lap therefore
  widened only the two tight frames the verdict named (clause-initial phrasal pairs,
  get+participle) plus one clause-anchored shape, never the loose one-word sets.
- C21 FIXED builder-side for the two named pins: test_triage_clause_scope.py :77 and
  :199 rewritten with the bank names REMOVED and fresh surfaces (no person name at all
  in the :77 family; a profession noun in the :199 family). The judge's fix candidate
  was run as designed: 4-token shingle scan of the test file vs dev transcripts plus a
  name scan against the union of dev persona/transcript proper nouns -> zero name hits;
  8 residual 4-token hits remain and are each the product regex's own literal trigger
  phrase ("deal with that later" IS the _DEFERRAL alternation; "oh sure i'll just" IS
  the vent-frame surface; "that goes on the" IS _LIST_PUT's shape; "hold it don't send
  anything" IS _COUNTERMAND's) — a pin that avoided them would not test the shape. One
  genuine sub-6-token content echo found by the same scan ("on the bike probably",
  inside a 131707Z-judge-inspected pin outside C21's flagged list) was rewritten.
  Mechanical verify_gate enforcement remains OPEN (foreman: C21's fix candidate).
- F14 NEW, FIXED same lap: a _PHRASAL_IMP entry whose verb doubles as a _SKIP_LEAD
  word is silently DEAD — the imperative machinery skipped the verb before the pair
  check ran ("go" is a lead word for "go grab the charger", so ("go", "through") could
  never fire on "Go through the receipts bin"). Found while sweeping the public
  inventory (it is the first pair to collide with the lead-word set); fixed by checking
  the pair BEFORE each lead-word skip; "go grab ..." behavior unchanged (a lead word
  followed by a non-pair word still skips). Regression check: the go-through in-situ
  SURVIVE pin in test_triage_clause_scope.py; the class check is any future pair whose
  verb appears in _SKIP_LEAD.

## Judge findings, lap 20260610T232257Z (verdict: VETO — holdout floor not met a third time; see laps/20260610T232257Z/verdict.md)
- F15 NEW (channel + measurement): two linked holes found while tracing why an honest,
  judge-verified-blind inventory sweep still missed the holdout floor.
  (a) REGISTER MIS-AIM IN THE DISCLOSURE CHANNEL: the 223727Z verdict characterized the
  residual lexeme as a "common errand lexeme"; the lap dutifully swept four public
  errand/office/work/school lists (this judge fetched all four — the sweep is faithful
  and the lexeme is on NONE of them). The register call was wrong: the lexeme's task
  sense is computing/print/media-staging, and common ESL technology lists do not
  reliably carry it either, while general references list it primarily in a
  people-queueing sense the lap's (correct) exclusion rule discards. A judge
  shape/register characterization is itself an instrument and can mis-aim an entire
  lap; verdicts should disclose residual surfaces at SHAPE granularity (precedent:
  "get <thing> to <person>"), not guessed register labels. The 232257Z verdict applies
  the fix: the residue is disclosed as a clause-anchored benefactive-staging imperative
  (object + "for me/us" tail), lexeme-free.
  (b) CLOSED-CLASS LEXICONS CHASING AN OPEN VOCABULARY: stub-tier triage catches by
  regex lexicon membership; the holdout measures open-vocabulary task speech. Each
  blind widening trades unmeasurable junk-ask risk at two personas sitting AT the
  interrupt ceiling (F13 demonstrated the trade) for coverage of finitely many new
  lexemes, and there is always another lexeme. Two falsified blind sweeps on one
  residual pair = the treadmill the factory exists to prevent (count is 4 after this
  lap). Structural options are foreman calls: amend the channel to permit judge-named
  lexemes after K falsified blind sweeps, or run the P2 holdout instrument at live
  tier (bounded spend) so the product's model tiebreak is measured instead of the stub
  regex ceiling. Until then, shape-level rules (benefactive tail, clause anchors) beat
  lexicon growth: they generalize, and their junk surfaces are enumerable enough to pin.
- C-class note, not ledgered separately: the lap's inventory exclusion comment
  enumerates its excluded list items but omits three (find out, knock off, work out)
  that the stated rule also excludes. Defensible under the rule, but a sweep that
  claims "every include/exclude is from the cited pages' senses" should enumerate
  exhaustively so the judge's audit is a diff, not a re-derivation.

## Class F addendum (builder lap 20260611T000748Z)
- F16 NEW, OPEN-DISCLOSED (residual of the F15a benefactive shape rule, found and
  bounded before commit): the benefactive-staging imperative's three structural
  anchors can be satisfied by APPOSITIVE third-person gratitude narration —
  "<Name> the <role> <finite-verb> <object> for me" — because the open-vocabulary
  head slot accepts a person name (clause-initial names and sentence-case verbs are
  indistinguishable at regex tier) and the finite verb sits in the tail gap where
  staging participles must remain legal ("Get the forms filled out for me"), so only
  the closed _BENEF_GAP_NARR list (was/is/felt/seemed/came/went/got/...) separates
  them. The SIMPLE form of the gratitude class ("Soren did the printer run for me")
  IS structurally excluded — a subject head is followed by a verb, not a determiner —
  and pinned, as are the other judge-enumerated junk classes (no-object "pray for
  me", dropped-subject past heads, gerund heads, 3rd-person-s heads, vicarious
  well-wishes, present-company favors, appositive-with-finite-verb). Regression
  check: the benefactive DROP pins in test_triage_clause_scope.py + the full-bank
  dev decision diff (zero changes beyond intended). If a judge holdout count ever
  names an appositive junk ask, extend _BENEF_GAP_NARR (the finite-verb list), never
  weaken the three anchors.

## Foreman repair, 2026-06-11 (false P2 closure after judge limit)
- C17 NEW, FIXED: phase closure trusted the mechanical gate when the adversarial judge
  failed externally. Lap 20260611T000748Z passed the dev-bank P2 gate and then the
  judge subprocess hit the Claude session limit before writing judge.json,
  verdict.md, or holdout_metrics.json. loop.sh treated missing judge output as
  non-veto, and scoreboard.py closed P2 from phase_gate_passed+kept alone. Fix:
  loop.sh writes JUDGE_ERROR/JUDGE_SKIPPED for any phase-close candidate without a
  trusted judge, blocks keep unless the verdict is REAL, and scoreboard.py only records
  first_closure when judge_verdict == REAL. Regression check: a phase gate pass with
  missing/non-REAL judge.json yields gate_closed False and cannot write
  RATCHET.phases_closed.
- D23 NEW, FIXED: Claude session-limit laps were counted as real no-movement laps.
  The five fast laps after 000748Z were api_error_status=429 "You've hit your session
  limit" envelopes, but verify/score still ran against unchanged HEAD and burned the
  treadmill to K=5. Fix: loop.sh detects build session-limit/429 results immediately,
  writes skipped.json status SKIPPED_LIMIT, removes .lap_in_progress, sleeps a backoff,
  and skips verify, scoreboard, spend, and treadmill. Regression check: a limit-hit
  build creates no product_scoreboard row and does not increment treadmill_count.

## Judge, lap 20260611T041654Z (P2 close verdict)
- C22 NEW, OPEN (judge): owner_mode.py routing regexes hardcode eval/test vocabulary.
  engine/anticipy_engine/owner_mode.py (landed in ee77765, foreman lane) routes with
  _BROWSER containing "water[- ]?table" and "that .* thing" and _SEND containing
  "decking|deck|new version|revised" — these literally match dev persona text
  (parent_dana day01 "that water table thing" + seed_memory; founder_jin/salesrep_pri/
  student_kayla "deck" lines) and the sample transcript in .claude/OWNER_ACTION_ENGINE.md
  that engine/scripts/test_owner_mode.py copies verbatim, making the two new owner suite
  tests partially self-fulfilling. INERT for the P2 persona gate (owner_mode is
  unreachable from POST /event; verified concretely this lap) so the 041654Z closure is
  not tainted — but TARGET v6 STAGE B plans to score owner cards against the same
  persona bank, which these literals would pre-game, and the owner_literals scan has a
  blind spot here: it targets Omar-personal literals, not persona-bank text. Required
  before any Stage B metric counts: generalize the routing tokens (or score against
  text the regexes were not tuned on) and extend the owner_literals scan (or a sibling)
  to flag dev-bank n-grams in product code on the owner path. Regression check: grep
  owner_mode.py routing tables against factory/personas/dev/*/days/*.txt 4-gram shingles
  must come back empty before Stage B scoring is trusted.

## Build lap 20260611T043446Z (owner-path honesty wiring, TARGET v6 STAGE B item 1)
- F17 NEW, OPEN (measured the moment the instrument existed): the owner lane ships a
  SECOND, WEAKER BRAIN. The deterministic regex first pass in owner_mode.py scores,
  on the very same dev bank where the proactive path holds catch 1.0/worst 1.0 with
  false 0: catch 0.5054 / worst 0.2222 (founder_jin), false_action_count 15 (acts on
  narration/reports the main triage correctly silences), memory_recall_worst 0.25,
  e2e_completion 0.0 (cards do not execute yet — honest), interrupt 0.6875/1.5,
  silent_harm 0 (money lines never act; blocked->ask mapping held). One product,
  two brains: every door routed through /owner/ingest today gets the 0.22 brain, not
  the 1.0 brain. The fix direction is NOT to grow the regex tables (F15 already
  falsified closed-class lexicon chasing on the main path; C22 shows where tuned
  tokens lead) but to route owner cards through the proven triage/decider/harm-line
  spine or a hybrid extractor (OWNER_ACTION_ENGINE item 4) — foreman/TARGET call.
  Regression check: the owner-lane instrument itself — ANTICIPY_OWNER_INGEST=1
  persona_run on the dev bank; any future owner-extractor change must move these
  numbers, and gate-grade claims must come from the judge's holdout, never this bank.
- C22 PRODUCT-SIDE LANDED this lap (scan side still foreman): the four judge-named
  eval-tuned routing literal groups (_BROWSER "water[- ]?table" + "that .* thing",
  _SEND "decking|deck|new version|revised") are deleted from owner_mode.py, plus two
  same-class deny-side literals (_VENT_OR_JOKE "clone myself", "that'?ll fix") that
  4-gram-shingle-match parent_dana day01's vent line verbatim. None were load-bearing:
  suite stays 39/39 green and owner-lane catch is UNCHANGED at 0.5054/0.2222 after
  removal (false dropped 17->15 — the tuned tokens were creating false actions, not
  catches). Distinctive-literal grep of remaining routing tables vs dev bank days +
  seeds now comes back clean of the judge-named class; residual disclosed honestly:
  "circle back" (2-gram generic business idiom in _SEND) and single generic verbs
  (send/buy/find/...) do appear in bank text — owner_mode.py POSTDATES the frozen bank,
  so the judge should rule whether any remaining short token counts as tuned; the
  4-gram shingle bar C22 set is met.
  The C22-required shingle SCAN (mechanical, every diff) remains OPEN for the foreman —
  builders cannot extend factory/ scans.
