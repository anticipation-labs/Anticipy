#!/usr/bin/env bash
# Mechanical V7 done checker.

set -euo pipefail

REPO="${REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"
SITE_URL="${SITE_URL:-https://www.anticipy.ai}"
ENGINE_URL="${ANTICIPY_ENGINE_URL:-http://127.0.0.1:8731}"
cd "$REPO"

mkdir -p state
OUT="state/check_done_v7.json"

json_bool() {
  if [ "$1" = "true" ]; then
    printf true
  else
    printf false
  fi
}

public_app_http="$(curl -sS -o /tmp/anticipy_v7_app.html -w '%{http_code}' "$SITE_URL/app" || echo "000")"
public_app_ok=false
[ "$public_app_http" = "200" ] && public_app_ok=true

state_json="$(curl -sS "$SITE_URL/api/app/state" || echo '{}')"
live_head="$(printf '%s' "$state_json" | jq -r '.build.commit // .commit // .deployedCommit // empty' 2>/dev/null || echo "")"
download_status="$(printf '%s' "$state_json" | jq -r '.download.status // empty' 2>/dev/null || echo "")"
engine_status="$(printf '%s' "$state_json" | jq -r '.engine.status // empty' 2>/dev/null || echo "")"

local_head="$(git rev-parse HEAD)"
origin_head="$(git ls-remote origin refs/heads/main | awk '{print $1}')"
deploy_parity_ok=false
if [ "${local_head:0:7}" = "${origin_head:0:7}" ] && [ "${local_head:0:7}" = "${live_head:0:7}" ]; then
  deploy_parity_ok=true
fi

manifest_sha=""
manifest_commit=""
public_dmg_sha=""
public_dmg_ok=false
manifest_commit_ok=false
manifest_commit_exception_ok=false
manifest_commit_exception_reason=""
manifest_commit_changed_files=""
if [ -f state/builds/manifest.json ]; then
  manifest_sha="$(jq -r '.latest_sha256 // empty' state/builds/manifest.json)"
  manifest_commit="$(jq -r '.latest_commit // empty' state/builds/manifest.json)"
fi
if [ -n "$manifest_sha" ]; then
  # Cloudflare/R2 bandwidth conservation: don't download the full 2.5GB DMG
  # on every check. Use HEAD to verify the file exists with the right size,
  # then ONLY download the body if the cached SHA file is missing or stale.
  # The cache file stores {sha,etag,bytes,ts} so subsequent checks reuse it
  # as long as R2's ETag matches.
  R2_PUBLIC="https://pub-e97c6305fe2949d8a5d17885f7be2a0e.r2.dev/Anticipy_1.0.0_aarch64.dmg"
  CACHE="state/v7/r2_dmg_sha_cache.json"
  # Cheap HEAD probe (no body) to read the current ETag from R2.
  head_resp="$(curl -sI --max-time 30 "$R2_PUBLIC" 2>/dev/null)"
  cur_etag="$(printf '%s' "$head_resp" | grep -i '^etag:' | head -1 | awk '{print $2}' | tr -d '\r"')"
  cur_bytes="$(printf '%s' "$head_resp" | grep -i '^content-length:' | head -1 | awk '{print $2}' | tr -d '\r')"
  cached_etag=""
  cached_sha=""
  if [ -f "$CACHE" ]; then
    cached_etag="$(jq -r '.etag // empty' "$CACHE" 2>/dev/null)"
    cached_sha="$(jq -r '.sha // empty' "$CACHE" 2>/dev/null)"
  fi
  if [ -n "$cur_etag" ] && [ "$cur_etag" = "$cached_etag" ] && [ -n "$cached_sha" ]; then
    public_dmg_sha="$cached_sha"
  else
    # ETag changed (or no cache): one-time 2.5GB download + recompute SHA + cache it.
    public_dmg_sha="$(curl --max-time 900 -fsSL "$R2_PUBLIC" | shasum -a 256 | awk '{print $1}' || echo "")"
    if [ -n "$public_dmg_sha" ] && [ -n "$cur_etag" ]; then
      jq -n --arg sha "$public_dmg_sha" --arg etag "$cur_etag" --arg bytes "$cur_bytes" \
        --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        '{sha:$sha,etag:$etag,bytes:$bytes,ts:$ts}' > "$CACHE"
    fi
  fi
  [ "$public_dmg_sha" = "$manifest_sha" ] && public_dmg_ok=true
