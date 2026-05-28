#!/usr/bin/env bash
# V7 bot-detection canary. Drives the user's real signed-in Chrome through
# three probes (sannysoft, areyouheadless, creepjs) via the loopback bridge
# at 127.0.0.1:7777. Harvests visible text via the Chrome DevTools Protocol
# on port 9222 (the cloned-real-profile Chrome that the bridge controls),
# screencaps the display, and writes per-site result.json + summary.md.
#
# Why CDP and not AppleScript cmd+a/cmd+c: Chrome tab groups split a single
# OS-level window across many AppleScript "windows", so System Events
# keystrokes always go to whichever tab group is OS-frontmost, not the tab
# we just navigated to. CDP reads the tab regardless of focus.
set -euo pipefail

REPO="${REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"
cd "$REPO"

if [ -f /Users/omarebrahim/Developer/Anticipy-DEV-FINAL/.env.local ]; then
  set -a; . /Users/omarebrahim/Developer/Anticipy-DEV-FINAL/.env.local; set +a
fi
if [ -f .env.local ]; then set -a; . .env.local; set +a; fi

BRIDGE_URL="${ANTICIPY_BRIDGE_URL:-http://127.0.0.1:7777}"
BRIDGE_SECRET="${ANTICIPY_TRIGGER_SECRET:-local-dev}"
CDP_URL="${ANTICIPY_CDP_URL:-http://127.0.0.1:9222}"
WAIT_SECS="${BOT_CANARY_WAIT_SECS:-12}"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="state/v7/bot_detection_${TS}"
mkdir -p "$OUT_DIR"

# slug | url | host-substring
SITES=(
  "sannysoft|https://bot.sannysoft.com|bot.sannysoft.com"
  "areyouheadless|https://arh.antoinevastel.com/bots/areyouheadless|arh.antoinevastel.com"
  "creepjs|https://abrahamjuliot.github.io/creepjs|abrahamjuliot.github.io"
)

bridge_navigate() {
  local url="$1" resp
  resp="$(curl -sS --max-time 30 -X POST -H "Content-Type: application/json" \
    -d "$(jq -n --arg s "$BRIDGE_SECRET" --arg u "$url" \
            '{secret:$s,command:"navigate",url:$u}')" \
    "${BRIDGE_URL}/surface-command")"
  printf '%s' "$resp"
  printf '%s' "$resp" | jq -e '.ok == true' >/dev/null 2>&1
}

# Extract document.body.innerText from the most recently-created CDP tab
# whose URL contains the given host substring. Outputs the visible text on
# stdout; emits nothing on failure (caller treats empty as INCONCLUSIVE_NO_TEXT).
cdp_extract_text() {
  local needle="$1"
  CDP_URL="$CDP_URL" CDP_NEEDLE="$needle" python3 - <<'PY'
# Uses websockets.sync.client (NOT websocket-client) because the latter
# always sends an Origin header that Chrome's --remote-allow-origins
# rejects. The websockets lib omits Origin, so the handshake passes.
import json, os, sys, time
from urllib.request import urlopen
from websockets.sync.client import connect as ws_connect

cdp = os.environ["CDP_URL"].replace("127.0.0.1", "localhost")
needle = os.environ["CDP_NEEDLE"].lower()

try:
    tabs = json.loads(urlopen(f"{cdp}/json", timeout=10).read().decode())
except Exception as e:
    sys.stderr.write(f"cdp /json failed: {e}\n"); sys.exit(1)

matched = [t for t in tabs if t.get("type") == "page"
           and needle in (t.get("url") or "").lower()
           and t.get("webSocketDebuggerUrl")]
if not matched:
    sys.stderr.write(f"no tab matched: {needle}\n"); sys.exit(1)

ws_url = matched[0]["webSocketDebuggerUrl"].replace("127.0.0.1", "localhost")

try:
    ws = ws_connect(ws_url, max_size=8 * 1024 * 1024, open_timeout=15)
except Exception as e:
    sys.stderr.write(f"ws connect failed: {e}\n"); sys.exit(1)

req_id = 1
def call(method, params=None):
    global req_id
    rid = req_id; req_id += 1
    ws.send(json.dumps({"id": rid, "method": method, "params": params or {}}))
    deadline = time.time() + 20
    while time.time() < deadline:
        msg = json.loads(ws.recv(timeout=5))
        if msg.get("id") == rid:
            return msg
    raise TimeoutError(method)

try:
    res = call("Runtime.evaluate", {
        "expression": "document.body && document.body.innerText || ''",
        "returnByValue": True,
    })
    val = (((res or {}).get("result") or {}).get("result") or {}).get("value") or ""
    sys.stdout.write(val)
finally:
    try: ws.close()
    except Exception: pass
PY
}

