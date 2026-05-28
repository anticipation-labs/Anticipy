#!/usr/bin/env bash
# Anticipy V7 bridge regression test: CDP-first behaviour.
#
# Drives a live bridge on 127.0.0.1:7777 through four checks:
#   1. /status reports bridge_kind=cdp_primary
#   2. /surface-command navigate opens a background tab (no foreground switch)
#   3. /surface-command eval_js returns the page title (no AppleScript permission)
#   4. /surface-command click lands on a known selector after a navigate
#
# Writes per-step JSON receipts + a summary under
# state/v7/test_bridge_cdp_primary_<ts>/. Exits 1 on first failure.
#
# Run modes:
#   - default (no args)                 : tests whichever bridge is on :7777
#   - --dryrun-target=<path-to-bridge>  : launches that bridge in dry-run
#                                          mode on port 7779 and tests it,
#                                          then kills it. Lets us validate
#                                          the new bridge without restarting
#                                          the live one.

set -u
set -o pipefail

REPO="/Users/omarebrahim/Developer/Anticipy-V7"
ENV_FILE="/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/.env.local"
SECRET="${ANTICIPY_TRIGGER_SECRET:-local-dev}"
[[ -f "${ENV_FILE}" ]] && set -a && . "${ENV_FILE}" && set +a || true

PORT=7777
DRY_TARGET=""
for arg in "$@"; do
  case "${arg}" in
    --dryrun-target=*) DRY_TARGET="${arg#--dryrun-target=}"; PORT=7779 ;;
  esac
done
BRIDGE="http://127.0.0.1:${PORT}"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
RUN="${REPO}/state/v7/test_bridge_cdp_primary_${TS}"
TRACE="${RUN}/trace.log"
SUMMARY="${RUN}/summary.json"
mkdir -p "${RUN}"

log(){ echo "[$(date -u +%H:%M:%S)] $*" | tee -a "${TRACE}" >&2; }

