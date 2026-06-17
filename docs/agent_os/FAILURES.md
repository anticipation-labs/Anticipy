# FAILURES — failure modes + tripwires (do not repeat)

The immune system. Never erase. Each entry: what broke, why, and the tripwire that catches a relapse.
Deep history: `logs/factory/FAILURES.md` + `logs/factory/FAILURE_MODES.md` + `FOREMAN_STATE.md`.

### F-001 — "Model is blocked/unfunded" assumed without a live test
- **Cause:** hours burned insisting the runtime model was rate-limited/unfunded; never ran a live call.
  It was funded and fast (~½s) the whole time.
- **Tripwire:** before claiming blocked/broken/done, run a check that can FAIL (Constitution rule:
  verify, never assume). Re-verify the model route every session (RESEARCH_LEDGER lane 1).

### F-002 — Sarcasm/vent rode a verb into an autonomous ACT (the cardinal sin)
- **Cause:** decider over-weighted "I'll/I owe/I promised" shapes; a vent clause produced an act/ask.
- **Tripwire:** `safety_mega_eval` must stay BREACHES 0, run independently through the real
  `/owner/ingest` split path with `execute_actions=True`. Any card/act from a vent = breach = revert.

### F-003 — Multi-task decomposition severed the action clause from its vent frame
- **Cause:** splitting a compound line ran "book the room" in isolation, losing the vent marker in a
  sibling clause → a vent produced an act. Builder + tester reported "BREACHES: 0" — a FALSE NEGATIVE
  (the eval was blind to the ingest split path at the time).
- **Tripwire:** a vent marker in ANY clause must suppress/ask-gate the WHOLE breath; never re-evaluate
  clauses independently without carrying line-level emotional context. The hardened floor now covers
  the ingest path. Multi-task decomposition is still WANTED but only with whole-breath vent propagation.

### F-004 — Self-attestation / write-response treated as proof
- **Cause:** trusting a builder's report or a write API's 200 as "done."
- **Tripwire:** no-slop law — independent skeptic + independent read-back of the real artifact. A test
  the builder could have edited proves nothing.

### F-005 — Stale-base worktree patches merged blindly
- **Cause:** integrating a patch built against an old HEAD.
- **Tripwire:** integrator re-applies verified patches to current HEAD and re-runs receipts; stale-base
  patches are design input, not landable code.

### F-006 — Live Twilio spammed Omar (the 31-text history)
- **Cause:** autonomous live-channel sends while Omar was away.
- **Tripwire:** unattended default = channels=mock, `ANTICIPY_INBOUND_POLL_SECONDS=0`, mic OFF. Live
  call/SMS only to Omar's confirmed number, only when supervised/approved. (Engine is currently
  channels=live — see CURRENT_TRUTH watch-item; do not send.)

### F-007 — Message cap shipped as anti-spam (BANNED)
- **Cause:** added a per-day message cap ("NF8") to stop spam. Omar banned caps/throttles.
- **Tripwire:** the brain is the anti-spam. If it spams, fix the inference, never the mouth.

### F-008 — Render-layer scrub mistaken for an engine cure
- **Cause:** premium reskin humanized/deduped card copy at the UI layer; the engine still emits
  rule-name titles, route-tag reasons, `[Anticipy test]` labels, and over-generates asks from one vent.
- **Tripwire:** distinguish "machinery exists / mock integrated" from "live proven." The durable fix is
  engine-side (cadence + over-asking, PRD NF8–NF12/F8–F11).

### F-009 — Loop-for-looping / research taper / grinding a saturated metric
- **Cause:** spawning audit waves on already-green code; broad research with no decision; grinding a
  metric stuck at ceiling.
- **Tripwire:** every cycle moves a real gate or it didn't count. 3 cycles with no receipt → halt + re-aim.
  Research must end in a decision (RESEARCH_LEDGER), not a dump.

### F-010 — Verifying the moat on the wrong path (preview vs reality)
- **Cause:** stress-testing with `execute=false` (preview) showed dropped tasks; the real app path uses
  `execute=true` and caught them. Wasted a cycle on a false alarm.
- **Tripwire:** verify the moat with `execute=true` (the real path the app uses), not preview.
