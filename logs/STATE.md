# STATE

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

## Current phase: P1-closed-loop (see factory/TARGET.md v2 for the work list)
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
- The proactive engine's known weakness is OVER-ASKING (measured: interrupt_cost 5.4/day)
  and acting on third-party-send lines the bank keys as ask-first (false_action_count 19).
  That is P2 decider territory; overnight/track_b/decider.py is the proven seed.

## Law digest (unchanged where it was right)
Never act on a vent (silent_harm guard is absolute and voids laps). Money/payment is the
only hard action stop. Real artifact read-back is the only completion proof. Builders never
grade themselves, never touch factory//personas//scoreboard, never read holdout. Honest
labels: UNPROVEN until a gate or judge says otherwise. Strategy changes are legal and go
through ESCALATION -> foreman -> TARGET.md, never silently.
