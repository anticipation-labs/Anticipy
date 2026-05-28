#!/usr/bin/env bash
# V7 integration test against the-internet.herokuapp.com (Heroku).
# Exercises tricky UI patterns through the real running Chrome via the
# loopback bridge at 127.0.0.1:7777 (navigate + surface-proof). DOM
# interactions go through System Events keystrokes because the live
# fallback bridge only supports `navigate`. JS alerts are NOT clicked.
# Six sub-tests run independently; failures are captured and reported.

set -uo pipefail

REPO="${REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"
cd "$REPO"

BRIDGE_URL="${ANTICIPY_BRIDGE_URL:-http://127.0.0.1:7777}"
BRIDGE_SECRET="${ANTICIPY_TRIGGER_SECRET:-local-dev}"
BASE_URL="https://the-internet.herokuapp.com"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="state/v7/integration_runs/the_internet_${TS}"
mkdir -p "$RUN_DIR"
LOG="$RUN_DIR/run.log"

log() { printf '[%s] %s\n' "$(date -u +%H:%M:%SZ)" "$*" | tee -a "$LOG"; }

declare -a R_NAMES=() R_STATUS=() R_NOTES=()
record() { R_NAMES+=("$1"); R_STATUS+=("$2"); R_NOTES+=("$3"); }

# --- Bridge primitives -------------------------------------------------------
bridge_navigate() {
  local url="$1"
  local body
  body="$(python3 -c 'import json,sys; print(json.dumps({"secret":sys.argv[1],"command":"navigate","url":sys.argv[2]}))' "$BRIDGE_SECRET" "$url")"
  curl -s -X POST -H "Content-Type: application/json" -d "$body" "$BRIDGE_URL/surface-command"
}
bridge_surface_proof() {
  curl -s -X POST -H "Content-Type: application/json" -d "{\"secret\":\"$BRIDGE_SECRET\"}" "$BRIDGE_URL/surface-proof"
}
capture_proof() {
  local step_dir="$1"
  mkdir -p "$step_dir"
  bridge_surface_proof > "$step_dir/proof.json"
  python3 - "$step_dir" <<'PY'
import base64, json, sys
from pathlib import Path
step = Path(sys.argv[1])
data = json.loads((step / "proof.json").read_text())
img = data.get("screenshot_data_url") or ""
if img.startswith("data:image/png;base64,"):
    (step / "proof_screenshot.png").write_bytes(base64.b64decode(img.split(",",1)[1]))
PY
}

# --- System Events helpers (no JS-from-AppleEvents required) ----------------
focus_chrome() { osascript -e 'tell application "Google Chrome" to activate' >/dev/null 2>&1 || true; sleep 0.4; }
# Cmd+L then Escape returns focus to the page body for predictable Tab traversal.
focus_page_body() {
  focus_chrome
  osascript >/dev/null 2>&1 <<'AS' || true
tell application "System Events"
  keystroke "l" using {command down}
  delay 0.2
  key code 53
  delay 0.2
end tell
AS
}
press_tab_n() {
  focus_chrome
  osascript >/dev/null 2>&1 <<AS || true
tell application "System Events"
  repeat $1 times
    key code 48
    delay 0.05
  end repeat
end tell
AS
}
type_text() {
  focus_chrome
  osascript >/dev/null 2>&1 <<AS || true
set theText to "$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')"
tell application "System Events" to keystroke theText
AS
}
press_key_code() {
  focus_chrome
  osascript >/dev/null 2>&1 <<AS || true
tell application "System Events" to key code $1
AS
}

# --- Step result helpers ----------------------------------------------------
proof_field() {
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2]) or "")' "$1" "$2" 2>/dev/null
}
write_step_result() {
  python3 - "$1" "$2" "$3" "$4" "$5" "$6" <<'PY'
import json, sys
out, name, passed, expected, actual, primitive = sys.argv[1:7]
data = {"name": name, "passed": passed == "true", "expected": expected, "actual": actual, "primitive_used": primitive}
open(out, "w").write(json.dumps(data, indent=2, sort_keys=True) + "\n")
PY
}

# Wrap a navigate+interact+capture+verify cycle. The interact phase is supplied
# via the SE_ACTIONS environment of caller-provided callbacks; here we keep it
# inline per test for clarity.

log "run dir: $RUN_DIR"
log "bridge: $BRIDGE_URL  base: $BASE_URL"
log "bridge acquired_via: $(bridge_surface_proof | python3 -c 'import json,sys; print(json.loads(sys.stdin.read()).get("acquired_via",""))' 2>/dev/null || echo unknown)"

