#!/usr/bin/env bash
# Regression harness — runs the full existing suite. Used as the hard guard:
# after every browser-hand change, this must stay green.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$REPO/engine/.venv/bin/python"
export PYTHONPATH="$REPO/engine"
# CI is ALWAYS free + deterministic: force stub model + mock hands so the .env.local live flags
# (real model / live hands for the running engine) never leak into the test suite. load_local_env
# uses load_dotenv(override=False), so these shell exports win over .env.local.
export ANTICIPY_MODEL_PROVIDER=stub
export ANTICIPY_HANDS_MODE=mock
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
for t in bus workers gateway gateway_retry orchestrator proactive triage triage_clause_scope harmline storesite trigger trigger_notify trigger_persistence duetime decider decision_wall deferred_persistence pending_persistence ask_roundtrip ask_debounce annoyance interrupt_cap frontend_api glassbox_scorecard api_hand browser_hand handoff site_hints agent_proof channels channel_worker inbound memory memory_capture memory_inject memory_maintain memory_infer memory_selfcheck memory_glue owner_mode owner_onboarding owner_ingest_event owner_upload_ingest owner_api_auth public_backend_path messy_proactive_handoff; do
  run "$t" "$PY" "$REPO/engine/scripts/test_$t.py"
done

run owner_app_auth bash "$REPO/scripts/test_owner_app_auth.sh"
run owner_app_product_path bash "$REPO/scripts/test_owner_app_product_path.sh"

run memory_eval_selftest "$PY" "$REPO/engine/scripts/memory_eval.py" --selftest  # instrument soundness (zero model calls)
run proactive_eval_selftest "$PY" "$REPO/engine/scripts/proactive_eval.py" --selftest  # proactive report-card instrument (zero model calls)
run journey_eval_selftest "$PY" "$REPO/engine/scripts/journey_eval.py" --selftest  # journey gauge soundness (zero model calls)

echo "== integration (boot engine/extension; free/stub) =="
run brain_loop      bash "$REPO/scripts/brain_loop.sh"
run hands_loop      bash "$REPO/scripts/hands_loop.sh"
run extension_link  bash "$REPO/engine/scripts/test_extension_link.sh"
run browser_hand_io bash "$REPO/engine/scripts/test_browser_hand.sh"

echo
echo "==== SUITE: $pass passed, $fail failed ====${failed:+  FAILED:$failed}"
[ "$fail" -eq 0 ] && echo "SUITE GREEN" || echo "SUITE RED"
exit "$fail"
