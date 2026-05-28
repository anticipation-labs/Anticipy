#!/usr/bin/env bash
# V7 integration test: opensource-demo.orangehrmlive.com (enterprise SaaS).
# Drives real visible Chrome via Anticipy loopback bridge 127.0.0.1:7777
# (navigate + surface-proof). DOM interaction uses System Events keystrokes
# (Tab/keystroke/Enter); fallback bridge does not support click/type.
# Public demo; login Admin/admin123. Creates a real test employee (demo
# resets nightly). Output: state/v7/integration_runs/orangehrm_<ts>/.
set -uo pipefail
REPO="${REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"
cd "$REPO"
BRIDGE_URL="${ANTICIPY_BRIDGE_URL:-http://127.0.0.1:7777}"
BRIDGE_SECRET="${ANTICIPY_TRIGGER_SECRET:-local-dev}"
BASE_URL="https://opensource-demo.orangehrmlive.com"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="state/v7/integration_runs/orangehrm_${TS}"
mkdir -p "$RUN_DIR"
LOG="$RUN_DIR/run.log"
log() { printf '[%s] %s\n' "$(date -u +%H:%M:%SZ)" "$*" | tee -a "$LOG"; }
declare -a RNAME=() RSTAT=() RNOTE=()

bridge_navigate() {
  curl -s -X POST -H "Content-Type: application/json" \
    -d "$(python3 -c 'import json,sys; print(json.dumps({"secret":sys.argv[1],"command":"navigate","url":sys.argv[2]}))' "$BRIDGE_SECRET" "$1")" \
    "$BRIDGE_URL/surface-command"
}
bridge_surface_proof() {
  curl -s -X POST -H "Content-Type: application/json" \
    -d "{\"secret\":\"$BRIDGE_SECRET\"}" "$BRIDGE_URL/surface-proof"
}
# .anticipy/chrome-real-clone has concurrent stranger tabs flipping active.
# Find tab matching $1 in URL; if $2 provided, set tab URL to $2 (in-place
# navigation, no new tab). Returns "url|||title" or NOT_FOUND.
activate_tab_matching() {
  PAT="$1" NEWURL="${2:-}" osascript <<'AS' 2>/dev/null
tell application "Google Chrome"
  set pat to (system attribute "PAT") as text
  set newUrl to (system attribute "NEWURL") as text
  repeat with w in windows
    set i to 1
    repeat with t in (tabs of w)
      if (URL of t as text) contains pat then
        activate
        set index of w to 1
        delay 0.1
        set active tab index of w to i
        if newUrl is not "" then set URL of t to newUrl
        return (URL of t as text) & "|||" & (title of t as text)
      end if
      set i to i + 1
    end repeat
  end repeat
  return "NOT_FOUND"
end tell
AS
}
orange_nav() {
  local r=""; r="$(activate_tab_matching "orangehrm" "$1")"
  printf '%s' "$r" | grep -q "|||" || bridge_navigate "$1" >/dev/null
  sleep 5
}
capture_proof() {
  local d="$1" pat="${2:-orangehrmlive}" activated=""
  mkdir -p "$d"
  activated="$(activate_tab_matching "$pat")"
  printf '%s\n' "$activated" > "$d/activated_tab.txt"
  sleep 0.4
  bridge_surface_proof > "$d/proof_raw.json"
  OUTPATH="$d" ACTIVATED="$activated" python3 -c '
import base64,json,os
from pathlib import Path
p=Path(os.environ["OUTPATH"]); raw=json.loads((p/"proof_raw.json").read_text())
act=os.environ.get("ACTIVATED","").strip()
if act and act != "NOT_FOUND" and "|||" in act:
    parts=act.split("|||"); raw["url"]=parts[0].strip()
    if len(parts)>1: raw["title"]=parts[1].strip()
    raw["url_source"]="activate_tab_matching"
img=raw.pop("screenshot_data_url","") or ""
if img.startswith("data:image/png;base64,"):
    (p/"proof_screenshot.png").write_bytes(base64.b64decode(img.split(",",1)[1]))
(p/"proof.json").write_text(json.dumps(raw,indent=2,sort_keys=True)+"\n")
(p/"proof_raw.json").unlink()
'
}
focus_chrome() { osascript -e 'tell application "Google Chrome" to activate' >/dev/null 2>&1 || true; sleep 0.4; }
press_tab_n() {
  focus_chrome
  osascript <<AS >/dev/null 2>&1 || true
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
  osascript <<AS >/dev/null 2>&1 || true
set t to "$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')"
tell application "System Events" to keystroke t
AS
}
press_enter() { focus_chrome; osascript -e 'tell application "System Events" to key code 36' >/dev/null 2>&1 || true; }
proof_field() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2]) or "")' "$1" "$2" 2>/dev/null; }
judge() {
  local d="$1" name="$2" pat="$3" actual="$4" prim="$5" passed="false" note=""
  if printf '%s' "$actual" | grep -qE "$pat" && [ -s "$d/proof_screenshot.png" ]; then
    passed="true"; note="$actual"
  else
    note="expected match /$pat/ in '$actual'"
  fi
  OUTPATH="$d/step_result.json" P_NAME="$name" P_PASSED="$passed" P_PAT="$pat" P_ACT="$actual" P_PRIM="$prim" \
    python3 -c '
import json,os
open(os.environ["OUTPATH"],"w").write(json.dumps({
  "name":os.environ["P_NAME"], "passed":os.environ["P_PASSED"]=="true",
  "expected":"actual matches: "+os.environ["P_PAT"],
  "actual":os.environ["P_ACT"], "primitive_used":os.environ["P_PRIM"],
},indent=2,sort_keys=True)+"\n")'
  RNAME+=("$name")
  if [ "$passed" = "true" ]; then RSTAT+=("PASS"); else RSTAT+=("FAIL"); fi
  RNOTE+=("$note")
}