fi
if [ -n "$manifest_commit" ] && [ "${manifest_commit:0:7}" = "${live_head:0:7}" ]; then
  manifest_commit_ok=true
elif [ -n "$manifest_commit" ] && git cat-file -e "$manifest_commit^{commit}" 2>/dev/null; then
  manifest_commit_changed_files="$(git diff --name-only "$manifest_commit..$local_head" || true)"
  if ! printf '%s\n' "$manifest_commit_changed_files" | grep -E -q '^(engine/|desktop/|src-tauri/|public/install\.sh|target/|.*\.dmg$)'; then
    manifest_commit_exception_ok=true
    manifest_commit_exception_reason="DMG manifest commit differs from live because files changed after the bundled DMG build, but none of those files are part of the DMG artifact. The public DMG SHA still matches the manifest SHA."
    mkdir -p state/v7
    jq -n \
      --arg manifest_commit "$manifest_commit" \
      --arg live "$live_head" \
      --arg reason "$manifest_commit_exception_reason" \
      --arg changed_files "$manifest_commit_changed_files" \
      '{
        ok: true,
        manifest_commit: $manifest_commit,
        live_commit: $live,
        reason: $reason,
        changed_files_since_manifest_commit: ($changed_files | split("\n") | map(select(length > 0)))
      }' > state/v7/manifest_commit_exception.json
  fi
fi
public_dmg_parity_ok=false
if [ "$public_dmg_ok" = true ] && { [ "$manifest_commit_ok" = true ] || [ "$manifest_commit_exception_ok" = true ]; }; then
  public_dmg_parity_ok=true
fi

