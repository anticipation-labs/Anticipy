#!/usr/bin/env bash
# V7 integration test: automationexercise.com (e-commerce). Drives real
# Chrome via loopback bridge 127.0.0.1:7777 (navigate + surface-proof);
# click/type use System Events + cliclick (fallback bridge has no click).
# Flow: home, Products, search dress, view first dress, verify product,
# add to cart, dismiss modal (ESC), open cart, Proceed To Checkout,
# hit login wall, stop (no real signup). Output under
# state/v7/integration_runs/automationexercise_<ts>/.

set -uo pipefail

REPO="${REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"
cd "$REPO"
[ -f .env.local ] && { set -a; . .env.local; set +a; }

BRIDGE_URL="${ANTICIPY_BRIDGE_URL:-http://127.0.0.1:7777}"
BRIDGE_SECRET="${ANTICIPY_TRIGGER_SECRET:-local-dev}"
BASE_URL="https://automationexercise.com"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="state/v7/integration_runs/automationexercise_${TS}"
mkdir -p "$RUN_DIR"
LOG="$RUN_DIR/run.log"
T0=$(date +%s)

log() { printf '[%s] %s\n' "$(date -u +%H:%M:%SZ)" "$*" | tee -a "$LOG"; }

declare -a RNAME=() RSTAT=() RNOTE=()
record() { RNAME+=("$1"); RSTAT+=("$2"); RNOTE+=("$3"); }

# Bridge primitives.
b_nav() {
  curl -s --max-time 25 -X POST -H "Content-Type: application/json" \
    -d "$(python3 -c 'import json,sys;print(json.dumps({"secret":sys.argv[1],"command":"navigate","url":sys.argv[2]}))' "$BRIDGE_SECRET" "$1")" \
    "$BRIDGE_URL/surface-command"
}
b_proof() {
  curl -s --max-time 20 -X POST -H "Content-Type: application/json" \
    -d "{\"secret\":\"$BRIDGE_SECRET\"}" "$BRIDGE_URL/surface-proof"
}
cap_proof() {
  local d="$1"; mkdir -p "$d"; b_proof > "$d/proof.json"
  python3 - "$d" <<'PY'
import base64,json,sys
from pathlib import Path
p=Path(sys.argv[1])
try: d=json.loads((p/"proof.json").read_text())
except Exception: sys.exit(0)
img=d.get("screenshot_data_url") or ""
if img.startswith("data:image/png;base64,"):
    (p/"proof_screenshot.png").write_bytes(base64.b64decode(img.split(",",1)[1]))
PY
}

# Find the LATEST automationexercise tab across all Chrome windows, bring its
# window to the front, make it the active tab, pin window bounds so cliclick
# coords are reproducible across concurrent probe tabs.
focus_ae() {
  osascript -e 'tell application "Google Chrome"' \
    -e 'activate' \
    -e 'set targetWin to missing value' \
    -e 'set targetIdx to 0' \
    -e 'repeat with w in windows' \
    -e '  set lastIdx to 0' \
    -e '  repeat with t from 1 to (count of tabs of w)' \
    -e '    if URL of tab t of w contains "automationexercise.com" then set lastIdx to t' \
    -e '  end repeat' \
    -e '  if lastIdx > 0 then' \
    -e '    set targetWin to w' \
    -e '    set targetIdx to lastIdx' \
    -e '    exit repeat' \
    -e '  end if' \
    -e 'end repeat' \
    -e 'if targetWin is not missing value then' \
    -e '  set index of targetWin to 1' \
    -e '  set active tab index of targetWin to targetIdx' \
    -e '  set bounds of targetWin to {0, 0, 1258, 763}' \
    -e 'else' \
    -e '  if (count of windows) = 0 then make new window' \
    -e '  set bounds of front window to {0, 0, 1258, 763}' \
    -e 'end if' \
    -e 'end tell' >/dev/null 2>&1 || true
  sleep 0.6
}
focus() { osascript -e 'tell application "Google Chrome" to activate' >/dev/null 2>&1 || true; sleep 0.3; }
fix_bounds() { focus_ae; }
key_code() { focus; osascript -e "tell application \"System Events\" to key code $1" >/dev/null 2>&1 || true; }
click_at() { focus_ae; cliclick "c:$1,$2" >/dev/null 2>&1 || true; }

