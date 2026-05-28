#!/usr/bin/env bash
# Anticipy v7 integration test: real e-commerce flow on saucedemo.com.
# Drives bridge -> universal_surface_runtime end to end with REAL clicks and
# typing. Bridge supports navigate; click/type fall back to CDP on the same
# Chrome (--remote-debugging-port=9222), documented as the bridge fallback
# when applescript_loopback_fallback bridge rejects click/type.
# Each step writes a screenshot and JSON receipt under
# state/v7/integration_runs/saucedemo_<ts>/. Exits 1 on first failure.

set -u
set -o pipefail

REPO="/Users/omarebrahim/Developer/Anticipy-V7"
ENV_FILE="/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/.env.local"
BRIDGE="http://127.0.0.1:7777"
SECRET="${ANTICIPY_TRIGGER_SECRET:-local-dev}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
RUN="${REPO}/state/v7/integration_runs/saucedemo_${TS}"
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
sd=[p for p in pages if p.get("type")=="page" and "saucedemo" in (p.get("url") or "")]
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

# CDP eval. Bridge-AppleScript-created tabs hang without /json/activate, so
# we activate first; Chrome 148 also rejects WS without suppress_origin.
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
# React-compatible: native value setter + input event.
cdp_type(){ cdp_js "$1" "(()=>{const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;const el=document.querySelector($2);if(!el)return'NOTFOUND';el.focus();s.call(el,$3);el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));return el.value;})()"
  fb "CDP fallback: type via Runtime.evaluate + native HTMLInputElement.value setter because bridge applescript_loopback_fallback rejects 'type'"; }

# Compact pass/fail helper. Args: name, expected_url_substring, receipt, shot.
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

# --- step 1: navigate to saucedemo via BRIDGE -------------------------------
br=$(bridge_nav "https://www.saucedemo.com/"); sleep 2.5
cdp_prune
TAB=$(cdp_find_tab "saucedemo.com")
u=""; for i in 1 2 3 4 5 6 7 8; do u=$(cdp_url "${TAB}"); [[ "${u}" == *"saucedemo.com"* ]] && break; sleep 0.5; done
shot=$(snap navigate_login)
[[ -z "${TAB}" ]] && { rec navigate_login false "no saucedemo tab found via CDP" "${shot}" "${br}"; exit 1; }
log "saucedemo CDP tab=${TAB} url=${u}"
if echo "${br}" | grep -q '"ok": true' && [[ "${u}" == *"saucedemo.com"* ]]; then
  rec navigate_login true "url=${u} via BRIDGE /surface-command navigate" "${shot}" "${br}"
else rec navigate_login false "url=${u} resp=${br:0:200}" "${shot}" "${br}"; exit 1; fi

# --- step 2-3: type username + password (CDP; bridge type unsupported) ------
r=$(cdp_type "${TAB}" "'#user-name'" "'standard_user'"); shot=$(snap type_username)
[[ "${r}" == *"standard_user"* ]] && rec type_username true "CDP fill #user-name (bridge type unsupported)" "${shot}" "${r}" \
                                 || { rec type_username false "type failed: ${r:0:200}" "${shot}" "${r}"; exit 1; }
r=$(cdp_type "${TAB}" "'#password'" "'secret_sauce'"); shot=$(snap type_password)
[[ "${r}" == *"secret_sauce"* ]] && rec type_password true "CDP fill #password" "${shot}" "${r}" \
                                || { rec type_password false "type failed: ${r:0:200}" "${shot}" "${r}"; exit 1; }

# --- step 4: click LOGIN (CDP; bridge click unsupported) --------------------
r=$(cdp_click "${TAB}" "'#login-button'"); sleep 2.0
shot=$(snap click_login); expect_url click_login "/inventory.html" "${r}" "${shot}"

# --- step 5: verify inventory page ------------------------------------------
t=$(cdp_title "${TAB}"); rec verify_inventory true "title=${t} url contains /inventory.html" "" "URL+title via CDP"

