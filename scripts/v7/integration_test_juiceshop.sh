#!/usr/bin/env bash
# Anticipy v7 integration test: OWASP Juice Shop e-commerce flow.
# Drives bridge -> universal_surface_runtime + CDP on the same real Chrome
# (--remote-debugging-port=9222). Bridge handles navigate; click/type fall
# back to CDP because applescript_loopback_fallback bridge rejects them.
# Each step writes a screenshot and JSON receipt under
# state/v7/integration_runs/juiceshop_<ts>/. Exits 1 on first failure.

set -u
set -o pipefail

REPO="/Users/omarebrahim/Developer/Anticipy-V7"
ENV_FILE="/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/.env.local"
BRIDGE="http://127.0.0.1:7777"
SECRET="${ANTICIPY_TRIGGER_SECRET:-local-dev}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
RUN="${REPO}/state/v7/integration_runs/juiceshop_${TS}"
TRACE="${RUN}/trace.log"
SUMMARY="${RUN}/summary.json"
mkdir -p "${RUN}"
[[ -f "${ENV_FILE}" ]] && set -a && . "${ENV_FILE}" && set +a || true

T0=$(python3 -c 'import time;print(time.time())')
PASS=0; FAIL=0; LAST=""; FAILED=""; RESULTS=()
FB_FILE="${RUN}/.fallbacks"; : > "${FB_FILE}"
fb(){ echo "$1" >> "${FB_FILE}"; }
log(){ echo "[$(date -u +%H:%M:%S)] $*" | tee -a "${TRACE}" >&2; }
# Background orchestrator may wipe untracked run dirs mid-flight; recreate.
ensure(){ [[ -d "${RUN}" ]] || mkdir -p "${RUN}"; }
snap(){
  ensure; local n; n=$(cat "${RUN}/.step" 2>/dev/null || echo 0); n=$((n+1)); echo "${n}" > "${RUN}/.step"
  local f="${RUN}/$(printf 'step-%02d-%s.png' "${n}" "$1")"
  screencapture -x "${f}" 2>>"${TRACE}" || true; echo "${f}"
}
cur(){ cat "${RUN}/.step" 2>/dev/null || echo 0; }
rec(){
  ensure; local name="$1" ok="$2" detail="$3" shot="$4" rcpt="$5"; local n; n=$(cur)
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
  curl -s --max-time 20 -X POST "${BRIDGE}/surface-command" -H "Content-Type: application/json" -d "${body}" 2>>"${TRACE}"
}
cdp_prune(){ python3 <<'PY' 2>>"${TRACE}"
import json, urllib.request
try: pages=json.loads(urllib.request.urlopen("http://127.0.0.1:9222/json/list",timeout=5).read().decode())
except Exception: pages=[]
js=[p for p in pages if p.get("type")=="page" and "juice-shop" in (p.get("url") or "")]
for t in js[1:]:
    try: urllib.request.urlopen(f"http://127.0.0.1:9222/json/close/{t['id']}",timeout=3)
    except Exception: pass
PY
}
cdp_find_tab(){ TARGET="$1" python3 <<'PY' 2>>"${TRACE}"
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
    ws.send(json.dumps({"id":1,"method":"Runtime.evaluate","params":{"expression":os.environ["EXPR"],"returnByValue":True,"awaitPromise":True}}))
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
    if m is None or m.get("id")!=1: print(json.dumps({"value":"","type":"timeout"}))
    else:
        r=m.get("result",{}).get("result",{})
        print(json.dumps({"value":r.get("value"),"type":r.get("type"),"exception":m.get("result",{}).get("exceptionDetails")}))
except Exception as e: print(json.dumps({"value":"","type":"error","exception":str(e)}))
PY
}
cdp_val(){ python3 -c "import json,sys;print(json.load(sys.stdin).get('value',''))"; }
cdp_url(){ cdp_js "$1" "location.href" | cdp_val; }
cdp_title(){ cdp_js "$1" "document.title" | cdp_val; }
cdp_click(){ cdp_js "$1" "(()=>{const el=document.querySelector($2);if(!el)return'NOTFOUND';el.click();return'OK';})()"
  fb "CDP fallback: click via Runtime.evaluate(el.click()) because bridge rejects 'click'"; }
cdp_type(){ cdp_js "$1" "(()=>{const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;const el=document.querySelector($2);if(!el)return'NOTFOUND';el.focus();s.call(el,$3);el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));return el.value;})()"
  fb "CDP fallback: type via native HTMLInputElement.value setter because bridge rejects 'type'"; }

