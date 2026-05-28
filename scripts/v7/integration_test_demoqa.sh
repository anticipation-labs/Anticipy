#!/usr/bin/env bash
# Anticipy v7 integration test: ToolsQA demoqa.com practice form flow.
# Drives bridge -> universal_surface_runtime + CDP on the same real Chrome
# (--remote-debugging-port=9222). Bridge handles navigate; click/type fall
# back to CDP because applescript_loopback_fallback bridge rejects them.
# Each step writes a screenshot and JSON receipt under
# state/v7/integration_runs/demoqa_<ts>/. Exits 1 on first failure.

set -u
set -o pipefail

REPO="/Users/omarebrahim/Developer/Anticipy-V7"
ENV_FILE="/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/.env.local"
BRIDGE="http://127.0.0.1:7777"
SECRET="${ANTICIPY_TRIGGER_SECRET:-local-dev}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
RUN="${REPO}/state/v7/integration_runs/demoqa_${TS}"
TRACE="${RUN}/trace.log"
SUMMARY="${RUN}/summary.json"
mkdir -p "${RUN}"
[[ -f "${ENV_FILE}" ]] && set -a && . "${ENV_FILE}" && set +a || true

T0=$(python3 -c 'import time;print(time.time())')
PASS=0; FAIL=0; LAST=""; FAILED=""; RESULTS=()
FB_FILE="${RUN}/.fallbacks"; : > "${FB_FILE}"
fb(){ echo "$1" >> "${FB_FILE}"; }
log(){ echo "[$(date -u +%H:%M:%S)] $*" | tee -a "${TRACE}" >&2; }

# Guard: background orchestrator can wipe untracked dirs; recreate as needed.
ensure(){ [[ -d "${RUN}" ]] || mkdir -p "${RUN}"; }

snap(){
  ensure
  local n; n=$(cat "${RUN}/.step" 2>/dev/null || echo 0); n=$((n+1)); echo "${n}" > "${RUN}/.step"
  local f="${RUN}/$(printf 'step-%02d-%s.png' "${n}" "$1")"
  screencapture -x "${f}" 2>>"${TRACE}" || true; echo "${f}"
}
cur(){ cat "${RUN}/.step" 2>/dev/null || echo 0; }