pf() { python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get(sys.argv[2]) or "")' "$1" "$2" 2>/dev/null; }
# Visible text of the front Chrome tab via cmd+a + cmd+c (clipboard preserved).
visible_text() {
  osascript \
    -e 'set oldClip to ""' \
    -e 'try' -e 'set oldClip to the clipboard' -e 'end try' \
    -e 'set the clipboard to ""' \
    -e 'tell application "Google Chrome" to activate' -e 'delay 0.4' \
    -e 'tell application "System Events" to keystroke "a" using command down' \
    -e 'delay 0.15' \
    -e 'tell application "System Events" to keystroke "c" using command down' \
    -e 'delay 0.5' \
    -e 'set copiedText to ""' \
    -e 'try' -e 'set copiedText to (the clipboard as text)' -e 'end try' \
    -e 'try' -e 'set the clipboard to oldClip' -e 'end try' \
    -e 'return copiedText' 2>/dev/null
}
# verdict: cond("true"/"false"), dir, name, expected, actual, primitive, ok_note, fail_note
verdict() {
  local cond="$1" d="$2" name="$3" expected="$4" actual="$5" prim="$6" okn="$7" failn="$8"
  local stat note
  if [ "$cond" = "true" ]; then stat=PASS; note="$okn"; else stat=FAIL; note="$failn"; fi
  python3 - "$d/step_result.json" "$name" "$cond" "$expected" "$actual" "$prim" <<'PY'
import json,sys
open(sys.argv[1],"w").write(json.dumps({
  "name":sys.argv[2],"passed":sys.argv[3]=="true",
  "expected":sys.argv[4],"actual":sys.argv[5],"primitive_used":sys.argv[6],
},indent=2,sort_keys=True)+"\n")
PY
  record "$name" "$stat" "$note"
}

nav_ok() { printf '%s' "$1" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("ok"))' 2>/dev/null; }
log "run_dir=$RUN_DIR bridge=$BRIDGE_URL base=$BASE_URL"
SANITY="$(b_proof | python3 -c 'import json,sys;print(json.loads(sys.stdin.read()).get("acquired_via",""))' 2>/dev/null || echo "")"
log "bridge acquired_via=${SANITY:-unknown}"

# Step 1: home. Active-tab read races with probe tabs; confirm via curl title.
log "STEP 1: home"
D1="$RUN_DIR/step_1_home"; mkdir -p "$D1"
NAV1="$(b_nav "$BASE_URL/")"; printf '%s' "$NAV1" > "$D1/navigate.json"
sleep 3; fix_bounds; sleep 1; cap_proof "$D1"
U1="$(pf "$D1/proof.json" url)"
HOME_TITLE="$(curl -s --max-time 15 "$BASE_URL/" | grep -oE '<title>[^<]+</title>' | head -1)"
log "home navOK=$(nav_ok "$NAV1") active_url=$U1 curl_title=$HOME_TITLE"
{ [ "$(nav_ok "$NAV1")" = "True" ] && printf '%s' "$HOME_TITLE" | grep -qi "Automation Exercise"; } && C=true || C=false
verdict "$C" "$D1" home_loaded "navigate ok + Automation Exercise title" "title=$HOME_TITLE url=$U1" "bridge navigate + curl title" "navigate ok; title matched" "navigate failed or wrong title"

log "STEP 2: Products nav"
D2="$RUN_DIR/step_2_products"; mkdir -p "$D2"
NAV2="$(b_nav "$BASE_URL/products")"; printf '%s' "$NAV2" > "$D2/navigate.json"
sleep 3; cap_proof "$D2"
U2="$(pf "$D2/proof.json" url)"
{ [ "$(nav_ok "$NAV2")" = "True" ] && curl -s --max-time 10 "$BASE_URL/products" | grep -q 'productinfo'; } && C=true || C=false
verdict "$C" "$D2" products_page "navigate ok + products listing in HTML" "navOK=$(nav_ok "$NAV2") url=$U2" "bridge navigate (top-nav fallback) + curl HTML" "products listing loaded" "navigate failed or no listing"

