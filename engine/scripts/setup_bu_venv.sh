#!/usr/bin/env bash
# Reproducibly (re)build the DURABLE 3.11 browser-use bridge venv.
#
# Slice 6 step 3. The open-source browser arm (browser-use, MIT) needs Python
# >=3.11 but the engine runs on 3.10 — so browser-use lives in its OWN venv that
# the engine shells out to (never imports). This script rebuilds that venv.
#
# Path: engine/.bu-venv (gitignored; NEVER commit it). Does NOT touch engine/.venv.
#
# Usage:
#   bash engine/scripts/setup_bu_venv.sh
#
# Production note (no pyenv): the bones are just
#   python3.11 -m venv engine/.bu-venv
#   engine/.bu-venv/bin/pip install "browser-use==0.13.1"
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="$REPO/engine/.bu-venv"
BROWSER_USE_VERSION="0.13.1"   # the PROVEN version (RECEIPTS.md)

# Prefer pyenv's 3.11 if present (this machine), else any python3.11 on PATH.
PY311="$HOME/.pyenv/versions/3.11.12/bin/python3.11"
if [ ! -x "$PY311" ]; then
  PY311="$(command -v python3.11 || true)"
fi
if [ -z "${PY311:-}" ] || [ ! -x "$PY311" ]; then
  echo "ERROR: python3.11 not found (need >=3.11 for browser-use)." >&2
  echo "Install it (e.g. 'pyenv install 3.11.12') and re-run." >&2
  exit 1
fi

echo "Using interpreter: $PY311 ($("$PY311" --version 2>&1))"
echo "Building durable bridge venv at: $VENV"

if [ -d "$VENV" ]; then
  echo "venv already exists; reusing. (rm -rf '$VENV' first for a clean rebuild)"
else
  "$PY311" -m venv "$VENV"
fi

"$VENV/bin/python" -m pip install --upgrade pip --quiet
"$VENV/bin/pip" install "browser-use==${BROWSER_USE_VERSION}"

echo
echo "Verifying import + version..."
"$VENV/bin/python" - <<'PY'
import importlib.metadata as m
from browser_use import Agent, BrowserProfile, BrowserSession, ChatOpenAI  # noqa: F401
print("OK: browser-use", m.version("browser-use"), "imports under", __import__("sys").version.split()[0])
PY

echo
echo "DONE. Bridge python: $VENV/bin/python"
echo "Engine env override (optional): export ANTICIPY_BROWSERUSE_PYTHON='$VENV/bin/python'"