log "run dir: ${RUN}"
status=""; for i in 1 2 3 4 5; do
  status=$(curl -s --max-time 8 "${BRIDGE}/status" 2>>"${TRACE}")
  echo "${status}" | grep -q '"ok": true' && break; sleep 1
done
echo "${status}" > "${RUN}/bridge_status.json"
echo "${status}" | grep -q '"ok": true' || { rec bridge_alive false "bridge not ok: ${status:0:200}" "" "${status}"; exit 1; }
cdp_prune
# Step 1: navigate to Juice Shop via BRIDGE.
br=$(bridge_nav "https://juice-shop.herokuapp.com/"); sleep 6
cdp_prune
# Retry tab lookup; bridge may rebind a brand-new tab and Chrome may report
# about:blank for up to ~10s while the SPA boots.
TAB=""; u=""
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  TAB=$(cdp_find_tab "juice-shop.herokuapp.com")
  [[ -n "${TAB}" ]] && u=$(cdp_url "${TAB}") || u=""
  [[ "${u}" == *"juice-shop"* ]] && break
  sleep 1
done
shot=$(snap navigate)
[[ -z "${TAB}" ]] && { rec navigate false "no juice-shop tab found via CDP" "${shot}" "${br}"; exit 1; }
log "juice-shop CDP tab=${TAB} url=${u}"
if echo "${br}" | grep -q '"ok": true' && [[ "${u}" == *"juice-shop"* ]]; then
  rec navigate true "url=${u} via BRIDGE /surface-command navigate" "${shot}" "${br}"
else rec navigate false "url=${u} resp=${br:0:200}" "${shot}" "${br}"; exit 1; fi
# Heroku free-tier sometimes returns "Application Error"; fall back to OWASP preview.
ttl=$(cdp_title "${TAB}")
if [[ "${ttl}" == *"Application Error"* ]]; then
  http_dump="$(curl -s --max-time 10 -o /dev/null -w 'http=%{http_code} size=%{size_download}' https://juice-shop.herokuapp.com/ 2>>"${TRACE}")"
  log "Heroku Juice Shop is down (${http_dump}); falling back to preview.owasp-juice.shop"
  br=$(bridge_nav "https://preview.owasp-juice.shop/"); sleep 5
  TAB2=$(cdp_find_tab "preview.owasp-juice.shop"); [[ -n "${TAB2}" ]] && TAB="${TAB2}"
  u=""; for i in 1 2 3 4 5 6 7 8 9 10; do u=$(cdp_url "${TAB}"); [[ "${u}" == *"juice"* ]] && break; sleep 0.7; done
  ttl=$(cdp_title "${TAB}"); shot=$(snap fallback_navigate)
  [[ "${ttl}" == *"Juice Shop"* ]] && rec fallback_navigate true "primary down; preview.owasp-juice.shop title='${ttl}' url=${u}" "${shot}" "${br}" \
                                   || { rec fallback_navigate false "fallback unhealthy title='${ttl}' ${http_dump}" "${shot}" "${br}"; exit 1; }
fi
rec target_health true "page title='${ttl}' url=${u}" "" "${ttl}"
for i in 1 2 3 4 5 6 7 8 9 10; do
  ready=$(cdp_js "${TAB}" "document.querySelector('mat-toolbar')!==null" | cdp_val)
  [[ "${ready}" == "True" ]] && break; sleep 1
done
# Step 2: dismiss welcome banner + cookie bar (best-effort; either may be absent).
cdp_js "${TAB}" "(()=>{const b=document.querySelector('button[aria-label=\"Close Welcome Banner\"]');if(b){b.click();return'BANNER';} return'NONE';})()" >/dev/null
sleep 0.7
cdp_js "${TAB}" "(()=>{const b=document.querySelector('a[aria-label=\"dismiss cookie message\"]');if(b){b.click();return'COOKIES';} return'NONE';})()" >/dev/null
sleep 0.7
shot=$(snap dismiss_banners)
rec dismiss_banners true "welcome banner + cookie bar dismissed (best-effort)" "${shot}" "defensive close"
# Step 3: click 'Open search' button (Juice Shop uses mat-icon-button with aria-label='Open search').
r=$(cdp_click "${TAB}" "'button[aria-label=\"Open search\"]'"); sleep 1.5
have_search=$(cdp_js "${TAB}" "(()=>{const ins=Array.from(document.querySelectorAll('input[type=\"text\"]')).filter(i=>i.offsetParent!==null);return ins.length;})()" | cdp_val)
shot=$(snap open_search)
[[ "${have_search}" =~ ^[1-9] ]] && rec open_search true "visible text inputs=${have_search} after Open search click" "${shot}" "${r}" \
                                 || { rec open_search false "no visible text input after Open search click (count=${have_search})" "${shot}" "${r}"; exit 1; }
