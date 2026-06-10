# Last Lap

Lap: 20260610T070648Z
Date: 2026-06-10
Phase: P1 closed -> operating as P2-brain STAGE 2 per TARGET v3 (registered phase_gate still gate_P1)
Slice: GROUNDWORK — the P2 decider (TARGET STAGE-2 items 1-2), live-only, zero paid calls

What changed (product):
- engine/anticipy_engine/proactive/decider.py — NEW. The Track-B-proven ACT/ASK/SILENT
  commitment prompt (overnight/track_b/decider.py seed, no eval lines) at temperature 0
  through the existing ModelGateway (cheap tier, caller "decider"). Hardened parse vs the
  seed: word-boundary regex only, safest-mentioned verdict wins on rambles, and EVERY
  failure path (no key, transport error, empty, unparseable) returns SILENT (ledger F4).
  Glass-box logs "decider" / "decider_error" entries for inspectability.
- engine/anticipy_engine/core/proactive.py — decider wired in as Room 1.5, between triage
  and the memory read. Construction is LIVE-ONLY: a Decider exists iff
  gateway.provider == openrouter (ANTICIPY_MODEL_PROVIDER; the suite forces stub, so CI
  and stub-tier persona evals never construct one); tests inject a stubbed decider via the
  new constructor param. One-way merge rule: decider SILENT -> event dropped (no memory
  read, no goal, no ask); decider ASK + harm-safe -> forced ask (goal paused waiting,
  pending ask registered, reason says "decider:"); decider ACT -> harm-line decides as
  before; harm-line detrimental ASK is FINAL and can never be overridden to act.
  on_event result now carries a "decider" key (None in stub).
- engine/scripts/test_decider.py — NEW, 9 pinned checks, zero model calls: parse
  boundaries/safety order, temp-0 cheap-tier call shape, raising + keyless gateways fail
  SILENT, live-only construction, SILENT-drop / forced-ask / act-defers / money-line-FINAL
  pipeline rules, triage-runs-first, stub-mode-unchanged.
- scripts/run_suite.sh — added decider to the unit list (suite 31 -> 32).

Eval numbers I saw (builder-side, stub tier, run 20260610T070648Z-pre; verify_gate
recomputes everything):
- catch 1.0 / worst 1.0, false_action 0, silent_harm 0, interrupt 1.0625 / 1.5 worst,
  correct_action 0.6788, e2e 0.3427, recall_worst 1.0, worst_persona contractor_luis —
  BIT-IDENTICAL to the ratchet best, which is the hypothesis: the decider must be
  invisible in stub mode. Suite 32/32 green.

Process notes:
- lap_type=groundwork; enables the P2 gate-close lap once the foreman flips
  current_phase/phase_gate to P2/gate_P2.sh. This lap cannot COUNT mechanically:
  catch_rate_worst is at the ratchet ceiling (1.0) on the dev bank, gate_P1 already
  first-closed, and the decider is live-only by design. Keep rides on scans+suite+
  personas green; the treadmill increment is expected and stated in the manifest.
- attempt_gate_close=false (gate_P1 re-run is status, not movement, and strands real
  calendar events per ledger B7).
- NEW ledger F4: the Track-B seed's tolerant parse was substring-over-set — word-interior
  matches ("multitasking" -> ASK) and nondeterministic on multi-verdict rambles. Fixed in
  the product decider; regression pinned in test_decider.py; seed left as read-only history.
- Zero real-world side effects: no gate run, no live model call, stub tier throughout.

Next:
- Foreman: flip current_phase/phase_gate to P2/gate_P2.sh; thresholds already pass
  builder-side on the dev bank, so a gate-close attempt lap is cheap once flipped.
- Live-tier validation of the decider (TIER=FULL lap with ANTICIPY_MODEL_PROVIDER=
  openrouter / Gemini free tier, ledger D18): measure false-ask reduction on the residual
  gray — money-retraction pairs and F3 first-person casual sends are its targets. The
  decider's live behavior is UNPROVEN until then.
- F3 still OPEN for first-person sends (recipient extraction or decider-gray routing).
- Still-open product gaps unchanged: B5/B6 (capture-time act artifact, quoted-title drop),
  B7/B8 (gate env), D16 (restart double-fire).
