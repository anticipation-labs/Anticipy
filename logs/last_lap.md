# Last Lap

Lap: 20260611T132034Z (groundwork — pending-ask persistence, the D16 sibling:
the ledger's LAST named mock-side P3 residual, sanctioned by TARGET v7 item 4's
"build and mock-prove everything around the P3 gate". DISCLOSED in the manifest
up front: primary metric e2e is at its F31 honest ceiling and gate_P3 cannot
first-close from a builder lap (live legs human-gated on OWNER_PHONE; the gate
script itself is a foreman item) — so this lap reads mechanically DEAD
(moved=none) by design, the fourth in the designed walk toward the K=5
escalation -> TARGET v8 re-aim.)

## What changed
- `engine/anticipy_engine/core/proactive.py`: ProactiveEngine takes `pending_path`;
  the pending-ask map (ask_id -> {goal_id, action, reason, category}) now persists
  atomically (tmp + os.replace) on EVERY mutation — the `_send_ask` add and the
  `resolve_ask` pop (pop persists BEFORE the goal resumes: a crash mid-resolve can
  only LOSE the ask toward silence, never replay an approval — the deferred-drain
  ordering law). `_restore_pending` on boot validates every entry against the
  durable goal store: only goals still at state=waiting come back; missing or
  already-run goals are dropped and pruned from the file; a corrupt file boots
  empty, logs `pending_restore_failed`, and is set aside `.corrupt`; no path
  (the default in every direct-construction test) = no IO at all. Restore is
  PASSIVE state — nothing re-enters the pipeline; a restored ask waits for the
  owner's own YES/NO exactly like a live one.
- `engine/anticipy_engine/core/control_core.py`: wires
  `pending_path=<data>/pending_asks.json` (mirrors `deferred_path`); fixed the
  now-stale "_owner_card_goals is in-memory like proactive.pending itself" comment.
- `engine/scripts/test_pending_persistence.py` (NEW, suite 43 -> 44): restart
  survival + YES resumes the EXACT goal to done; NO-after-restart declines without
  executing; store-validation drops stale entries and prunes the file; crash
  ordering (pop persists before resume; the goal stays honestly paused after a
  lost approval); corrupt set-aside; no-path zero-IO; and the gate_P3 inbound leg
  END-TO-END — ControlCore restart with BOTH in-memory maps gone, inbound
  "YES <code>" resolves the restored ask, goal done, owner card written back
  through the F18 durable linkage.
- `scripts/run_suite.sh`: wired the new test.
- Ledger: D16-sibling residual (under F18) -> FIXED entry with regression check;
  remaining D16-family siblings disclosed (D16 proper TriggerWatcher._fired,
  budget/debounce day-state — all lose toward silence on restart).

## Why (the product fact)
The whole P3 inbound chain was restart-proof EXCEPT its first link: goals are
durable, owner-card linkage is durable (F18), inbound seen-sids are durable —
but the pending map that lets a reply MATCH an ask was in-memory. On a live day
(gate_P3: "inbound reply resolves a real pending ask") any engine restart between
the ask SMS and the owner's reply made the reply resolve NOTHING; the F20
clarifier would then honestly tell the owner "nothing is pending" about an ask
the product itself had sent. Named in STATE.md and the last lap's commit as the
remaining mock-side item under TARGET v7 item 4.

## Eval numbers seen (builder-side, stub)
- Suite 44/44 green.
- OFFICIAL instrument (full pre AND post runs, BOTH lanes): bit-identical at the
  ratchet bests — catch 1.0/1.0, false 0, harm 0, interrupt 0.625/1.0,
  e2e 0.6483, correct 0.8475, recall 1.0; aggregate AND per-persona JSON equal.
- Per-line decision diff pre->post: ZERO in both lanes (default 493 decision
  lines, owner 492 — counts equal pre vs post within each lane; the 1-line lane
  difference exists in the pre runs and predates this change). Goal
  (intent,state) multisets identical; /pending dumps identical modulo fresh-run
  UUIDs; the only new run artifact is the intended data/pending_asks.json.
- Zero spend, zero real-world artifacts, no live legs.

## What's next
- P3 mock-side residuals under item 4 are now EXHAUSTED builder-side: the D16
  sibling is fixed; F19 (live text auth realm) is live-observable only.
- gate_P3 closure still waits on the two human/foreman gates: Omar's OWNER_PHONE
  confirmation (PENDING_FOR_OMAR) and the gate_P3.sh script itself (foreman item
  — it does not exist yet).
- The designed next step remains the K=5 escalation -> TARGET v8 re-aim
  (correct_action_rate has real headroom at 0.8475). D16 proper
  (TriggerWatcher._fired double-fire on restart) is the one remaining
  restart-robustness sibling with a non-silent failure direction.
