#!/bin/bash
# Anticipy installer. The app is ad-hoc signed but not yet Apple-
# notarized, so a plain download is quarantined by macOS and shows
# "is damaged and can't be opened." This script downloads the real
# app, installs it to /Applications, and removes the quarantine
# attribute so it opens normally. This is the standard approach for
# un-notarized Mac software. Zero-friction-without-this-script needs
# Apple notarization (an Apple Developer account).
set -euo pipefail

URL="https://www.anticipy.ai/download"
TMP="$(mktemp -d)"
DMG="$TMP/Anticipy.dmg"

cleanup() { rm -rf "$TMP" 2>/dev/null || true; }
trap cleanup EXIT

echo "Anticipy: downloading the real app (~96 MB)..."
curl -fL --retry 3 -o "$DMG" "$URL"

# Sanity: a real disk image, not a truncated/parked file.
if ! hdiutil imageinfo "$DMG" >/dev/null 2>&1; then
  echo "Download did not produce a valid disk image. Aborting (nothing installed)."
  exit 1
fi

echo "Anticipy: mounting..."
MNT="$(hdiutil attach "$DMG" -nobrowse -readonly | grep -o '/Volumes/.*' | head -1)"
APP="$(/bin/ls -d "$MNT"/*.app 2>/dev/null | head -1)"
if [ -z "${APP:-}" ]; then
  hdiutil detach "$MNT" -quiet 2>/dev/null || true
  echo "No .app found in the image. Aborting."
  exit 1
fi

echo "Anticipy: installing to /Applications..."
rm -rf "/Applications/Anticipy.app" 2>/dev/null || true
cp -R "$APP" /Applications/
hdiutil detach "$MNT" -quiet 2>/dev/null || true

echo "Anticipy: clearing the macOS quarantine flag..."
xattr -dr com.apple.quarantine "/Applications/Anticipy.app" 2>/dev/null || true

echo ""
echo "Done. Anticipy is installed in your Applications folder and"
echo "will open normally (no 'damaged' warning)."
open "/Applications/Anticipy.app" 2>/dev/null || true
