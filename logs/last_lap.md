# Last Lap

Lap: 20260611T085136Z
Date: 2026-06-11
Phase: P2-brain CLOSED -> TARGET v6 STAGE B (Owner Action Engine execution path)
Slice: F21 FIXED on the main path — the bare reported promise ("Sam needs the revised
decking before Friday; I told him I'd send it.") is now CAUGHT by the spine and lands
as a real pending ask. Root cause was in code: triage._CONDITIONAL_VENT's bare \bi'd\b
alternative consumed any reported-promise clause as a counterfactual vent at clause
scope before positives ran. Aimed at catch_rate_worst; pre-registered honestly that
the OFFICIAL metric CANNOT move (saturated 1.0 on the dev bank AND the last judged
holdout per the 041654Z verdict, counts only) — the catch movement lives off-bank.

What changed:
- engine/anticipy_engine/proactive/triage.py: new clause-scoped REPORTED-PROMISE
  shape (_reported_promise + _RP_* regexes/sets): first-person matrix frame
  ("I told/promised <person>", "I said") + irrealis complement (I'd/I would/I'll/
  I will) + open-vocabulary base-form committed verb + content floor. It BOTH cancels
  the bare-I'd vent reading in actionable() (precedent: _TIME_ANCHOR cancels _HEDGE)
  and counts as a positive in _clause_positive (after the vent_frame gate, so open
  sarcasm frames still win). Junk bound: structural anchors + closed-class
  deny-direction checks — participle backshift ('d=had), negation/hedge/vow verb-slot
  words, deferral heads/idioms, vow heads, unanchored be-vows, tag-question retorts,
  wish-regret, promised-myself, habitual prefixes, resolved/failed complements
  ("...and I did", tail-scoped "but"), joke markers. An adversarial probe session
  (instructed to refute the junk bound, 23 families) drove the deny set; its
  surviving residuals are disclosed in FAILURE_MODES (unmarked hyperbole fails
  toward ask).
- engine/scripts/test_triage_clause_scope.py: +30 reported-promise pins (allow AND
  every deny class; 187 pins total). New pin names verified absent from the dev bank
  (the one collision found, a bank proper noun, was renamed before commit).
- engine/scripts/test_owner_ingest_event.py: the F21 pin flipped exactly per the
  ledger's written regression check — PROMISE_SILENT renamed REPORTED_PROMISE,
  decision ignore -> ask with a real ask_id, record open -> waiting, /pending now
  carries it (count 2 -> 3). The F17 one-brain contract is unchanged: this is the
  SPINE's verdict, not a regex side-door.

Eval numbers I saw (verify_gate recomputes the official ones):
- Suite: 42/42 green (187 clause-scope pins, 0 smart calls).
- Default lane, dev bank, stub: -pre vs final HEAD (-post3) per-line decision diff =
  ZERO changes across 493 lines x 16 persona-days; aggregates bit-identical to
  ratchet bests (catch 1.0/1.0, false 0, harm 0, interrupt 0.625/1.0, recall 1.0,
  correct 0.6788, e2e 0.3427).
- Owner lane (ANTICIPY_OWNER_INGEST=1): same — zero per-line diffs, aggregates
  exactly the documented owner numbers (interrupt 1.125/1.5 = the F23 money
  pre-gate delta, untouched).
- The rule is provably inert on the dev bank; its only behavior change is off-bank
  (the F21 family, pinned). Zero model calls, zero spend, zero real-world artifacts.

Honest accounting:
- This is the 5th lap since last_movement_lap with the primary metric saturated on
  every instrument a builder may read. If the scoreboard rules it dead, the designed
  K=5 treadmill escalation fires and the foreman re-aims — that is the system
  working, not a failure of this lap. attempt_gate_close=false (P2 already closed).
- Disclosed risk: a NEW ask shape carries blind holdout interrupt risk
  (interrupt_cost_worst 3.0 at zero margin on two holdout personas). The deny
  battery + zero-diff dev bar are the defense; the next judge holdout run rules.

Next:
- F23 foreman ruling (money pre-gate asks on money-flavored vents — the whole
  owner-lane interrupt delta).
- The /owner/ingest execute_actions=false preview door still uses the regex-only
  extractor (needs the one-brain treatment before any non-executing door ships).
- P3 closure waits ONLY on OWNER_PHONE confirmation + live Twilio env
  (PENDING_FOR_OMAR item 2); F20 clarification reply and D16 pending-map
  persistence remain queued for live ops.
- Foreman: the primary instrument is saturated (dev AND holdout at 1.0 catch) —
  TARGET needs a new measurable aim (bank v2 / holdout red-pen / live-tier
  instrument / e2e or interrupt as primary).
