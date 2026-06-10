# Last Lap

Lap: 20260610T052102Z
Date: 2026-06-10
Phase: P1-closed-loop (Factory)
Slice: gate_P1 first-close attempt — re-land the falsely-reverted S2 chain + fix S3 vent silence

What changed:
- RE-LANDED (verbatim from logs/factory/laps/20260610T045550Z/reverted.patch; that lap was
  falsely reverted by the old holdout string-scan, ledger C11):
  - NEW `engine/anticipy_engine/live_memory/duetime.py`: deterministic tz-aware due-time
    parser anchored to event meta `observed_at` (never engine time), conservative None.
  - `live_memory/capture.py`: open_loop captures get `due_ts` + `remind_ts = due_ts - 15min`;
    `capture()` takes `meta=`; `control_core.feed` passes meta through.
  - `proactive/trigger.py`: TriggerWatcher fires on `remind_ts` before `due_ts`.
  - `core/proactive.py`: `_fire_reminder` — fired time-grounded reminder re-gated on the
    harm-line; safe -> budget-capped channel NOTIFY (loop marked `waiting` via new `mark_loop`
    intent), detrimental -> existing ask round-trip; ungrounded loops keep the act path.
  - `main.py`: lifespan asyncio scheduler (ANTICIPY_TICK_SECONDS, default 30, 0=off) +
    POST /trigger/tick; `core/workers/memory.py`: remind_ts surfaced + mark_loop.
  - Suite tests `test_duetime.py` + `test_trigger_notify.py`, registered in run_suite.sh.
- NEW: `proactive/triage.py` hedge rule — hedge-nonspecific lines (someday / some day /
  eventually / at some point / one of these days / sooner or later / when I get a chance|
  around to it) DROP unless a concrete time anchor cancels the hedge. Vents stop becoming
  asks; capture still remembers the line; the 3-day stale path is unchanged for ungrounded
  loops. Vent cases added to `test_triage.py` (recall bar still 1.000, drop 1.000).
  Dev-bank check before building: the only hedge-keyed expected item is keyed `silence`
  (student_kayla day02 s3), so this cannot kill any expected act/ask catch.

Eval numbers I saw (builder-side; verify_gate recomputes everything):
- Suite: 31/31 PASS.
- 8-persona stub eval (lap 20260610T052102Z-pre): catch 0.6667 / worst 0.50 (doctor_amara),
  correct 0.5062, false_action 19, silent_harm 0, interrupt 5.4375 / 10.5, e2e 0.2354,
  recall_worst 0.3333 — IDENTICAL to the last no-change lap 20260610T051949Z (the
  0.6984->0.6667 catch drift predates this lap; it appeared in that no-change lap too).
- gate_P1 (live hands, builder precheck): **verdict_pass=TRUE, rc=0** — S1 act+done+proof
  (live Arcade), S2_reminder_fires pass via the real 30s scheduler, S3 ignore, S4 ask ->
  pending -> deny round-trip. S5 honest skip (no live Twilio). Manifest sets
  attempt_gate_close=true so verify_gate re-runs the gate mechanically.

Real-world side effects this lap (all self-owned, all cleaned):
- The live gate run created 2 real calendar events (S1's "Calendar event" + S2's
  "[Anticipy test] stretch"); the previous lap's gate run had stranded 2 more. The gate's
  own cleanup NEVER fires (proof-shape mismatch, ledger B4) and never covered S2 (B5).
  All 4 deleted via Arcade GoogleCalendar.DeleteEvent; ListEvents read-back confirms gone.
- NOT touched: 5 older `[Anticipy test]` fixture events June 10-11 (Doctor's checkup,
  Errands, Focus time, 1:1 with Alex, Reading time) — predate this lap, unknown owner-seed.

Honest findings (NOT fixed in this lap):
- B6 (OPEN): the deterministic calendar planner drops the quoted title — S1's real artifact
  lands as generic "Calendar event", not "[Anticipy test] gate-P1 <lap>". Semantically wrong
  artifact + label-convention break. Next-slice candidate: quoted-title extraction in the
  orchestrator calendar pre-plan + a test pinning the summary.
- B4/B5 gate cleanup fixes are foreman-only (factory/gates/gate_P1.sh).
- Fire-once is still in-memory (D16): an engine restart re-fires a past-remind_ts loop once.

Next:
- B6 quoted-title fix (product, small, testable).
- TARGET item 4: ChannelWorker + TWILIO_PHONE_NUMBER->TWILIO_FROM normalization + delete the
  owner-email literal in core/control_core.py:66; pass channel/user_contact (OWNER_PHONE)
  into ProactiveEngine.
- TARGET item 5: MainView SideDoor TextField.
- S5/S6 live legs still need OWNER_PHONE + Twilio + OpenRouter top-up (PENDING_FOR_OMAR).
