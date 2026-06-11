# STATE

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
- Steering: `factory/TARGET.md` (foreman-owned, currently v2 / phase P1-closed-loop).
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

## Current phase: P2-brain CLOSED (lap 20260611T041654Z, judge REAL — F15a holdout state finally judged) -> TARGET v6 STAGE B: the Owner Action Engine execution path
- OWNER LANE IS NOW MEASURABLE (lap 20260611T043446Z, groundwork — STAGE B item 1):
  with ANTICIPY_OWNER_INGEST=1 the unchanged persona runner drives /event through the
  owner card path (decision mapping fails toward ask; goal-shaped card records under
  <data>/owner_cards/ harvested by the existing collector; default path verified
  bit-identical to ratchet bests without the env var). First honest dev-bank read,
  post-C22 literal removal: catch 0.5054 / worst 0.2222 (founder_jin), false 15,
  harm 0, interrupt 0.6875/1.5, recall_worst 0.25, e2e 0.0 (cards do not execute yet)
  — versus 1.0/1.0/false-0 on the proactive path, same bank, same HEAD. Ledger F17:
  the owner doors ship a second, weaker brain; fix direction is the proven
  triage/decider spine or a hybrid extractor, not more regex. C22 product-side
  literals deleted (catch unchanged, false 17->15); the mechanical shingle scan stays
  foreman-side OPEN.
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
