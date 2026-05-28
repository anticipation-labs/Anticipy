#!/usr/bin/env bash
# cost_audit.sh — verify product runtime cost stays under $200/year per heavy user
# at 100k complex tasks. Fails the cycle if over.
#
# Reads recent OpenRouter usage, divides by tasks run, extrapolates.

set -euo pipefail

if [ -z "${REPO:-}" ]; then
  REPO="$(git rev-parse --show-toplevel 2>/dev/null || (cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P))"
fi
cd "$REPO"

source scripts/load_env.sh
load_anticipy_env

python3 scripts/cost_audit.py "$@"
