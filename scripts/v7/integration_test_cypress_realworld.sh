#!/usr/bin/env bash
# Anticipy v7 integration test: example.cypress.io Kitchen Sink demo.
# Drives real visible Chrome via bridge navigate + CDP on port 9222 for
# clicks and typing (bridge applescript_loopback_fallback rejects those).
# realworld.cypress.io is NXDOMAIN; example.cypress.io is the real demo
# Cypress publishes for automation practice. Verifies querying + actions
# subpages with real DOM assertions, per-step JSON and screenshots under
# state/v7/integration_runs/cypress_realworld_<ts>/. Exits 1 on failure.

set -u
set -o pipefail

REPO="/Users/omarebrahim/Developer/Anticipy-V7"
ENV_FILE="/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/.env.local"
BRIDGE="http://127.0.0.1:7777"
SECRET="${ANTICIPY_TRIGGER_SECRET:-local-dev}"
BASE="https://example.cypress.io"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
RUN="${REPO}/state/v7/integration_runs/cypress_realworld_${TS}"
TRACE="${RUN}/trace.log"
SUMMARY="${RUN}/summary.json"
mkdir -p "${RUN}"
[[ -f "${ENV_FILE}" ]] && set -a && . "${ENV_FILE}" && set +a || true

T0=$(python3 -c 'import time;print(time.time())')
PASS=0; FAIL=0; LAST=""; FAILED=""; RESULTS=()
FB_FILE="${RUN}/.fallbacks"; : > "${FB_FILE}"
fb(){ echo "$1" >> "${FB_FILE}"; }
log(){ echo "[$(date -u +%H:%M:%S)] $*" | tee -a "${TRACE}" >&2; }

snap(){
  local n; n=$(cat "${RUN}/.step" 2>/dev/null || echo 0); n=$((n+1)); echo "${n}" > "${RUN}/.step"
  local f="${RUN}/$(printf 'step-%02d-%s.png' "${n}" "$1")"
  screencapture -x "${f}" 2>>"${TRACE}" || true; echo "${f}"
}
cur(){ cat "${RUN}/.step" 2>/dev/null || echo 0; }

rec(){
  local name="$1" ok="$2" detail="$3" shot="$4" rcpt="$5"; local n; n=$(cur)
  [[ -n "${shot}" ]] && LAST="${shot}"
  python3 - "${RUN}/$(printf 'step-%02d-%s.json' "${n}" "${name}")" \
          "${name}" "${ok}" "${detail}" "${shot}" "${rcpt}" <<'PY' 2>>"${TRACE}"
import json,sys
o,n,k,d,s,r=sys.argv[1:7]
json.dump({"name":n,"ok":k=="true","detail":d,"screenshot":s,"receipt":r[:1500]},open(o,"w"),indent=2)
PY
  RESULTS+=("${name}=${ok}")
  if [[ "${ok}" == "true" ]]; then PASS=$((PASS+1)); log "PASS step ${n} ${name} :: ${detail}"
  else FAIL=$((FAIL+1)); FAILED="${name}"; log "FAIL step ${n} ${name} :: ${detail}"; fi
}

bridge_nav(){
  local body
  body=$(SECRET="${SECRET}" URL="$1" python3 -c 'import json,os;print(json.dumps({"secret":os.environ["SECRET"],"command":"navigate","url":os.environ["URL"]}))')
  curl -s --max-time 15 -X POST "${BRIDGE}/surface-command" -H "Content-Type: application/json" -d "${body}" 2>>"${TRACE}"
}

cdp_prune(){
  python3 <<'PY' 2>>"${TRACE}"
import json, urllib.request
try: pages=json.loads(urllib.request.urlopen("http://127.0.0.1:9222/json/list",timeout=5).read().decode())
except Exception: pages=[]
sd=[p for p in pages if p.get("type")=="page" and "example.cypress.io" in (p.get("url") or "")]
for t in sd[1:]:
    try: urllib.request.urlopen(f"http://127.0.0.1:9222/json/close/{t['id']}",timeout=3)
    except Exception: pass
PY
}

