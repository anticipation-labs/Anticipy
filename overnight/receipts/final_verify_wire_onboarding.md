# FINAL VERIFY — wire + onboarding build (W1–W4)

Verified on branch `hoe/build` at HEAD `ca53636` (W4). Re-ran the un-gameable gates
from a clean tree; did NOT touch the live engine on :8787 or drive live Chrome.

## Suite — `bash scripts/run_suite.sh`
```
==== SUITE: 118 passed, 8 failed ====  FAILED: owner_mode owner_ingest_event owner_upload_ingest messy_proactive_handoff retraction_silenced owner_app_product_path owner_test_day01 create_print_routing_selftest
```
- **118 passed / 8 failed** (SUITE RED is expected — the 8 are known-open, not regressions).
- **FAILED name-set vs baseline (loop_state, WATCHDOG.md L51 = 113/9):** SHRANK by exactly one.
  - baseline 9-set: owner_mode · owner_ingest_event · owner_upload_ingest · messy_proactive_handoff · **onboarding_frontdoor** · retraction_silenced · owner_app_product_path · owner_test_day01 · create_print_routing_selftest
  - current 8-set is **byte-identical minus `onboarding_frontdoor`** (W3 re-pointed it to the Phase-Zero layout → GREEN). No new name appeared. Set did NOT grow.
- New GREEN test `onboarding_firstcards_e2e_selftest` (W4) added and passing — proves first cards derived from the inhale land on the board, with a planted corrupt-inhale battery (walled/empty → no fake cards).

## Wiring — `engine/.venv/bin/python factory/bin/check_wiring.py`
```
WIRING: CLEAN (66 endpoints / 48 routes / 100 modules checked, 36 allowlisted incl. 20 TODO-debt)
```
- **CLEAN.** **20 TODO-debt seams** remain (down from baseline 35): W1 wired 6 severed seams (resolve-loop, download/anticipy-execute, trigger/tick, digest, derive, owner/stop), W2 retired 9 dead browser control-plane arms into the permanent SUPERSEDED-by-/agent/run class (ws/state·reload·browse·observe·act, agent/act·reset·events·judge). 35 − 6 − 9 = 20.
- The allowlist file has 23 TODO-tagged lines; 3 are section/convention comments, so exactly 20 map to flagged seams — no inflation.

## Honest read of what onboarding + small-component wiring now genuinely does vs what's still open
Onboarding is now a real end-to-end spine that produces a payoff, not just plumbing: a
throwaway engine on its own ephemeral port is driven land → consent → connect → INHALE →
complete over real HTTP, and the memory drawers fill with FIRST CARDS carrying tokens that
exist ONLY in the inhaled text (un-gameable extractor, invents nothing); corrupt inhales
produce no fake cards. W1 closed 6 severed UI seams into PhaseZeroApp (resolve-loop, download
button, tick, digest, derive/anticipate-now, owner/stop). What is STILL open and honestly not
done: Call stages 4/6/8 remain stubs (owner_mode / owner_ingest_event / owner_upload_ingest /
owner_app_product_path / owner_test_day01 fail); the real OAuth-consent path is still a gated
stub (no live Google consent); FIX-08 remembered-review UI is unwired (approve/dryrun/dryrun-day
routes have no button); FIX-17 owner session/auth is script-only (login UI never calls it);
FIX-02 deep-research surface exists with zero UI callers; create_print routing selftest and
messy_proactive_handoff / retraction_silenced remain in the failing set. Net: the onboarding
promise holds in a hermetic proof and the quick-win UI seams are wired, but the Call arm, real
auth/consent, and the remembered-review / research surfaces are genuinely unbuilt.