# --- step 6: click first Add-to-cart ----------------------------------------
# Reset cart (saucedemo uses sessionStorage 'session-username') so the test
# is idempotent across reruns; then click the first Add-to-cart button.
cdp_js "${TAB}" "window.localStorage.removeItem('cart-contents');window.localStorage.removeItem('cart-quantities');location.reload();'OK'" >/dev/null
sleep 1.5
r=$(cdp_click "${TAB}" "'.inventory_item button.btn_primary'"); sleep 1.2
shot=$(snap add_to_cart)
badge=$(cdp_js "${TAB}" "document.querySelector('.shopping_cart_badge')?.textContent||''" | cdp_val)
[[ "${badge}" == "1" ]] && rec add_to_cart true "badge=1 after CDP click first .btn_primary (Add to cart)" "${shot}" "${r}" \
                       || { rec add_to_cart false "expected badge=1 got '${badge}' (cart may be stale)" "${shot}" "${r}"; exit 1; }

# --- step 7: click cart icon ------------------------------------------------
r=$(cdp_click "${TAB}" "'.shopping_cart_link'"); sleep 1.2
shot=$(snap open_cart); expect_url open_cart "/cart.html" "${r}" "${shot}"

# --- step 8: verify cart has 1 item -----------------------------------------
items=$(cdp_js "${TAB}" "document.querySelectorAll('.cart_item').length" | cdp_val)
[[ "${items}" == "1" ]] && rec verify_cart_item true ".cart_item count=1 via CDP" "" "${items}" \
                       || { rec verify_cart_item false "expected 1 cart item got ${items}" "" "${items}"; exit 1; }

# --- step 9: click CHECKOUT -------------------------------------------------
r=$(cdp_click "${TAB}" "'#checkout'"); sleep 1.5
shot=$(snap click_checkout); expect_url click_checkout "/checkout-step-one.html" "${r}" "${shot}"

# --- step 10: fill first/last/postal ----------------------------------------
r1=$(cdp_type "${TAB}" "'#first-name'" "'Anticipy'")
r2=$(cdp_type "${TAB}" "'#last-name'"  "'Test'")
r3=$(cdp_type "${TAB}" "'#postal-code'" "'12345'")
shot=$(snap fill_checkout_form)
if [[ "${r1}" == *"Anticipy"* && "${r2}" == *"Test"* && "${r3}" == *"12345"* ]]; then
  rec fill_checkout_form true "CDP fill first=Anticipy last=Test zip=12345" "${shot}" "${r1}|${r2}|${r3}"
else rec fill_checkout_form false "fill mismatch r1=${r1:0:60} r2=${r2:0:60} r3=${r3:0:60}" "${shot}" ""; exit 1; fi

# --- step 11: click CONTINUE ------------------------------------------------
r=$(cdp_click "${TAB}" "'#continue'"); sleep 1.5
shot=$(snap click_continue); expect_url click_continue "/checkout-step-two.html" "${r}" "${shot}"

# --- step 12: verify summary page -------------------------------------------
sv=$(cdp_js "${TAB}" "document.querySelector('.summary_info')!==null" | cdp_val)
[[ "${sv}" == "True" ]] && rec verify_summary true ".summary_info present" "" "${sv}" \
                       || { rec verify_summary false ".summary_info missing" "" "${sv}"; exit 1; }

# --- step 13: click CANCEL (NOT finish; avoids spamming saucedemo orders) ---
r=$(cdp_click "${TAB}" "'#cancel'"); sleep 1.5
shot=$(snap click_cancel); expect_url click_cancel "/inventory.html" "${r}" "${shot}"

# --- step 14: final screenshot ----------------------------------------------
shot=$(snap final); t=$(cdp_title "${TAB}")
rec final_verify true "back on inventory title=${t}" "${shot}" "complete"

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
o={"run_dir":run,"elapsed_seconds":float(el),"steps_passed":int(p),"steps_failed":int(f),
   "failed_step":fs,"final_screenshot":shot,"results":results,
   "bridge_fallbacks_used":sorted(set(fb_lines)),
   "verdict":"PASS" if int(f)==0 else "FAIL"}
json.dump(o,open(out,"w"),indent=2); print(json.dumps(o,indent=2))
PY

if [[ "${FAIL}" -eq 0 ]]; then log "PASS steps=${PASS} elapsed=${ELAPSED}s final=${LAST}"; exit 0
else log "FAIL failed_step=${FAILED} elapsed=${ELAPSED}s"; exit 1; fi
