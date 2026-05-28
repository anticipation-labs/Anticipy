#!/usr/bin/env bash
#
# Anticipy v6 native bridge installer for macOS.
#
# What it does (in order):
#   1. Verifies Python 3.10+ is available.
#   2. Creates ~/.anticipy/ with a virtualenv and pip-installs deps.
#   3. Copies anticipy_agent.py + protocol.py + native_bridge.py + engine/
#      into ~/.anticipy/.
#   4. Writes a launcher script /usr/local/bin/anticipy-agent that
#      activates the venv and runs the daemon.
#   5. Drops com.anticipy.agent.json into the NativeMessagingHosts dir
#      with __EXTENSION_ID__ replaced by the v6 pinned ID.
#   6. Prints next steps for loading the unpacked extension.
#
# Linux / Windows paths noted but NOT implemented. PRs welcome.

set -euo pipefail

# Pinned v6 extension ID. Derived from the RSA public key in
# extension_v4/manifest.json. DO NOT change without regenerating the key.
EXTENSION_ID="npnpagopediecennpleihemoochikggb"

ANTICIPY_HOME="${HOME}/.anticipy"
VENV_DIR="${ANTICIPY_HOME}/venv"
LAUNCHER="${ANTICIPY_HOME}/anticipy-agent"
LEGACY_LAUNCHER="/usr/local/bin/anticipy-agent"
NM_DIR="${HOME}/Library/Application Support/Google/Chrome/NativeMessagingHosts"

# Resolve native_host/ and engine/ relative to this script.  Supports two
# bundle layouts:
#   layout A (legacy):  bundle_root/{installer,native_host,engine}/
#   layout B (v6+):     bundle_root/DAEMON-INSTALLER/{install.sh,native_host,engine}/
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -d "${SCRIPT_DIR}/native_host" ]; then
  BUNDLE_ROOT="${SCRIPT_DIR}"
else
  BUNDLE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
fi
NATIVE_HOST_SRC="${BUNDLE_ROOT}/native_host"
ENGINE_SRC="${BUNDLE_ROOT}/engine"
EXTENSION_LOAD_DIR="${BUNDLE_ROOT}/EXTENSION-LOAD-THIS-IN-CHROME"
if [ ! -d "${EXTENSION_LOAD_DIR}" ] && [ -d "${BUNDLE_ROOT}/../EXTENSION-LOAD-THIS-IN-CHROME" ]; then
  EXTENSION_LOAD_DIR="$(cd "${BUNDLE_ROOT}/.." && pwd)/EXTENSION-LOAD-THIS-IN-CHROME"
fi

step() { printf "\033[1;36m==>\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m!! \033[0m %s\n" "$*" >&2; }
die()  { printf "\033[1;31m!! \033[0m %s\n" "$*" >&2; exit 1; }

wait_for_pid_exit() {
  local pid="$1"
  for _ in $(seq 1 40); do
    if ! kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
    sleep 0.25
  done
  return 1
}

stop_existing_bridge() {
  local pids=""
  pids="$pids $(lsof -tiTCP:7777 -sTCP:LISTEN 2>/dev/null || true)"
  pids="$pids $(pgrep -f "${ANTICIPY_HOME}/anticipy_agent.py" 2>/dev/null || true)"
  pids="$pids $(pgrep -f "${ANTICIPY_HOME}/anticipy-agent" 2>/dev/null || true)"
  pids="$pids $(pgrep -f "${LEGACY_LAUNCHER}" 2>/dev/null || true)"
  pids="$(printf '%s\n' $pids | awk 'NF && $1 != "'"$$"'" {seen[$1]=1} END {for (pid in seen) print pid}')"
  if [ -z "$pids" ]; then
    return 0
  fi
  step "Stopping prior native bridge PID(s): $(printf '%s' "$pids" | tr '\n' ' ')"
  printf '%s\n' "$pids" | xargs kill -TERM 2>/dev/null || true
  for pid in $pids; do
    wait_for_pid_exit "$pid" || true
  done
  local still_running=""
  for pid in $pids; do
    if kill -0 "$pid" 2>/dev/null; then
      still_running="$still_running $pid"
    fi
  done
  if [ -n "$still_running" ]; then
    warn "Force-stopping stubborn native bridge PID(s):$still_running"
    printf '%s\n' $still_running | xargs kill -KILL 2>/dev/null || true
  fi
}

# 0. Sanity ───────────────────────────────────────────────────────────────

case "$(uname -s)" in
  Darwin) ;;
  *) die "This installer supports macOS only. Linux/Windows: see README.md.";;
esac

if [ ! -d "${NATIVE_HOST_SRC}" ]; then
  die "Missing native_host/ next to installer/. Did you unzip the full bundle?"
fi

# 1. Python ───────────────────────────────────────────────────────────────