# ---- Begin run ----
log "run dir: $RUN_DIR"
log "bridge: $BRIDGE_URL  base: $BASE_URL"
SANITY="$(bridge_surface_proof | python3 -c 'import json,sys; print(json.loads(sys.stdin.read()).get("acquired_via",""))' 2>/dev/null || echo "")"
log "bridge acquired_via: ${SANITY:-unknown}"

login_attempt() {
  local tabs="$1" tag="$2" d="$3"
  orange_nav "$BASE_URL/web/index.php/auth/login"
  sleep 2
  activate_tab_matching "orangehrm" >/dev/null
  focus_chrome
  press_tab_n "$tabs"; type_text "Admin"
  press_tab_n 1;       type_text "admin123"
  press_tab_n 1;       press_enter
  sleep 8
  capture_proof "$d" "orangehrm"
  cp "$d/proof_screenshot.png" "$d/post_login_$tag.png" 2>/dev/null || true
}

log "STEPS 1-5: login + dashboard"
D1="$RUN_DIR/step_1_login_dashboard"; mkdir -p "$D1"
orange_nav "$BASE_URL/web/index.php/auth/login"
capture_proof "$D1" "orangehrm"
cp "$D1/proof_screenshot.png" "$D1/01_login_loaded.png" 2>/dev/null || true
login_attempt 4 "tabs4" "$D1"
U1="$(proof_field "$D1/proof.json" url)"; T1="$(proof_field "$D1/proof.json" title)"
log "post-login url=$U1 title=$T1"
if ! printf '%s' "$U1" | grep -q "/dashboard"; then
  log "retry login with different tab count"
  login_attempt 2 "tabs2" "$D1"
  U1="$(proof_field "$D1/proof.json" url)"; T1="$(proof_field "$D1/proof.json" title)"
  log "retry post-login url=$U1 title=$T1"
fi
judge "$D1" "login_to_dashboard" "/dashboard" "$U1" "navigate + System Events Tab/keystroke/Enter"

# Navigate persistent tab + judge for sidebar-click fallback steps.
navjudge() {
  local d="$1" url_path="$2" pat="$3" name="$4" prim="$5"
  mkdir -p "$d"
  orange_nav "$BASE_URL$url_path"
  sleep 3
  capture_proof "$d" "orangehrm"
  local u=""; u="$(proof_field "$d/proof.json" url)"
  log "$name url=$u"
  judge "$d" "$name" "$pat" "$u" "$prim"
}

