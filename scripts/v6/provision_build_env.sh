#!/usr/bin/env bash
# Idempotent build-environment provisioning for V6.

set -euo pipefail

REPO="${REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"
cd "$REPO"

if [ -f scripts/load_env.sh ]; then
  . scripts/load_env.sh
  load_anticipy_env || true
fi

if [ -d engine ]; then
  PYTHON_BIN="${PYTHON_BIN:-}"
  if [ -z "$PYTHON_BIN" ] && [ -f engine/.python-version ]; then
    py_ver="$(tr -d '[:space:]' < engine/.python-version)"
    if [ -x "$HOME/.pyenv/versions/$py_ver/bin/python3" ]; then
      PYTHON_BIN="$HOME/.pyenv/versions/$py_ver/bin/python3"
    fi
  fi
  PYTHON_BIN="${PYTHON_BIN:-python3}"
  if [ -x engine/.venv/bin/python ]; then
    venv_ver=$(engine/.venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    req_ver=$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    if [ "$venv_ver" != "$req_ver" ]; then
      rm -rf engine/.venv
    fi
  fi
  "$PYTHON_BIN" -m venv engine/.venv
  engine/.venv/bin/python -m pip install --upgrade pip setuptools wheel
  if [ -f engine/requirements.txt ]; then
    engine/.venv/bin/pip install -r engine/requirements.txt
  fi
  engine/.venv/bin/pip install pyinstaller parakeet-mlx >/dev/null
fi

if [ -d desktop ]; then
  (cd desktop && pnpm install)
fi

echo "provision_build_env_ok"
