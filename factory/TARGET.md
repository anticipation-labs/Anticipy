# TARGET v4
updated: 2026-06-10T11:02:00Z by foreman (escalation 20260610T1059 resolved: dev bank saturated; strategy change to P2 closure then P3 plumbing)
north_star: A person's messy day in -> the right tasks caught, done for real, proven; wrong ones never done.
current_phase: P2-brain
primary_metric: catch_rate_worst
guards: false_action_count==0 silent_harm_count==0
phase_gate: factory/gates/gate_P2.sh
eval_tier: stub
budget_week_usd: 200
allowed_strategies: |
  Check logs/factory/RATCHET.json phases_closed to find your stage:

  STAGE A (P2-brain NOT in phases_closed): attempt the P2 closure. The dev bank already
  exceeds every gate_P2 threshold (worst 1.0 / false 0 / harm 0 / interrupt_worst 1.5),
  so your lap is: verify HEAD healthy (suite + quick stub persona pass), set
  "attempt_gate_close": true in your manifest, and let the gate + judge run. The judge
  runs the HOLDOUT bank — the real test of the speech-act triage rewrite (perfect dev
  score + weak holdout = overfit; expect a VETO and treat its findings as the next
  hypothesis). NEVER touch personas/ to make holdout pass — improve the PRODUCT
  (triage/decider generality), never the eval.
  KNOWN HOLDOUT REALITY: at P1 closure the holdout worst-persona catch was 0.33. If the
  judge reports holdout weak, subsequent laps generalize triage/decider until the judge's
  holdout numbers clear the same thresholds; pre-register intended_metric
  "holdout via judge" honestly even though the stub scoreboard cannot see it.
  Cleanup rules apply to ANY real artifact a gate creates: confirm cleanup in results;
  if reported failed, delete the reported id via Arcade before finishing the lap.

  STAGE B (P2-brain IS in phases_closed): begin P3-voice PLUMBING (closure needs the
  owner's phone confirmation — build everything testable without it):
  1. engine/anticipy_engine/channels/call.py: Twilio Calls API with inline
     Twiml=<Response><Say> (no public webhook needed); mock/live/audit pattern mirroring
     text.py; escalation policy: SMS default, CALL when remind lead <= threshold.
  2. ChannelWorker registration for send_text/call extending the P1 notify routing to
     channel selection.
  3. channels/inbound.py: poll Twilio Messages REST from the lifespan scheduler (~15s);
     ask SMS carries a short code; YES/NO+code -> resolve_ask; other inbound ->
     core.feed(source="sms").
  4. Focused tests with mock Twilio clients; suite green; persona guards absolute.
banned_work: |
  Per-store DOM recipes. UI polish. Status surfaces. Onboarding. example.com / localhost /
  fixture targets. Search-bar task dumping. Never edit factory/ control plane, personas/,
  scripts/realday.sh, the scoreboard, or read any holdout content. No third-party
  messages; test artifacts self-owned, labeled, reversible, cleaned up. Never edit the
  persona bank to make a score pass.
notes: |
  Escalation 2026-06-10T10:59 (K=5 on a saturated dev bank) resolved by this re-aim —
  the laps in that stretch were honest kept work (decider, live validation, F5, margin
  hardening); the bank ceiling, not the work, stalled the counter. C14 fixed earlier
  tonight: reverts can no longer roll back measurement files; rows marked RECONSTRUCTED
  are authoritative. gate_P1 cleanup loads .env.local itself (B4). Owner items pending,
  non-blocking: OWNER_PHONE for P3 closure, holdout red-pen, bank v2 (foreman-owned).
