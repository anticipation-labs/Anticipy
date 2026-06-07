#!/usr/bin/env bash
# Room 3 build: compile the SwiftUI app with SwiftPM (no Xcode) and assemble a
# launchable .app bundle. The bundle is signed so package checks catch resource
# seal regressions before anything is uploaded.
set -euo pipefail

MACAPP="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_NAME=AnticipyApp
APP_NAME=Anticipy
SIGN_IDENTITY="${ANTICIPY_CODESIGN_IDENTITY:--}"

echo "--- swift build -c release ---"
swift build -c release --package-path "$MACAPP"

BIN="$MACAPP/.build/release/$BIN_NAME"
test -x "$BIN" || { echo "FAIL: $BIN not built" >&2; exit 1; }

APP="$MACAPP/dist/$APP_NAME.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/$APP_NAME"
cp "$MACAPP/Resources/Info.plist" "$APP/Contents/Info.plist"

if command -v codesign >/dev/null 2>&1; then
  echo "--- codesign $APP ---"
  codesign --force --sign "$SIGN_IDENTITY" "$APP"
  codesign --verify --strict --verbose=2 "$APP"
else
  echo "WARN: codesign unavailable; built bundle is unsigned" >&2
fi

echo "--- PASS: built $APP ---"
ls -la "$APP/Contents/MacOS"
