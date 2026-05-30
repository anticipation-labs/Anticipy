#!/bin/bash
# Anticipy installer. The app is ad-hoc signed but not yet Apple-
# notarized, so a plain download is quarantined by macOS and shows
# "is damaged and can't be opened." This script downloads the real
# app, installs it to /Applications, and removes the quarantine
# attribute so it opens normally. This is the standard approach for
# un-notarized Mac software. Zero-friction-without-this-script needs
# Apple notarization (an Apple Developer account).
set -euo pipefail

URL="https://www.anticipy.ai/dl/Anticipy_1.0.0_aarch64.dmg"
BRIDGE_URL="https://www.anticipy.ai/anticipy-extension.zip"
EXTENSION_ID="npnpagopediecennpleihemoochikggb"
TMP="$(mktemp -d)"
DMG="$TMP/Anticipy.dmg"
BRIDGE_ZIP="$TMP/anticipy-extension.zip"
BRIDGE_DIR="$TMP/anticipy-extension"
ANTICIPY_HOME="$HOME/.anticipy"
VENV_DIR="$ANTICIPY_HOME/venv"
BRIDGE_LAUNCHER="$ANTICIPY_HOME/anticipy-agent"
LEGACY_BRIDGE_LAUNCHER="/usr/local/bin/anticipy-agent"
NM_DIR="$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts"
LOG="$ANTICIPY_HOME/product-engine.log"
PIDFILE="$ANTICIPY_HOME/product-engine.pid"

cleanup() { rm -rf "$TMP" 2>/dev/null || true; }
trap cleanup EXIT

wait_for_pid_exit() {
  pid="$1"
  for _ in $(seq 1 40); do
    if ! kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
    sleep 0.25
  done
  return 1
}

stop_existing_engine() {
  pids=""
  if [ -f "$PIDFILE" ]; then
    pids="$pids $(cat "$PIDFILE" 2>/dev/null || true)"
  fi
  pids="$pids $(lsof -tiTCP:8731 -sTCP:LISTEN 2>/dev/null || true)"
  pids="$pids $(pgrep -f '/Applications/Anticipy.app/Contents/MacOS/Anticipy' 2>/dev/null || true)"
  pids="$pids $(pgrep -f '/Applications/Anticipy.app/Contents/MacOS/anticipy-engine' 2>/dev/null || true)"

  pids="$(printf '%s\n' $pids | awk 'NF && $1 != "'"$$"'" {seen[$1]=1} END {for (pid in seen) print pid}')"
  if [ -n "$pids" ]; then
    echo "Anticipy: stopping prior local engine/app PID(s): $(printf '%s' "$pids" | tr '\n' ' ')"
    printf '%s\n' "$pids" | xargs kill -TERM 2>/dev/null || true
    for pid in $pids; do
      wait_for_pid_exit "$pid" || true
    done
    still_running=""
    for pid in $pids; do
      if kill -0 "$pid" 2>/dev/null; then
        still_running="$still_running $pid"
      fi
    done
    if [ -n "$still_running" ]; then
      echo "Anticipy: force-stopping stubborn prior PID(s):$still_running"
      printf '%s\n' $still_running | xargs kill -KILL 2>/dev/null || true
      for pid in $still_running; do
        wait_for_pid_exit "$pid" || true
      done
    fi
  fi
  rm -f "$PIDFILE"

  if lsof -tiTCP:8731 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Anticipy: port 8731 is still occupied after stop. Aborting install."
    lsof -nP -iTCP:8731 -sTCP:LISTEN || true
    exit 1
  fi
}