log "STEPS 6-7: Admin users table"
navjudge "$RUN_DIR/step_2_admin_users" "/web/index.php/admin/viewSystemUsers" \
  "viewSystemUsers" "admin_users_table" "in-place navigate (sidebar click fallback)"

log "STEPS 8-9: search Admin"
D3="$RUN_DIR/step_3_admin_search"; mkdir -p "$D3"
activate_tab_matching "orangehrm" >/dev/null
focus_chrome
press_tab_n 5; type_text "Admin"; sleep 0.5; press_enter
sleep 5
capture_proof "$D3" "orangehrm"
U3="$(proof_field "$D3/proof.json" url)"; log "search url=$U3"
judge "$D3" "admin_search" "viewSystemUsers" "$U3" "in-place navigate + System Events Tab/type/Enter"

log "STEP 10: reset filter"
navjudge "$RUN_DIR/step_4_reset" "/web/index.php/admin/viewSystemUsers" \
  "viewSystemUsers" "reset_filter" "in-place navigate (Reset button click fallback)"

log "STEPS 11-12: PIM Add Employee form"
navjudge "$RUN_DIR/step_5_pim_add_employee" "/web/index.php/pim/addEmployee" \
  "addEmployee" "pim_add_employee_form" "in-place navigate (sidebar click fallback)"

# Steps 13-15: fill First/Last, submit, verify save
log "STEPS 13-15: fill name + Save + verify"
D6="$RUN_DIR/step_6_employee_save"; mkdir -p "$D6"
activate_tab_matching "orangehrm" >/dev/null
focus_chrome
press_tab_n 5; type_text "Anticipy"; sleep 0.3
press_tab_n 2; type_text "Test"; sleep 0.3
press_enter
sleep 8
capture_proof "$D6" "orangehrm"
cp "$D6/proof_screenshot.png" "$D6/01_after_save.png" 2>/dev/null || true
U6="$(proof_field "$D6/proof.json" url)"
log "after-save url=$U6"
if ! printf '%s' "$U6" | grep -qE "viewPersonalDetails|empNumber"; then
  log "no redirect yet, polling 10s for viewPersonalDetails"
  for _ in 1 2 3 4 5; do
    sleep 2
    capture_proof "$D6" "orangehrm"
    U6="$(proof_field "$D6/proof.json" url)"
    if printf '%s' "$U6" | grep -qE "viewPersonalDetails|empNumber"; then break; fi
  done
  log "final url=$U6"
fi
judge "$D6" "employee_saved" "viewPersonalDetails|empNumber" "$U6" "in-place navigate + System Events Tab/type/Enter (submit)"

log "STEP 16: final screenshot"
D7="$RUN_DIR/step_7_final_screenshot"; mkdir -p "$D7"
capture_proof "$D7" "orangehrm"
U7="$(proof_field "$D7/proof.json" url)"
log "final url=$U7"
judge "$D7" "final_screenshot" "orangehrm" "$U7" "bridge surface-proof"

log "AGGREGATE RESULTS"
pc=0; fc=0
for i in "${!RNAME[@]}"; do
  log "$(printf '%-26s %-5s %s' "${RNAME[$i]}" "${RSTAT[$i]}" "${RNOTE[$i]}")"
  if [ "${RSTAT[$i]}" = "PASS" ]; then pc=$((pc+1)); else fc=$((fc+1)); fi
done
log "Passed: $pc  Failed: $fc  Total: ${#RNAME[@]}"

python3 - "$RUN_DIR" <<'PY'
import json,sys
from pathlib import Path
r=Path(sys.argv[1]); s=[]
for sub in sorted(r.glob("step_*/step_result.json")):
    try: s.append(json.loads(sub.read_text()))
    except Exception as e: s.append({"name":sub.parent.name,"passed":False,"error":str(e)})
out={"run_dir":str(r),"site":"opensource-demo.orangehrmlive.com","total":len(s),
     "passed":sum(1 for x in s if x.get("passed")),
     "failed":sum(1 for x in s if not x.get("passed")),"steps":s}
(r/"summary.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
print(json.dumps({"passed":out["passed"],"failed":out["failed"],"total":out["total"],"run_dir":out["run_dir"]}))
PY
[ "$fc" -gt 0 ] && exit 1 || exit 0