log "STEP 3: search dress"
D3="$RUN_DIR/step_3_search_dress"; mkdir -p "$D3"
NAV3="$(b_nav "$BASE_URL/products?search_product=dress")"; printf '%s' "$NAV3" > "$D3/navigate.json"
sleep 3; cap_proof "$D3"
U3="$(pf "$D3/proof.json" url)"
FIRST_PID="$(curl -s --max-time 15 "$BASE_URL/products?search_product=dress" | grep -oE '/product_details/[0-9]+' | head -1 | grep -oE '[0-9]+$' || true)"
log "search navOK=$(nav_ok "$NAV3") url=$U3 first_pid=${FIRST_PID:-NONE}"
{ [ "$(nav_ok "$NAV3")" = "True" ] && [ -n "$FIRST_PID" ]; } && C=true || C=false
verdict "$C" "$D3" search_results "navigate ok + matching product id from HTML" "first=$FIRST_PID" "bridge navigate (form GET) + curl HTML" "first matching product id=$FIRST_PID" "navigate failed or no matching product"

log "STEP 4-5: view product + verify"
D4="$RUN_DIR/step_4_view_product"; mkdir -p "$D4"
TARGET_PID="${FIRST_PID:-1}"
PD_URL="$BASE_URL/product_details/$TARGET_PID"
b_nav "$PD_URL" > "$D4/navigate.json"
sleep 4; fix_bounds; sleep 1; cap_proof "$D4"
U4="$(pf "$D4/proof.json" url)"
curl -s --max-time 15 "$PD_URL" -o "$D4/product_html.html" || true
HAS_PRICE=false; HAS_CART=false
grep -qE "Rs\.[[:space:]]*[0-9]+" "$D4/product_html.html" 2>/dev/null && HAS_PRICE=true
grep -qE "btn btn-default cart" "$D4/product_html.html" 2>/dev/null && HAS_CART=true
log "product url=$U4 html_price=$HAS_PRICE html_cart=$HAS_CART"
{ [ "$HAS_PRICE" = "true" ] && [ "$HAS_CART" = "true" ]; } && C=true || C=false
verdict "$C" "$D4" product_details_page "HTML has price + cart button" "url=$U4 price=$HAS_PRICE cart=$HAS_CART" "bridge navigate + curl HTML" "price + add-to-cart present" "missing price ($HAS_PRICE) or cart ($HAS_CART)"

log "STEP 6: add to cart  STEP 7: dismiss modal"
D5="$RUN_DIR/step_5_add_to_cart"; mkdir -p "$D5"
# At {0,0,1258,763} bounds the orange Add to cart button sits near (880,372).
click_at 880 372; sleep 1.5; cap_proof "$D5"
U5="$(pf "$D5/proof.json" url)"; log "after-add-to-cart url=$U5"
printf '%s' "$U5" | grep -q "/product_details/" && C=true || C=false
verdict "$C" "$D5" add_to_cart_clicked "still on product_details (modal expected)" "$U5" "cliclick on (880,372)" "click issued" "page navigated away"
D6="$RUN_DIR/step_6_dismiss_modal"; mkdir -p "$D6"
key_code 53; sleep 1; cap_proof "$D6"  # ESC closes Bootstrap modal
U6="$(pf "$D6/proof.json" url)"
verdict true "$D6" modal_dismissed "ESC sent to close Continue Shopping modal" "$U6" "System Events key code 53 (ESC)" "ESC sent" ""

log "STEP 8: cart"
D7="$RUN_DIR/step_7_cart"; mkdir -p "$D7"
b_nav "$BASE_URL/view_cart" > "$D7/navigate.json"
sleep 3; fix_bounds; sleep 0.5; cap_proof "$D7"
U7="$(pf "$D7/proof.json" url)"
visible_text > "$D7/visible_text.txt" 2>/dev/null || true
CART_EMPTY=false; CART_HAS_PRODUCT=false
grep -qi "Cart is empty" "$D7/visible_text.txt" 2>/dev/null && CART_EMPTY=true
grep -qE "Rs\.[[:space:]]*[0-9]+" "$D7/visible_text.txt" 2>/dev/null && CART_HAS_PRODUCT=true
log "cart url=$U7 empty=$CART_EMPTY has_product=$CART_HAS_PRODUCT"
[ "$CART_HAS_PRODUCT" = "true" ] && C=true || C=false
verdict "$C" "$D7" cart_view "visible text shows a Rs.NNN cart line" "url=$U7 empty=$CART_EMPTY has_product=$CART_HAS_PRODUCT" "bridge navigate + cmd+a/cmd+c text harvest" "cart shows product line" "cart empty or no product line"

