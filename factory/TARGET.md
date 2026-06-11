# TARGET v6
updated: 2026-06-11T03:35:00Z by foreman (Owner Action Engine lane ruled ALIVE + Amendment 1; lanes unified — one machine, one honesty instrument)
north_star: A person's messy day in -> the right tasks caught, done for real, proven; wrong ones never done.
current_phase: P2-brain
primary_metric: catch_rate_worst
guards: false_action_count==0 silent_harm_count==0
phase_gate: factory/gates/gate_P2.sh
eval_tier: stub
budget_week_usd: 200
allowed_strategies: |
  Read .claude/OWNER_ACTION_ENGINE.md (incl. AMENDMENT 1) first — it defines what the
  product IS. This file defines what to build next. Check RATCHET phases_closed for stage:

  STAGE A (P2-brain NOT in phases_closed): re-attempt the P2 closure. The F15a
  benefactive-staging SHAPE fix (commit 96eb92f) is ON HEAD and was never judged — its
  closure attempt died to an external judge session limit (C17: closure now requires
  judge_verdict REAL, so that void was correct). Your lap: verify HEAD healthy (suite +
  quick stub persona pass), set "attempt_gate_close": true, let the gate + judge run the
  holdout. Pre-F15a holdout stood at worst 0.6667 (nurse_helen 2/3, single benefactive
  sentence); if F15a works, this closes. If the judge VETOes again, its named residue is
  the next hypothesis. NEVER touch personas/; improve the product.
  Cleanup rules apply to any real gate artifact: confirm cleanup in results; delete
  reported ids via Arcade before finishing the lap.

  STAGE B (P2-brain IS in phases_closed): the OWNER ACTION ENGINE execution path —
  make the cards real, in this order:
  1. Owner-path honesty wiring: extend factory/bin/persona_run.py with an
     --owner-ingest mode that feeds persona days through POST /owner/ingest and scores
     the produced cards with persona_score.py against the same expected.json keys.
     The owner lane gets worst-persona honesty from day one. (Builders may not edit
     factory/ — implement the engine side so the existing runner can drive it via env
     ANTICIPY_OWNER_INGEST=1 on /event, or expose card output in glassbox where the
     scorer already looks.)
  2. Card execution: act-route cards execute through the existing orchestrator/ApiHand
     with proof written back onto the card (artifact id + read-back); ask_required cards
     surface in /pending and resolve through the existing YES/NO flow; money cards can
     NEVER execute (harm-line is final).
  3. P3-voice plumbing (closure needs OWNER_PHONE, build everything testable without):
     channels/call.py (Twilio Calls, inline Twiml=<Response><Say>, mock/live/audit like
     text.py); ChannelWorker for send_text/call; channels/inbound.py polling Twilio
     Messages REST (~15s) — YES/NO+code resolves asks, other inbound -> /owner/ingest.
  4. Focused tests with mocks; suite green; persona guards absolute.
banned_work: |
  Per-store DOM recipes. UI polish beyond the owner input doors. example.com / localhost /
  fixture targets as task evidence. Search-bar task dumping. Never edit factory/ control
  plane, personas/, scripts/realday.sh, the scoreboard, or read any holdout content.
  No third-party messages; test artifacts self-owned, labeled, reversible, cleaned up.
  Never edit the persona bank to make a score pass. NEVER edit or commit while
  factory/.lock exists (applies to every actor, incl. the 30-min Owner automation).
notes: |
  Owner Action Engine lane (POST /owner/ingest, /owner/onboard) ruled ALIVE by foreman
  with Amendment 1: one lock discipline for all actors, commit-every-session, ONE honesty
  instrument (persona bank + scorer + judge cover the owner path), execution inherits the
  harm-line/proof spine. C17 (judge-REAL required for closure) and D23/SKIPPED_LIMIT
  hardening from TARGET v5 carried forward. Owner items pending, non-blocking:
  OWNER_PHONE for P3 closure, holdout red-pen, bank v2 (foreman-owned).
