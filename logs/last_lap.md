# Last Lap

Lap: 20260611T133818Z (groundwork — trigger fired-state persistence, D16 PROPER:
the ledger's oldest open restart-robustness entry, the one with a NON-SILENT
failure direction; sanctioned by TARGET v7 item 4's "build and mock-prove
everything around the P3 gate". DISCLOSED in the manifest up front: primary
metric e2e is at its F31 honest ceiling and gate_P3 cannot first-close from a
builder lap (live legs human-gated on OWNER_PHONE; the gate script is a foreman
item) — so this lap reads mechanically DEAD (moved=none) by design, and it is
dead lap #5: the DESIGNED K=5 escalation should fire after this lap and hand
the foreman the TARGET v8 re-aim.)

## What changed
- `engine/anticipy_engine/proactive/trigger.py`: `_due` treats a loop whose
  record carries a non-None `fired_at` as fired-forever (corrupt values fail
  toward silence); the in-memory `_fired` set stays as the same-session guard.
- `engine/anticipy_engine/core/proactive.py`: `trigger_tick` stamps `fired_at`
  onto the DURABLE loop record (existing `mark_loop` bus intent) BEFORE any
  send or pipeline re-entry — mark-before-act, the inbound seen-sid law. A
  crash after the stamp loses that firing toward silence (never a late
  duplicate); a FAILED stamp skips the firing entirely (never fire unstamped),
  logs `trigger_stamp_failed`, and the loop fires on the next healthy boot.
- `engine/anticipy_engine/core/workers/memory.py`: `list_open_loops` output
  carries `fields.fired_at`; `mark_loop` takes an optional `fired_at` arg — a
  pure stamp leaves ledger status alone; the legacy no-arg default ("waiting")
  is preserved and pinned. No new wiring or files: the stamp rides the SQLite
  ledger every engine already has.
- `engine/scripts/test_trigger_persistence.py` (NEW, suite 44 -> 45): reminder
  restart no-double-fire (stamp lands before the send); follow-up/act restart
  never re-enters the pipeline (no second goal); crash-after-stamp loses toward
  silence across restart; failed-stamp skips unstamped then fires next healthy
  boot; mark_loop contract pins; ControlCore end-to-end restart on one data dir
  (the gate_P3 trigger leg cannot double-interrupt).
- `scripts/run_suite.sh`: wired the new test.
- Ledger: D16 -> FIXED with regression check; remaining restart-state siblings
  disclosed (AnnoyanceBudget day-counts / AskDebounce holds — annoyance-bounded,
  money still never executes; _owner_card_goals in-memory BY DESIGN per F18).

## Why (the product fact)
gate_P3's trigger leg is "trigger->call <= 60s". On a live day the engine
restarts (deploys, crashes, sleep). The ledger is durable, so a restarted
engine re-listed every open/waiting loop — and with the fire-once guard gone,
re-fired every one already past its time: duplicate reminder texts/calls to the
owner, and duplicate pipeline re-entry where an ACT-decided follow-up would
execute a second time. test_trigger_notify.py's second engine was already
exercising exactly this on HEAD (it just never asserted about the old loops).
After this lap a fired trigger is fired forever, restart or not.

## Eval numbers seen (builder-side, stub)
- Suite 45/45 green.
- OFFICIAL instrument (full pre AND post runs, BOTH lanes): bit-identical at
  the ratchet bests — catch 1.0/1.0, false 0, harm 0, interrupt 0.625/1.0,
  e2e 0.6483, correct 0.8475, recall 1.0; aggregate AND per-persona JSON equal.
- Per-line decision diff pre->post: ZERO in both lanes (owner 492 / default 493
  decision lines x 16 persona-days). Goal (intent,state) multisets identical.
  `fired_at` absent from every persona-run artifact (trigger_tick never runs in
  persona runs — verified by grep AND artifact scan).
- Zero spend, zero real-world artifacts, no live legs.

## What's next
- The D16 restart-robustness family is now closed on every non-silent edge:
  deferred queue (1ce2269), pending asks (41da3c3), fired triggers (this lap).
  Remaining siblings fail toward bounded annoyance only (budget/debounce day
  state) — separate, lower-stakes slices.
- This is dead lap #5 by design: the treadmill should fire the K=5 escalation
  and halt; the foreman re-aims TARGET v8 (correct_action_rate has real
  headroom at 0.8475; F23 money stance and F31 are foreman calls).
- gate_P3 closure still waits on the two human/foreman gates: Omar's
  OWNER_PHONE confirmation (PENDING_FOR_OMAR) and the gate_P3.sh script itself.
