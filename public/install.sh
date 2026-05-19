#!/bin/bash
# Anticipy installer. The app is ad-hoc signed but not yet Apple-
# notarized, so a plain download is quarantined by macOS and shows
# "is damaged and can't be opened." This script downloads the real
# app, installs it to /Applications, and removes the quarantine
# attribute so it opens normally. This is the standard approach for
# un-notarized Mac software. Zero-friction-without-this-script needs
# Apple notarization (an Apple Developer account).
set -euo pipefail

URL="https://www.anticipy.ai/download"
TMP="$(mktemp -d)"
DMG="$TMP/Anticipy.dmg"
ANTICIPY_HOME="$HOME/.anticipy"
LOG="$ANTICIPY_HOME/product-engine.log"
PIDFILE="$ANTICIPY_HOME/product-engine.pid"
LABEL="ai.anticipy.engine"
LAUNCH_AGENT_DIR="$HOME/Library/LaunchAgents"
PLIST="$LAUNCH_AGENT_DIR/$LABEL.plist"

cleanup() { rm -rf "$TMP" 2>/dev/null || true; }
trap cleanup EXIT

stop_existing_engine() {
  launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "Anticipy: stopping prior local engine PID $(cat "$PIDFILE") ..."
    kill -TERM "$(cat "$PIDFILE")" 2>/dev/null || true
    for _ in $(seq 1 40); do
      if ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        break
      fi
      sleep 0.25
    done
  fi
  rm -f "$PIDFILE"
}

mkdir -p "$ANTICIPY_HOME"
mkdir -p "$LAUNCH_AGENT_DIR"
stop_existing_engine

echo "Anticipy: downloading the real app (~609 MB)..."
curl -fL --retry 3 -o "$DMG" "$URL"

# Sanity: a real disk image, not a truncated/parked file.
if ! hdiutil imageinfo "$DMG" >/dev/null 2>&1; then
  echo "Download did not produce a valid disk image. Aborting (nothing installed)."
  exit 1
fi

echo "Anticipy: mounting..."
MNT="$(hdiutil attach "$DMG" -nobrowse -readonly | grep -o '/Volumes/.*' | head -1)"
APP="$(/bin/ls -d "$MNT"/*.app 2>/dev/null | head -1)"
if [ -z "${APP:-}" ]; then
  hdiutil detach "$MNT" -quiet 2>/dev/null || true
  echo "No .app found in the image. Aborting."
  exit 1
fi

echo "Anticipy: installing to /Applications..."
rm -rf "/Applications/Anticipy.app" 2>/dev/null || true
cp -R "$APP" /Applications/
hdiutil detach "$MNT" -quiet 2>/dev/null || true

echo "Anticipy: clearing the macOS quarantine flag..."
xattr -dr com.apple.quarantine "/Applications/Anticipy.app" 2>/dev/null || true

echo "Anticipy: starting the local engine on http://127.0.0.1:8731 ..."
cat >"$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Applications/Anticipy.app/Contents/MacOS/Anticipy</string>
    <string>--server</string>
    <string>--port</string>
    <string>8731</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>ANTICIPY_HEADLESS</key>
    <string>1</string>
    <key>ANTICIPY_PORT</key>
    <string>8731</string>
    <key>HOME</key>
    <string>$HOME</string>
  </dict>
  <key>WorkingDirectory</key>
  <string>$HOME</string>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG</string>
  <key>StandardErrorPath</key>
  <string>$LOG</string>
</dict>
</plist>
EOF

launchctl bootstrap "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || {
  launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
}
launchctl enable "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
launchctl kickstart -k "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true

for _ in $(seq 1 80); do
  if curl -fsS "http://127.0.0.1:8731/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if ! curl -fsS "http://127.0.0.1:8731/health" >/dev/null 2>&1; then
  echo "Anticipy engine did not become healthy. Log:"
  tail -80 "$LOG" 2>/dev/null || true
  exit 1
fi

lsof -tiTCP:8731 -sTCP:LISTEN > "$PIDFILE" 2>/dev/null || true

echo ""
echo "Done. Anticipy is installed and the local engine is running."
echo "Health: http://127.0.0.1:8731/health"
echo "Log: $LOG"