cdp_find_tab(){
  TARGET="$1" python3 <<'PY' 2>>"${TRACE}"
import json, os, urllib.request
try: pages=json.loads(urllib.request.urlopen("http://127.0.0.1:9222/json/list",timeout=5).read().decode())
except Exception: pages=[]
t=os.environ["TARGET"]
for p in pages:
    u=p.get("url") or ""
    if p.get("type")=="page" and t in u: print(p.get("id","")); break
PY
}

cdp_js(){
  curl -s --max-time 3 "http://127.0.0.1:9222/json/activate/$1" >/dev/null 2>&1 || true
  TAB="$1" EXPR="$2" python3 <<'PY' 2>>"${TRACE}"
import json, os, time, urllib.request
from websocket import create_connection, WebSocketTimeoutException
def run():
    ws=create_connection(f"ws://localhost:9222/devtools/page/{os.environ['TAB']}",timeout=12,suppress_origin=True)
    ws.send(json.dumps({"id":1,"method":"Runtime.evaluate","params":{"expression":os.environ["EXPR"],"returnByValue":True}}))
    m=None
    while True:
        try: m=json.loads(ws.recv())
        except WebSocketTimeoutException: break
        if m.get("id")==1: break
    ws.close(); return m
try:
    m=run()
    if m is None or m.get("id")!=1:
        try: urllib.request.urlopen(f"http://127.0.0.1:9222/json/activate/{os.environ['TAB']}",timeout=3)
        except Exception: pass
        time.sleep(0.5); m=run()
    if m is None or m.get("id")!=1:
        print(json.dumps({"value":"","type":"timeout"}))
    else:
        r=m.get("result",{}).get("result",{})
        print(json.dumps({"value":r.get("value"),"type":r.get("type"),"exception":m.get("result",{}).get("exceptionDetails")}))
except Exception as e:
    print(json.dumps({"value":"","type":"error","exception":str(e)}))
PY
}
cdp_val(){ python3 -c "import json,sys;print(json.load(sys.stdin).get('value',''))"; }
cdp_url(){ cdp_js "$1" "location.href" | cdp_val; }
cdp_title(){ cdp_js "$1" "document.title" | cdp_val; }
cdp_click(){ cdp_js "$1" "(()=>{const el=document.querySelector($2);if(!el)return'NOTFOUND';el.click();return'OK';})()"
  fb "CDP fallback: click via Runtime.evaluate(el.click()) because bridge applescript_loopback_fallback rejects 'click'"; }
# Bridge navigate opens a new tab on each call; CDP in-place navigate keeps
# the same TAB id so subsequent DOM queries stay bound to the same target.
cdp_nav(){ cdp_js "$1" "location.assign($2);'OK'" >/dev/null; fb "CDP fallback: in-place location.assign navigate because bridge navigate spawns a new tab and breaks TAB binding"; }
cdp_type(){ cdp_js "$1" "(()=>{const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;const el=document.querySelector($2);if(!el)return'NOTFOUND';el.focus();s.call(el,$3);el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));return el.value;})()"
  fb "CDP fallback: type via Runtime.evaluate + native HTMLInputElement.value setter because bridge applescript_loopback_fallback rejects 'type'"; }

expect_url(){
  local name="$1" need="$2" r="$3" shot="$4" u
  u=$(cdp_url "${TAB}")
  if [[ "${u}" == *"${need}"* ]]; then rec "${name}" true "url=${u}" "${shot}" "${r}"
  else rec "${name}" false "expected ${need} got ${u}" "${shot}" "${r}"; exit 1; fi
}

# --- preflight --------------------------------------------------------------
log "run dir: ${RUN}"
status=""; for i in 1 2 3 4 5; do
  status=$(curl -s --max-time 8 "${BRIDGE}/status" 2>>"${TRACE}")
  echo "${status}" | grep -q '"ok": true' && break; sleep 1
done
echo "${status}" > "${RUN}/bridge_status.json"
if ! echo "${status}" | grep -q '"ok": true'; then
  rec bridge_alive false "bridge not ok after 5 tries: ${status:0:200}" "" "${status}"; exit 1