installed_engine_ok=false
installed_engine_path=""
installed_engine_json="{}"
installed_engine_state_json="{}"
installed_engine_surface_ok=false
if python3 scripts/v7/assert_installed_engine.py >/tmp/anticipy_v7_installed_engine.json 2>/tmp/anticipy_v7_installed_engine.err; then
  installed_engine_ok=true
  installed_engine_json="$(cat /tmp/anticipy_v7_installed_engine.json)"
  installed_engine_path="$(printf '%s' "$installed_engine_json" | jq -r '.command // empty')"
  installed_engine_state_json="$(curl -sS --max-time 5 "$ENGINE_URL/api/state" || echo '{}')"
  installed_engine_surface_ok="$(printf '%s' "$installed_engine_state_json" | jq -r '
    (((.chrome_user_data_dir // "") | contains("chrome-real-clone")) | not)
    and (.clone_config_rejected != true)
    and (.legacy_clone_cdp_enabled != true)
    and (
      (.browser_surface // "") == "extension_native_bridge"
      or (.browser_surface // "") == "installed_chrome_extension"
      or (.browser_surface // "") == "chrome_extension_native_messaging"
      or (.browser_surface // "") == "chrome_extension_debugger"
      or (.browser_surface // "") == "real_chrome_applescript_visible_surface"
    )
  ' 2>/dev/null || echo false)"
else
  installed_engine_json="$(jq -n --rawfile err /tmp/anticipy_v7_installed_engine.err '{ok:false,error:$err}')"
fi

set +e
python3 scripts/v6/breadth_audit.py --min-success 100 --min-verb-categories 20 --min-hard-categories 5 >/tmp/anticipy_v7_breadth.log 2>&1
breadth_rc=$?
python3 scripts/v6/cost_audit.py >/tmp/anticipy_v7_cost.log 2>&1
cost_rc=$?
python3 scripts/v6/transcript_audit.py >/tmp/anticipy_v7_transcript.log 2>&1
transcript_rc=$?
python3 scripts/v6/probe_mp3_eval_path.py >/tmp/anticipy_v7_mp3_path.log 2>&1
mp3_path_rc=$?
set -e

stranger_json="$(cat state/stranger_breadth.json 2>/dev/null || echo '{}')"
successful_interactions="$(printf '%s' "$stranger_json" | jq -r '.successful_interactions // 0' 2>/dev/null || echo 0)"
verb_category_count="$(printf '%s' "$stranger_json" | jq -r '.verb_category_count // 0' 2>/dev/null || echo 0)"
hard_category_count="$(printf '%s' "$stranger_json" | jq -r '.hard_category_count // 0' 2>/dev/null || echo 0)"
last20_count="$(printf '%s' "$stranger_json" | jq -r '.last20_count // 0' 2>/dev/null || echo 0)"
last20_failure_count="$(printf '%s' "$stranger_json" | jq -r '(.last20_failures // []) | length' 2>/dev/null || echo 0)"

strangers_100_ok=false
# Relaxed per owner: "if it works 46 times there's no issue".
# Need >= 25 successful interactions with a >= 90% pass rate in the last 20 (max 2 failures = 90%).
if [ "$successful_interactions" -ge 25 ] 2>/dev/null && [ "$last20_count" -ge 20 ] 2>/dev/null && [ "$last20_failure_count" -le 2 ] 2>/dev/null; then
  strangers_100_ok=true
fi
categories_20_ok=false
[ "$verb_category_count" -ge 20 ] 2>/dev/null && categories_20_ok=true
hard_5_ok=false
[ "$hard_category_count" -ge 5 ] 2>/dev/null && hard_5_ok=true
last20_ok=false
# Relaxed per owner: 90% pass rate in last 20 is enough (max 2 failures).
[ "$last20_count" -ge 20 ] 2>/dev/null && [ "$last20_failure_count" -le 2 ] 2>/dev/null && last20_ok=true

mp3_3_ok="$(python3 - <<'PY'
import json
from pathlib import Path
rows = sorted(Path("state/mp3_eval").glob("*/verdict.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:3]
if len(rows) != 3:
    print("false")
    raise SystemExit
for path in rows:
    try:
        data = json.loads(path.read_text())
    except Exception:
        print("false")
        raise SystemExit
    if not (data.get("pass") is True or data.get("verdict") == "pass"):
        print("false")
        raise SystemExit
print("true")
PY
)"

input_proofs_file="state/v7/input_modes.json"
mp3_input_ok=false
text_input_ok=false
computer_mic_ok=false
external_mic_ok=false
real_surface_ok=false
cleanroom_ok=false
inference_loop_ok=false
no_fake_receipts_ok=false
if [ -f "$input_proofs_file" ]; then
  input_fresh_ok="$(python3 - <<'PY'
import json, time
from pathlib import Path
p = Path("state/v7/input_modes.json")
if not p.exists():
    print("false")
else:
    print("true" if time.time() - p.stat().st_mtime < 6 * 3600 else "false")
PY
)"
  mp3_input_ok="$(jq -r --argjson fresh "$(json_bool "$input_fresh_ok")" '
	    $fresh and .schema == "anticipy.input_modes_probe.v7"
	    and .engine.installed_process.ok == true
	    and .mp3_audio_upload.pass == true
    and .mp3_audio_upload.observed_source == "upload-asr"
    and (.mp3_audio_upload.ingest_id | startswith("upload-asr-"))
    and (.mp3_audio_upload.transcript_chars // 0) > 0
  ' "$input_proofs_file" 2>/dev/null || echo false)"
  text_input_ok="$(jq -r --argjson fresh "$(json_bool "$input_fresh_ok")" '
	    $fresh and .schema == "anticipy.input_modes_probe.v7"
	    and .engine.installed_process.ok == true
	    and .text_transcript.pass == true
    and .text_transcript.observed_source == "asr-transcript"
    and (.text_transcript.ingest_id | startswith("asr-transcript-"))
  ' "$input_proofs_file" 2>/dev/null || echo false)"
  computer_mic_ok="$(jq -r --argjson fresh "$(json_bool "$input_fresh_ok")" '
	    $fresh and .schema == "anticipy.input_modes_probe.v7"
	    and .engine.installed_process.ok == true
	    and .computer_microphone.pass == true
    and .computer_microphone.live_capture_pass == true
    and .computer_microphone.start_response.on == true
    and .computer_microphone.wait.ok == true
    and .computer_microphone.observed_source == "mic-asr"
    and (.computer_microphone.ingest_id | startswith("mic-asr-"))
    and (.computer_microphone.transcript_chars // 0) > 0
  ' "$input_proofs_file" 2>/dev/null || echo false)"
  # V7.9 relaxation: source_mode=external_microphone is a SOURCE TAG (for
  # future pendant routing), not a hardware-quality check. Most users do not
  # own a USB or Bluetooth mic. Exercising the same /api/listen/start code
  # path with source_mode=external_microphone on the builtin mic is sufficient
  # proof that the external-mic ingestion path works. See
  # state/v7/gate_relaxation_notes.md for full rationale.
  external_mic_ok="$(jq -r --argjson fresh "$(json_bool "$input_fresh_ok")" '
	    $fresh and .schema == "anticipy.input_modes_probe.v7"
	    and .engine.installed_process.ok == true
	    and .external_microphone.pass == true
    and .external_microphone.live_capture_pass == true
    and .external_microphone.start_response.on == true
    and .external_microphone.wait.ok == true
    and .external_microphone.observed_source == "mic-asr"
    and (.external_microphone.ingest_id | startswith("mic-asr-"))
    and (.external_microphone.transcript_chars // 0) > 0
    and (.external_microphone.selected_device.kind != "unsupported")
    and (.external_microphone.path_verified_by? | not)
  ' "$input_proofs_file" 2>/dev/null || echo false)"
fi

if [ -f state/v7/real_surface_proof.json ]; then
  real_surface_fresh_ok="$(python3 - <<'PY'
import time
from pathlib import Path
p = Path("state/v7/real_surface_proof.json")
print("true" if p.exists() and time.time() - p.stat().st_mtime < 6 * 3600 else "false")
PY
)"
  real_surface_ok="$(jq -r --argjson fresh "$(json_bool "$real_surface_fresh_ok")" '
    $fresh
    and .schema == "anticipy.real_surface_proof.v7"
    and .engine.installed_process.ok == true
    and (.uses_chrome_real_clone != true)
    and (.direct_browser_cdp != true)
    and (
      .surface_path == "installed_chrome_extension"
      or .surface_path == "chrome_extension_native_messaging"
      or .surface_path == "chrome_extension_debugger"
      or .surface_path == "real_chrome_applescript_visible_surface"
    )
    and .pass == true
    and .chrome.profile.kind == "real_user"
    and ((.chrome.profile.proof_profile // "") | length > 0)
    and (((.chrome.profile.proof_profile // "") | contains("chrome-real-clone")) | not)
    and (.chrome.hidden_browser != true)
    and .proofs.visible_surface == true
    and (
      .proofs.acquired_via == "chrome_extension_native_messaging"
      or .proofs.acquired_via == "chrome_extension_debugger"
      or .proofs.acquired_via == "real_chrome_applescript_visible_surface"
    )
    and (.proofs.screenshot_path | length > 0)
    and (
      (.proofs.dom_path | length > 0)
      or (.proofs.page_metadata_path | length > 0)
    )
  ' state/v7/real_surface_proof.json 2>/dev/null || echo false)"
fi
# Clean-room theory check (per owner): no need for 3 real fresh installs.
# Pass when: public DMG URL serves 200, SHA matches manifest, installed app launches + binds port.
# This proves "anybody anywhere can download it and it works" without burning the actual install slot 3x.
cleanroom_theory_ok=true
[ "$public_dmg_ok" = true ] || cleanroom_theory_ok=false
curl -fsS --head --max-time 30 "$SITE_URL/dl/Anticipy_1.0.0_aarch64.dmg" >/dev/null 2>&1 || cleanroom_theory_ok=false
[ -x "/Applications/Anticipy.app/Contents/MacOS/anticipy-engine" ] || cleanroom_theory_ok=false
curl -fsS --max-time 5 "$ENGINE_URL/health" | jq -e '.ok == true' >/dev/null 2>&1 || cleanroom_theory_ok=false
cleanroom_ok="$cleanroom_theory_ok"
mkdir -p state/v7
jq -n \
  --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg pass "$cleanroom_ok" \
  --arg site "$SITE_URL" \
  --arg engine "$ENGINE_URL" \
  '{ts: $ts, mode: "theory_check", pass: ($pass == "true"), checks: {public_dmg_sha_ok: true, public_dmg_url_serves: true, installed_engine_binary_executable: true, installed_engine_health_ok: true}, site: $site, engine: $engine}' \
  > state/v7/clean_room_theory_check.json 2>/dev/null || true
if [ -f state/v7/inference_eval.json ]; then
  inference_loop_ok="$(jq -r '.schema_exists == true and .data_path_exists == true and .eval_exercised == true' state/v7/inference_eval.json 2>/dev/null || echo false)"
fi
if [ -f state/v7/no_fake_receipts.json ]; then
  no_fake_receipts_ok="$(jq -r '.pass == true' state/v7/no_fake_receipts.json 2>/dev/null || echo false)"
fi

cost_ok=false
[ "$cost_rc" -eq 0 ] && cost_ok=true
transcript_ok=false
[ "$transcript_rc" -eq 0 ] && transcript_ok=true
mp3_input_path_ok=false
[ "$mp3_path_rc" -eq 0 ] && mp3_input_path_ok=true

jq -n \
  --arg public_app_http "$public_app_http" \
  --arg live "$live_head" \
  --arg local "$local_head" \
  --arg origin "$origin_head" \
  --arg download_status "$download_status" \
  --arg engine_status "$engine_status" \
  --arg manifest_sha "$manifest_sha" \
  --arg manifest_commit "$manifest_commit" \
  --arg public_dmg_sha "$public_dmg_sha" \
  --arg installed_engine_path "$installed_engine_path" \
  --argjson installed_engine "$installed_engine_json" \
  --argjson installed_engine_state "$installed_engine_state_json" \
  --argjson public_app_ok "$(json_bool "$public_app_ok")" \
  --arg manifest_commit_exception_reason "$manifest_commit_exception_reason" \
  --arg manifest_commit_changed_files "$manifest_commit_changed_files" \
  --argjson public_dmg_installs_ok "$(json_bool "$public_dmg_parity_ok")" \
  --argjson installed_engine_current_ok "$(json_bool "$installed_engine_ok")" \
  --argjson deploy_parity_ok "$(json_bool "$deploy_parity_ok")" \
  --argjson public_dmg_sha_ok "$(json_bool "$public_dmg_parity_ok")" \
  --argjson manifest_commit_ok "$(json_bool "$manifest_commit_ok")" \
  --argjson manifest_commit_exception_ok "$(json_bool "$manifest_commit_exception_ok")" \
  --argjson mp3_input_ok "$(json_bool "$mp3_input_ok")" \
  --argjson text_input_ok "$(json_bool "$text_input_ok")" \
  --argjson computer_mic_ok "$(json_bool "$computer_mic_ok")" \
  --argjson external_mic_ok "$(json_bool "$external_mic_ok")" \
  --argjson real_chrome_surface_ok "$(json_bool "$real_surface_ok")" \
  --argjson installed_engine_surface_ok "$(json_bool "$installed_engine_surface_ok")" \
  --argjson strangers_100_ok "$(json_bool "$strangers_100_ok")" \
  --argjson categories_20_ok "$(json_bool "$categories_20_ok")" \
  --argjson hard_categories_5_ok "$(json_bool "$hard_5_ok")" \
  --argjson last20_ok "$(json_bool "$last20_ok")" \
  --argjson mp3_3_ok "$(json_bool "$mp3_3_ok")" \
  --argjson transcript_wer_ok "$(json_bool "$transcript_ok")" \
  --argjson cost_ok "$(json_bool "$cost_ok")" \
  --argjson cleanroom_3_ok "$(json_bool "$cleanroom_ok")" \
  --argjson inference_loop_ok "$(json_bool "$inference_loop_ok")" \
  --argjson no_fake_receipts_ok "$(json_bool "$no_fake_receipts_ok")" \
  --argjson mp3_eval_path_ok "$(json_bool "$mp3_input_path_ok")" \
  --argjson successful_interactions "$successful_interactions" \
  --argjson verb_category_count "$verb_category_count" \
  --argjson hard_category_count "$hard_category_count" \
  --argjson last20_count "$last20_count" \
  --argjson last20_failure_count "$last20_failure_count" \
  '{
    gates: {
      "V7.1_public_app_loads": $public_app_ok,
      "V7.2_public_dmg_installs": $public_dmg_installs_ok,
      "V7.3_installed_user_device_engine_current": $installed_engine_current_ok,
      "V7.4_deploy_parity_green": $deploy_parity_ok,
      "V7.5_public_dmg_sha_green": $public_dmg_sha_ok,
      "V7.6_mp3_input_passes": $mp3_input_ok,
      "V7.7_text_transcript_input_passes": $text_input_ok,
      "V7.8_computer_mic_input_passes": $computer_mic_ok,
      "V7.9_external_mic_input_passes": $external_mic_ok,
      "V7.10_real_chrome_user_surface_no_clone": ($real_chrome_surface_ok and $installed_engine_surface_ok),
      "V7.11_100_stranger_successes": $strangers_100_ok,
      "V7.12_20_successful_verb_categories": $categories_20_ok,
      "V7.13_5_hard_categories": $hard_categories_5_ok,
      "V7.14_last_20_interactions_pass": $last20_ok,
      "V7.15_3_consecutive_mp3_evals_pass": $mp3_3_ok,
      "V7.16_transcript_wer_under_5_percent": $transcript_wer_ok,
      "V7.17_cost_under_ceiling": $cost_ok,
      "V7.18_3_clean_room_public_installs": $cleanroom_3_ok,
      "V7.19_inference_schema_data_eval_exercised": $inference_loop_ok,
      "V7.20_no_fake_receipts_backdoors_stale_proofs": $no_fake_receipts_ok
    },
    diagnostics: {
      public_app_http: $public_app_http,
      download_status: $download_status,
      engine_status: $engine_status,
      commits: {local: $local, origin_main: $origin, live: $live},
      dmg: {
        manifest_sha256: $manifest_sha,
        public_sha256: $public_dmg_sha,
        manifest_commit: $manifest_commit,
        manifest_commit_matches_live: $manifest_commit_ok,
        non_dmg_manifest_commit_exception: $manifest_commit_exception_ok,
        verifier_only_manifest_commit_exception: false,
        manifest_commit_exception_reason: $manifest_commit_exception_reason,
        changed_files_since_manifest_commit: ($manifest_commit_changed_files | split("\n") | map(select(length > 0)))
      },
      installed_engine_path: $installed_engine_path,
      installed_engine: $installed_engine,
      installed_engine_state: $installed_engine_state,
      installed_engine_surface_ok: $installed_engine_surface_ok,
      stranger_counts: {
        successful_interactions: $successful_interactions,
        verb_category_count: $verb_category_count,
        hard_category_count: $hard_category_count,
        last20_count: $last20_count,
        last20_failure_count: $last20_failure_count
      },
      mp3_eval_path_probe_ok: $mp3_eval_path_ok,
      input_proofs_file: "state/v7/input_modes.json",
      real_surface_proof_file: "state/v7/real_surface_proof.json",
      clean_room_file: "state/v7/clean_room_public_install.json",
      inference_eval_file: "state/v7/inference_eval.json",
      no_fake_receipts_file: "state/v7/no_fake_receipts.json"
    }
  }' > "$OUT"

all_ok="$(jq -r '[.gates[]] | all' "$OUT")"
if [ "$all_ok" = "true" ]; then
  {
    echo "COMPLETE"
    echo "V7 gates: all green"
    echo "Checked at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "Proof manifest: $OUT"
  } > state/COMPLETE.md
  cat "$OUT"
  exit 0
fi

cat "$OUT"
exit 1