# Step 4: type 'apple' into the (now-visible) toolbar search input + submit Enter.
# Juice Shop's input has no id/aria; pick the first visible text input.
r=$(cdp_js "${TAB}" "(()=>{const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;const el=Array.from(document.querySelectorAll('input[type=\"text\"]')).find(i=>i.offsetParent!==null);if(!el)return'NOTFOUND';el.focus();s.call(el,'apple');el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));['keydown','keypress','keyup'].forEach(t=>el.dispatchEvent(new KeyboardEvent(t,{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true})));return el.value;})()" | cdp_val)
fb "CDP fallback: type via native HTMLInputElement.value setter because bridge rejects 'type'"
sleep 2.5; shot=$(snap type_apple)
[[ "${r}" == "apple" ]] && rec type_apple true "typed 'apple' into search; submitted via Enter" "${shot}" "${r}" \
                        || { rec type_apple false "type failed: ${r:0:200}" "${shot}" "${r}"; exit 1; }
# Step 5: verify at least one apple product appears. Older Heroku builds seed
# zero results; if that happens, fall back to preview.owasp-juice.shop.
count=0
for i in 1 2 3 4 5 6 7 8; do
  count=$(cdp_js "${TAB}" "Array.from(document.querySelectorAll('mat-card,mat-grid-tile')).filter(e=>/apple/i.test(e.textContent||'')).length" | cdp_val)
  [[ -n "${count}" && "${count}" != "0" ]] && break; sleep 1
done
if [[ -z "${count}" || "${count}" == "0" ]]; then
  log "Primary deployment has no apple products; falling back to preview.owasp-juice.shop"
  br2=$(bridge_nav "https://preview.owasp-juice.shop/"); sleep 6
  TAB2=$(cdp_find_tab "preview.owasp-juice.shop"); [[ -n "${TAB2}" ]] && TAB="${TAB2}"
  sleep 2
  cdp_click "${TAB}" "'button[aria-label=\"Open search\"]'" >/dev/null; sleep 1.2
  cdp_js "${TAB}" "(()=>{const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;const el=Array.from(document.querySelectorAll('input[type=\"text\"]')).find(i=>i.offsetParent!==null);if(!el)return'NF';el.focus();s.call(el,'apple');el.dispatchEvent(new Event('input',{bubbles:true}));['keydown','keypress','keyup'].forEach(t=>el.dispatchEvent(new KeyboardEvent(t,{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true})));return'OK';})()" >/dev/null
  sleep 2.5
  for i in 1 2 3 4 5 6 7 8; do
    count=$(cdp_js "${TAB}" "Array.from(document.querySelectorAll('mat-card,mat-grid-tile')).filter(e=>/apple/i.test(e.textContent||'')).length" | cdp_val)
    [[ -n "${count}" && "${count}" != "0" ]] && break; sleep 1
  done
fi
shot=$(snap verify_results)
[[ -n "${count}" && "${count}" != "0" ]] && rec verify_apple_results true "apple-matching cards=${count}" "${shot}" "count=${count}" \
                                          || { rec verify_apple_results false "no apple products after fallback" "${shot}" "count=${count}"; exit 1; }
# Step 6: open the first apple product detail dialog (click the product image/section, not the basket button).
r=$(cdp_js "${TAB}" "(()=>{const cards=Array.from(document.querySelectorAll('mat-card'));for(const c of cards){if(/apple/i.test(c.textContent||'')){const sec=c.querySelector('section[role=\"button\"],article.product');(sec||c).click();return 'CLICKED:'+(c.textContent||'').replace(/\\s+/g,' ').trim().slice(0,80);}}return'NOTFOUND';})()" | cdp_val)
sleep 2.0; fb "CDP fallback: click via Runtime.evaluate(el.click()) because bridge rejects 'click'"
shot=$(snap open_product)
[[ "${r}" == CLICKED:* ]] && rec open_product true "opened product: ${r}" "${shot}" "${r}" \
                          || { rec open_product false "click apple card failed: ${r}" "${shot}" "${r}"; exit 1; }
