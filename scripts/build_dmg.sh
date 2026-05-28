#!/usr/bin/env bash
# build_dmg.sh - build the packaged Mac app and place the DMG where ship.sh expects it.

set -euo pipefail

if [ -z "${REPO:-}" ]; then
  REPO="$(git rev-parse --show-toplevel 2>/dev/null || (cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P))"
fi
cd "$REPO"

export ANTICIPY_BUILD_COMMIT="${ANTICIPY_BUILD_COMMIT:-$(git rev-parse HEAD)}"
echo "[build_dmg] Embedding build commit ${ANTICIPY_BUILD_COMMIT}"

echo "[build_dmg] Building PyInstaller engine sidecar"
bash desktop/scripts/build-engine-sidecar.sh

echo "[build_dmg] Staging Parakeet ASR model resources"
bash desktop/scripts/bundle-parakeet-model.sh

echo "[build_dmg] Building Tauri app bundle and DMG"
cd desktop
node ./scripts/tauri.mjs build --target aarch64-apple-darwin
cd "$REPO"

DMG_PATH=$(find -L desktop/target desktop/src-tauri/target -name "Anticipy_*.dmg" -type f 2>/dev/null | sort | tail -1)
[ -f "$DMG_PATH" ] || { echo "[build_dmg] DMG not found"; exit 1; }

mkdir -p target/release/bundle/dmg
cp "$DMG_PATH" "target/release/bundle/dmg/$(basename "$DMG_PATH")"
echo "[build_dmg] wrote target/release/bundle/dmg/$(basename "$DMG_PATH")"
