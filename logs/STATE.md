# STATE

CERTIFIED 2026-06-11 (overnight): **P2-brain CLOSED, judge REAL** (lap 20260611T041654Z)
— holdout catch_rate_worst 1.0 (14/14 tasks, 4 never-seen personas), false 0, harm 0.
Then four kept Stage-B laps: owner lane is ONE BRAIN (F17 closed — every owner line
through triage->decider->harm-line->orchestrator; regex only shapes cards + pre-gates
money), cards execute with read-back proof (owner false actions 15->0), full Twilio
voice/inbound plumbing mock-proven, F21 reported-promise catch fixed on main path.
K=5 treadmill fired (metric saturated, not work dead) -> foreman re-aimed TARGET v7:
official instrument = owner lane (eval_env ANTICIPY_OWNER_INGEST=1), primary metric
e2e_completion_rate (baseline 0.3427). Twilio account verified in console ($17.85,
pay-as-you-go, +1 619 658 4447, webhooks live); TWILIO_FROM env gap fixed in .env.local.
P3 live gate awaits Omar's OWNER_PHONE confirmation (+1 604 724 5161 corroborated).
Phases closed: P0, P1, P2 — gates remaining: P3 voice, P4 browser, P5 owner test.
TARGET v9 resumed the factory on Codex with the harder dev_v2 owner-ingest instrument:
first local baseline lap 20260613T011932Z-pre measured catch 0.6825, catch_worst 0.5,
false 0, harm 0, interrupt 1.0/2.0, e2e 0.3778, correct 0.6222, recall_worst 0.5,
worst_persona freelancer_nora. Suite stayed 46/46 green. P3 live gate was not attempted
because `factory/config/owner_phone.confirmed` is still absent. First build lap on v2
closed F33 (schedule-change calendar holds) and moved the official local stub score
to catch 0.8413, catch_worst 0.6667, false 0, harm 0, interrupt 1.0/2.0, e2e 0.5833,
correct 0.6945, recall_worst 0.5, worst_persona freelancer_nora; suite stayed 46/46
green and legacy dev stayed at ratchet bests. Second build lap on v2 closed F34
(time-anchored before-I-forget holds) and moved the official local stub score to
catch 0.8413, catch_worst 0.6667, false 0, harm 0, interrupt 1.0/2.0, e2e 0.6389,
correct 0.75, recall_worst 0.5, worst_persona freelancer_nora; suite stayed 46/46
green and legacy dev stayed at ratchet bests. Third build lap on v2 closed F36
(context-backed slot-choice bookings) and moved the official local stub score to
catch 0.8413, catch_worst 0.6667, false 0, harm 0, interrupt 1.0/2.0, e2e 0.6945,
correct 0.8055, recall_worst 0.5, worst_persona freelancer_nora; suite stayed 46/46
green and legacy dev stayed at ratchet bests. Fourth build lap on v2 closed F39
(imperative note commands) and moved the official local stub score to catch 0.8413,
catch_worst 0.6667, false 0, harm 0, interrupt 1.0/2.0, e2e 0.75, correct 0.8611,
recall_worst 0.5, worst_persona freelancer_nora; suite stayed 46/46 green and
legacy dev stayed at ratchet bests. The broad capture-to-visibility attempt from
F34 was ripped out after it produced false_action_count 2; the no-clock pickup-alarm
auto-hold attempt in F37 was ripped out after it produced false_action_count 1, and
a narrower context-backed retry in F38 also produced false_action_count 1 and was
ripped out.

OWNER DIRECTIVE 2026-06-10: the immediate product priority is the Owner Action Engine,
not another narrow loop around one brain metric. Durable directive:
`.claude/OWNER_ACTION_ENGINE.md`. The required path is memory + proactive engine +
onboarding + API hand + browser hand + voice/text, with pay-to-try, Start Listening, MP3,
and pasted transcript all feeding the same engine. First implementation landed this
session: `POST /owner/ingest` -> `OwnerMode.ingest` -> durable task cards in memory/open
loops, pinned by `engine/scripts/test_owner_mode.py`. Follow-up implementation in the
same session: `POST /owner/onboard` -> `OwnerOnboardingIn` -> owner identity, people,
preferences, app-connection state, stores, and missing-connection open loops in memory,
pinned by `engine/scripts/test_owner_onboarding.py`. Do not build a special handoff mode;
use explicit `ask` or `blocked` cards. Do not test primarily on clean commands; use ugly
real-life transcript with mostly useless speech and a tiny useful fraction.

REGIME CHANGE 2026-06-10: the autopilot/ loop (Codex-driven, milestone M-ladder) is RETIRED.
The successor is the FACTORY (factory/), built and smoke-proven this session. The owner
approved the plan at ~/.claude/plans/oh-my-god-everybody-iterative-puffin.md: finish line for
this phase of work = THE OWNER TEST (5 consecutive real owner days through the live system,
zero vent-actions, persona-bank thresholds held simultaneously). Strangers/onboarding/front
door are the NEXT plan; pendant and iPhone after that. autopilot/ remains read-only history;
its LESSONS.md still binds.

## The Factory (how work happens now)
- Steering: `factory/TARGET.md` (foreman-owned, currently v9 / phase P3-voice).
- Phases and gates: `factory/PHASES.yaml`, gates in `factory/gates/`.
- Nightly: launchd `com.anticipy.factory` starts `factory/bin/loop.sh --nightly` at 22:30,
  stops by 07:00. Manual: `factory/bin/loop.sh --once|--max-laps N`.
- Each lap: fresh `claude -p` builder session (bounded, pre-registers a manifest) ->
  mechanical verify (scans + 29-test suite + 8-persona eval -> metrics.json) -> optional
  judge session -> scoreboard row -> keep or git-revert -> treadmill check.
- Scoreboard: `logs/factory/product_scoreboard.csv` (sole writer: scoreboard.py).
  A lap counts ONLY if the primary metric moves or a phase gate first-closes.
- Treadmill: K=5 dead laps -> ESCALATION.md + halt; foreman (interactive session with the
  owner) re-aims by editing TARGET.md. The loop refuses to run while an escalation is OPEN.
- Persona bank: 8 dev personas x 2 messy days with ground-truth keys (frozen,
  SUITE_HASH e0db2ed3d218) + 4 holdout personas (judge-only, gitignored, builder must
  NEVER read). Worst-persona scoring. Owner red-pen of holdout keys is pending.
- Spend: `factory/config/budget.json` ($200/wk envelope, per-lap caps, 25% judge reserve);
  `spend.py` records per lap; FREE mode (deterministic work only) when exhausted.

## Proven (Factory bootstrap, this session)
- Scorer selftest catches planted caught/missed/false/silent-harm cases (every invocation).
- gate_P0_floor green: isolated-engine persona runs, scoring, scoreboard dry-run, spend parse.
- Smoke loop: 3 no-op laps -> first-measurement counted, dead laps incremented, K=2 halt
  fired, ESCALATION written, restart refused while OPEN, foreman resolve flow worked.
- Judge selfcheck (real fresh `claude -p` session) correctly ruled the planted fake FAKE
  with evidence-based reasoning: `logs/factory/laps/selfcheck-*/selfcheck.md`.