PY="$(command -v python3 || true)"
if [ -z "${PY}" ]; then
  die "Python 3.10+ not found. Install from https://www.python.org/downloads/ then re-run."
fi
PYV="$(${PY} -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PYMAJ="${PYV%%.*}"
PYMIN="${PYV##*.}"
if [ "${PYMAJ}" -lt 3 ] || { [ "${PYMAJ}" -eq 3 ] && [ "${PYMIN}" -lt 10 ]; }; then
  die "Python 3.10+ required (found ${PYV}). Install from python.org and re-run."
fi
step "Using Python ${PYV} at ${PY}"

# 2. Home + venv ──────────────────────────────────────────────────────────

step "Creating ${ANTICIPY_HOME}"
mkdir -p "${ANTICIPY_HOME}"
stop_existing_bridge

if [ ! -d "${VENV_DIR}" ]; then
  step "Creating venv"
  "${PY}" -m venv "${VENV_DIR}"
fi

# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade pip >/dev/null

# Minimal deps: no patchright, no browser-use. The daemon doesn't drive
# a browser; the extension does.  cryptography is needed by engine.app.config.
step "Installing Python dependencies"
pip install --quiet \
  "httpx>=0.25" \
  "cryptography>=41" \
  "supabase>=2.0" \
  "python-dotenv>=1.0"

# 3. Copy daemon files ────────────────────────────────────────────────────

step "Copying daemon files"
cp "${NATIVE_HOST_SRC}/anticipy_agent.py"  "${ANTICIPY_HOME}/anticipy_agent.py"
cp "${NATIVE_HOST_SRC}/protocol.py"        "${ANTICIPY_HOME}/protocol.py"
cp "${NATIVE_HOST_SRC}/native_bridge.py"   "${ANTICIPY_HOME}/native_bridge.py"
cp "${NATIVE_HOST_SRC}/__init__.py"        "${ANTICIPY_HOME}/__init__.py"
chmod +x "${ANTICIPY_HOME}/anticipy_agent.py"

if [ -d "${ENGINE_SRC}" ]; then
  step "Copying engine modules"
  rm -rf "${ANTICIPY_HOME}/engine"
  cp -R  "${ENGINE_SRC}" "${ANTICIPY_HOME}/engine"
else
  warn "engine/ not in bundle. Daemon will fail until you also place it at ${ANTICIPY_HOME}/engine"
fi

# 4. Launcher ─────────────────────────────────────────────────────────────

step "Writing launcher at ${LAUNCHER}"
cat > "${LAUNCHER}" <<EOF
#!/usr/bin/env bash
# Anticipy agent launcher generated by install.sh.
# Activates the venv so anticipy_agent.py imports cleanly, then execs it.
# stdio is piped directly to/from Chrome (do NOT print anything else!).
export PYTHONUNBUFFERED=1
exec "${VENV_DIR}/bin/python" "${ANTICIPY_HOME}/anticipy_agent.py"
EOF
chmod +x "${LAUNCHER}"

if [ -e "${LEGACY_LAUNCHER}" ] && [ -w "${LEGACY_LAUNCHER}" ]; then
  step "Refreshing legacy launcher at ${LEGACY_LAUNCHER}"
  cp "${LAUNCHER}" "${LEGACY_LAUNCHER}"
  chmod +x "${LEGACY_LAUNCHER}"
fi
[ -x "${LAUNCHER}" ] || die "Launcher not executable: ${LAUNCHER}"

# 5. Native messaging manifest ────────────────────────────────────────────

step "Installing native messaging manifest"
mkdir -p "${NM_DIR}"
cp "${NATIVE_HOST_SRC}/com.anticipy.agent.json" "${NM_DIR}/com.anticipy.agent.json"
"${PY}" - "${NM_DIR}/com.anticipy.agent.json" "${LAUNCHER}" "${EXTENSION_ID}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
launcher = sys.argv[2]
extension_id = sys.argv[3]
data = json.loads(path.read_text(encoding="utf-8"))
data["path"] = launcher
data["allowed_origins"] = [f"chrome-extension://{extension_id}/"]
path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PY

step "Manifest written to ${NM_DIR}/com.anticipy.agent.json"

# 6. Done ────────────────────────────────────────────────────────────────

cat <<EOF

================================================================
 Anticipy v6 native bridge installed.

 Next steps:
   1. Open chrome://extensions
   2. Toggle "Developer mode" (top-right)
   3. Click "Load unpacked"
   4. Pick the Chrome bridge folder from the bundle:
        ${EXTENSION_LOAD_DIR}

   The extension ID should appear as:
        ${EXTENSION_ID}

   (If you see a different ID, the pinned key was modified and the
    native-messaging manifest will refuse to launch the daemon.)

 Logs:  tail -f ~/Library/Logs/Anticipy/agent.log
================================================================
EOF