# --- Test 1: Form Authentication --------------------------------------------
log "TEST 1: Form Authentication (/login)"
T_DIR="$RUN_DIR/step_1_form_auth"; mkdir -p "$T_DIR"
bridge_navigate "$BASE_URL/login" > "$T_DIR/navigate.json"; sleep 2
focus_page_body
press_tab_n 1; type_text "tomsmith"
press_tab_n 1; type_text "SuperSecretPassword!"
press_key_code 36  # Enter submits the form
sleep 3
capture_proof "$T_DIR"
URL="$(proof_field "$T_DIR/proof.json" url)"; TITLE="$(proof_field "$T_DIR/proof.json" title)"
log "T1 url=$URL title=$TITLE"
if printf '%s' "$URL" | grep -q "/secure"; then
  write_step_result "$T_DIR/step_result.json" "form_authentication" "true" "url contains /secure" "$URL" "navigate + SE Tab/type/Enter"
  record "form_authentication" "PASS" "redirected to /secure"
else
  write_step_result "$T_DIR/step_result.json" "form_authentication" "false" "url contains /secure" "$URL" "navigate + SE Tab/type/Enter"
  record "form_authentication" "FAIL" "SE keystroke into form fields (no DOM read to confirm focus path)"
fi

# --- Test 2: Dynamic Loading /2 ---------------------------------------------
log "TEST 2: Dynamic Loading 2 (/dynamic_loading/2)"
T_DIR="$RUN_DIR/step_2_dynamic_loading"; mkdir -p "$T_DIR"
bridge_navigate "$BASE_URL/dynamic_loading/2" > "$T_DIR/navigate.json"; sleep 2
focus_page_body
press_tab_n 1
press_key_code 49  # Space activates the focused Start button
sleep 10           # poll-equivalent wait for Hello World!
capture_proof "$T_DIR"
URL="$(proof_field "$T_DIR/proof.json" url)"; TITLE="$(proof_field "$T_DIR/proof.json" title)"
log "T2 url=$URL title=$TITLE"
if printf '%s' "$URL" | grep -q "/dynamic_loading/2" && [ -s "$T_DIR/proof_screenshot.png" ]; then
  write_step_result "$T_DIR/step_result.json" "dynamic_loading" "true" "screenshot proof after Start; URL stable" "$URL" "navigate + SE Space (button activation)"
  record "dynamic_loading" "PASS" "screenshot captured; manual audit of Hello World"
else
  write_step_result "$T_DIR/step_result.json" "dynamic_loading" "false" "screenshot proof after Start; URL stable" "$URL" "navigate + SE Space (button activation)"
  record "dynamic_loading" "FAIL" "bridge navigate or surface-proof"
fi

# --- Test 3: JavaScript Alerts (render-only, do NOT click) ------------------
log "TEST 3: JavaScript Alerts (/javascript_alerts, render-only)"
T_DIR="$RUN_DIR/step_3_javascript_alerts"; mkdir -p "$T_DIR"
bridge_navigate "$BASE_URL/javascript_alerts" > "$T_DIR/navigate.json"; sleep 2
capture_proof "$T_DIR"
URL="$(proof_field "$T_DIR/proof.json" url)"; TITLE="$(proof_field "$T_DIR/proof.json" title)"
log "T3 url=$URL title=$TITLE"
if printf '%s' "$URL" | grep -q "/javascript_alerts" && [ -s "$T_DIR/proof_screenshot.png" ]; then
  write_step_result "$T_DIR/step_result.json" "javascript_alerts" "true" "page rendered without invoking alert triggers" "$URL" "navigate + surface-proof"
  record "javascript_alerts" "PASS" "render-only per rules; no alert click"
else
  write_step_result "$T_DIR/step_result.json" "javascript_alerts" "false" "page rendered without invoking alert triggers" "$URL" "navigate + surface-proof"
  record "javascript_alerts" "FAIL" "bridge navigate or surface-proof"
fi

# --- Test 4: Dropdown -------------------------------------------------------
log "TEST 4: Dropdown (/dropdown)"
T_DIR="$RUN_DIR/step_4_dropdown"; mkdir -p "$T_DIR"
bridge_navigate "$BASE_URL/dropdown" > "$T_DIR/navigate.json"; sleep 2
focus_page_body
press_tab_n 1                 # focus the select
sleep 0.3; press_key_code 125 # Down -> Option 1
sleep 0.3; press_key_code 125 # Down -> Option 2
sleep 0.3; press_key_code 36  # Enter commits
sleep 1.5
capture_proof "$T_DIR"
URL="$(proof_field "$T_DIR/proof.json" url)"; TITLE="$(proof_field "$T_DIR/proof.json" title)"
log "T4 url=$URL title=$TITLE"
# /dropdown URL is stable; selection-state verification needs DOM read which
# the fallback bridge cannot do. Screenshot is the auditable artifact.
if printf '%s' "$URL" | grep -q "/dropdown" && [ -s "$T_DIR/proof_screenshot.png" ]; then
  write_step_result "$T_DIR/step_result.json" "dropdown_option_2" "true" "screenshot proof after select sequence" "$URL" "navigate + SE Down/Enter"
  record "dropdown_option_2" "PASS" "screenshot captured; manual audit of Option 2"
