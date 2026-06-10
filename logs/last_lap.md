# Last Lap

Lap: 20260610T102837Z
Date: 2026-06-10
Phase: registered P1-closed-loop (gate_P1, already closed) — product work is P2-brain
per TARGET v3 STAGE 2; lap is mechanically dead by D22 (stated in manifest up front;
treadmill 3->4 is the designed escalation toward the foreman flipping TARGET to v4)
Slice: BUILD — F7 residual #1: the gateway ignored the server's own 429 retry guidance
(the live brain is Gemini FREE TIER; blind retries during a quota window are themselves
quota-counting requests that deepen the outage)

What changed (commit 6efcad7, code-first per the D20 binding rule):
- engine/anticipy_engine/core/gateway.py: on 429, _retry_hint_seconds reads the
  server's stated wait — Retry-After header (delta-seconds; OpenRouter's documented
  signal) > google.rpc.RetryInfo retryDelay in the error body (proto3 Duration string
  like "21s"/"15.002899939s", defensive {seconds,nanos} fallback; handles the
  one-element-ARRAY wrapper the Gemini OpenAI-compat endpoint emits) > a
  "retry in Ns" phrase in error.message (the only signal confirmed surviving the
  compat layer). Hint <= 8s (RETRY_HINT_INLINE_CAP_S): sleep hint + 0.25s margin
  inline, still bounded by the 4-attempt loop. Hint > 8s: return "" after ONE request
  — fast-fail into the existing Decider UNAVAILABLE -> 75s defer path (F7), which
  outlasts per-minute windows, instead of burning ~13s and 3 more quota-counting
  blind retries against a closed window. No hint (the detail-less 429 variant) and
  all 5xx: byte-identical blind backoff. Hints recorded on gateway.calls for
  postmortems. New `transport=` injection point so tests never touch the network.
- engine/scripts/test_gateway_retry.py (NEW, suite 33->34; registered in
  scripts/run_suite.sh): MockTransport + recorded sleep — pins the parse ladder
  (header > RetryInfo str/obj > message; array wrap; detail-less/garbage -> None,
  never raises), short-hint inline recovery, long-hint single-request fast-fail,
  bounded loop under sustained short hints, 5xx hint-blindness, and the F7
  end-to-end (long-hint 429 storm -> Decider UNAVAILABLE after exactly one request).
- Research-first (per contract): two parallel web sweeps established the real shapes
  before any code — Gemini has NO reliable Retry-After header; per-DAY exhaustion can
  return a misleading "1s" retryDelay (contained: the attempt bound makes a bad short
  hint cost at most 3 extra spaced retries before the honest "" -> defer path).
- Real-world side effects: NONE beyond 5 cheap live model calls (healthy-path probe,
  invented lines). No 429 was induced (would poison tonight's shared free-tier quota
  for verify_gate's own live runs); the deterministic pins stand in.

Eval numbers I saw (verify_gate recomputes everything):
- Suite: 34/34 green (was 33; +test_gateway_retry).
- Stub tier, full 8-persona dev bank (run 20260610T102837Z-pre): bit-identical to the
  ratchet bests — catch 1.0 / worst 1.0, false 0, harm 0, interrupt 0.625 avg / 1.0
  worst, recall_worst 1.0, correct_action 0.6788, e2e 0.3427, worst contractor_luis.
  Expected invariance (the change only engages on live 429 responses), not movement.
- Targeted live check (healthy path, 5 invented lines, post-commit): 5/5 expected
  verdicts (delegated reminder ACT, money ASK, -ing/past-tense/vent SILENT);
  hints_seen=[] — the hint path never engages on healthy replies.

Honest counting:
- Mechanically dead lap as pre-registered (D22): stub primary catch_rate_worst at the
  ratchet ceiling 1.0, gate_P1 already first-closed, TARGET.md on disk still v3.
  Treadmill burns one tick (3->4) toward the designed foreman escalation. The product
  value — under real quota pressure the engine now waits exactly as long as the server
  says (short windows recover INLINE with a verdict, long windows stop hammering after
  one request and defer honestly) — is live-tier catch protection the stub scoreboard
  cannot see, by design.

Next:
- Foreman, priority 1 (D22, unchanged, third lap running): actually write TARGET v4 —
  current_phase: P2-brain, phase_gate: factory/gates/gate_P2.sh. gate_P2 thresholds
  hold at stub on HEAD, so the first post-flip lap with attempt_gate_close=true should
  close P2. One more dead lap reaches K=5 and forces this via ESCALATION.
- Foreman, priority 2 (D20 x2, unchanged): verify_gate should FAIL when
  uncommitted.patch touches product files, or auto-WIP-commit at session end.
- Next builder/foreman: full 8-persona LIVE bank post-v10 (foreman/verify_gate run,
  not a builder session — D20); deferred-queue persistence across engine restarts
  (F7 residual, D16 family — now the LAST F7 residual besides live observation);
  F6 (triage live tiebreak fails open, deliberate defer); B6 (quoted-title drop);
  B7/B8 (gate env); ask-dedupe for restated reminders.
