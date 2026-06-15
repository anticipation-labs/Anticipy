#!/usr/bin/env bash
# Anticipy Execute — dev launcher. When the app opens, this boots the local engine
# (port 8787) and the web interface (port 3000) if they aren't already running, then
# exits once the UI is reachable so the app can show it.
#
# HONEST STATUS: this dev preview launches the engine + UI from the repo on THIS Mac.
# A distributable build bundles the engine + a prebuilt UI inside the .app (and is
# Apple-signed/notarized) — that bundling + signing is the remaining packaging work.
set -u
REPO="${ANTICIPY_REPO:-/Users/omarebrahim/Anticipy}"
cd "$REPO" 2>/dev/null || { echo "repo not found: $REPO" >&2; exit 2; }

# 1) engine on 8787
if ! curl -s -m2 http://127.0.0.1:8787/readiness >/dev/null 2>&1; then
  ANTICIPY_HANDS_MODE=mock ANTICIPY_CHANNELS_MODE=mock PYTHONPATH="$REPO/engine" \
    nohup "$REPO/engine/.venv/bin/python" -m uvicorn --app-dir "$REPO/engine" \
    anticipy_engine.main:app --port 8787 >/tmp/anticipy_engine.log 2>&1 &
fi

# 2) web UI on 3000
if ! curl -s -m2 http://127.0.0.1:3000 >/dev/null 2>&1; then
  ANTICIPY_ENGINE_URL=http://127.0.0.1:8787 nohup npm run dev >/tmp/anticipy_web.log 2>&1 &
fi

# 3) wait until the interface answers (engine boots fast; next dev compiles on first hit)
for i in $(seq 1 120); do
  if curl -s -m2 http://127.0.0.1:3000 >/dev/null 2>&1; then echo "ready"; exit 0; fi
  sleep 1
done
echo "timed out waiting for the interface" >&2
exit 1
