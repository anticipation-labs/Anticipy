#!/usr/bin/env bash
# Refresh the verifier's local Anticipy install from the public production
# installer after a shipped bundled-code change. This keeps the local
# product surface on 127.0.0.1:8731 aligned with the public DMG.

set -euo pipefail

if [ -z "${REPO:-}" ]; then
  REPO="$(git rev-parse --show-toplevel 2>/dev/null || (cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P))"
fi
cd "$REPO"

mkdir -p state
TMP="$(mktemp -d)"
LOG="${ANTICIPY_REFRESH_LOG:-state/refresh-local-engine.log}"
cleanup() { rm -rf "$TMP" 2>/dev/null || true; }
trap cleanup EXIT

INSTALL_SH="$TMP/install.sh"
echo "[refresh-local] fetching production install.sh" | tee "$LOG"
curl -fsSL https://www.anticipy.ai/install.sh -o "$INSTALL_SH"
chmod +x "$INSTALL_SH"

echo "[refresh-local] running production installer" | tee -a "$LOG"
bash "$INSTALL_SH" 2>&1 | tee -a "$LOG"

echo "[refresh-local] verifying local engine health" | tee -a "$LOG"
for _ in $(seq 1 80); do
  if curl -fsS http://127.0.0.1:8731/health >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if ! curl -fsS http://127.0.0.1:8731/health | tee -a "$LOG"; then
  echo "[refresh-local] local engine did not become healthy" | tee -a "$LOG"
  exit 1
fi

echo "" | tee -a "$LOG"
echo "[refresh-local] local engine refreshed from public installer" | tee -a "$LOG"
