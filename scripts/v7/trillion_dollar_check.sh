#!/usr/bin/env bash
# Trillion-dollar gate. Exit 0 if all 7 criteria met. Else exit 1 + write
# state/v7/trillion_dollar_status.json describing what's missing so the ralph
# loop can pick the next thing to fix.
set -u
REPO="${REPO:-/Users/omarebrahim/Developer/Anticipy-V7}"
cd "$REPO"
mkdir -p state/v7
STATUS="state/v7/trillion_dollar_status.json"
MISSING=()

newest_in() { ls -dt $1/$2 2>/dev/null | head -1; }

# 1. All 20 gates green
green=$(jq -r '[.gates[] | select(. == true)] | length' state/check_done_v7.json 2>/dev/null || echo 0)
red_keys=$(jq -c '[.gates | to_entries[] | select(.value == false) | .key]' state/check_done_v7.json 2>/dev/null || echo '[]')
if [ "$green" -lt 20 ]; then MISSING+=("gates:$red_keys"); fi

# 2. Memory precision composite
PREC_FILE="$(newest_in state/v7 'memory_precision_*.json')"
if [ -n "$PREC_FILE" ]; then
  composite=$(jq -r '.summary.composite_mean // .aggregate.composite_mean // .composite_mean // 0' "$PREC_FILE" 2>/dev/null || echo 0)
else composite=0; fi
under=$(awk -v c="$composite" 'BEGIN{print (c+0 < 0.75) ? 1 : 0}')
if [ "$under" = "1" ]; then MISSING+=("precision:composite=$composite need=0.75"); fi

# 3. Z-001 9/9
Z001_DIR="$(newest_in state/v7/z001_e2e_runs '*')"
if [ -n "$Z001_DIR" ] && [ -f "$Z001_DIR/result.json" ]; then
  z_pass=$(jq -r '[.steps[]? | select(.status == "PASS")] | length' "$Z001_DIR/result.json" 2>/dev/null || echo 0)
  if [ "$z_pass" != "9" ]; then MISSING+=("z001:$z_pass/9"); fi
else MISSING+=("z001:no_run"); fi

# 4. Bridge load >=40/50
BRIDGE_DIR="$(newest_in state/v7 'bridge_load_*')"
if [ -n "$BRIDGE_DIR" ] && [ -f "$BRIDGE_DIR/result.json" ]; then
  bridge_pass=$(jq -r '.success_count // .summary.success_count // 0' "$BRIDGE_DIR/result.json" 2>/dev/null || echo 0)
  if [ "$bridge_pass" -lt 40 ] 2>/dev/null; then MISSING+=("bridge_load:$bridge_pass/50"); fi
else MISSING+=("bridge_load:no_run"); fi

# 5. M3 Supabase round trip
M3_DIR="$(newest_in state/v7 'm3_cloud_sync_*')"
if [ -n "$M3_DIR" ] && [ -f "$M3_DIR/result.json" ]; then
  m3_ok=$(jq -r '.round_trip_pass // .pass // false' "$M3_DIR/result.json" 2>/dev/null || echo false)
  if [ "$m3_ok" != "true" ]; then MISSING+=("m3_sync:$(jq -r '.verdict // "unknown"' "$M3_DIR/result.json" 2>/dev/null)"); fi
else MISSING+=("m3_sync:no_run"); fi

# 6. Verb categories >=20
verb_count=$(jq -r '.verb_category_count' state/stranger_breadth.json 2>/dev/null || echo 0)
if [ "$verb_count" -lt 20 ] 2>/dev/null; then MISSING+=("verb_categories:$verb_count need=20"); fi

# 7. Deploy parity
local_head=$(git rev-parse HEAD 2>/dev/null || echo "")
origin_head=$(git ls-remote origin refs/heads/main 2>/dev/null | awk '{print $1}')
live_head=$(curl -fsS --max-time 5 -H 'Cache-Control: no-cache' "https://www.anticipy.ai/api/app/state?x=$(date +%s)" 2>/dev/null | jq -r '.build.commit // ""' || echo "")
if [ -n "$local_head" ] && [ -n "$origin_head" ] && [ -n "$live_head" ]; then
  if [ "${local_head:0:7}" != "${origin_head:0:7}" ] || [ "${local_head:0:7}" != "${live_head:0:7}" ]; then
    MISSING+=("deploy_parity:local=${local_head:0:7} origin=${origin_head:0:7} live=${live_head:0:7}")
  fi
fi

if [ "${#MISSING[@]}" -eq 0 ]; then
  jq -n --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --arg verdict "TRILLION_DOLLAR_MET" '{ts: $ts, verdict: $verdict, missing: []}' > "$STATUS"
  echo "TRILLION_DOLLAR_MET"
  exit 0
fi

jq -n --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --arg verdict "NOT_DONE" \
  --argjson missing "$(printf '%s\n' "${MISSING[@]}" | jq -R . | jq -s .)" \
  '{ts: $ts, verdict: $verdict, missing: $missing}' > "$STATUS"

printf 'NOT_DONE: %d criteria missing\n' "${#MISSING[@]}"
for m in "${MISSING[@]}"; do echo "  - $m"; done
exit 1
