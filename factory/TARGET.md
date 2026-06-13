# TARGET v10
updated: 2026-06-13T03:58:00Z by foreman (F47 resolved; asks are first-class owner success, not action failures)
north_star: A person's messy day in -> the right tasks caught, done for real, proven; wrong ones never done.
current_phase: P3-voice
primary_metric: v2_owner_success_rate
guards: false_action_count==0 silent_harm_count==0
phase_gate: factory/gates/gate_P3.sh
eval_tier: stub
eval_bank: factory/personas/dev_v2
eval_env: ANTICIPY_OWNER_INGEST=1
metric_alias_from: owner_success_rate
budget_week_usd: 200
allowed_strategies: |
  HUMAN TARGET: the app should let a user press Go, type/paste/upload messy life input,
  and watch the proactive engine create clear task cards, execute safe actions with
  receipts, ask before human-impacting actions, never spend money, and close loops through
  UI, memory, browser/API hands, and voice/text. This is the product. Do not drift back
  into a hidden science project.

  FIRST v10 LAP: baseline only, and it must count. The official eval now measures
  owner success, not action-only completion: expected actions count only when done
  with proof; expected asks count only when the product creates a real waiting ask
  card; false actions and silent harm stay hard zero. The metric alias
  v2_owner_success_rate is a first measurement, so a kept baseline lap resets the
  treadmill without pretending old-bank progress. Write an honest manifest, make no
  product-code changes unless a harness bug is found, run suite/eval, commit logs, stop.

  AFTER BASELINE COUNTS: improve the largest dev_v2 gap that blocks the real integrated
  product: UI/input door -> owner ingest -> card -> execution -> proof -> ask/block
  receipt. Use actual run dirs, not theory. The known first target is Nora's Northstar
  invoice-draft line: it should become an ask-first card with a waiting ask receipt,
  not an ignored line and not a sent invoice. Do not chase bank wording; fix shared
  product plumbing, planner grounding, proof write-back, UI wiring, or policy boundaries.

  Check factory/config/owner_phone.confirmed for stage:

  STAGE A (owner_phone.confirmed EXISTS — Omar confirmed his number): attempt the P3
  closure. gate_P3.sh now exists (foreman-written): real outbound TTS call to
  OWNER_PHONE with independent Twilio REST read-back, real reply-code ask SMS, and
  Omar's real "YES <code>" resolving the ask (S3 is interactive — the gate waits up to
  10 min; it is meant to run while Omar is awake, typically a foreman-supervised
  daytime run with FACTORY_FORCE_GATE=1). Verify engine HEAD healthy first (suite +
  stub persona pass), set "attempt_gate_close": true, let the gate + judge rule.
  Judge instruction: closure-grade holdout runs use ANTICIPY_OWNER_INGEST=1 (C13).

  STAGE B (no confirm marker): keep building the integrated owner product against dev_v2;
  browser groundwork is only valuable when it moves card execution/proof on messy input:
  1. agent/site_hints.py: per-host hints (search/cart/product URL shapes) as JSON in
     the data dir; one-time export from webvoyager's host-literal tables; successful
     runs write learned hints back. Then DELETE the host literals from agent code —
     the P4 grep gate (zero retailer hostnames in agent/*.py) is the target shape.
  2. agent/proof.py: extract the multi-read artifact read-back discipline from the
     cart path and generalize it beyond carts.
  3. Focused tests with mocks; suite green; persona guards absolute; default lane and
     owner lane bit-identical to ratchet bests (the e2e ceiling means ANY decision
     drift is a regression, not progress).
  FOREMAN-OWNED (not builder work, listed for honesty): persona bank v2 authoring
  (unsaturates catch, gives e2e headroom — the durable instrument fix), Omar's
  OWNER_PHONE confirm, holdout red-pen.
banned_work: |
  NEVER run live calls/SMS to OWNER_PHONE unless factory/config/owner_phone.confirmed
  exists (gate_P3.sh enforces this; the ban is absolute everywhere else too).
  Never invent a store/site for memory-fenced acts (F31) — that is a faked completion.
  Per-store DOM recipes. example.com / localhost / fixture targets as task evidence.
  Search-bar task dumping. Never edit factory/ control plane, personas/,
  scripts/realday.sh, the scoreboard, or read any holdout content. Never edit the
  persona bank to make a score pass. No third-party messages; test artifacts
  self-owned, labeled, reversible, cleaned up. NEVER edit or commit while
  factory/.lock exists (applies to every actor).
notes: |
  v10 (foreman, 2026-06-13T03:58Z): F47 resolved by fixing the instrument, not by
  lowering the goal. `e2e_completion_rate` was action-only and punished the product
  for catching required ask-first work. `owner_success_rate` now counts proof-bearing
  actions and real waiting ask cards, while false_action_count and silent_harm_count
  remain absolute hard guards. The next countable lap is a v10 baseline, then the
  expected build target is Nora's Northstar invoice-draft ask card.
  v9 (foreman, 2026-06-13T01:30Z): Omar approved resumption. Claude credits are not
  available, so FACTORY_AGENT defaults to Codex. The first resumed lap is steered to a
  bank-v2 baseline measurement, not live phone and not dead-by-design P4. eval_bank and
  metric_alias_from are now honored by verify_gate/scoreboard. Once baseline counts, the
  treadmill has honest headroom again.
  v8.1 (foreman, 2026-06-11T14:45Z): treadmill sits at 5+ and ONLY metric movement
  resets it — so the FIRST lap after any resume must be one that can count: a bank-v2
  baseline measurement (first-measurement counts) or a Stage A P3 closure attempt.
  Never start a pre-registered-dead Stage B lap while the counter is at the ceiling;
  it re-halts instantly (proven by the 14:40Z echo escalation). Loop is currently
  PAUSED by owner order (factory/.halt) — no actor restarts it until Omar says so.
  Night of 2026-06-10/11 in one line: P2-brain CLOSED judge-REAL (holdout worst 1.0),
  owner lane became the product (one brain, executing cards with proof, voice+inbound
  plumbing mock-proven, restart-safe asks and triggers), official e2e 0.3427 -> 0.6483,
  ten ledger entries FIXED, two honest K=5 escalations resolved by re-aim. The second
  escalation's root causes were foreman debts: F31 (instrument ceiling — bank v2 is
  the fix, foreman-owned) and the missing gate_P3.sh (now written, human-guarded).
  C17 judge-REAL closures, D23 SKIPPED_LIMIT handling, eval_env lever carried forward.
  Phases closed: P0, P1, P2.
