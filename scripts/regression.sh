#!/usr/bin/env bash
# V7 regression guard.
#
# This is not the done checker. It only verifies that the repo and production
# are eligible for a V7 cycle: production parity, no closed fixture libraries,
# no verifier credential backdoors, no banned runtime models, and required V6
# helper entry points present.

set -uo pipefail

REPO="${REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"
SITE_URL="${SITE_URL:-https://www.anticipy.ai}"
REGRESSION_SKIP_DEPLOY_PARITY="${REGRESSION_SKIP_DEPLOY_PARITY:-0}"
cd "$REPO"
if [ "${V6_DEFER_WORKTREE_SHIP:-0}" = "1" ] && printf '%s\n' "$REPO" | grep -q '/\.worktrees/'; then
  REGRESSION_SKIP_DEPLOY_PARITY=1
fi

RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
LOG_DIR="state/regression-$RUN_ID"
mkdir -p "$LOG_DIR"

fails=0
DEPLOY_PARITY_OK=false
record_fail() {
  echo "FAIL: $1" | tee -a "$LOG_DIR/fails.log"
  fails=$((fails + 1))
}

record_pass() {
  echo "PASS: $1" | tee -a "$LOG_DIR/passes.log"
}

check_contract() {
  if [ ! -f ANTICIPY_V7.md ]; then
    record_fail "ANTICIPY_V7.md missing"
    return
  fi
  grep -q "public downloadable user-device engine" ANTICIPY_V7.md \
    && grep -q "No completion claim without gates" ANTICIPY_V7.md \
    && record_pass "V7 correction file present" \
    || record_fail "ANTICIPY_V7.md does not contain the V7 public product target"
}

check_deploy_parity() {
  if [ "$REGRESSION_SKIP_DEPLOY_PARITY" = "1" ]; then
    record_pass "deploy parity skipped for isolated worktree success test"
    return
  fi
  local live local_head origin_head
  live=$(curl -sS "$SITE_URL/api/app/state" | tee "$LOG_DIR/app-state.json" | jq -r '.build.commit // .commit // .deployedCommit // empty' || echo "")
  local_head=$(git rev-parse HEAD)
  origin_head=$(git ls-remote origin refs/heads/main | awk '{print $1}')
  if [ "${live:0:7}" = "${local_head:0:7}" ] && [ "${origin_head:0:7}" = "${local_head:0:7}" ]; then
    DEPLOY_PARITY_OK=true
    record_pass "deploy parity live=${live:0:7} local=${local_head:0:7}"
  else
    record_fail "deploy parity mismatch live=$live local=$local_head origin=$origin_head"
  fi
}

check_public_dmg() {
  if [ "$DEPLOY_PARITY_OK" != true ]; then
    record_pass "public DMG hash deferred until deploy parity is green"
    return
  fi
  # The manifest moved to the website repo on 2026-09-04. Look there; only call
  # it missing if the website checkout has no manifest either.
  . "$(git rev-parse --show-toplevel)/scripts/website_repo.sh"
  MANIFEST="$(website_repo --optional)/state/builds/manifest.json"
  if [ ! -f "$MANIFEST" ]; then
    record_fail "state/builds/manifest.json missing (looked in the website repo; set WEBSITE_REPO)"
    return
  fi
  local expected live_sha
  expected=$(jq -r '.latest_sha256 // empty' "$MANIFEST")
  if [ -z "$expected" ]; then
    record_fail "manifest latest_sha256 empty"
    return
  fi
  live_sha=$(curl --max-time 240 -fsSL "$SITE_URL/dl/Anticipy_1.0.0_aarch64.dmg" | shasum -a 256 | awk '{print $1}') \
    || { record_fail "could not download public DMG for hashing"; return; }
  [ "$live_sha" = "$expected" ] \
    && record_pass "public DMG SHA matches manifest" \
    || record_fail "public DMG SHA mismatch live=$live_sha expected=$expected"
}