- BASELINE (8 dev personas, stub tier, lap baseline0): catch_rate 0.6984,
  catch_rate_worst 0.50 (doctor_amara), correct_action_rate 0.48, false_action_count 19,
  silent_harm_count 0, interrupt_cost 5.44 avg / 10.5 worst, e2e_completion 0.23,
  memory_recall_worst 0.33. These are the numbers laps must move.

## Carried over from the old regime (still true)
- M0 clean floor was judge-proven once: one real typed Calendar task end-to-end
  (`logs/verdicts/20260607T032947Z.md`).
- Real and live-proven: Arcade Calendar create/list/delete (12/12 overnight run),
  Gmail send. Gmail compose scope still needs a human OAuth tap. Slack unavailable.
- The engine's browser agent (agent/webvoyager.py) has ~19 stores of builder-side
  verified cart paths and ~16 hard-site findings, all judge-unproven. Per-store recipe
  growth is BANNED (TARGET v2); P4 will pivot to a general agent + hints cache and the
  recipe tables become seeds for `agent/site_hints.py`.
- Apple Developer ID signing unavailable on this Mac (0 identities) — needed only for the
  public front door (next plan).
- One owner-email literal remains in product code (core/control_core.py:66) — P1 work
  item 4 deletes it; the owner-literal scan now guards regressions.
- Possible stray artifact: `[Anticipy test] M2 typed smoke 20260607-continue` calendar
  event on June 12 (cleanup blocked by TCC; do not touch other calendar data).

## Current phase: P2-brain CLOSED (lap 20260611T041654Z, judge REAL — F15a holdout state finally judged) -> TARGET v7: owner lane IS the official instrument (eval_env ANTICIPY_OWNER_INGEST=1, primary e2e_completion_rate) -> TARGET v8 (second K=5 resolved): Stage A = P3 closure on OWNER_PHONE confirm, Stage B = P4-browser groundwork -> TARGET v9: first resumed lap is the countable dev_v2 owner-ingest baseline, then build from the actual dev_v2 gaps
- IMPERATIVE NOTE COMMANDS NOW COMPLETE IN OWNER LANE (lap 20260613T022002Z,
  build - F39 FIXED, fourth post-baseline dev_v2 metric movement). The v2 run
  dirs showed an over-gate: an imperative note-creation line with audience
  language was caught as an ask because Room 2 read the audience phrase as a
  binding send instead of note content. Fix = shared `note_task.py` recognizes
  only imperative note creation, Room 2 treats that narrow shape as reversible
  note capture after hard stops, and the deterministic planner writes the exact
  note text as one proof-bearing `write_memory` open-loop step. Official TARGET
  v9 lane (`ANTICIPY_OWNER_INGEST=1`, `factory/personas/dev_v2`, stub): e2e
  0.6945 -> 0.75, correct 0.8055 -> 0.8611, catch 0.8413, catch_worst 0.6667,
  false 0, harm 0, interrupt 1.0/2.0, recall_worst 0.5, worst_persona
  freelancer_nora. Legacy dev-bank smoke stayed at ratchet bests (catch 1.0/1.0,
  false 0, harm 0, interrupt 0.625/1.0, e2e 0.6483, correct 0.8475, recall
  1.0). Suite 46/46 green. F38 NEW AVOIDED: a narrower context-backed no-clock
  pickup/dropoff alarm adjustment retry still produced false_action_count 1 and
  was ripped out before the kept run; do not retry that family without a new
  owner/foreman product law. P3 live gate still waits on
  `factory/config/owner_phone.confirmed`.
- CONTEXT-BACKED SLOT-CHOICE BOOKINGS NOW COMPLETE IN OWNER LANE (lap
  20260613T020216Z, build - F36 FIXED, third post-baseline dev_v2 metric movement).
  The v2 run dirs showed a memory-to-intent gap: memory had a named person plus
  availability slot, then a later "book the <slot> one with <person>" line was caught
  but over-asked because same-line slot-choice logic required the appointment noun
  in the same utterance. Fix = shared slotbooking context resolver requiring person,
  slot, and availability cue in memory with commerce/travel deny bounds; Room 2 uses
  it before fail-safe ask, and the deterministic orchestrator uses the same resolver
  to emit one proof-bearing create_event step. Official TARGET v9 lane
  (`ANTICIPY_OWNER_INGEST=1`, `factory/personas/dev_v2`, stub): e2e 0.6389 -> 0.6945,
  correct 0.75 -> 0.8055, catch 0.8413, catch_worst 0.6667, false 0, harm 0,
  interrupt 1.0/2.0, recall_worst 0.5, worst_persona freelancer_nora. Legacy dev-bank
  smoke stayed at ratchet bests (catch 1.0/1.0, false 0, harm 0, interrupt 0.625/1.0,
  e2e 0.6483, correct 0.8475, recall 1.0). Suite 46/46 green. F37 NEW AVOIDED:
  no-clock pickup/dropoff alarm adjustment auto-holds produced false_action_count 1
  and were ripped out before the kept run; do not retry that shape without a new
  product law and a zero-false eval. P3 live gate still waits on
  `factory/config/owner_phone.confirmed`.
- TIME-ANCHORED BEFORE-I-FORGET HOLDS NOW COMPLETE IN OWNER LANE (lap
  20260613T014006Z, build - F34 FIXED, second post-baseline dev_v2 metric
  movement). The v2 run dirs showed a proof gap where a concrete, time-anchored
  "before I forget" commitment was caught as an ask but not completed, even
  though the safe product action is only to capture an open loop and re-gate the
  future external action when it fires. Fix = Room 2 treats only time-anchored
  forget-holds as reversible calendar/open-loop holds after hard money/send/delete
  checks, and the stub planner writes the exact goal text as one `write_memory`
  open-loop step. Official TARGET v9 lane (`ANTICIPY_OWNER_INGEST=1`,
  `factory/personas/dev_v2`, stub): e2e 0.5833 -> 0.6389, correct 0.6945 ->
  0.75, catch 0.8413, catch_worst 0.6667, false 0, harm 0, interrupt 1.0/2.0,
  recall_worst 0.5, worst_persona freelancer_nora. Legacy dev-bank smoke stayed
  at ratchet bests (catch 1.0/1.0, false 0, harm 0, interrupt 0.625/1.0,
  e2e 0.6483, correct 0.8475, recall 1.0). Suite 46/46 green. F35 NEW
  AVOIDED: a broader capture-to-visibility matcher produced false_action_count
  2 and was ripped out before the kept run; do not retry that broad shape
  without a narrower product law and a zero-false eval. P3 live gate still waits
  on `factory/config/owner_phone.confirmed`.
- SCHEDULE-CHANGE CALENDAR HOLDS NOW COMPLETE IN OWNER LANE (lap
  20260613T012751Z, build — F33 FIXED, first post-baseline dev_v2 metric
  movement). The v2 run dirs showed a shared miss-family: concrete schedule
  changes with explicit block/capture cues were ignored or over-asked, so they
  never produced proof-bearing calendar cards. Fix = a shared
  schedule-change matcher requiring a change cue + capture/block cue +
  concrete time/daypart, wired through Room 1 triage, Room 2 harm-line, and
  the stub planner. It also narrows the harmless "my brain deletes it" metaphor
  away from destructive-delete gating while true delete/remove/wipe hard stops
  still ask. Official TARGET v9 lane (`ANTICIPY_OWNER_INGEST=1`,
  `factory/personas/dev_v2`, stub): catch 0.6825 -> 0.8413, catch_worst 0.5 ->
  0.6667, e2e 0.3778 -> 0.5833, correct 0.6222 -> 0.6945, false 0, harm 0,
  interrupt unchanged 1.0/2.0, recall_worst 0.5. Legacy dev-bank smoke stayed
  at ratchet bests (catch 1.0/1.0, false 0, harm 0, interrupt 0.625/1.0, e2e
  0.6483, correct 0.8475, recall 1.0). Suite 46/46 green. P3 live gate still
  waits on `factory/config/owner_phone.confirmed`.