screencap() {
  screencapture -x -D 1 "$1" >/dev/null 2>&1 || screencapture -x "$1" >/dev/null 2>&1 || true
}

PARSER="$REPO/scripts/v7/_bot_detection_parse.py"

REAL=0; BOT=0; INCON=0
SUMMARY_ROWS=()

for entry in "${SITES[@]}"; do
  SLUG="${entry%%|*}"; REST="${entry#*|}"
  URL="${REST%%|*}"; HOST="${REST#*|}"
  printf '\n=== %s -> %s ===\n' "$SLUG" "$URL"
  SITE_DIR="$OUT_DIR/$SLUG"; mkdir -p "$SITE_DIR"

  if ! bridge_navigate "$URL" > "$SITE_DIR/navigate.json"; then
    jq -n --arg s "$SLUG" '{slug:$s,verdict:"NAV_FAILED",reason:"bridge_navigate"}' \
      > "$SITE_DIR/result.json"
    SUMMARY_ROWS+=("$SLUG|NAV_FAILED|bridge navigate failed")
    INCON=$((INCON+1)); continue
  fi

  printf 'waiting %ss for detection scripts...\n' "$WAIT_SECS"
  sleep "$WAIT_SECS"

  TEXT="$(cdp_extract_text "$HOST" 2>>"$SITE_DIR/cdp.err" || true)"
  printf '%s' "$TEXT" > "$SITE_DIR/visible_text.txt"
  screencap "$SITE_DIR/screenshot.png"

  python3 "$PARSER" "$SITE_DIR/visible_text.txt" "$SLUG" > "$SITE_DIR/result.json"
  VERDICT="$(jq -r '.verdict' "$SITE_DIR/result.json" 2>/dev/null || echo UNKNOWN)"
  REASON="$(jq -r '.reason' "$SITE_DIR/result.json" 2>/dev/null || echo '')"
  printf '  verdict: %s (%s) text_chars=%d\n' "$VERDICT" "$REASON" "${#TEXT}"
  SUMMARY_ROWS+=("$SLUG|$VERDICT|$REASON")
  case "$VERDICT" in
    REAL_HUMAN_BROWSER) REAL=$((REAL+1));;
    BOT_DETECTED)       BOT=$((BOT+1));;
    *)                  INCON=$((INCON+1));;
  esac
done

if   [ "$BOT" -eq 0 ] && [ "$REAL" -ge 2 ]; then HEADLINE="REAL HUMAN BROWSER"
elif [ "$BOT" -ge 2 ]; then HEADLINE="BOT DETECTED"
elif [ "$BOT" -ge 1 ] && [ "$REAL" -ge 1 ]; then HEADLINE="MIXED (partial detection)"
else HEADLINE="INCONCLUSIVE"
fi

{
  printf '# Bot detection canary %s\n\nBridge: %s\nCDP: %s\nWait per site: %ss\n\n## Per-site verdicts\n\n| site | verdict | reason |\n|---|---|---|\n' \
    "$TS" "$BRIDGE_URL" "$CDP_URL" "$WAIT_SECS"
  for row in "${SUMMARY_ROWS[@]}"; do
    IFS='|' read -r s v r <<<"$row"
    printf '| %s | %s | %s |\n' "$s" "$v" "$r"
  done
  printf '\n## Headline\n\nAnticipy drives real Chrome and appears as: [%s]\n\n(real=%d bot=%d inconclusive=%d)\n\n## Signals flagged\n\n' \
    "$HEADLINE" "$REAL" "$BOT" "$INCON"
  for slug in sannysoft areyouheadless creepjs; do
    rj="$OUT_DIR/$slug/result.json"
    [ -f "$rj" ] && { printf '### %s\n\n```json\n' "$slug"; jq '.' "$rj" 2>/dev/null || cat "$rj"; printf '\n```\n\n'; }
  done
} > "$OUT_DIR/summary.md"

printf '\nWrote %s\n' "$OUT_DIR/summary.md"
printf 'Headline: %s (real=%d bot=%d inconclusive=%d)\n' \
  "$HEADLINE" "$REAL" "$BOT" "$INCON"
