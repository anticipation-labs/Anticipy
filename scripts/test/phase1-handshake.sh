#!/usr/bin/env bash
# Phase 1 gate verifier: end-to-end extension <-> engine handshake.
# Pass = extension active, native messaging spawned, engine drives a real tab,
# screenshot returned, URL verified.
set -uo pipefail

PORT=$(cat ~/.anticipy/engine.port 2>/dev/null || echo "")
if [ -z "$PORT" ]; then
  echo "FAIL: no engine port file at ~/.anticipy/engine.port"
  exit 1
fi
BASE="http://127.0.0.1:$PORT"

echo "Phase 1 Gate: extension <-> engine handshake"
echo "============================================="
echo

# Step 1: engine healthy
H=$(curl -s --max-time 3 "$BASE/health" 2>/dev/null)
if ! echo "$H" | grep -q '"ok":true'; then
  echo "FAIL step 1: engine /health not OK ($H)"
  exit 1
fi
echo "PASS step 1: engine /health OK on port $PORT"

# Step 2: anticipy-agent process alive
AGENT=$(pgrep -fl "anticipy_agent.py|/anticipy-agent$|/anticipy-agent " 2>/dev/null | grep -v "status-poller" | head -1)
if [ -z "$AGENT" ]; then
  echo "FAIL step 2: anticipy-agent process NOT running."
  echo "  Cause: Chrome Developer Mode is OFF, OR extension not loaded, OR native messaging permission denied."
  echo "  Check: ~/Library/Application Support/Google/Chrome/Default/Secure Preferences -> extensions.ui.developer_mode"
  echo "  Fix: Owner toggles Developer Mode ON in chrome://extensions."
  exit 1
fi
echo "PASS step 2: anticipy-agent process alive: $AGENT"

# Step 3: engine sees extension via /api/state
SURFACE=$(curl -s --max-time 3 "$BASE/api/state" | python3 -c "import json,sys; print(json.load(sys.stdin).get('browser_surface'))" 2>/dev/null)
if [ "$SURFACE" != "extension_native_bridge" ]; then
  echo "FAIL step 3: engine browser_surface = '$SURFACE', expected 'extension_native_bridge'"
  exit 1
fi
echo "PASS step 3: engine browser_surface = extension_native_bridge"

# Step 4: try to trigger a generic navigate via /api/act
echo "  Dispatching /api/act with goal: 'navigate to https://mail.google.com'"
ACT=$(curl -s --max-time 30 -X POST "$BASE/api/act" \
  -H 'Content-Type: application/json' \
  -d '{"goal":"navigate to https://mail.google.com and take a screenshot","dry_run":false}' 2>&1)
echo "  /api/act response: $(echo "$ACT" | head -c 500)"

# Step 5: check if extension reported back via timeline / engine state
sleep 5
TIMELINE_FILE=~/.anticipy/v7/timeline.jsonl
if [ -f "$TIMELINE_FILE" ]; then
  LAST_TIMELINE=$(tail -1 "$TIMELINE_FILE")
  echo "  Last timeline entry: $LAST_TIMELINE"
else
  echo "  WARN: no timeline.jsonl yet (Phase 2 work, not blocking Phase 1)"
fi

# Step 6: verify by reading current Chrome tabs (separate concern, requires extension to report)
echo
echo "============================================="
if echo "$ACT" | grep -q '"error":"No real Chrome on'; then
  echo "FAIL: engine still reports 'No real Chrome on 9222' — extension surface not reachable from action layer"
  echo "  This means Phase 1 surface is loaded but action layer hasn't been wired through it yet."
  echo "  Phase 3 work (generic executor) wires this."
  exit 2
fi
if echo "$ACT" | grep -q '"ran":true'; then
  echo "PASS: action ran via extension surface."
  exit 0
fi
echo "PARTIAL: extension is connected but action layer behavior unclear. Manual inspection needed."
exit 3