- THE AGENT'S PER-HOST FACTS ARE DATA, NOT CODE (lap 20260611T135937Z,
  groundwork — TARGET v8 STAGE B item 1; honest DEAD lap by design, disclosed
  in the manifest: e2e is at the F31 ceiling, foreman-owned). webvoyager's
  three retailer host tables (35 hosts: search templates, cart URLs, product
  URL regexes) were exported byte-faithfully to a packaged seed
  (engine/anticipy_engine/data/site_hints_seed.json — placed OUTSIDE agent/
  because factory scan 5 greps added quoted hostnames under the whole agent/
  subtree, ledger D24) and DELETED from agent code; agent/*.py is now
  hostname-free including docstrings — the P4 grep-gate target shape. New
  agent/site_hints.py serves seed + per-engine learned overlay
  (<data>/site_hints.json, wired by ControlCore like pending_path; agent code
  never reads env): exact-then-longest-suffix host matching, per-field
  overlay-wins, learn() only at the two durable cart-proof chokepoints with
  verbatim verified facts (sanitized observed cart URL + visited product
  paths; never derived {q} templates), every failure toward the seed (corrupt
  overlay -> .corrupt set-aside; off-host/no-{q}/uncompilable fields dropped
  per-field; no path -> no IO; mock proofs never learn — pinned). Verified:
  suite 46/46 (new 9-pin test_site_hints.py); pre/post persona runs BOTH
  lanes bit-identical at the ratchet bests (catch 1.0/1.0, false 0, harm 0,
  interrupt 0.625/1.0, e2e 0.6483, correct 0.8475, recall 1.0; per-persona
  equal), per-line decision diff ZERO (493 lines x 16 persona-days per lane),
  normalized full-response diff ZERO, goal multisets identical, zero hint
  artifacts in run dirs. F32 NEW OPEN: the hostname-free
  CART_URL_RE/SEARCH_RESULTS_URL_RE classifiers stay coupled to the per-host
  facts — a LEARNED host with a non-classic cart path fails CLOSED (no false
  success) but its hint silently does nothing; fix direction = verified
  learned cart paths extend recognition under the same verified-only law (the
  P4 build lap). Stage B item 2 (agent/proof.py read-back generalization)
  remains.
- FIRED TRIGGERS NEVER RE-FIRE ACROSS RESTARTS (lap 20260611T133818Z,
  groundwork — D16 PROPER FIXED, the ledger's oldest open restart entry and
  the one with a NON-SILENT failure direction; TARGET v7 item 4 "mock-prove
  everything around the P3 gate"; honest DEAD lap by design, disclosed in the
  manifest — dead lap #5, the DESIGNED K=5 escalation -> TARGET v8 re-aim).
  TriggerWatcher._fired (the fire-once guard) was in-memory over a durable
  ledger: every engine restart re-fired every already-fired due loop —
  duplicate reminder sends to the owner, duplicate full-pipeline re-entry
  where an ACT follow-up would execute AGAIN (test_trigger_notify's second
  engine silently exercised this on HEAD). Fix = the D16 entry's own queued
  one: trigger_tick stamps fields["fired_at"] on the DURABLE loop record via
  the existing mark_loop intent BEFORE any send/re-entry (mark-before-act, the
  seen-sid law); _due treats any stamp as fired-forever; a crash after the
  stamp LOSES the firing toward silence (never a late duplicate); a failed
  stamp skips the firing unstamped (honest trigger_stamp_failed log) and
  retries next healthy boot; pure stamps leave ledger status alone, legacy
  mark_loop default pinned. No new files/wiring — the stamp rides the SQLite
  ledger. Verified: suite 45/45 (new test_trigger_persistence.py 6-pin battery
  incl. ControlCore restart e2e — the gate_P3 trigger leg cannot
  double-interrupt); full pre/post persona runs BOTH lanes bit-identical at
  the ratchet bests, per-line decision diff ZERO (owner 492 / default 493
  lines x 16 persona-days), goal multisets identical, fired_at absent from
  every persona-run artifact. The D16 family is now closed on every non-silent
  edge (deferred queue 1ce2269, pending asks 41da3c3, fired triggers here);
  remaining siblings (budget/debounce day-state) fail toward bounded annoyance
  only. gate_P3 still waits on OWNER_PHONE (Omar) + gate_P3.sh (foreman).
- PENDING ASKS NOW SURVIVE ENGINE RESTARTS (lap 20260611T132034Z, groundwork —
  the D16 SIBLING FIXED, the ledger's last named mock-side P3 residual; TARGET
  v7 item 4 "mock-prove everything around the P3 gate"; honest DEAD lap by
  design, disclosed in the manifest — treadmill walks 3 -> 4 toward the designed
  K=5 re-aim). The P3 inbound chain was restart-proof except its FIRST link:
  goals, owner-card linkage (F18), and seen-sids are all durable, but
  proactive.pending — the map that lets the owner's YES/NO match an ask — was
  in-memory, so a restart between the ask SMS and the reply made the reply
  resolve NOTHING (and the F20 clarifier would honestly say "nothing is
  pending" about an ask the product itself sent). Fix = the residual's own
  named pattern (decider_deferred.json): ProactiveEngine(pending_path=...)
  persists the map atomically on every mutation (the resolve pop persists
  BEFORE the goal resumes — a crash mid-resolve loses the ask toward silence,
  never replays an approval); boot-restore is PASSIVE (never re-enters the
  pipeline) and store-validated (only still-waiting goals come back; stale
  entries pruned; corrupt files set aside .corrupt; no path = no IO);
  ControlCore wires <data>/pending_asks.json. Verified: suite 44/44 (new
  test_pending_persistence.py 7-pin battery incl. the gate_P3 inbound leg
  end-to-end: ControlCore restart with BOTH in-memory maps gone -> inbound
  "YES <code>" resolves, goal done, card written back via F18); full pre/post
  persona runs BOTH lanes bit-identical at the ratchet bests, per-line decision
  diff ZERO, goal-state multisets identical. P3 mock-side residuals are now
  EXHAUSTED builder-side (F19 is live-observable only); gate_P3 waits on
  OWNER_PHONE (Omar) + the gate script (foreman). D16 proper
  (TriggerWatcher._fired restart double-fire) is the one remaining
  restart-robustness sibling with a non-silent failure direction.
- AMBIGUOUS INBOUND REPLIES NOW DRAW A BOUNDED CLARIFICATION (lap
  20260611T120957Z, groundwork — ledger F20 FIXED; TARGET v7 item 4
  "mock-prove everything around the P3 gate"; honest DEAD lap by design,
  disclosed in the manifest: e2e is at the F31 ceiling and gate_P3 is
  human-gated, treadmill walks toward the designed K=5 re-aim). An ambiguous
  owner SMS reply (bare YES/NO with !=1 asks pending, or a code matching
  nothing) still resolves NOTHING — but the owner is now TOLD so:
  InboundPoller._clarify sends ONE bounded clarification per poll pass through
  notify_user (ChannelWorker -> shared TextChannel, mock/live triad), listing
  the exact pending reply codes ("nothing is pending" when none; at most 5
  listed, 60-char action snippets). Every bound fails toward silence: one send
  per pass, AnnoyanceBudget-counted AND budget-suppressed when the day's
  interruptions are spent, owner-recipient-only, seen-sid gated (never
  replays); no resolve/approve/goal/execution in any branch, and the
  exact-code resolution itself is never budget-gated. Verified: suite 43/43
  (F20 battery in test_inbound.py); full pre/post persona runs BOTH lanes
  bit-identical at the ratchet bests; per-line decision diff ZERO (493 lines x
  16 persona-days — the poller never runs in persona runs, proven not
  assumed). P3 mock-side residuals left under item 4: the D16 sibling
  (proactive.pending in-memory across restarts) and F19 (live text auth
  realm pattern, live-observable only).
- THE OWNER LANE'S INTERRUPT COST IS AT EXACT SPINE PARITY (lap
  20260611T115207Z, build — ledger F23 pre-gate interrupt component FIXED;
  TARGET v7 ranked item 2; honest DEAD lap by design, disclosed in the
  manifest: primary e2e is at the F31 ceiling). Post-F28 the ENTIRE remaining
  owner-vs-default interrupt delta was ONE line (parent_dana d02 L31 "Just buy
  the birthday stuff already, me. ... Probably." — a money-flavored self-talk
  vent the spine ignores but the money pre-gate short-circuited into a blocked
  ask BEFORE the spine could vent it). Fix = the F23 entry's own queued option:
  ControlCore._spine_card consults the spine's OWN triage instance (pure
  classification — no decider/harm-line/orchestrator/goal//pending; one brain,
  F17) on blocked-shaped lines; confident vent -> silent like the default
  path, anything else -> the blocked ask stands (live tiebreak fails OPEN
  toward the ask). Silence and blocked both never execute: the money stop is
  intact in every branch. The bank's only other blocked-shaped line (rob's
  "Order the replacement beakers tonight on the district card") triages
  actionable and keeps its ask. Owner lane (OFFICIAL): interrupt 0.6875/1.5 ->
  0.625/1.0 (exact default parity, at ratchet bests); catch 1.0/1.0, false 0,
  harm 0, e2e 0.6483, correct 0.8475, recall 1.0 bit-identical. Default lane:
  ZERO diffs. Per-line diff both lanes = exactly the one intended flip (493
  lines x 16 persona-days); record diff = exactly the vent's blocked card
  disappearing. Suite 43/43 (new non-bank MONEY_VENT pin + unchanged MONEY
  blocked pins). TARGET v7's builder-workable items are now EXHAUSTED: item 1
  at the F31 ceiling, item 2 at parity (remaining asks are the spine's own
  stance in both lanes), items 3/4 judge/human-gated. Still F23-OPEN
  (foreman): the money STANCE question — pri's keyed expected-act "buy"
  command asks by fail-safe; auto-staging "buy X" is a product-stance call.
- SLOT-CHOICE BOOKINGS ACT + CALENDAR PLANS ARE GROUNDED, e2e AT ITS HONEST
  CEILING (lap 20260611T112537Z, build — ledger F30 FIXED, F27 FIXED, F31
  OPENED): "Book the Friday 9am one" asked purely for shape (the slot
  anaphor's head is "one", so rule-6 verb..noun shapes never saw the
  appointment) — new shared/slotbooking.py (F29 one-shape-two-consumers
  pattern: book-verb + concrete-time slot anaphor + same-line closed-class
  appointment anchor + commerce/travel deny; money outranks) flips exactly
  parent_dana d02 L7 ask->act in both lanes, and the stub planner's new
  grounded-calendar branch (GOAL line only, before keyword triggers) plans
  EXACTLY one create_event with spoken-line args for slot-choice bookings and
  time-anchored "block X to Y" lines — dana completes ("Maya's checkup" /
  "Friday 9am", labeled mock proof), the luis cabinet completion now carries
  calendar proof instead of the "on site" browse screenshot (F27's own
  regression check), and three already-completing block lines got grounded
  args (disclosed). Owner lane (OFFICIAL): e2e 0.6305 -> 0.6483 (+0.0178,
  exactly the one intended completion); catch 1.0/1.0, false 0, harm 0,
  interrupt 0.6875/1.5, recall 1.0 exactly unchanged; correct 0.8296 ->
  0.8475. Default lane equal. Per-line diff both lanes = exactly the one
  flip. Suite 43/43 (new F30 battery + planner pins). F31 (foreman-owned):
  +0.0178 is UNDER the 0.02 epsilon — dead-but-kept by design — and every
  remaining non-complete expected act is fenced (storeless carts = owner-path
  capture territory, pri behind F23, 16 expected-asks structural), so the e2e
  instrument can no longer register honest builder work; the right move is a
  TARGET v8 re-aim (correct_action_rate has real headroom at 0.8475), not
  metric-chasing.
- MEMORY-NAMED STORES NOW RESOLVE, e2e MOVED AGAIN (lap 20260611T105558Z, build —
  ledger F29 FIXED): the whole memory->site chain required the owner to have
  SPOKEN a hostname, but people remember stores the way they speak ("at
  Target", "on Amazon") — so the harm-line's memory-resolved cart rule and the
  orchestrator's resolver were dead code on real speech, and 2 of the 5
  cart-staging expected-acts stalled as asks purely for vocabulary. New
  shared/storesite.py derives https://www.<store>.com from a product-shaped
  memory line (single capitalized store name after at/on/from; NO retailer
  literals; deny bounds all fail toward "": multi-word proper nouns,
  possessives, weekday/month/holiday/place closed class, non-product lines;
  eBay/IKEA-style casing misses by design). Both consumers import it, so the
  decision-layer ACT population == the plan-layer completable population;
  resolved steps record site_derived_from_store_name + the no-checkout
  instruction. The vague-anaphor shapes take bounded modifiers ("that water
  table thing", "the clamp one"); harm's _MEM_PRODUCT realigned with the
  orchestrator list (the "comparing" drift). DELIBERATE non-fix (F29
  near-miss): bare stick/throw cart verbs stay un-widened — a storeless
  flipped line (rob) would junk-complete via the stub planner's canned
  "later"->write_memory step; storeless cart-puts stay fail-safe asks, pinned.
  Owner lane (OFFICIAL): e2e 0.5918 -> 0.6305 (+0.0387, exactly the 2 intended
  completions: dana water table -> target.com, kayla desk lamp -> amazon.com,
  labeled mock proof + derived provenance); catch 1.0/1.0, false 0, harm 0,
  interrupt 0.6875/1.5, recall 1.0 exactly unchanged; correct 0.7909 -> 0.8296.
  Default lane equal at 0.6305 (shared plumbing), interrupt 0.625/1.0 at
  ratchet bests. Per-line diff BOTH lanes = exactly the 2 flips (493 lines x
  16 days). Suite 43/43 (new storesite battery). Next named: dana "Book the
  Friday 9am one" slot-choice rule + F27 "block X to Y" trigger (pair to clear
  epsilon); luis/amara/rob cart items have NO store in memory (honest
  fail-safe — owner-path capture territory); 16 expected-asks remain the e2e
  structural ceiling.
- THE HARM-LINE GATES THE REQUESTED ACTION, e2e MOVED BIG (lap 20260611T101809Z,
  build — ledger F28 FIXED): six dev-bank expected-acts were asks because the
  harm-line and the owner money pre-gate matched money/send TOKENS anywhere in
  the line instead of the requested action: _HARD_SEND outranked the reminder
  rule ("Remind me Wednesday at 7pm to SEND X" — the docstring's own design says
  holds are reversible and _fire_reminder already re-gates at fire time), draft
  purpose tails ("so I just hit send", "ready to send") read as send-now,
  "drafted" missing from the draft frame, "purchasing window" read as money,
  owner_mode money-blocked the bare NOUN "order" before the spine, and
  "follow-up" was missing from the calendar nouns. Fixed as closed-class scope
  rules with pinned deny bounds (money rule still first and untouched for real
  spends; FOLLOWUP_PREFIX refires never re-cancel), plus plan-layer honesty:
  self-reminder lines plan EXACTLY the open-loop hold (remind_ts grounded from
  the spoken time; fired = NOTIFY, proven zero send jobs end-to-end) and draft
  requests plan send_email_draft (never sends). Owner lane (OFFICIAL): e2e
  0.4797 -> 0.5918 (+0.1121, exactly the six intended completions); catch
  1.0/1.0, false 0, harm 0, recall 1.0 unchanged; correct 0.6788 -> 0.7909;
  interrupt 1.125 -> 0.6875 avg (worst 1.5) — the noun-"order" pre-gate junk
  asks died and the money-tripwire lines now follow the spine's own
  debounce/triage stance, per-line identical to the default lane (F17 parity;
  the F23 delta shrank as a side effect of scope, not of weakening — money
  still never executes). Default lane: per-line diff = EXACTLY the six flips,
  everything else at ratchet bests. Suite 42/42 (brain_loop/hands_loop pins
  re-derived per F25 — the draft-framed email is the send_email_draft leg now).
  Disclosed, not chased: the 5 cart-staging expected-acts (separate root cause
  + no memory-resolved site in mock, P4), dana's anaphoric "book the Friday 9am
  one" (open-vocab purchase risk), pri's "buy" line (F23 stance), F27 still
  open (the cabinet item's right artifact is a calendar block).
- THE BROWSER HAND HAS A MOCK TIER, e2e MOVED AGAIN (lap 20260611T095522Z, build —
  ledger F26 FIXED): BrowserHand was the only hand without a mock mode — every
  browser-routed step in a stub run hit the real hand with no extension and
  parked its goal at waiting ("browser helper isn't connected"), so the e2e
  instrument could never see the browser path. Now it takes the SAME
  ANTICIPY_HANDS_MODE contract as ApiHand (mock default via ControlCore, live
  only explicit; class default LIVE keeps the /ws/browse diagnostic + unit pins
  real; ANTICIPY_BROWSER_HAND_MODE narrows the knob for hands_loop's real-WS
  reroute leg). The mock runs the live path's OWN deterministic refusal gates
  first (action task with no resolved real site fails the identical live way —
  no search dumping; the amara cart whole-prompt dump now fails honestly
  instead of waiting) and only live-navigable jobs return a loudly-labeled
  proof artifact. Owner lane (OFFICIAL): e2e 0.4618 -> 0.4797; catch 1.0/1.0,
  false 0, harm 0, interrupt 1.125/1.5, correct 0.6788, recall 1.0 all exactly
  unchanged; default lane equal at 0.4797 (shared plumbing, disclosed),
  interrupt 0.625/1.0; per-line decisions ZERO diffs (493 lines x 16
  persona-days, both lanes). Suite 42/42. Disclosed fail-safe behavior change:
  default-boot engines no longer drive the owner's real Chrome (browse mock
  unless live env, like real sends). F27 OPEN: the one moved item (luis
  "block Monday 8 to 9" cabinet delivery) completes via its junk-but-live-
  navigable browse step; the right artifact is a calendar block — the stub
  planner needs a time-anchored "block X to Y" trigger (next plumbing slice).
  Remaining dev-bank e2e gap is NOT plumbing: 16 expected-asks (scorer never
  counts them complete) + 12 spine-ASK expected-acts (decider/harm-line).
- PLANNER JUNK STEPS KILLED, e2e MOVED (lap 20260611T093358Z, build — first lap under
  TARGET v7; ledger F24 FIXED, F25 FIXED): _plan_prompt appended the RELEVANT MEMORY
  dump for every provider while the stub planner keyword-greps the whole prompt, so
  injected memory lines ("site plan", "post-call") and bare-substring spoken hits
  ("post-shift" -> post) grew junk browse_task/post_to_x steps that returned
  needs_human in mock and parked proof-complete goals at "waiting" (7 of the 19
  stalled expected acts; the other 12 are spine ASK decisions, decider territory).
  Fix: memory section provider-gated exactly like the existing intent-vocabulary gate
  (deterministic tier's memory reader stays the _memory_resolved_browser_step
  pre-pass); stub post trigger is the WORD post; "set up" joined the scheduling
  triggers. Owner lane (OFFICIAL): e2e 0.3427 -> 0.4618, catch 1.0/1.0, false 0,
  harm 0, interrupt 1.125/1.5 (F23 delta) all exactly unchanged; default lane equal
  at 0.4618, everything else at ratchet bests; per-line decisions ZERO diffs in both
  lanes (plan-layer only). F25 lesson: two suite pins were green only BECAUSE of the
  pollution (junk steps carried PICKUP's artifact id and completed UNSHAPED_ACT) —
  when fixing plumbing, re-derive what each touched pin should assert. Suite 42/42.
  Residuals: "on site" keeps one luis goal waiting (carving it = bank-fitting); the
  stub's empty-plan fallback dumps the whole prompt into browse_task.
- THE BARE REPORTED PROMISE IS CAUGHT (lap 20260611T085136Z, build — ledger F21
  FIXED on the main path): root cause was triage._CONDITIONAL_VENT's bare-I'd
  alternative eating reported-promise clauses as counterfactual vents at clause
  scope. New clause-scoped reported-promise shape (first-person told/promised/said
  frame + irrealis I'd/I'll complement + open-vocabulary base verb) cancels the
  bare-I'd vent reading and counts as a positive; harm-line re-gates the send ->
  REAL pending ask (the owner-lane PROMISE pin flipped ignore->ask exactly per the
  F21 regression check; F17 one-brain contract unchanged). Junk bound: structural
  anchors + closed-class deny-direction checks (participle 'd=had, negation/hedge/
  vow words, deferral idioms, retorts/regret/habituals/resolved-"and I did"/
  but-failure tails, joke markers), every class pinned (clause-scope pins 157->187,
  suite 42/42); an adversarial probe session drove the deny set, residuals
  disclosed in FAILURE_MODES. Provably inert on the dev bank: per-line decision
  diff vs pre = ZERO across 493 lines x 16 persona-days in BOTH lanes; aggregates
  bit-identical to ratchet bests / documented owner numbers. Catch movement is
  off-bank only — the primary instrument is now SATURATED everywhere a builder can
  read (dev 1.0/1.0 AND last judged holdout 1.0 worst, 041654Z verdict): foreman
  needs a new measurable aim. Disclosed risk: new ask shape, blind holdout
  interrupt margin (3.0 zero-margin x2 personas) — next judge holdout run rules.
- THE OWNER LANE IS ONE BRAIN (lap 20260611T082216Z, build — ledger F17 CLOSED on
  the dev instrument): ControlCore._spine_card feeds every observed owner line
  through the proven spine (triage -> decider -> harm-line -> orchestrator/hands,
  recursion-guarded); owner_mode regex only shapes cards, pre-gates money (blocked:
  never the spine, never /pending, never executes — pin held), and adds silent
  memory. owner_event reports the spine's verdict verbatim; spine-silent shaped
  cards stay durable open loops, never paper asks. Owner instrument (dev, stub):
  catch 0.5054/0.2222 -> 1.0/1.0, false 0, harm 0, recall_worst 0.25 -> 1.0,
  e2e 0.0208 -> 0.3427 — SPINE PARITY on every brain metric (parity shares the
  spine's C13 bank-fit; holdout still rules gate-grade claims). Interrupt 1.125/1.5:
  the entire delta vs the spine is the money pre-gate asking on money-flavored
  vents (F23 OPEN, fail-safe direction, foreman call queued). F22 FIXED (synthetic
  card titles in open_loops polluted planner inject and stranded act goals waiting
  -> drawer now stores spoken source_text). F21 NEW OPEN: the spine itself silently
  drops the bare reported-promise shape ("X needs Y; I told him I'd send it") —
  surfaced when the one-brain change removed the regex paper-ask that masked it;
  pinned as-is in test_owner_ingest_event (PROMISE_SILENT), triage-shape fix is a
  future main-path lap and the likely next holdout lever. Default path provably
  inert: full-bank stub bit-identical to ratchet bests (9/9 aggregates) and 16/16
  persona-days per-line identical at final HEAD. Suite 42/42. Residual: the
  /owner/ingest execute_actions=false preview door still uses the regex-only
  extractor (side-effect-free by design; needs the one-brain treatment before any
  non-executing door ships).
- P3-VOICE PLUMBING IS BUILT, MOCK-PROVEN (lap 20260611T051236Z, groundwork —
  STAGE B item 3): channels/call.py is a real Twilio Calls channel (mock/live/
  audit triad like text.py; researched REST shape — POST Calls.json with
  To/From/Twiml=<Response><Say>, escaped + 4000-char-bounded, explicit basic-auth
  header per ledger F19; response sid/status = the gate_P3 read-back handle).
  A real ChannelWorker owns send_text/call on the bus (failed live send -> failed
  Result, never fake delivery; ChannelStub keeps send_email); notify_user routes
  through it. channels/inbound.py polls Twilio Messages (To= + PageSize= +
  persisted seen-sids + cold-start floor; owner-sender-only; OWNER_PHONE unset ->
  refuse everything; mark-seen-before-act so approvals never replay): YES/NO+code
  resolves asks THROUGH ControlCore.resolve — F18 CLOSED for the resolve path via
  the durable execution.goal_id fallback (map-cleared pin in test_inbound) — and
  other inbound is owner speech into owner_ingest (source "sms", spine rules).
  The ask SMS now carries the reply code (decision-inert, proven). Poller runs in
  the engine lifespan ONLY with live env (default poll 15s). Suite 42/42; default
  path bit-identical to ratchet bests (9/9 aggregates; per-line 16/16 days
  identical vs 045035Z-pre); owner-lane instrument exactly unchanged; zero spend.
  P3 closure now waits ONLY on OWNER_PHONE confirmation + live Twilio env. NEW
  ledger: F19 (text.py realm-dependent live auth, port header pattern if live SMS
  fails), F20 (ambiguous inbound reply refused SILENTLY — needs a bounded
  clarification reply). D16 sibling now binds live ops: an engine restart strands
  pending asks themselves (the record linkage survives, the pending map doesn't).
- OWNER CARDS NOW EXECUTE (lap 20260611T045035Z, build — STAGE B item 2): do-cards
  run through the PROVEN proactive spine (feed -> triage -> harm-line ->
  orchestrator/hands) with outcome+proof (artifact id, read-back) mirrored onto the
  durable card record ("done" only when the goal finished with proof); ask-cards are
  REAL pending asks (/pending + existing YES/NO; resolution writes state+proof back
  onto the record); money/blocked cards can NEVER execute (state "blocked", never in
  /pending, no goal — the harm-line is final); remember cards carry drawer read-back
  proof. owner_event reports the POST-EXECUTION decision (spine may refuse ->
  "ignore" or re-gate -> "ask") — no more paper acts. Owner-lane dev instrument:
  false_action_count 15 -> 0, e2e 0.0 -> 0.0208, catch EXACTLY unchanged
  0.5054 / worst 0.2222 (founder_jin), harm 0, interrupt 0.875/1.5. The catch
  ceiling is now purely the weak card extractor (F17, foreman call: one brain).
  NEW F18 (D16 family): the resolve write-back linkage is in-memory; item 3's
  inbound resolver must route through ControlCore.resolve. C22 mechanical shingle
  scan stays foreman-side OPEN.
- OWNER LANE IS MEASURABLE (lap 20260611T043446Z, groundwork — STAGE B item 1):
  with ANTICIPY_OWNER_INGEST=1 the unchanged persona runner drives /event through the
  owner card path (decision mapping fails toward ask; goal-shaped card records under
  <data>/owner_cards/ harvested by the existing collector; default path verified
  bit-identical to ratchet bests without the env var). First honest dev-bank read,
  post-C22 literal removal: catch 0.5054 / worst 0.2222 (founder_jin), false 15,
  harm 0, interrupt 0.6875/1.5, recall_worst 0.25, e2e 0.0 (cards did not execute yet)
  — versus 1.0/1.0/false-0 on the proactive path, same bank, same HEAD. Ledger F17:
  the owner doors ship a second, weaker brain; fix direction is the proven
  triage/decider spine or a hybrid extractor, not more regex. C22 product-side
  literals deleted (catch unchanged, false 17->15).
- ACCOUNTING DESTRUCTION (2026-06-10, ledger D21): lap 083047Z's kept=False revert
  (`git reset --hard`) rolled the tracked-but-never-lap-committed scoreboard/RATCHET back
  to foreman snapshot ea08490 — erasing the P1 first-close record, six scoreboard rows
  (060701Z..080849Z), the ratchet bests, and a treadmill count of 4 (one dead lap from
  the designed escalation, which was thereby silently defeated). Lap 20260610T091120Z
  re-verified HEAD (suite 33/33; stub bank identical to the lost bests; gate_P1 live
  precheck verdict_pass=TRUE) and set attempt_gate_close=true so the sole writers
  re-record the P1 close. The PRODUCT lost nothing — all kept commits are on HEAD; the
  lost rows' evidence survives in logs/factory/laps/<lap>/. Foreman: fix loop.sh per D21.
- P1-closed-loop first-closed mechanically at lap 20260610T060701Z (RATCHET phases_closed;
  record destroyed by D21, re-closed at lap 20260610T091120Z).
  Scope honesty: S1-S4 proven live; S5 (real SMS) owner-blocked, S6 (MP3 day) deferred —
  see ledger B9 for the gate-vs-PHASES.yaml scope mismatch (foreman item).
- Lap 20260610T062952Z (builder, deterministic): triage rewritten from bag-of-words to
  speech-act shapes + harm-line calendar-put/delegated-send routing (ledger F2 PREVENTED,
  F3 CONTAINED-for-delegation/OPEN-for-first-person). Builder-side stub eval on the dev
  bank: catch 1.0 / worst 1.0 (was 0.6667/0.50), false_action 0 (was 19), interrupt
  1.06 avg / 1.5 worst (was 5.44/10.5), silent_harm 0, recall_worst 1.0 (was 0.33);
  suite 31/31. All four gate_P2 thresholds met on the DEV bank builder-side; holdout
  (judge-only) expected lower — dev-bank perfection is partly bank-fit. Residual asks are
  mostly money commands the product MUST ask on (bank keys them silence because the speaker
  retracts next line; causal engine can't know at ask time) — decider/ask-debounce territory.
- The P2 decider LANDED (lap 20260610T070648Z, groundwork): proactive/decider.py (Track-B
  prompt, temp 0, word-boundary safest-wins parse, every failure path -> SILENT; ledger F4)
  wired into core/proactive.py as Room 1.5 — constructed only when
  ANTICIPY_MODEL_PROVIDER=openrouter, one-way (SILENT drops, ASK forces the ask path,
  ACT defers; the harm-line's ASK is FINAL). Suite 32/32 (new test_decider.py); stub
  persona metrics bit-identical to the ratchet best (the decider is invisible in stub).
- The decider's LIVE behavior is now PROBED AND HOLDING (laps 20260610T072358Z +
  20260610T074854Z, Gemini free tier): the first live run exposed F5 (the cheap model
  read narration — past-tense reports, future-schedule self-plans, banter, first-person
  casual sends — as commitment: 2 false actions on contractor_luis) and F6 (triage's
  live tiebreak calls run_until_complete inside the running loop, always raises, fails
  OPEN — the decider carries live precision alone; deliberate defer). The prompt was
  rewritten around the HANDOFF test (narration of one's own past/plans/social acts is
  never a task; a task exists only when the line delegates one) and extended for
  present-progressive self-activity and self-personification self-talk ("tomorrow-me")
  after live doctor_amara evidence. Lap 072358Z died at its session bound BEFORE
  committing (the fix survived only in its lap dir's uncommitted.patch — ledger D20);
  lap 074854Z recovered, independently re-verified, and committed it. Live evidence:
  31/31 on the self-authored probe; contractor_luis + doctor_amara live false_action 0,
  catch 1.0, harm 0, interrupt 2.0/2.5 — all four gate_P2 guards held at live tier on
  the probed pair. Unproven: the other 6 personas live, and behavior under sustained
  429/quota pressure (fail-SILENT is safe for harm but uncounted catch risk).
- Decider v8+v10 (live interrupt precision + noun-fragment fold) is now DURABLY ON HEAD
  (lap 20260610T100043Z, commit d788778) after being destroyed twice: authored at lap
  083047Z (probe 62/63; killed the v8 full-bank live false action — a spoken
  deliverable-name fragment drew ACT and the harm-line's draft category made it real),
  destroyed by that lap's D5 empty-build.json revert; recovery lap 094944Z re-applied
  and re-verified it but died at its session bound mid-live-baseline before committing
  (D20 recurrence #2 — full-bank live runs do not fit a builder session; commit first).
  Recovery was byte-exact from 094944Z's uncommitted.patch (= dangling ebb0789 + the C13
  docstring scrub), re-verified independently: suite 33/33, stub bank bit-identical to
  ratchet bests, live probe 62/63 (the one residual is a relay-ACT the harm-line's send
  assessment contains). Targeted live re-run of lawyer_marcus (the v8 false-action
  persona) CONFIRMS the fix: false_action 0 (was 1), catch 1.0 (8/8), harm 0,
  interrupt 1.0, recall 1.0 — all four gate_P2 guard dimensions held live on it.
  Still unproven: full 8-persona live bank post-v10 (a foreman/verify_gate run, not a
  builder session — D20); real-429 behavior observed live (see the F7 bullet below).
- 429/quota outage behavior is now DESIGNED AND PINNED (lap 20260610T101115Z, commit
  81eb8ea, ledger F7): previously the gateway's exhausted retries returned "" which the
  decider read as SILENT — under sustained quota pressure every triage-passed line was
  silently dropped with the false reason "not a real commitment" (free-tier Gemini makes
  this a when-not-if). Now transport non-reads return UNAVAILABLE, on_event defers them
  75s x<=2 retries through trigger_tick (full pipeline re-entry; a recovered verdict
  still crosses the harm-line; deferral never creates a goal/ask), and exhaustion drops
  with an honest reason. Deterministic pins in test_decider.py; live healthy path 5/5
  post-change. Residuals: in-memory deferred queue (restart loses it, D16 family),
  real-429 storm not live-observed (would poison the night's shared quota for
  verify_gate's live runs).
- The gateway now HONORS 429 retry hints (lap 20260610T102837Z, commit 6efcad7 —
  closes F7 residual "gateway ignores Retry-After"): research-verified shapes
  (Gemini has no reliable Retry-After header; the signal is RetryInfo retryDelay in
  the body — sometimes array-wrapped on the OpenAI-compat endpoint we call, sometimes
  only a "retry in Ns" message phrase; OpenRouter documents Retry-After delta-seconds).
  Hint <= 8s sleeps inline (+0.25s margin, 4-attempt bound holds); hint > 8s
  fast-fails after ONE request into the UNAVAILABLE -> 75s defer path instead of
  burning 3 more quota-counting blind retries against a closed window; no-hint 429s
  and 5xx keep byte-identical blind backoff. Pins: test_gateway_retry.py (suite
  33->34, MockTransport, zero network/waiting). Live healthy path 5/5, hint path
  provably dormant on healthy replies (hints_seen=[]).
- The outage queue now SURVIVES ENGINE RESTARTS (lap 20260610T104837Z, commit
  1ce2269 — closes the F7 residual "in-memory deferred queue", D16 family):
  decider_deferred + attempt counts persist atomically to
  <ANTICIPY_DATA_DIR>/decider_deferred.json on every mutation; a LIVE boot restores
  them and entries re-enter the FULL pipeline at their due tick. Live-only on both
  ends (a stub boot neither restores nor touches the file — an unread line never
  re-enters without a decider); the retry bound holds ACROSS restarts; a restored
  money line still ends at the harm-line ASK; corrupt files are set aside honestly;
  the drain persists BEFORE re-entry so a mid-retry crash loses-toward-silence,
  never replays. Pins: test_deferred_persistence.py (suite 34->35). D16 sibling
  still open: self.pending asks remain in-memory (restart strands paused goals —
  the persistence pattern now exists to copy). F7's last residual: real-429 storm
  live observation.
- The HOLDOUT CAMPAIGN (P2 closure, TARGET v4 STAGE A): three judge-verified-good
  diffs (laps 131707Z, 223727Z, 232257Z) were each VETOed-and-reverted solely because
  the holdout floor (worst >= 0.70) was not yet met — VETO is the judge's only lever
  that prevents a false P2 close (scoreboard stamps phases_closed on any kept
  phase_gate_passed row). Trajectory of the judge's holdout counts: worst 0.3333 ->
  0.6667, aggregate 0.625 -> 0.8542, false 0, harm 0 throughout; interrupt_worst 3.0
  at ZERO margin on gradta_ming and nurse_helen (one junk ask on either fails the
  gate). Two falsified blind lexicon sweeps established F15: closed-class lexicons
  cannot chase the holdout's open vocabulary; verdicts now disclose residuals at
  SHAPE granularity. Lap 20260611T000748Z re-landed the 232257Z diff VERBATIM (its
  verdict's condition 1) and added the disclosed shape: the BENEFACTIVE-STAGING
  IMPERATIVE (clause-initial open-vocabulary imperative or causative-get +
  determiner-fronted object + same-clause "for me/us" tail), junk-bounded by three
  structural anchors + closed-class denies, every judge-enumerated junk class pinned
  (154 pins), full-bank dev decision diff = exactly the one intended re-land change
  (the rule is provably inert on dev). Disclosed residual: F16 (appositive gratitude
  narration). Gate-close attempted; the judge holdout run decides. If VETO again,
  verdict condition 3 hands the structural options to the foreman (judge-named-lexeme
  channel amendment after K falsified sweeps, or live-tier holdout instrument);
  treadmill at 4 — the next dead lap fires the designed escalation.
  UPDATE (lap 20260611T041654Z): the 000748Z closure attempt ended JUDGE_ERROR (external
  judge session limit; C17 correctly voided the close — F15a has NEVER been judged).
  Foreman repaired (D23: session-limit laps don't count as treadmill; treadmill reset 0)
  and landed TARGET v6 + the Owner Action Engine lane (ee77765). Lap 041654Z is the
  TARGET v6 STAGE A re-attempt: HEAD verified healthy (suite 38/38 incl. 2 new owner
  tests; fresh stub full bank bit-identical to ratchet bests, selftest PASS; per-line
  decision diff vs 000748Z-pre = 16/16 persona-days byte-identical, so the owner lane
  is provably inert on the persona path and the judge rules on exactly the F15a brain
  state). attempt_gate_close=true; zero code changes, zero spend; the judge's fresh
  holdout run decides.

## P1 history (work list was TARGET v2)
Scheduler for trigger_tick; due-time grounding (duetime.py); reminder routing (notify,
not YES/NO ask); real ChannelWorker + Twilio env normalization + owner-literal removal;
MainView SideDoor as a real TextField. Gate: factory/gates/gate_P1.sh (live legs SKIP
honestly until OWNER_PHONE is confirmed and OpenRouter is topped up).
- Lap 20260610T052102Z re-landed the falsely-reverted (ledger C11) due-time chain from lap
  20260610T045550Z (duetime.py grounding, remind_ts firing, notify routing, lifespan
  scheduler ANTICIPY_TICK_SECONDS default 30 + POST /trigger/tick) and fixed gate S3:
  triage now drops hedge-nonspecific vent lines (someday/eventually/at some point/...)
  unless a concrete time anchor cancels the hedge. Builder-side: suite 31/31, persona
  metrics unmoved, gate_P1 verdict_pass=TRUE (S1-S4 green live, S5 honest skip).
- Live-gate side-effect leaks found + contained (ledger B4/B5): gate S1 cleanup never fired
  (proof-shape mismatch) and live S2 strands a second calendar event — 4 stray real events
  deleted via Arcade with read-back. B6 OPEN: calendar planner drops quoted titles, so real
  artifacts land unlabeled as "Calendar event" (next-slice candidate).
- Lap 20260610T060701Z (verification, no code changes) independently re-confirmed gate_P1
  on HEAD: suite 31/31, personas at baseline, gate precheck verdict_pass=TRUE rc=0 with
  S1 auto-cleanup proven live (a6ce4a3 fix works WHEN env present) and S2's stray deleted
  + read back. NEW ledger B7: the production verify_gate chain (launchd sets only PATH)
  never gives the gate shell ARCADE_API_KEY, so mechanical gate runs strand S1+S2 events
  until the foreman exports .env.local in the gate path. NEW B8: gate S5 reads gate-shell
  env, not engine reality (engine channel sends go to placeholder +10000000000).

## Durable dead ends (do not blindly retry; full history in autopilot/LESSONS.md and git)
- example.com / localhost / fixture pages as task targets or evidence.
- Typing the whole task into a search bar; search fallback for URL-less action tasks.
- Add-click as cart proof; modals/badges/screenshots as completion proof; recommendation
  rows as cart proof. Independent fresh-probe read-back is the standard.
- Captcha/anti-bot arms races (Harbor Freight, Container Store walls are site gates).
- Hard sites pending a NEW hypothesis: Barnes & Noble, Office Depot, Staples, Nordstrom,
  Home Depot, Sur La Table, LEGO, Guitar Center, Ulta, Dick's, Kohl's, Ace, ThriftBooks,
  Vitamin Shoppe, Five Below, PetSmart, Wayfair retry-after-mutation, Lowe's token-rich.
- Google Sheets/Docs canvas synthetic input; Amazon.ca Playwright automation.
- Always-on cloud transcription (sidecar cache is the pattern).
- The proactive engine's OVER-ASKING and act-on-narration weakness (interrupt 5.4/day,
  false_action 19 at baseline) was mostly a triage bag-of-words inversion — fixed
  deterministically at lap 20260610T062952Z (ledger F2; now 1.06/day, 0 false on dev bank).
  The residual gray (money-retraction pairs, first-person casual sends, F3) is P2 decider
  territory; overnight/track_b/decider.py is the proven seed.

## Law digest (unchanged where it was right)
Never act on a vent (silent_harm guard is absolute and voids laps). Money/payment is the
only hard action stop. Real artifact read-back is the only completion proof. Builders never
grade themselves, never touch factory//personas//scoreboard, never read holdout. Honest
labels: UNPROVEN until a gate or judge says otherwise. Strategy changes are legal and go
through ESCALATION -> foreman -> TARGET.md, never silently.

## Codex backend takeover prep (2026-06-12)
Owner reports Claude credits are unavailable. The successful part of the prior system was
NOT the Claude backend; it was the Factory's control law: one locked workshop, pre-
registered hypotheses, research-before-editing, mechanical gates, adversarial judge,
holdout secrecy, read-back proof, scoreboard ratchet, treadmill escalation, and durable
handoffs. Those laws now survive a backend swap: the Factory defaults to
`FACTORY_AGENT=codex`, which runs builder and judge laps through `codex exec --json`;
Claude is now only an explicit override. Codex smoke test passed from this repo, shell
syntax passed, and the suite is green at 46/46.

The product remains paused by Omar's `.halt`. First resume must be countable per TARGET
v8.1: either supervised P3 voice closure after explicit phone confirmation, or a bank-v2
baseline measurement that creates real instrument headroom. Do not resume into dead-by-
design P4 groundwork while treadmill_count is 6.