check_no_closed_fixtures() {
  local bad=0
  for d in verifier/fixtures/verbs verifier/fixtures/intents verifier/fixtures/transcripts; do
    if [ -e "$d" ]; then
      echo "$d" >> "$LOG_DIR/closed-fixtures.txt"
      bad=1
    fi
  done
  [ "$bad" -eq 0 ] \
    && record_pass "closed V5 fixture directories absent" \
    || record_fail "closed V5 fixture directories still present"
}

check_no_verifier_backdoors() {
  local out="$LOG_DIR/verifier-backdoors.txt"
  : > "$out"
  if [ -d verifier ]; then
    rg -n "IMAP|imap|SUPABASE_SERVICE|service_role|service role|GOOGLE_CALENDAR|SLACK_BOT|BOT_TOKEN|NOTION_API|app password" verifier -S \
      > "$out" || true
  fi
  if [ -s "$out" ]; then
    record_fail "verifier credential backdoor references remain"
  else
    record_pass "no verifier credential backdoor references"
  fi
}

check_runtime_models() {
  local out="$LOG_DIR/banned-runtime-models.txt"
  : > "$out"
  rg -n "anthropic/claude|claude-sonnet|claude-opus|gpt-4|gpt-5|gemini-pro" \
    engine/app src/app src/lib -S > "$out" || true
  if [ -s "$out" ]; then
    record_fail "runtime banned model references remain"
  else
    record_pass "no banned runtime model references"
  fi
}

check_v6_helpers() {
  local missing=0
  for f in \
    scripts/orchestrate_v6.sh \
    scripts/v6/dispatch_planner.sh \
    scripts/v6/dispatch_worker.sh \
    scripts/v6/dispatch_judge.sh \
    scripts/v6/dispatch_stranger_generator.sh \
    scripts/v6/dispatch_stranger_driver.sh \
    scripts/v6/dispatch_evaluator.sh \
    scripts/v6/cost_audit.py \
    scripts/v6/transcript_audit.py \
    scripts/v6/breadth_audit.py \
    scripts/v6/check_done.sh \
    scripts/v6/ship_if_bundled.sh \
    verifier/v6/trace_reader.py; do
    if [ ! -f "$f" ]; then
      echo "$f" >> "$LOG_DIR/missing-v6-helpers.txt"
      missing=1
    fi
  done
  [ "$missing" -eq 0 ] \
    && record_pass "V6 helper entry points present" \
    || record_fail "V6 helper entry points missing"
}

check_v7_helpers() {
  local missing=0
  for f in \
    scripts/v7/check_done.sh \
    scripts/v7/orchestrate_v7.sh \
    ANTICIPY_V7.md \
    contracts/PRODUCT_TARGET.md \
    contracts/USER_DEVICE_ENGINE.md \
    contracts/INPUT_MODES.md \
    contracts/INFERENCE.md \
    contracts/CLEAN_ROOM_PUBLIC_INSTALL.md \
    scripts/v7/assert_installed_engine.py \
    scripts/v7/probe_input_modes.py \
    scripts/v6/probe_mp3_eval_path.py; do
    if [ ! -f "$f" ]; then
      echo "$f" >> "$LOG_DIR/missing-v7-helpers.txt"
      missing=1
    fi
  done
  [ "$missing" -eq 0 ] \
    && record_pass "V7 helper entry points present" \
    || record_fail "V7 helper entry points missing"
}

check_installed_engine_surface() {
  if python3 scripts/v7/assert_installed_engine.py > "$LOG_DIR/installed-engine.json" 2> "$LOG_DIR/installed-engine.err"; then
    record_pass "port 8731 is served by installed user-device engine"
  else
    record_fail "port 8731 is not served by installed user-device engine"
  fi
}

check_contract
check_deploy_parity
check_public_dmg
check_no_closed_fixtures
check_no_verifier_backdoors
check_runtime_models
check_v6_helpers
check_v7_helpers
check_installed_engine_surface

ln -sfn "$(basename "$LOG_DIR")" state/regression-latest

if [ "$fails" -ne 0 ]; then
  echo "regression: FAIL ($fails)"
  exit 1
fi

echo "regression: PASS"
exit 0
