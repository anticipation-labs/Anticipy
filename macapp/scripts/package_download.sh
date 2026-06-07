#!/usr/bin/env bash
set -euo pipefail

MACAPP="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="$(cd "$MACAPP/.." && pwd)"
APP="$MACAPP/dist/Anticipy.app"
OUT_DIR="$ROOT/public/downloads"
ZIP="$OUT_DIR/Anticipy-mac.zip"

bash "$MACAPP/scripts/build_app.sh"

if command -v codesign >/dev/null 2>&1; then
  codesign --force --deep --sign - "$APP"
  codesign --verify --deep --strict --verbose=2 "$APP"
fi

mkdir -p "$OUT_DIR"
rm -f "$ZIP" "$ZIP.sha256"
ditto -c -k --keepParent "$APP" "$ZIP"
shasum -a 256 "$ZIP" > "$ZIP.sha256"

ls -lh "$ZIP" "$ZIP.sha256"
