#!/usr/bin/env bash
# Check or ensure Chrome CDP on port 9222.

set -euo pipefail

MODE="${1:-check}"
PORT="${ANTICIPY_CDP_PORT:-9222}"

if curl -fsS "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1; then
  echo "chrome_cdp_ok port=$PORT"
  exit 0
fi

if [ "$MODE" != "ensure" ]; then
  echo "chrome_cdp_unavailable port=$PORT"
  exit 1
fi

open -na "Google Chrome" --args --remote-debugging-port="$PORT" --restore-last-session
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1; then
    echo "chrome_cdp_started port=$PORT"
    exit 0
  fi
  sleep 1
done

echo "chrome_cdp_start_failed port=$PORT"
exit 1
