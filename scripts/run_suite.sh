#!/usr/bin/env bash
# Regression harness — runs the full existing suite. Used as the hard guard:
# after every browser-hand change, this must stay green.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$REPO/engine/.venv/bin/python"
export PYTHONPATH="$REPO/engine"
# CI is ALWAYS free + deterministic: force stub model + mock hands + mock channels so the
# .env.local live flags (real model / live hands / LIVE TWILIO for the running engine) never
# leak into the test suite. ANTICIPY_CHANNELS_MODE=mock is load-bearing for SAFETY: without it,
# a live .env.local makes the channels/inbound tests place REAL Twilio calls/SMS in CI.
# load_local_env uses load_dotenv(override=False), so these shell exports win over .env.local.
export ANTICIPY_MODEL_PROVIDER=stub
export ANTICIPY_HANDS_MODE=mock
export ANTICIPY_CHANNELS_MODE=mock
pass=0; fail=0; failed=""

run() {  # name, command...
  local name="$1"; shift
  if "$@" >/tmp/suite_"$name".log 2>&1; then
    echo "  PASS  $name"; pass=$((pass+1))
  else
    echo "  FAIL  $name   (see /tmp/suite_$name.log)"; fail=$((fail+1)); failed="$failed $name"
  fi
}

echo "== unit (free, deterministic) =="
for t in bus workers gateway gateway_retry gateway_tiers orchestrator glassbox_rotation proactive triage triage_clause_scope harmline storesite trigger trigger_notify trigger_persistence follow_up_fires proactive_outreach duetime decider decision_wall deferred_persistence pending_persistence ask_roundtrip ask_debounce annoyance interrupt_cap digest frontend_api glassbox_scorecard api_hand api_readback api_calendar_window token_vault api_vault core_api_mesh browser_hand browser_prompt_injection purchase_guard browser_safety_loop browser_use_cdp browser_available_probe browser_result_on_card navwall form_prepare handoff agent_proof channels channel_worker conversation_relay inbound agent_reply voice memory memory_capture memory_inject memory_maintain memory_infer memory_selfcheck memory_glue memctx_contextpack memctx_reconcile memctx_temporal memctx_salience memctx_privacy memctx_rerank memctx_flywheel memory_remembered review_infer press_go dryrun_preview demo_day readiness mac_mic inputs_same_brain onboarding_profile onboarding_profile_endpoint onboarding_scan onboard_discover onboard_scan clarify owner_mode owner_onboarding owner_ingest_event owner_upload_ingest owner_api_auth endpoint_hardening public_backend_path messy_proactive_handoff phase1_act_routing per_user_hands owner_duplicate_collapse memory_handoff memory_intent_gate autonomy_modes_gate onboarding_frontdoor preview_moat_rescue browser_binary_selfheal directed_question_aside aside_floor_no_model retraction_silenced onboard_people_discovery twentylife_floor_fixes; do
  run "$t" "$PY" "$REPO/engine/scripts/test_$t.py"
done

run owner_app_auth bash "$REPO/scripts/test_owner_app_auth.sh"
run owner_app_product_path bash "$REPO/scripts/test_owner_app_product_path.sh"
run download_route bash "$REPO/scripts/test_download_route.sh"

run safety_mega_eval "$PY" "$REPO/engine/scripts/safety_mega_eval.py"  # 145-line adversarial cardinal-sin/money corpus vs the REAL assembled engine (proactive + press-go); exits 1 on ANY breach
run premium_copy "$PY" "$REPO/factory/bin/check_premium_copy.py" --quiet  # UX_SPEC §4.8/R4.1 banned-strings gate: no dev-console leaks (Owner Mode/Press Go/route tags/raw engine fields) reach the surface; source backstop + raw-JSX check run even without :3000
run wiring_gate "$PY" "$REPO/factory/bin/check_wiring.py" --quiet  # PLUMBING GATE: every engine endpoint has a product caller, every app/api route a UI caller, no orphan modules — "built but never wired" fails; debt is explicit TODO(FIX-NN) lines in factory/wiring_allowlist.txt, burned down via PLANS/ (FIX-19 flips --strict)
run derive_tick "$PY" "$REPO/engine/scripts/test_derive_tick.py"  # TRUE PROACTIVITY (FIX-07): derive→research→ONE-front-door→notify orchestration, fire-once ledger, structural money/confidence floors, stub honesty
run onboard_loop_expansion "$PY" "$REPO/engine/scripts/test_onboard_loop_expansion.py"  # SELF-EXPANDING SCRAPE (FIX-11): layer 2+ follows the discovered graph (real-URL-only, nav-wall refused, consent-gated)
run memory_eval_selftest "$PY" "$REPO/engine/scripts/memory_eval.py" --selftest  # instrument soundness (zero model calls)
run proactive_eval_selftest "$PY" "$REPO/engine/scripts/proactive_eval.py" --selftest  # proactive report-card instrument (zero model calls)
run journey_eval_selftest "$PY" "$REPO/engine/scripts/journey_eval.py" --selftest  # journey gauge soundness (zero model calls)
run owner_test_selftest "$PY" "$REPO/engine/scripts/owner_test.py" --selftest  # P5 finish-line scorer self-proof (zero model calls)
run owner_test_run_selftest "$PY" "$REPO/engine/scripts/owner_test_run.py" --selftest  # P5 RUNNER: a real day through the engine, scored (0 cardinal-sin end to end)
run owner_test_day01 "$PY" "$REPO/engine/scripts/owner_test_run.py" --key "$REPO/factory/owner/expected/day01.json"  # P5 DONE-GATE: a realistic founder day end-to-end -> PASS (0 false-action, money held, catch>=0.70)
run onboarding_e2e_selftest "$PY" "$REPO/engine/scripts/test_onboarding_e2e.py" --selftest  # ONBOARDING DONE-GATE: full flow (permissions->owner/onboard->discover->loop->complete->status) end-to-end + planted-failure battery (empty dossier / skipped complete / no consent / login-walled)
run onboard_web_contract_selftest "$PY" "$REPO/engine/scripts/test_onboard_web_contract.py" --selftest  # ONBOARDING WEB: the front-end forward-finish path is wired (no dead-end when nothing's readable) + retry no-op removed
run create_print_routing_selftest "$PY" "$REPO/engine/scripts/test_create_print_routing.py" --selftest  # CREATE+PRINT routing: physical signs print; digital requests (slack/gmail/website) excluded from the real-PDF path; door-sign happy path intact

echo "== integration (boot engine/extension; free/stub) =="
run brain_loop      bash "$REPO/scripts/brain_loop.sh"
run hands_loop      bash "$REPO/scripts/hands_loop.sh"
run extension_link  bash "$REPO/engine/scripts/test_extension_link.sh"
run browser_hand_io bash "$REPO/engine/scripts/test_browser_hand.sh"

echo
echo "==== SUITE: $pass passed, $fail failed ====${failed:+  FAILED:$failed}"
[ "$fail" -eq 0 ] && echo "SUITE GREEN" || echo "SUITE RED"
exit "$fail"