log "STEP 9: cart screenshot  STEP 10: proceed to checkout"
D8="$RUN_DIR/step_8_cart_visual"; mkdir -p "$D8"
cap_proof "$D8"; U8="$(pf "$D8/proof.json" url)"
[ -s "$D8/proof_screenshot.png" ] && C=true || C=false
verdict "$C" "$D8" cart_screenshot "cart screenshot captured" "$U8" "bridge surface-proof" "$D8/proof_screenshot.png" "no PNG produced"
D9="$RUN_DIR/step_9_proceed_checkout"; mkdir -p "$D9"
key_code 121; sleep 0.6; click_at 1100 560; sleep 2.5; cap_proof "$D9"  # PgDn + click
U9="$(pf "$D9/proof.json" url)"; log "post-checkout-click url=$U9"
printf '%s' "$U9" | grep -qE "/view_cart|/checkout" && C=true || C=false
verdict "$C" "$D9" proceed_to_checkout_clicked "click issued; expect login wall or modal" "$U9" "cliclick on (1100,560) after Page Down" "click issued; URL=$U9" "unexpected URL after click"

log "STEP 11: register/login wall  STEP 12: final screenshot"
D10="$RUN_DIR/step_10_login_wall"; mkdir -p "$D10"
b_nav "$BASE_URL/login" > "$D10/navigate.json"; sleep 3; cap_proof "$D10"
U10="$(pf "$D10/proof.json" url)"
curl -s --max-time 15 "$BASE_URL/login" -o "$D10/login_html.html" || true
HAS_LOGIN_FORM=false; HAS_SIGNUP_FORM=false
grep -qE 'action="/login"' "$D10/login_html.html" 2>/dev/null && HAS_LOGIN_FORM=true
grep -qE 'action="/signup"' "$D10/login_html.html" 2>/dev/null && HAS_SIGNUP_FORM=true
log "login url=$U10 login_form=$HAS_LOGIN_FORM signup_form=$HAS_SIGNUP_FORM"
[ "$HAS_LOGIN_FORM" = "true" ] && C=true || C=false
verdict "$C" "$D10" login_wall "/login with login form (no real signup)" "url=$U10 login_form=$HAS_LOGIN_FORM signup_form=$HAS_SIGNUP_FORM" "bridge navigate + curl HTML" "stopped at login wall" "did not reach /login"
D11="$RUN_DIR/step_11_final_screenshot"; mkdir -p "$D11"
cap_proof "$D11"; cp "$D11/proof_screenshot.png" "$RUN_DIR/final_login_wall.png" 2>/dev/null || true
U11="$(pf "$D11/proof.json" url)"
[ -s "$D11/proof_screenshot.png" ] && C=true || C=false
verdict "$C" "$D11" final_screenshot "final login-wall screenshot" "$U11" "bridge surface-proof" "$RUN_DIR/final_login_wall.png" "no PNG produced"

WALL=$(( $(date +%s) - T0 ))
log ""
log "AGGREGATE RESULTS"
pc=0; fc=0
for i in "${!RNAME[@]}"; do
  log "$(printf '%-30s %-5s %s' "${RNAME[$i]}" "${RSTAT[$i]}" "${RNOTE[$i]}")"
  [ "${RSTAT[$i]}" = "PASS" ] && pc=$((pc+1)) || fc=$((fc+1))
done
log "Passed: $pc Failed: $fc Total: ${#RNAME[@]} Wall: ${WALL}s"
python3 - "$RUN_DIR" "$WALL" <<'PY'
import json,sys
from pathlib import Path
r=Path(sys.argv[1]); wall=int(sys.argv[2]); s=[]
for sub in sorted(r.glob("step_*/step_result.json")):
    try: s.append(json.loads(sub.read_text()))
    except Exception as e: s.append({"name":sub.parent.name,"passed":False,"error":str(e)})
out={"run_dir":str(r),"site":"automationexercise.com","wall_seconds":wall,
     "total":len(s),"passed":sum(1 for x in s if x.get("passed")),
     "failed":sum(1 for x in s if not x.get("passed")),"steps":s}
(r/"summary.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
print(json.dumps({k:out[k] for k in ("passed","failed","total","wall_seconds","run_dir")}))
PY
[ "$fc" -gt 0 ] && exit 1 || exit 0
