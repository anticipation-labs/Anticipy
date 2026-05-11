#!/usr/bin/env bash
#
# Anticipy v4 uninstaller — reverses what install.sh did.

set -euo pipefail

ANTICIPY_HOME="${HOME}/.anticipy"
LAUNCHER="/usr/local/bin/anticipy-agent"
NM_DIR="${HOME}/Library/Application Support/Google/Chrome/NativeMessagingHosts"
NM_FILE="${NM_DIR}/com.anticipy.agent.json"

step() { printf "\033[1;36m==>\033[0m %s\n" "$*"; }

step "Removing native messaging manifest"
[ -f "${NM_FILE}" ] && rm -f "${NM_FILE}" || true

step "Removing launcher"
if [ -f "${LAUNCHER}" ]; then
  if [ -w "${LAUNCHER}" ]; then
    rm -f "${LAUNCHER}"
  else
    sudo rm -f "${LAUNCHER}"
  fi
fi

step "Removing ${ANTICIPY_HOME}"
[ -d "${ANTICIPY_HOME}" ] && rm -rf "${ANTICIPY_HOME}" || true

cat <<EOF

================================================================
 Anticipy v4 uninstalled.
 Manually remove the extension at chrome://extensions if desired.
================================================================
EOF
