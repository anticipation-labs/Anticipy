#!/bin/bash
set -e

# Start Xvfb for headful display
Xvfb :99 -screen 0 1920x1080x24 &
XVFB_PID=$!
export DISPLAY=:99

# Wait until Xvfb is actually accepting connections; uvicorn (and Chromium
# launches it triggers) must not start before X is up
for _ in $(seq 1 30); do
  if xdpyinfo -display :99 >/dev/null 2>&1; then
    break
  fi
  sleep 0.1
done

# If Xvfb dies, kill the container (so the orchestrator restarts us cleanly
# instead of running a broken display)
trap "kill -TERM $XVFB_PID 2>/dev/null || true" EXIT

# Start the FastAPI server
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