for i in 1 2 3 4 5 6 7; do
  has_dlg=$(cdp_js "${TAB}" "document.querySelector('mat-dialog-container')!==null" | cdp_val)
  [[ "${has_dlg}" == "True" ]] && break; sleep 0.8
done
# Step 7: click 'Add to Basket' inside the dialog (or on the card if the dialog never opened on this build).
r=$(cdp_js "${TAB}" "(()=>{const scope=document.querySelector('mat-dialog-container')||document.body;const buttons=Array.from(scope.querySelectorAll('button'));for(const b of buttons){const t=(b.textContent||'').trim().toLowerCase();if(t.includes('add to basket')||t.includes('add_shopping_cart')){b.click();return 'CLICKED:'+t.slice(0,60);}}return'NOTFOUND';})()" | cdp_val)
sleep 2.0; shot=$(snap add_to_basket)
[[ "${r}" == CLICKED:* ]] && rec add_to_basket true "clicked: ${r}" "${shot}" "${r}" \
                          || { rec add_to_basket false "Add to Basket not found: ${r}" "${shot}" "${r}"; exit 1; }
# Step 8: verify basket counter increments. The toolbar 'Your Basket' button
# contains a trailing digit (e.g. 'shopping_cart Your Basket 1'); product-card
# 'Add to Basket' buttons also exist so we must scope to mat-toolbar.
cdp_js "${TAB}" "(()=>{const c=document.querySelector('mat-dialog-container button[aria-label=\"Close Dialog\"],mat-dialog-container button.close-dialog');if(c){c.click();return'CLOSED';}document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',keyCode:27,bubbles:true}));return'ESC';})()" >/dev/null
sleep 1.5; badge=""  # Juice Shop has TWO <mat-toolbar>; basket lives in second row.
for i in 1 2 3 4 5 6 7 8; do
  badge=$(cdp_js "${TAB}" "(()=>{const tbs=Array.from(document.querySelectorAll('mat-toolbar'));for(const tb of tbs){const buttons=Array.from(tb.querySelectorAll('button'));for(const b of buttons){const t=(b.textContent||'').toLowerCase();if(t.includes('your basket')||(t.includes('shopping_cart')&&!t.includes('add'))){const m=(b.textContent||'').match(/(\\d+)/);if(m)return m[1];}}}return'';})()" | cdp_val)
  [[ -n "${badge}" && "${badge}" =~ ^[1-9] ]] && break; sleep 0.8
done
shot=$(snap basket_counter)
[[ -n "${badge}" && "${badge}" =~ ^[1-9] ]] && rec basket_counter true "basket count=${badge}" "${shot}" "count=${badge}" \
                                            || { rec basket_counter false "count='${badge}'" "${shot}" "count=${badge}"; exit 1; }
# Step 9: click the navbar basket button. Scoped across all mat-toolbar rows.
r=$(cdp_js "${TAB}" "(()=>{const tbs=Array.from(document.querySelectorAll('mat-toolbar'));for(const tb of tbs){const buttons=Array.from(tb.querySelectorAll('button'));for(const b of buttons){const t=(b.textContent||'').toLowerCase();if(t.includes('your basket')||(t.includes('shopping_cart')&&!t.includes('add'))){b.click();return 'CLICKED:'+t.replace(/\\s+/g,' ').slice(0,60);}}}return'NOTFOUND';})()" | cdp_val)
sleep 3.0; shot=$(snap open_basket); u=$(cdp_url "${TAB}")
[[ "${r}" == CLICKED:* && "${u}" == *"/basket"* ]] && rec open_basket true "basket page url=${u} via ${r}" "${shot}" "${r}" \
                                                   || { rec open_basket false "click=${r} url=${u}" "${shot}" "${r}"; exit 1; }
# Step 10: verify the apple product is in the basket + final screenshot.
items=$(cdp_js "${TAB}" "Array.from(document.querySelectorAll('table tr, mat-row, .mat-mdc-row, mat-card')).filter(r=>/apple/i.test(r.textContent||'')).length" | cdp_val)
shot=$(snap final)
[[ -n "${items}" && "${items}" != "0" ]] && rec verify_basket_apple true "apple rows in basket=${items}" "${shot}" "rows=${items}" \
                                         || { rec verify_basket_apple false "no apple row (rows=${items})" "${shot}" "rows=${items}"; exit 1; }
T1=$(python3 -c 'import time;print(time.time())')
ELAPSED=$(python3 -c "print(round(${T1}-${T0},2))")
ensure
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
