#!/usr/bin/env bash
# E2E: 20 hard proactive transcripts × rich dossier → score memory-aware intent extraction.
set -u

REPO="/Users/omarebrahim/Developer/Anticipy-V7"
ENGINE="http://127.0.0.1:8731"
ACCOUNT="e2e_rich_test_2026_05_28"
TRANSCRIPTS="$REPO/state/v7/hard_proactive_transcripts.json"
RUN_DIR="$REPO/state/v7/e2e_hard_transcripts_$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "$RUN_DIR"

total=$(jq '.transcripts | length' "$TRANSCRIPTS")
echo "running $total hard transcripts against $ENGINE (account $ACCOUNT)"
echo "run dir: $RUN_DIR"
echo

pass=0
fail=0
results="["

for i in $(seq 0 $((total - 1))); do
  id=$(jq -r ".transcripts[$i].id" "$TRANSCRIPTS")
  cat=$(jq -r ".transcripts[$i].category" "$TRANSCRIPTS")
  diff=$(jq -r ".transcripts[$i].difficulty" "$TRANSCRIPTS")
  text=$(jq -r ".transcripts[$i].raw" "$TRANSCRIPTS")
  expected_intent=$(jq -r ".transcripts[$i].expected_intent" "$TRANSCRIPTS")
  expected_memory=$(jq -c ".transcripts[$i].expected_memory_used" "$TRANSCRIPTS")

  echo "[$id $cat d=$diff] injecting..."

  # Reset listening state between injects so each is fresh.
  curl -fsS -X POST --max-time 5 "$ENGINE/api/listen/reset" -d '{}' -H 'Content-Type: application/json' >/dev/null 2>&1 || true

  # Inject the transcript at the ASR boundary.
  inject_body=$(jq -n --arg t "$text" --arg a "$ACCOUNT" '{text: $t, account_id: $a, user_id: $a, source: "asr-transcript"}')
  curl -s -X POST -H 'Content-Type: application/json' --max-time 30 \
    "$ENGINE/api/listen/inject" -d "$inject_body" \
    -o "$RUN_DIR/${id}_inject.json" -w "%{http_code}" > "$RUN_DIR/${id}_inject.http"

  # Give the engine a moment to plan.
  sleep 3

  # Pull the plan / proposal / state.
  curl -fsS --max-time 10 "$ENGINE/api/listen/status" > "$RUN_DIR/${id}_status.json" 2>&1 || true
  curl -fsS --max-time 10 "$ENGINE/api/memory?account_id=$ACCOUNT" > "$RUN_DIR/${id}_memory.json" 2>&1 || true

  # Run intent extraction directly for a clean signal.
  intent_body=$(jq -n --arg t "$text" --arg a "$ACCOUNT" '{text: $t, account_id: $a, user_id: $a}')
  curl -s -X POST -H 'Content-Type: application/json' --max-time 30 \
    "$ENGINE/api/intent/extract" -d "$intent_body" \
    -o "$RUN_DIR/${id}_intent.json" -w "%{http_code}" > "$RUN_DIR/${id}_intent.http"

  intent_http=$(cat "$RUN_DIR/${id}_intent.http")
  inject_http=$(cat "$RUN_DIR/${id}_inject.http")

  # Score: pass if inject HTTP 200 AND intent extracted with non-empty action.
  case_pass=false
  if [ "$inject_http" = "200" ] && [ "$intent_http" = "200" ]; then
    action=$(jq -r '.action // .intent.action // .extracted.action // ""' "$RUN_DIR/${id}_intent.json" 2>/dev/null)
    if [ -n "$action" ] && [ "$action" != "null" ]; then
      case_pass=true
    fi
  fi
  if $case_pass; then pass=$((pass + 1)); else fail=$((fail + 1)); fi

  results=$(jq -c --argjson r "$(jq -n --arg id "$id" --arg cat "$cat" --argjson diff "$diff" --arg ih "$inject_http" --arg eh "$intent_http" --arg pass "$case_pass" --arg expected "$expected_intent" --argjson memory "$expected_memory" '{id:$id, category:$cat, difficulty:$diff, inject_http:$ih, intent_http:$eh, pass:($pass=="true"), expected_intent:$expected, expected_memory_used:$memory}')" '. + [$r]' <<< "$results")
done
results+="]"

jq -n --argjson r "$(echo "$results" | jq -c '.')" --arg account "$ACCOUNT" --argjson pass "$pass" --argjson fail "$fail" --argjson total "$total" \
  '{ts: (now | strftime("%Y-%m-%dT%H:%M:%SZ")), account_id: $account, total: $total, pass: $pass, fail: $fail, pass_rate: ($pass / $total), results: $r}' \
  > "$RUN_DIR/summary.json"

echo
echo "=== summary ==="
jq '{total, pass, fail, pass_rate}' "$RUN_DIR/summary.json"
echo
echo "details: $RUN_DIR/summary.json"
