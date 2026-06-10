# Last Lap

Lap: 20260610T100043Z
Date: 2026-06-10
Phase: registered P1-closed-loop (gate_P1, already closed) — product work is P2-brain
per TARGET v3 STAGE 2; lap is mechanically dead by D22 (stated in manifest up front)
Slice: BUILD — complete the decider v8+v10 recovery that killed two builders

What changed:
- engine/anticipy_engine/proactive/decider.py + engine/scripts/test_decider.py:
  re-landed the destroyed v8+v10 prompt byte-exact from lap 094944Z's uncommitted.patch
  (blob b7a0f15 = dangling commit ebb0789's content + the C13 docstring scrub). New
  SILENT clauses: speech to a physically present person, reported third-party
  demands/news, own-hands chores, celebration/pep-talk/debrief fragments, bare
  noun-fragment work labels; imperative-vs-"-ing" relay split; money-always-ASK
  hardening. Committed at d788778 BEFORE any live run — the ordering inversion that
  laps 083047Z (D5 revert) and 094944Z (D20 recurrence #2, died mid-live-baseline)
  both failed to do.
- Ledger: lap 094944Z's surviving uncommitted D22 entry committed; D20 recurrence #2
  appended with the binding rule (full-bank live re-baselines do NOT fit a builder
  session; commit first, then at most a targeted single-persona live check).
- Real-world side effects: NONE (no calendar/SMS/browser; live runs hit only the
  Gemini free-tier model API; persona engines isolated on local ports).

Eval numbers I saw (verify_gate recomputes everything):
- Suite: 33/33 green.
- Stub tier, full 8-persona dev bank (run 20260610T100043Z-pre): bit-identical to the
  ratchet bests — catch 1.0 / worst 1.0, false 0, harm 0, interrupt 0.625 avg / 1.0
  worst, recall_worst 1.0, correct_action 0.6788, e2e 0.3427, worst contractor_luis.
  Expected invariance (decider is live-only), not claimed as movement.
- Live probe, 63 self-authored lines (probe_relanded.out): 62/63 — identical to the
  destroyed laps' verification; the one residual is a relay line judged ACT that the
  harm-line's send assessment contains (it can only move ACT->ASK/SILENT, never the
  reverse).
- Live targeted re-run, lawyer_marcus both days (live_lm_score.out): false_action 0
  (the v8 live2 run had 1 — the day02 deliverable-name fragment that drew decider ACT
  -> harm-line draft -> real act), catch 1.0 (8/8), harm 0, interrupt 1.0, recall 1.0.
  The specific regression this slice exists to kill is dead, live.

Honest counting:
- Mechanically dead lap as pre-registered: stub primary catch_rate_worst sits at the
  ratchet ceiling 1.0, gate_P1 already first-closed, TARGET.md on disk still v3 (D22).
  Treadmill burns one tick toward the designed foreman escalation. The product value
  (live false-action fix durable on HEAD, no longer one `git gc` from oblivion) is
  invisible to the stub scoreboard by design.

Next:
- Foreman, priority 1 (D22): actually write TARGET v4 — current_phase: P2-brain,
  phase_gate: factory/gates/gate_P2.sh. gate_P2 thresholds hold at stub on HEAD, so
  the first post-flip lap with attempt_gate_close=true should close P2 mechanically.
- Foreman, priority 2 (D20 x2): make verify_gate FAIL (not WARN) when uncommitted.patch
  touches product files, or auto-WIP-commit at session end — two firings now.
- Next builder/foreman: full 8-persona LIVE bank post-v10 (only lawyer_marcus +
  the older contractor_luis/doctor_amara probes are live-proven); 429-pressure
  behavior; F6 (triage live tiebreak fails open, deliberate defer); B6 (quoted-title
  drop); B7/B8 (gate env); D16 (restart double-fire); ask-dedupe for restated
  reminders.
