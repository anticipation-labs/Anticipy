# Last Lap

Lap: 20260611T093358Z
Date: 2026-06-11
Phase: P3-voice (TARGET v7 — official instrument is the owner lane, eval_env ANTICIPY_OWNER_INGEST=1)
Slice: e2e_completion_rate, ranked work item 1 (stalled expected acts -> completed with
proof). Owner-lane e2e 0.3427 -> 0.4618 builder-side; verify_gate recomputes.

Diagnosis (evidence first, from runs/20260611T085136Z-owner-post3): of 56 caught expected
tasks, 19 stalled. 12 are spine ASK decisions (decider/harm-line territory — out of
scope). 7 were goals whose REAL steps already succeeded WITH proof but whose plan also
carried a junk browse_task/post_to_x step that returns needs_human in mock — parking the
goal "waiting" forever. Junk sources, located in code:
- 5/7: _plan_prompt appended "RELEVANT MEMORY: {context}" for EVERY provider while the
  deterministic stub planner keyword-greps the whole prompt; injected memory lines
  ("...site plan...", "...post-call...") triggered steps the goal never asked for.
- 2/7: bare-substring keyword hits in the spoken line itself ("post-shift" -> "post").

What changed:
- engine/anticipy_engine/core/orchestrator.py (_plan_prompt): the memory section now
  rides only with a real provider — the SAME documented gate the function already used
  for the intent vocabulary ("the stub gateway greps the prompt for keywords"). At the
  deterministic tier the memory reader remains the _memory_resolved_browser_step
  pre-pass, which receives context directly before any model call. Live-provider prompt
  unchanged (pinned).
- engine/anticipy_engine/core/gateway.py (default_stub): the post_to_x trigger is the
  WORD post (\bpost(?:ed|ing|s)?\b(?!-)) — hyphen compounds/prefixes ("post-shift",
  "postpone") no longer plan a social post; "set up" joined the create_event triggers
  (already a gate trigger; a time-anchored "set up X" is a calendar write). The stub is
  also the planner for keyless default boots, so these are product fixes, not eval-only.
- Pins: test_orchestrator.test_stub_plan_ignores_memory_inject (noisy inject must not
  change the stub plan or prompt; live prompt must keep RELEVANT MEMORY),
  test_gateway post-word pins (non-bank sentences), test_owner_ingest_event proof pin
  now accepts the drawer memory_id as the artifact reference for a reminder line whose
  honest plan IS the open-loop write.
- Ledger: F24 (planner memory-noise junk steps park proof-complete goals; FIXED),
  F25 (two suite pins were green only BECAUSE of F24 — pins masked by the bug they
  could not see; FIXED, with the lesson written).

Eval numbers I saw (verify_gate recomputes the official ones):
- Owner lane (OFFICIAL, ANTICIPY_OWNER_INGEST=1, dev bank, stub): e2e 0.3427 -> 0.4618;
  catch 1.0/1.0, false 0, harm 0, interrupt 1.125/1.5, recall 1.0, correct 0.6788 — all
  exactly unchanged. Per-persona e2e: luis 0->0.2857, amara 0.1667->0.5, kayla
  0.3333->0.5, rob 0.3333->0.5; jin/marcus/dana/pri unchanged (no regressions).
- Default lane: e2e 0.3427 -> 0.4618 (shared planner, disclosed); every other aggregate
  exactly at ratchet bests (catch 1.0/1.0, false 0, harm 0, interrupt 0.625/1.0).
- Per-line decision diff pre vs final HEAD: ZERO across 16 persona-days in BOTH lanes —
  the change is plan-layer only; act/ask/silent verdicts untouched.
- Suite 42/42. Zero model calls, zero spend, zero real-world artifacts.

Honest accounting:
- Two unplanned-but-disclosed fixes (manifest addendum): the suite exposed pins that
  passed only via the pollution; fixing them honestly was required to keep the suite
  green at the fixed planner.
- Residuals NOT chased: "on site" spoken text keeps one contractor_luis goal waiting
  (carving that phrase out would be bank-fitting); the stub's empty-plan fallback still
  dumps the whole prompt into browse_task (LESSONS' search-bar shape, now more visible);
  C13 applies — dev-bank numbers are bank-fit, holdout rules gate-grade claims.

Next:
- The remaining e2e headroom on this instrument: 12 expected acts the spine decides ASK
  on (the eval never answers asks) — decider/harm-line territory, needs a foreman call
  on whether chasing it is in-scope vs the F23 money pre-gate interrupt item (TARGET
  ranked item 2).
- F23: owner-lane interrupt 1.125 vs default 0.625 is still entirely the money pre-gate
  on money-flavored vents (fail-safe; foreman ruling queued).
- P3 closure still waits ONLY on OWNER_PHONE confirmation + live Twilio env
  (PENDING_FOR_OMAR item 2).
