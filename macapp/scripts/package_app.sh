#!/usr/bin/env bash
# Build the local macOS bundle and package it for the download front door.
set -euo pipefail

MACAPP="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(cd "$MACAPP/.." && pwd)"
APP="$MACAPP/dist/Anticipy.app"
OUT_DIR="$REPO/public/downloads"
OUT="$OUT_DIR/Anticipy-mac.zip"

bash "$MACAPP/scripts/build_app.sh"

mkdir -p "$OUT_DIR"
rm -f "$OUT"
(
  cd "$MACAPP/dist"
  ditto -c -k --sequesterRsrc --keepParent "Anticipy.app" "$OUT"
)

echo "--- PASS: packaged $OUT ---"
ls -lh "$OUT"
shasum -a 256 "$OUT"