fi
cdp_prune

# --- step 1: navigate to kitchen-sink home via BRIDGE -----------------------
br=$(bridge_nav "${BASE}/"); sleep 2.5
cdp_prune
TAB=$(cdp_find_tab "example.cypress.io")
u=""; for i in 1 2 3 4 5 6 7 8; do u=$(cdp_url "${TAB}"); [[ "${u}" == *"example.cypress.io"* ]] && break; sleep 0.5; done
shot=$(snap navigate_home)
[[ -z "${TAB}" ]] && { rec navigate_home false "no example.cypress.io tab found via CDP" "${shot}" "${br}"; exit 1; }
log "cypress CDP tab=${TAB} url=${u}"
if echo "${br}" | grep -q '"ok": true' && [[ "${u}" == *"example.cypress.io"* ]]; then
  rec navigate_home true "url=${u} via BRIDGE /surface-command navigate" "${shot}" "${br}"
else rec navigate_home false "url=${u} resp=${br:0:200}" "${shot}" "${br}"; exit 1; fi

# --- step 2: verify Kitchen Sink header visible -----------------------------
h=$(cdp_js "${TAB}" "(document.querySelector('h1')?.textContent||document.title||'').trim()" | cdp_val)
shot=$(snap verify_kitchen_sink)
if [[ "${h}" == *"Kitchen Sink"* ]]; then rec verify_kitchen_sink true "h1/title contains Kitchen Sink: ${h}" "${shot}" "${h}"
else rec verify_kitchen_sink false "expected Kitchen Sink got: ${h}" "${shot}" "${h}"; exit 1; fi

# --- step 3: click Commands dropdown in nav ---------------------------------
r=$(cdp_click "${TAB}" "'a.dropdown-toggle'"); sleep 0.8
shot=$(snap click_commands)
open=$(cdp_js "${TAB}" "document.querySelectorAll('.dropdown-menu a[href^=\"/commands/\"]').length" | cdp_val)
if [[ "${open}" -gt 0 ]]; then rec click_commands true "Commands dropdown revealed ${open} command links" "${shot}" "${r}"
else rec click_commands false "no /commands/ links visible after click: ${open}" "${shot}" "${r}"; exit 1; fi

# --- step 4: navigate to Querying sub-page (CDP in-place; bridge spawns tab)
cdp_nav "${TAB}" "'${BASE}/commands/querying'"
u=""; for i in 1 2 3 4 5 6 7 8; do u=$(cdp_url "${TAB}"); [[ "${u}" == *"/commands/querying"* ]] && break; sleep 0.5; done
shot=$(snap nav_querying); expect_url nav_querying "/commands/querying" "CDP location.assign" "${shot}"

# --- step 5: verify #query-btn example button present -----------------------
qb=$(cdp_js "${TAB}" "(()=>{const el=document.querySelector('#query-btn');return el?(el.textContent||'').trim():'MISSING';})()" | cdp_val)
shot=$(snap verify_query_btn)
if [[ "${qb}" == *"Button"* ]]; then rec verify_query_btn true "#query-btn text=${qb}" "${shot}" "${qb}"
else rec verify_query_btn false "expected #query-btn with Button text got: ${qb}" "${shot}" "${qb}"; exit 1; fi

# --- step 6: type into .query-form input (inputEmail per page markup) -------
r=$(cdp_type "${TAB}" "'.query-form input#inputEmail'" "'cypress-demo@example.com'")
shot=$(snap type_query_form)
if [[ "${r}" == *"cypress-demo@example.com"* ]]; then
  rec type_query_form true "typed into .query-form input#inputEmail value=${r}" "${shot}" "${r}"
else rec type_query_form false "type failed: ${r:0:200}" "${shot}" "${r}"; exit 1; fi

# --- step 7: click #query-btn -----------------------------------------------
r=$(cdp_click "${TAB}" "'#query-btn'"); sleep 0.5
shot=$(snap click_query_btn)
if [[ "${r}" == *"OK"* ]]; then rec click_query_btn true "CDP click #query-btn ok" "${shot}" "${r}"
else rec click_query_btn false "click failed: ${r:0:200}" "${shot}" "${r}"; exit 1; fi

