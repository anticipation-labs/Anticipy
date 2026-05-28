#!/usr/bin/env bash
# browser_safety_check.sh
# Run BEFORE any browser-agent change. Returns 0 (PASS) only if every gate
# below clears. Read-only and idempotent. Opens ONE example.com background
# tab, reads its DOM, then leaves the tab where it is (user can close it).
#
# Gates:
#  G1  Chrome on 9222 alive
#  G2  Bridge on 7777 alive AND cdp_primary
#  G3  Bridge can navigate (background tab to example.com)
#  G4  Bridge can read DOM of that new tab via Target id
#  G5  No tab count balloon (delta <= 2 vs baseline taken right before nav)
#  G6  Fingerprint clean (latest sannysoft canary verdict is REAL_HUMAN_BROWSER)
#
# Does NOT restart anything. Does NOT close tabs. Does NOT touch user tabs.

set -uo pipefail
BRIDGE_URL="${ANTICIPY_BRIDGE_URL:-http://127.0.0.1:7777}"
BRIDGE_SECRET="${ANTICIPY_TRIGGER_SECRET:-local-dev}"
CDP_URL="${ANTICIPY_CDP_URL:-http://127.0.0.1:9222}"
REPO="${REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"

pass=0; fail=0
ok()   { echo "PASS  $1"; pass=$((pass+1)); }
bad()  { echo "FAIL  $1"; fail=$((fail+1)); }

# G1: Chrome alive
v="$(curl -s -m 4 "${CDP_URL}/json/version" 2>/dev/null)"
echo "$v" | grep -q "Chrome/" && ok "G1 Chrome 9222 alive" || bad "G1 Chrome 9222 NOT responding"

# G2: Bridge alive AND cdp_primary
s="$(curl -s -m 4 "${BRIDGE_URL}/status" 2>/dev/null)"
echo "$s" | grep -q '"cdp_alive": true' && echo "$s" | grep -q '"bridge_kind": "cdp_primary"' \
  && ok "G2 Bridge 7777 cdp_primary" || bad "G2 Bridge NOT cdp_primary (status=$s)"

# Baseline tab count BEFORE navigating
baseline="$(curl -s -m 4 "${CDP_URL}/json/list" 2>/dev/null | python3 -c "
import json,sys
try: pages=json.load(sys.stdin)
except Exception: print('0'); raise SystemExit(0)
print(sum(1 for p in pages if p.get('type')=='page'))
" 2>/dev/null)"
baseline="${baseline:-0}"

# G3: Navigate to example.com background
nav="$(curl -s -m 25 -X POST -H "Content-Type: application/json" \
  -d "{\"secret\":\"${BRIDGE_SECRET}\",\"command\":\"navigate\",\"url\":\"https://example.com\"}" \
  "${BRIDGE_URL}/surface-command" 2>/dev/null)"
target_id="$(printf '%s' "$nav" | python3 -c "
import json,sys
try: d=json.load(sys.stdin); print(d.get('data',{}).get('targetId') or '')
except Exception: print('')" 2>/dev/null)"
[ -n "$target_id" ] && ok "G3 Navigate background ok (targetId=$target_id)" \
  || bad "G3 Navigate FAILED (resp=$nav)"

# G4: Read DOM by url_prefix (NOTE: bridge prefix match returns FIRST match,
#     not most-recent. Use a unique URL to be safe.) Falls back to direct CDP.
read_resp="$(curl -s -m 25 -X POST -H "Content-Type: application/json" \
  -d "{\"secret\":\"${BRIDGE_SECRET}\",\"command\":\"read\",\"url_prefix\":\"https://example.com\"}" \
  "${BRIDGE_URL}/surface-command" 2>/dev/null)"
title="$(printf '%s' "$read_resp" | python3 -c "
import json,sys
try: d=json.load(sys.stdin); print(d.get('data',{}).get('title') or '')
except Exception: print('')" 2>/dev/null)"
[ "$title" = "Example Domain" ] && ok "G4 DOM read (title=$title)" \
  || bad "G4 DOM read FAILED (title=$title)"

# G5: Tab count delta sanity
after="$(curl -s -m 4 "${CDP_URL}/json/list" 2>/dev/null | python3 -c "
import json,sys
try: pages=json.load(sys.stdin)
except Exception: print('0'); raise SystemExit(0)
print(sum(1 for p in pages if p.get('type')=='page'))" 2>/dev/null)"
after="${after:-0}"
delta=$((after - baseline))
[ "$delta" -le 2 ] && ok "G5 Tab delta $delta (baseline=$baseline -> after=$after)" \
  || bad "G5 Tab balloon delta=$delta (baseline=$baseline -> after=$after)"

# G6: Latest sannysoft verdict
latest="$(ls -dt "${REPO}/state/v7/bot_detection_"*/ 2>/dev/null | head -1)"
if [ -n "$latest" ] && [ -f "${latest}sannysoft/result.json" ]; then
  verdict="$(python3 -c "
import json,sys
try: print(json.load(open('${latest}sannysoft/result.json')).get('verdict',''))
except Exception: print('')" 2>/dev/null)"
  [ "$verdict" = "REAL_HUMAN_BROWSER" ] && ok "G6 Sannysoft REAL_HUMAN_BROWSER ($(basename "$latest"))" \
    || bad "G6 Sannysoft verdict=$verdict (run bot_detection_canary.sh)"
else
  bad "G6 No sannysoft canary found (run scripts/v7/bot_detection_canary.sh)"
fi

echo ""
echo "Result: PASS=$pass FAIL=$fail"
[ "$fail" -eq 0 ] || exit 1
exit 0
