#!/usr/bin/env bash
# Bounded disk cleanup for V6 cycles.

set -euo pipefail

REPO="${REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"
cd "$REPO"

mkdir -p state

if [ -d target/release/bundle/dmg ]; then
  find target/release/bundle/dmg -name "Anticipy_*.dmg" -type f -mtime +1 -delete
fi

if [ -d .worktrees ]; then
  find .worktrees -mindepth 1 -maxdepth 1 -type d -mtime +3 -exec rm -rf {} +
fi

free_kb=$(df -k . | awk 'NR==2 {print $4}')
if [ "${free_kb:-0}" -lt 2097152 ]; then
  mkdir -p state/decisions
  {
    echo "## $(date -u +%Y-%m-%dT%H:%M:%SZ) - Disk pressure"
    echo
    echo "Less than 2GB free in the repo volume after bounded cleanup."
    echo "Default: continue the current cycle and let build steps fail loudly if space is insufficient."
  } >> state/decisions/queue.md
fi