# --- step 8: verify expected text in .query-list (apples/oranges/bananas) ---
ql=$(cdp_js "${TAB}" "(()=>{const ul=document.querySelector('.query-list');return ul?ul.textContent.replace(/\s+/g,' ').trim():'MISSING';})()" | cdp_val)
shot=$(snap verify_query_list)
if [[ "${ql}" == *"apples"* && "${ql}" == *"oranges"* && "${ql}" == *"bananas"* ]]; then
  rec verify_query_list true ".query-list contains apples/oranges/bananas: ${ql}" "${shot}" "${ql}"
else rec verify_query_list false "missing list items: ${ql}" "${shot}" "${ql}"; exit 1; fi

# --- step 9: navigate to actions sub-page (CDP in-place) --------------------
cdp_nav "${TAB}" "'${BASE}/commands/actions'"
u=""; for i in 1 2 3 4 5 6 7 8; do u=$(cdp_url "${TAB}"); [[ "${u}" == *"/commands/actions"* ]] && break; sleep 0.5; done
shot=$(snap nav_actions); expect_url nav_actions "/commands/actions" "CDP location.assign" "${shot}"

# --- step 10: fill .action-email with fake@email.com ------------------------
r=$(cdp_type "${TAB}" "'.action-email'" "'fake@email.com'")
shot=$(snap fill_action_email)
if [[ "${r}" == *"fake@email.com"* ]]; then rec fill_action_email true "filled .action-email value=${r}" "${shot}" "${r}"
else rec fill_action_email false "fill failed: ${r:0:200}" "${shot}" "${r}"; exit 1; fi

# --- step 11: verify value persists in DOM ----------------------------------
v=$(cdp_js "${TAB}" "document.querySelector('.action-email')?.value||''" | cdp_val)
shot=$(snap verify_action_email_value)
if [[ "${v}" == "fake@email.com" ]]; then rec verify_action_email_value true ".action-email DOM value=${v}" "${shot}" "${v}"
else rec verify_action_email_value false "expected fake@email.com got '${v}'" "${shot}" "${v}"; exit 1; fi

# --- step 12: final screenshot ----------------------------------------------
shot=$(snap final); t=$(cdp_title "${TAB}"); u=$(cdp_url "${TAB}")
rec final_screenshot true "actions page title=${t} url=${u}" "${shot}" "complete"

# --- summary ----------------------------------------------------------------
T1=$(python3 -c 'import time;print(time.time())')
ELAPSED=$(python3 -c "print(round(${T1}-${T0},2))")
python3 - "${SUMMARY}" "${RUN}" "${ELAPSED}" "${PASS}" "${FAIL}" "${FAILED}" "${LAST}" \
        "${FB_FILE}" "${RESULTS[*]:-}" <<'PY'
import json, sys
out,run,el,p,f,fs,shot,fbf,res=sys.argv[1:10]
results=[{"name":r.split("=")[0],"ok":r.split("=")[1]=="true"} for r in res.split() if "=" in r]
try: fb_lines=[l.strip() for l in open(fbf).read().splitlines() if l.strip()]
except Exception: fb_lines=[]
o={"run_dir":run,"site":"example.cypress.io","elapsed_seconds":float(el),
   "steps_passed":int(p),"steps_failed":int(f),"failed_step":fs,
   "final_screenshot":shot,"results":results,
   "bridge_fallbacks_used":sorted(set(fb_lines)),
   "verdict":"PASS" if int(f)==0 else "FAIL"}
json.dump(o,open(out,"w"),indent=2); print(json.dumps(o,indent=2))
PY

if [[ "${FAIL}" -eq 0 ]]; then log "PASS steps=${PASS} elapsed=${ELAPSED}s final=${LAST}"; exit 0
else log "FAIL failed_step=${FAILED} elapsed=${ELAPSED}s"; exit 1; fi
