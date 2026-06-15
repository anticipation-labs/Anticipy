#!/usr/bin/env bash
# Room 3 build: compile the SwiftUI app with SwiftPM (no Xcode) and assemble a
# launchable .app bundle.
set -euo pipefail

MACAPP="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_NAME=AnticipyApp
APP_NAME=Anticipy

echo "--- swift build -c release ---"
swift build -c release --package-path "$MACAPP"

BIN="$MACAPP/.build/release/$BIN_NAME"
test -x "$BIN" || { echo "FAIL: $BIN not built" >&2; exit 1; }

APP="$MACAPP/dist/$APP_NAME.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/$APP_NAME"
cp "$MACAPP/Resources/Info.plist" "$APP/Contents/Info.plist"
# bundle the launcher so the app can boot the engine + UI on open
cp "$MACAPP/Resources/boot.sh" "$APP/Contents/Resources/boot.sh"
chmod +x "$APP/Contents/Resources/boot.sh"

echo "--- PASS: built $APP ---"
ls -la "$APP/Contents/MacOS"
