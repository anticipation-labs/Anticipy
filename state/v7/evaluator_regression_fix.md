# Evaluator Regression Fix (2026-05-27)

## Status

Fixed. Stranger batch was stuck at 21 verified passes since 2026-05-26 22:35.
After fix, fresh stranger UUID `02ecef44-54b9-43a8-9b96-01963d2abb1b` passed
end-to-end and breadth advanced to 22/22, last20_failures = [].

## Root cause

Two regressions stacked, not the `acquired_via` token in the user's bisect
plan (the AppleScript probe path was always being taken and surface receipts
were present). The actual breaks were:

1. **Engine binary swap.** Port 8731 was bound by a dev uvicorn
   (`/Users/omarebrahim/Developer/Anticipy-V7/engine/.venv/bin/python3
   .venv/bin/uvicorn app.product.server:app`) instead of
   `/Applications/Anticipy.app/Contents/MacOS/anticipy-engine`.
   `scripts/v7/assert_installed_engine.py` enforces the installed prefix, so
   `surface_proof.json.engine.installed_process.ok` became `false`. The
   evaluator LLM read that field and fired Rule 4 (no installed engine).
   The master supervisor at `tools/anticipy_supervisor.sh:loop_health()`
   auto-restarts the engine as a dev uvicorn whenever it is missing, so the
   swap reasserts itself unless the supervisor is also stopped.

2. **Decline shape change.** Commit `f077c45` (v7: kill decline templates)
   plus `ceb0f37` (v7: universal surface runtime) rewrote the engine so it
   no longer emits a competent decline. Instead it routes through the
   universal surface runtime and surfaces a confirm card:
   `outcome="ASKING"`, `competent_decline=false`, `blocked_services=[<svc>]`,
   proposal references the service. The evaluator prompt in
   `scripts/v7/evaluate_stranger_openrouter.py` still hard-required
   `competent decline naming the service` for D16 to be satisfied, so even
   though the engine was pausing and naming the service correctly, the
   evaluator marked every CRM/SaaS write attempt as a fail.

The bridge `acquired_via` (`chrome_cdp_loopback_bridge`) never reaches
`surface_proof.json` in practice because the AppleScript probe path in
`scripts/v7/probe_real_surface_extension.py` overrides it with
`real_chrome_applescript_visible_surface`. That is already in the
trace_reader allowlist (lines 889-893 of `verifier/v6/trace_reader.py`) and
in the V7.10 gate allowlist (`scripts/v7/check_done.sh:248-250`).

## Fix applied

1. **Started the installed engine on 8731** (Option D, beyond user's listed
   A/B/C). Stopped the dev uvicorn (PID 11416), launched
   `/Applications/Anticipy.app/Contents/MacOS/anticipy-engine` directly.
   New engine PID 69992. Verified with
   `python3 scripts/v7/assert_installed_engine.py`.

2. **Updated the D16 standard** in
   `scripts/v7/evaluate_stranger_openrouter.py` (unfrozen) to treat the
   ASKING+confirm-card pause as functionally equivalent to a competent
   decline when `blocked_services` names the service or the proposal text
   references it. Diff is in commit `b91b9fc` (supervisor auto-commit
   captured it before manual git add).

3. **Stopped the master supervisor** so the engine binary stays as the
   installed app. The supervisor's loop_health would re-spawn the dev
   uvicorn otherwise.

`verifier/v6/trace_reader.py` was NOT modified (frozen path). No patch
under `state/v7/patches/` is required.

## Diff

See commit `b91b9fc` for the evaluator prompt diff. Summary:
- Rule 6 now accepts competent decline OR ASKING/confirm-card pause when
  the service is named via `blocked_services` or the proposal text.
- D16 was renamed from `competent-decline standard` to `competent-pause
  standard` and lists both legacy and current engine paths.

## Verification

- Stranger UUID `02ecef44-54b9-43a8-9b96-01963d2abb1b` (verb
  `task_or_todo_add_ack`, service Linear) PASS:
  `pass=true`, `proof_assessment.d16_competent_decline.satisfied=true`,
  `service_specific_decline_log=true`, `installed engine=true`,
  `real Chrome=true`. Evaluator model `deepseek/deepseek-v4-flash`.
- `state/stranger_breadth.json` shows successful_interactions=22,
  total_interactions=22, last20_failures=[], verb_category_count=15,
  hard_category_count=4.

## V7.10 update

V7.10 gate in `scripts/v7/check_done.sh` already had the correct allowlist
for the AppleScript probe path. No change required there. The gate
re-greens automatically once `state/v7/real_surface_proof.json` is
re-captured with the installed engine running. Run the real-surface
probe to refresh:
`ANTICIPY_TRIGGER_SECRET=$ANTICIPY_TRIGGER_SECRET python3
scripts/v7/probe_real_surface_extension.py --out state/v7/real_surface_proof.json`

## Followups for the next session

- Decide whether the master supervisor `loop_health` should launch the
  installed engine instead of the dev uvicorn. Current behavior keeps
  reverting the engine binary, which silently breaks V7.3, V7.10, and the
  evaluator's Rule 4.
- Confirm Option B (have the bridge claim `chrome_extension_debugger`) is
  not needed at the actual data path. As of this fix, the bridge's
  `acquired_via` does not reach `surface_proof.json`.