stop_existing_bridge() {
  pids=""
  pids="$pids $(lsof -tiTCP:7777 -sTCP:LISTEN 2>/dev/null || true)"
  pids="$pids $(pgrep -f "$ANTICIPY_HOME/anticipy_agent.py" 2>/dev/null || true)"
  pids="$pids $(pgrep -f "$BRIDGE_LAUNCHER" 2>/dev/null || true)"
  pids="$pids $(pgrep -f "$LEGACY_BRIDGE_LAUNCHER" 2>/dev/null || true)"
  pids="$(printf '%s\n' $pids | awk 'NF && $1 != "'"$$"'" {seen[$1]=1} END {for (pid in seen) print pid}')"
  if [ -z "$pids" ]; then
    return 0
  fi
  echo "Anticipy: stopping prior native bridge PID(s): $(printf '%s' "$pids" | tr '\n' ' ')"
  printf '%s\n' "$pids" | xargs kill -TERM 2>/dev/null || true
  for pid in $pids; do
    wait_for_pid_exit "$pid" || true
  done
  still_running=""
  for pid in $pids; do
    if kill -0 "$pid" 2>/dev/null; then
      still_running="$still_running $pid"
    fi
  done
  if [ -n "$still_running" ]; then
    echo "Anticipy: force-stopping stubborn native bridge PID(s):$still_running"
    printf '%s\n' $still_running | xargs kill -KILL 2>/dev/null || true
    for pid in $still_running; do
      wait_for_pid_exit "$pid" || true
    done
  fi
  if lsof -tiTCP:7777 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Anticipy: native bridge port 7777 is still occupied after stop. Aborting install."
    lsof -nP -iTCP:7777 -sTCP:LISTEN || true
    exit 1
  fi
}

install_native_bridge() {
  PY="$(command -v python3 || true)"
  if [ -z "$PY" ]; then
    echo "Anticipy: python3 is required for the Chrome native bridge. Aborting install."
    exit 1
  fi
  PYV="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
  PYMAJ="${PYV%%.*}"
  PYMIN="${PYV##*.}"
  # Stock macOS ships /usr/bin/python3 as 3.9. The bridge packages
  # (httpx>=0.25, cryptography>=41, supabase>=2.0, python-dotenv>=1.0)
  # all support Python 3.8+, so 3.9 is the right floor for zero-friction
  # stranger install. Per STRANGER_INSTALL_AUDIT W4 closed in cycle 129.
  if [ "$PYMAJ" -lt 3 ] || { [ "$PYMAJ" -eq 3 ] && [ "$PYMIN" -lt 9 ]; }; then
    echo "Anticipy: Python 3.9+ is required for the Chrome native bridge (found $PYV). Stock macOS Sonoma ships Python 3.9, so this should be present at /usr/bin/python3. If you removed it, reinstall the Xcode Command Line Tools: xcode-select --install"
    exit 1
  fi

  echo "Anticipy: installing/updating the Chrome native bridge..."
  curl -fL --retry 3 -o "$BRIDGE_ZIP" "$BRIDGE_URL"
  mkdir -p "$BRIDGE_DIR"
  unzip -q "$BRIDGE_ZIP" -d "$BRIDGE_DIR"

  NATIVE_HOST_SRC="$(find "$BRIDGE_DIR" -path '*/DAEMON-INSTALLER/native_host' -type d | head -1)"
  ENGINE_SRC="$(find "$BRIDGE_DIR" -path '*/DAEMON-INSTALLER/engine' -type d | head -1)"
  if [ -z "${NATIVE_HOST_SRC:-}" ] || [ ! -d "$NATIVE_HOST_SRC" ]; then
    echo "Anticipy: extension bundle is missing DAEMON-INSTALLER/native_host. Aborting install."
    exit 1
  fi

  mkdir -p "$ANTICIPY_HOME"
  if [ ! -d "$VENV_DIR" ]; then
    "$PY" -m venv "$VENV_DIR"
  fi
  # shellcheck source=/dev/null
  source "$VENV_DIR/bin/activate"
  python -m pip install --upgrade pip >/dev/null
  pip install --quiet \
    "httpx>=0.25" \
    "cryptography>=41" \
    "supabase>=2.0" \
    "python-dotenv>=1.0"

  cp "$NATIVE_HOST_SRC/anticipy_agent.py" "$ANTICIPY_HOME/anticipy_agent.py"
  cp "$NATIVE_HOST_SRC/protocol.py" "$ANTICIPY_HOME/protocol.py"
  cp "$NATIVE_HOST_SRC/native_bridge.py" "$ANTICIPY_HOME/native_bridge.py"
  cp "$NATIVE_HOST_SRC/__init__.py" "$ANTICIPY_HOME/__init__.py"
  chmod +x "$ANTICIPY_HOME/anticipy_agent.py"

  if [ -n "${ENGINE_SRC:-}" ] && [ -d "$ENGINE_SRC" ]; then
    rm -rf "$ANTICIPY_HOME/engine"
    cp -R "$ENGINE_SRC" "$ANTICIPY_HOME/engine"
  fi

  cat > "$BRIDGE_LAUNCHER" <<EOF
#!/usr/bin/env bash
# Anticipy agent launcher generated by public install.sh.
# stdio is piped directly to/from Chrome; do not print anything here.
export PYTHONUNBUFFERED=1
exec "$VENV_DIR/bin/python" "$ANTICIPY_HOME/anticipy_agent.py"
EOF
  chmod +x "$BRIDGE_LAUNCHER"

  if [ -e "$LEGACY_BRIDGE_LAUNCHER" ] && [ -w "$LEGACY_BRIDGE_LAUNCHER" ]; then
    cp "$BRIDGE_LAUNCHER" "$LEGACY_BRIDGE_LAUNCHER"
    chmod +x "$LEGACY_BRIDGE_LAUNCHER"
  fi

  mkdir -p "$NM_DIR"
  "$PY" - "$NM_DIR/com.anticipy.agent.json" "$BRIDGE_LAUNCHER" "$EXTENSION_ID" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
launcher = sys.argv[2]
extension_id = sys.argv[3]
data = {
    "name": "com.anticipy.agent",
    "description": "Anticipy local agent daemon",
    "path": launcher,
    "type": "stdio",
    "allowed_origins": [f"chrome-extension://{extension_id}/"],
}
path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PY
}