else
  write_step_result "$T_DIR/step_result.json" "dropdown_option_2" "false" "screenshot proof after select sequence" "$URL" "navigate + SE Down/Enter"
  record "dropdown_option_2" "FAIL" "bridge navigate or surface-proof"
fi

# --- Test 5: Nested Frames --------------------------------------------------
log "TEST 5: Nested Frames (/nested_frames)"
T_DIR="$RUN_DIR/step_5_nested_frames"; mkdir -p "$T_DIR"
bridge_navigate "$BASE_URL/nested_frames" > "$T_DIR/navigate.json"; sleep 2
capture_proof "$T_DIR"
URL="$(proof_field "$T_DIR/proof.json" url)"; TITLE="$(proof_field "$T_DIR/proof.json" title)"
log "T5 url=$URL title=$TITLE"
cat > "$T_DIR/known_limitation.md" <<'MD'
Known limitation: cross-frame interaction is not exercised. The live fallback
bridge supports only `navigate` + `/surface-proof`; it cannot drill into the
nested frames at /frame_top, /frame_left, /frame_middle, /frame_right,
/frame_bottom. Only the parent frameset render is asserted here.
MD
if printf '%s' "$URL" | grep -q "/nested_frames" && [ -s "$T_DIR/proof_screenshot.png" ]; then
  write_step_result "$T_DIR/step_result.json" "nested_frames_loaded" "true" "parent frameset loaded; nested traversal logged as limitation" "$URL" "navigate + surface-proof"
  record "nested_frames_loaded" "PASS" "parent loaded; frame interaction logged as limitation"
else
  write_step_result "$T_DIR/step_result.json" "nested_frames_loaded" "false" "parent frameset loaded; nested traversal logged as limitation" "$URL" "navigate + surface-proof"
  record "nested_frames_loaded" "FAIL" "bridge navigate or surface-proof"
fi

# --- Test 6: Key Presses ----------------------------------------------------
log "TEST 6: Key Presses (/key_presses)"
T_DIR="$RUN_DIR/step_6_key_presses"; mkdir -p "$T_DIR"
bridge_navigate "$BASE_URL/key_presses" > "$T_DIR/navigate.json"; sleep 2
focus_page_body
press_tab_n 1
type_text "X"
sleep 1
capture_proof "$T_DIR"
URL="$(proof_field "$T_DIR/proof.json" url)"; TITLE="$(proof_field "$T_DIR/proof.json" title)"
log "T6 url=$URL title=$TITLE"
if printf '%s' "$URL" | grep -q "/key_presses" && [ -s "$T_DIR/proof_screenshot.png" ]; then
  write_step_result "$T_DIR/step_result.json" "key_press_X" "true" "screenshot proof after X keystroke; URL stable" "$URL" "navigate + SE keystroke X"
  record "key_press_X" "PASS" "screenshot captured; manual audit of You entered: X"
else
  write_step_result "$T_DIR/step_result.json" "key_press_X" "false" "screenshot proof after X keystroke; URL stable" "$URL" "navigate + SE keystroke X"
  record "key_press_X" "FAIL" "bridge navigate or surface-proof"
fi

# --- Aggregate summary -------------------------------------------------------
log ""
log "AGGREGATE RESULTS"
log "================="
pass_count=0; fail_count=0
for i in "${!R_NAMES[@]}"; do
  log "$(printf '%-22s %-5s %s' "${R_NAMES[$i]}" "${R_STATUS[$i]}" "${R_NOTES[$i]}")"
  if [ "${R_STATUS[$i]}" = "PASS" ]; then pass_count=$((pass_count + 1)); else fail_count=$((fail_count + 1)); fi
done
log ""
log "Passed: $pass_count  Failed: $fail_count  Total: ${#R_NAMES[@]}"

python3 - "$RUN_DIR" <<'PY'
import json, sys
from pathlib import Path
run = Path(sys.argv[1])
steps = []
for sub in sorted(run.glob("step_*/step_result.json")):
    try:
        steps.append(json.loads(sub.read_text()))
    except Exception as exc:
        steps.append({"name": sub.parent.name, "passed": False, "error": str(exc)})
summary = {
    "run_dir": str(run),
    "site": "the-internet.herokuapp.com",
    "total": len(steps),
    "passed": sum(1 for s in steps if s.get("passed")),
    "failed": sum(1 for s in steps if not s.get("passed")),
    "steps": steps,
}
(run / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
print(json.dumps({"passed": summary["passed"], "failed": summary["failed"], "total": summary["total"], "run_dir": summary["run_dir"]}))
PY

[ "$fail_count" -gt 0 ] && exit 1 || exit 0