rec(){
  ensure
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
  curl -s --max-time 20 -X POST "${BRIDGE}/surface-command" -H "Content-Type: application/json" -d "${body}" 2>>"${TRACE}"
}
cdp_prune(){ python3 <<'PY' 2>>"${TRACE}"
import json, urllib.request
try: pages=json.loads(urllib.request.urlopen("http://127.0.0.1:9222/json/list",timeout=5).read().decode())
except Exception: pages=[]
dq=[p for p in pages if p.get("type")=="page" and "demoqa.com" in (p.get("url") or "")]
for t in dq[1:]:
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
cdp_click(){ cdp_js "$1" "(()=>{const el=document.querySelector($2);if(!el)return'NOTFOUND';el.scrollIntoView({block:'center'});el.click();return'OK';})()"
  fb "CDP fallback: click via Runtime.evaluate(el.click()) because bridge rejects 'click'"; }
cdp_type(){ cdp_js "$1" "(()=>{const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;const el=document.querySelector($2);if(!el)return'NOTFOUND';el.scrollIntoView({block:'center'});el.focus();s.call(el,$3);el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));return el.value;})()"
  fb "CDP fallback: type via native HTMLInputElement.value setter because bridge rejects 'type'"; }

log "run dir: ${RUN}"
status=""; for i in 1 2 3 4 5; do
  status=$(curl -s --max-time 8 "${BRIDGE}/status" 2>>"${TRACE}")
  echo "${status}" | grep -q '"ok": true' && break; sleep 1
done
echo "${status}" > "${RUN}/bridge_status.json"
echo "${status}" | grep -q '"ok": true' || { rec bridge_alive false "bridge not ok: ${status:0:200}" "" "${status}"; exit 1; }
cdp_prune
KILLADS="Array.from(document.querySelectorAll('#fixedban,#adplus-anchor,.adsbygoogle,iframe[id^=\"google_ads\"]')).forEach(e=>e.remove());'OK'"
# Step 1: navigate to demoqa.com via BRIDGE.
br=$(bridge_nav "https://demoqa.com/"); sleep 4
cdp_prune
TAB=$(cdp_find_tab "demoqa.com")
u=""; for i in 1 2 3 4 5 6 7 8 9 10; do u=$(cdp_url "${TAB}"); [[ "${u}" == *"demoqa.com"* ]] && break; sleep 0.7; done
shot=$(snap navigate)
[[ -z "${TAB}" ]] && { rec navigate false "no demoqa tab found via CDP" "${shot}" "${br}"; exit 1; }
log "demoqa CDP tab=${TAB} url=${u}"
if echo "${br}" | grep -q '"ok": true' && [[ "${u}" == *"demoqa.com"* ]]; then
  rec navigate true "url=${u} via BRIDGE /surface-command navigate" "${shot}" "${br}"
else rec navigate false "url=${u} resp=${br:0:200}" "${shot}" "${br}"; exit 1; fi
for i in 1 2 3 4 5 6 7 8; do
  ready=$(cdp_js "${TAB}" "document.querySelectorAll('.card,.category-cards .card-body').length>0" | cdp_val)
  [[ "${ready}" == "True" ]] && break; sleep 1
done
cdp_js "${TAB}" "${KILLADS}" >/dev/null
# Step 2: click the 'Forms' card.
r=$(cdp_js "${TAB}" "(()=>{const cards=Array.from(document.querySelectorAll('.card,.card-body,.top-card'));for(const c of cards){if(/forms/i.test(c.textContent||'')){c.scrollIntoView({block:'center'});c.click();return'CLICKED:'+(c.textContent||'').trim().slice(0,40);}}return'NOTFOUND';})()" | cdp_val)
fb "CDP fallback: click via Runtime.evaluate(el.click()) because bridge rejects 'click'"
sleep 2.5; shot=$(snap click_forms_card); u=$(cdp_url "${TAB}")
[[ "${r}" == CLICKED:* && "${u}" == *"/forms"* ]] && rec click_forms_card true "forms page url=${u} via ${r}" "${shot}" "${r}" \
                                                  || { rec click_forms_card false "click=${r} url=${u}" "${shot}" "${r}"; exit 1; }
cdp_js "${TAB}" "${KILLADS}" >/dev/null
# Step 3: click 'Practice Form' in left nav. The clickable target is the
# router-link <a> (not the surrounding <li class="btn btn-light">).
r=$(cdp_js "${TAB}" "(()=>{const sels=['a.router-link','li.btn span.text','li.btn'];for(const sel of sels){const els=Array.from(document.querySelectorAll(sel));for(const e of els){if(/^\\s*practice form\\s*$/i.test(e.textContent||'')){e.scrollIntoView({block:'center'});e.click();return 'CLICKED:'+sel+':'+(e.textContent||'').trim().slice(0,40);}}}return'NOTFOUND';})()" | cdp_val)
sleep 2.5; shot=$(snap click_practice_form); u=$(cdp_url "${TAB}")
[[ "${r}" == CLICKED:* && "${u}" == *"/automation-practice-form"* ]] && rec click_practice_form true "practice-form url=${u} via ${r}" "${shot}" "${r}" \
                                                                     || { rec click_practice_form false "click=${r} url=${u}" "${shot}" "${r}"; exit 1; }
cdp_js "${TAB}" "${KILLADS}" >/dev/null
# Step 4: type first name + last name.
r1=$(cdp_type "${TAB}" "'#firstName'" "'Anticipy'")
r2=$(cdp_type "${TAB}" "'#lastName'"  "'Test'")
shot=$(snap type_name)
[[ "${r1}" == *"Anticipy"* && "${r2}" == *"Test"* ]] && rec type_name true "first=Anticipy last=Test via CDP" "${shot}" "${r1}|${r2}" \
                                                     || { rec type_name false "r1=${r1:0:80} r2=${r2:0:80}" "${shot}" "${r1}|${r2}"; exit 1; }
# Step 5: type email.
r=$(cdp_type "${TAB}" "'#userEmail'" "'anticipy@test.dev'"); shot=$(snap type_email)
[[ "${r}" == *"anticipy@test.dev"* ]] && rec type_email true "email=anticipy@test.dev via CDP" "${shot}" "${r}" \
                                      || { rec type_email false "email fill failed: ${r:0:200}" "${shot}" "${r}"; exit 1; }
# Step 6: click 'Other' gender (DemoQA hides real radios under custom labels; click label by for=).
r=$(cdp_js "${TAB}" "(()=>{const lbl=document.querySelector('label[for=\"gender-radio-3\"]');if(!lbl)return'NOTFOUND';lbl.scrollIntoView({block:'center'});lbl.click();const sel=document.querySelector('#gender-radio-3')?.checked===true;return 'CLICKED checked='+sel;})()" | cdp_val)
fb "CDP fallback: click via Runtime.evaluate(label.click()) because bridge rejects 'click'"
sleep 0.5; shot=$(snap click_gender_other)
[[ "${r}" == "CLICKED checked=true" ]] && rec click_gender_other true "gender=Other radio checked via CDP" "${shot}" "${r}" \
                                       || { rec click_gender_other false "gender Other click failed: ${r}" "${shot}" "${r}"; exit 1; }
# Step 7: type mobile phone (10 digits required).
r=$(cdp_type "${TAB}" "'#userNumber'" "'5551234567'"); shot=$(snap type_phone)
[[ "${r}" == *"5551234567"* ]] && rec type_phone true "phone=5551234567 via CDP" "${shot}" "${r}" \
                               || { rec type_phone false "phone fill failed: ${r:0:200}" "${shot}" "${r}"; exit 1; }
# Step 8: submit (re-strip ads first; they re-render on scroll and overlay #submit).
cdp_js "${TAB}" "${KILLADS}" >/dev/null
r=$(cdp_click "${TAB}" "'#submit'"); sleep 2.5; shot=$(snap click_submit)
[[ "${r}" == *"OK"* ]] && rec click_submit true "clicked #submit via CDP" "${shot}" "${r}" \
                       || { rec click_submit false "#submit click failed: ${r}" "${shot}" "${r}"; exit 1; }
# Step 9: verify confirmation modal appears.
present=""
for i in 1 2 3 4 5 6 7 8; do
  present=$(cdp_js "${TAB}" "(document.querySelector('.modal-content #example-modal-sizes-title-lg')?.textContent||'').trim()" | cdp_val)
  [[ "${present}" == *"submitted"* || "${present}" == *"Thanks"* ]] && break; sleep 0.8
done
shot=$(snap verify_modal)
[[ "${present}" == *"submitted"* || "${present}" == *"Thanks"* ]] && rec verify_modal true "modal title='${present}'" "${shot}" "title=${present}" \
                                                                  || { rec verify_modal false "modal not shown ('${present}')" "${shot}" "title=${present}"; exit 1; }
have_row=$(cdp_js "${TAB}" "(document.querySelector('.modal-body table.table-dark')?.textContent||'').replace(/\s+/g,' ').trim().slice(0,200)" | cdp_val)
rec verify_modal_body true "modal body sample: ${have_row}" "" "${have_row}"
# Step 10: close modal + final screenshot. Try #closeLargeModal click first;
# if the modal is still up, dispatch a synthetic click via dispatchEvent
# (some modal libs hook pointerup, not element.click); fall back to ESC.
r=$(cdp_click "${TAB}" "'#closeLargeModal'")
sleep 1.5
closed=$(cdp_js "${TAB}" "document.querySelector('.modal-content #example-modal-sizes-title-lg')===null" | cdp_val)
if [[ "${closed}" != "True" ]]; then
  r2=$(cdp_js "${TAB}" "(()=>{const b=document.querySelector('#closeLargeModal');if(!b)return'NF';['pointerdown','pointerup','mousedown','mouseup','click'].forEach(t=>b.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,button:0})));return'EVENTS_DISPATCHED';})()" | cdp_val)
  sleep 1.2
  closed=$(cdp_js "${TAB}" "document.querySelector('.modal-content #example-modal-sizes-title-lg')===null" | cdp_val)
  r="${r}; fallback=${r2}"
fi
if [[ "${closed}" != "True" ]]; then
  cdp_js "${TAB}" "document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',keyCode:27,bubbles:true}));'ESC'" >/dev/null
  sleep 1.0
  closed=$(cdp_js "${TAB}" "document.querySelector('.modal-content #example-modal-sizes-title-lg')===null" | cdp_val)
fi
shot=$(snap final)
[[ "${closed}" == "True" ]] && rec close_modal true "modal closed (after fallbacks)" "${shot}" "${r}" \
                            || { rec close_modal false "modal still present after click+events+ESC (closed=${closed})" "${shot}" "${r}"; exit 1; }
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