mkdir -p "$ANTICIPY_HOME"
stop_existing_engine
stop_existing_bridge

# B055: in v7 the Tauri .app self-bootstraps the bridge + engine on first
# launch. The legacy install_native_bridge call below installed the v6
# extension zip, which produced an architecture mismatch (v6 native_host
# overwriting v7's). Skip when the v7 app is already / about to be installed.
# Set ANTICIPY_LEGACY_BRIDGE=1 to opt back in if you depend on the v6 zip.
if [ "${ANTICIPY_LEGACY_BRIDGE:-0}" = "1" ]; then
  install_native_bridge
else
  echo "Anticipy: skipping legacy v6 bridge install (v7 app self-bootstraps; set ANTICIPY_LEGACY_BRIDGE=1 to force)."
fi

echo "Anticipy: downloading the real app (~2.3 GB; includes the local speech model)..."
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
/usr/bin/perl -MPOSIX=setsid -e '
  my ($pidfile, $log, $home, @cmd) = @ARGV;
  defined(my $pid = fork) or die "fork: $!";
  if ($pid) {
    open my $fh, ">", $pidfile or die $!;
    print $fh $pid;
    close $fh;
    exit 0;
  }
  setsid() or die "setsid: $!";
  chdir $home or die "chdir: $!";
  open STDIN, "<", "/dev/null";
  open STDOUT, ">>", $log or die "log $log: $!";
  open STDERR, ">&STDOUT" or die $!;
  $ENV{HOME} = $home;
  $ENV{ANTICIPY_HEADLESS} = 1;
  $ENV{ANTICIPY_PORT} = 8731;
  exec @cmd or die "exec: $!";
' "$PIDFILE" "$LOG" "$HOME" \
  /Applications/Anticipy.app/Contents/MacOS/Anticipy --server --port 8731

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
