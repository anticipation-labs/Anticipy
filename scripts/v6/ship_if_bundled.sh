#!/usr/bin/env bash
# Ship only when a merged change touched code that affects production or DMG.

set -euo pipefail

REPO="${REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"
cd "$REPO"

BEFORE="${BEFORE:-HEAD~1}"
AFTER="${AFTER:-HEAD}"

changed=$(git diff --name-only "$BEFORE" "$AFTER" || true)
if printf '%s\n' "$changed" | rg -q '^(engine/|desktop/|src-tauri/|src/app/|src/lib/|public/|package.json|pnpm-lock.yaml|scripts/build_dmg.sh|scripts/ship.sh)'; then
  bash scripts/ship.sh
  if [ "${ANTICIPY_REFRESH_LOCAL_AFTER_SHIP:-1}" = "1" ]; then
    bash scripts/v6/refresh_local_engine_from_public.sh
  fi
else
  git push origin HEAD:main
fi