# Optional dry-run: launch the candidate bridge on PORT, wait for it, run
# the tests, then kill it. The live bridge on :7777 stays untouched.
DRY_PID=""
cleanup(){
  if [[ -n "${DRY_PID}" ]]; then
    kill "${DRY_PID}" 2>/dev/null || true
    sleep 0.5
    kill -9 "${DRY_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

if [[ -n "${DRY_TARGET}" ]]; then
  if [[ ! -f "${DRY_TARGET}" ]]; then
    log "FATAL: --dryrun-target=${DRY_TARGET} not found"
    exit 1
  fi
  log "launching dry-run bridge: ${DRY_TARGET} on port ${PORT}"
  ANTICIPY_TRIGGER_PORT="${PORT}" \
  ANTICIPY_TRIGGER_HOST="127.0.0.1" \
  ANTICIPY_TRIGGER_SECRET="${SECRET}" \
  nohup python3 "${DRY_TARGET}" > "${RUN}/bridge_dryrun.log" 2>&1 &
  DRY_PID=$!
  log "dry-run bridge pid=${DRY_PID}, waiting up to 6s for HTTP up"
  for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
    sleep 0.5
    if curl -fsS --max-time 1 "${BRIDGE}/status" >/dev/null 2>&1; then break; fi
  done
fi

PASS=0; FAIL=0; FAILED=""
RESULTS=()

rec(){
  local name="$1" ok="$2" detail="$3" rcpt="$4"
  local n=${#RESULTS[@]}; n=$((n+1))
  RESULTS+=("${name}=${ok}")
  python3 - "${RUN}/$(printf 'step-%02d-%s.json' "${n}" "${name}")" \
          "${name}" "${ok}" "${detail}" "${rcpt}" <<'PY' 2>>"${TRACE}"
import json,sys
o,n,k,d,r=sys.argv[1:6]
json.dump({"name":n,"ok":k=="true","detail":d,"receipt":r[:2000]},
          open(o,"w"),indent=2)
PY
  if [[ "${ok}" == "true" ]]; then PASS=$((PASS+1)); log "PASS ${name} :: ${detail}"
  else FAIL=$((FAIL+1)); FAILED="${name}"; log "FAIL ${name} :: ${detail}"; fi
}

# ---------- check 1: /status -> bridge_kind=cdp_primary ----------
status_raw=""; for i in 1 2 3 4 5; do
  status_raw=$(curl -fsS --max-time 5 "${BRIDGE}/status" 2>>"${TRACE}" || true)
  echo "${status_raw}" | grep -q '"ok"' && break
  sleep 0.6
done
echo "${status_raw}" > "${RUN}/status.json"
kind=$(echo "${status_raw}" | python3 -c 'import json,sys;print(json.loads(sys.stdin.read()).get("bridge_kind",""))' 2>>"${TRACE}" || true)
cdp_alive=$(echo "${status_raw}" | python3 -c 'import json,sys;print(json.loads(sys.stdin.read()).get("cdp_alive",""))' 2>>"${TRACE}" || true)
if [[ "${kind}" == "cdp_primary" && "${cdp_alive}" == "True" ]]; then
  rec status_cdp_primary true "bridge_kind=${kind} cdp_alive=${cdp_alive}" "${status_raw}"
else
  rec status_cdp_primary false "bridge_kind=${kind!r} (expected cdp_primary); cdp_alive=${cdp_alive}" "${status_raw}"
fi

# ---------- check 2: navigate does NOT steal foreground focus ----------
# The right invariant: after the navigate, the URL of the active tab of the
# front Chrome window should NOT contain the marker we just navigated to.
# If it does, the bridge brought the new tab to the foreground (regression).
# Use a unique URL with a marker so we can tell our tab from anything else.
target_url="https://example.com/?anticipy_cdp_test=${TS}"
body=$(SECRET="${SECRET}" URL="${target_url}" python3 -c '
import json, os
print(json.dumps({"secret": os.environ["SECRET"], "command": "navigate", "url": os.environ["URL"]}))
')
nav=$(curl -fsS --max-time 20 -X POST "${BRIDGE}/surface-command" \
  -H "Content-Type: application/json" -d "${body}" 2>>"${TRACE}" || true)
echo "${nav}" > "${RUN}/navigate.json"
nav_ok=$(echo "${nav}" | python3 -c 'import json,sys;print(json.loads(sys.stdin.read()).get("ok",""))' 2>>"${TRACE}" || true)
nav_url=$(echo "${nav}" | python3 -c 'import json,sys;d=json.loads(sys.stdin.read()).get("data",{});print(d.get("url",""))' 2>>"${TRACE}" || true)
nav_in_place=$(echo "${nav}" | python3 -c 'import json,sys;d=json.loads(sys.stdin.read()).get("data",{});print(d.get("in_place",""))' 2>>"${TRACE}" || true)
nav_via=$(echo "${nav}" | python3 -c 'import json,sys;print(json.loads(sys.stdin.read()).get("acquired_via",""))' 2>>"${TRACE}" || true)
sleep 1.5
fg_url_after=$(osascript -e 'tell application "Google Chrome" to if (count of windows) > 0 then return URL of active tab of front window' 2>>"${TRACE}" || true)
log "frontmost URL after navigate: ${fg_url_after:0:160}"
log "navigate response: in_place=${nav_in_place} url=${nav_url:0:160} via=${nav_via}"

# A pass means:
#  - navigate ok=true via CDP
#  - the bridge confirms the target tab now holds the marker URL
#  - the frontmost-Chrome tab URL does NOT equal the navigated URL
#    (the new/reused tab is NOT brought to the foreground)
if [[ "${nav_ok}" == "True" && "${nav_url}" == *"anticipy_cdp_test"* && "${nav_via}" == "chrome_cdp_loopback_bridge" && "${fg_url_after}" != *"anticipy_cdp_test"* ]]; then
  rec navigate_background true "tab navigated to ${nav_url:0:60}; frontmost is ${fg_url_after:0:60} (no foreground steal)" "${nav:0:400}"
elif [[ "${nav_ok}" == "True" && "${fg_url_after}" == *"anticipy_cdp_test"* ]]; then
  rec navigate_background false "REGRESSION: new tab is frontmost; bridge stole focus" "${nav:0:400}"
else
  rec navigate_background false "navigate failed: ok=${nav_ok} url=${nav_url:0:120} via=${nav_via}" "${nav:0:500}"
fi

# ---------- check 3: eval_js returns document.title (no Apple Events menu) ----------
body=$(SECRET="${SECRET}" python3 -c '
import json, os
print(json.dumps({"secret": os.environ["SECRET"], "command": "eval_js",
                  "code": "document.title", "url_prefix": "https://example.com"}))
')
ev=$(curl -fsS --max-time 15 -X POST "${BRIDGE}/surface-command" \
  -H "Content-Type: application/json" -d "${body}" 2>>"${TRACE}" || true)
echo "${ev}" > "${RUN}/eval_js.json"
ev_ok=$(echo "${ev}" | python3 -c 'import json,sys;print(json.loads(sys.stdin.read()).get("ok",""))' 2>>"${TRACE}" || true)
ev_res=$(echo "${ev}" | python3 -c 'import json,sys;d=json.loads(sys.stdin.read()).get("data",{});print(d.get("result",""))' 2>>"${TRACE}" || true)
ev_via=$(echo "${ev}" | python3 -c 'import json,sys;print(json.loads(sys.stdin.read()).get("acquired_via",""))' 2>>"${TRACE}" || true)
if [[ "${ev_ok}" == "True" && "${ev_res}" == "Example Domain" && "${ev_via}" == "chrome_cdp_loopback_bridge" ]]; then
  rec eval_js_title true "result='${ev_res}' via=${ev_via} (no Apple Events permission needed)" "${ev:0:500}"
else
  rec eval_js_title false "ok=${ev_ok} result='${ev_res:0:80}' via=${ev_via}" "${ev:0:500}"
fi

# ---------- check 4: click on a known selector ----------
# example.com has an <a> link to iana.org in the page body. Click it and
# assert the bridge reports OK (the actual navigation is async; we just
# verify the click handler returned OK / NOTFOUND signal correctly).
body=$(SECRET="${SECRET}" python3 -c '
import json, os
print(json.dumps({"secret": os.environ["SECRET"], "command": "click",
                  "selector": "a", "url_prefix": "https://example.com"}))
')
clk=$(curl -fsS --max-time 15 -X POST "${BRIDGE}/surface-command" \
  -H "Content-Type: application/json" -d "${body}" 2>>"${TRACE}" || true)
echo "${clk}" > "${RUN}/click.json"
clk_ok=$(echo "${clk}" | python3 -c 'import json,sys;print(json.loads(sys.stdin.read()).get("ok",""))' 2>>"${TRACE}" || true)
clk_res=$(echo "${clk}" | python3 -c 'import json,sys;d=json.loads(sys.stdin.read()).get("data",{});print(d.get("result",""))' 2>>"${TRACE}" || true)
if [[ "${clk_ok}" == "True" && "${clk_res}" == "OK" ]]; then
  rec click_selector true "selector=a -> result=${clk_res}" "${clk:0:500}"
else
  rec click_selector false "ok=${clk_ok} result='${clk_res}' resp=${clk:0:200}" "${clk:0:500}"
fi

# ---------- summary ----------
python3 - "${SUMMARY}" "${RUN}" "${PASS}" "${FAIL}" "${FAILED}" "${RESULTS[*]:-}" <<'PY'
import json, sys
out, run, p, f, fs, res = sys.argv[1:7]
results = [{"name": r.split("=")[0], "ok": r.split("=")[1] == "true"}
           for r in res.split() if "=" in r]
o = {"run_dir": run, "steps_passed": int(p), "steps_failed": int(f),
     "failed_step": fs, "results": results,
     "verdict": "PASS" if int(f) == 0 else "FAIL"}
json.dump(o, open(out, "w"), indent=2)
print(json.dumps(o, indent=2))
PY

if [[ "${FAIL}" -eq 0 ]]; then log "PASS steps=${PASS}"; exit 0
else log "FAIL failed_step=${FAILED}"; exit 1; fi
