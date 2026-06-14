#!/usr/bin/env bash
# package_app.sh — build the "Anticipy Execute" desktop app (DEV path).
#
# What this does TODAY (honest): builds the Next web front-end and stages a
# desktop-wrapper plan. The full desktop bundle (a Tauri shell around the engine
# + web) and a SIGNED/NOTARIZED public download are the live-deferred steps — they
# need an Apple Developer ID (Omar's account) and Apple notarization, which no
# script can fake. This script never produces a "signed" artifact it didn't sign;
# it prints exactly what is real vs. what is still gated.
#
# Usage: bash scripts/package_app.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== Anticipy Execute — packaging (dev) =="

# 1) Web front-end (real, runs now).
if command -v npm >/dev/null 2>&1; then
  echo "-- building the web app (next build)…"
  npm run build >/tmp/anticipy_web_build.log 2>&1 && echo "   web build OK (.next/)" \
    || { echo "   web build FAILED — see /tmp/anticipy_web_build.log"; exit 1; }
else
  echo "-- npm not found; skipping web build (install Node to build the front-end)."
fi

# 2) Desktop wrapper (Tauri preferred — small, native webview; no Chromium bundle).
echo "-- desktop wrapper plan (Tauri):"
if command -v cargo >/dev/null 2>&1 && command -v tauri >/dev/null 2>&1; then
  echo "   toolchain present — run: tauri build   (produces a DEV .app/.dmg, UNSIGNED)"
else
  echo "   NOT INSTALLED. To produce a dev .app:"
  echo "     1. install Rust (https://rustup.rs) + the Tauri CLI (cargo install tauri-cli)"
  echo "     2. scaffold src-tauri/ wrapping the engine (uvicorn) + the built web UI"
  echo "     3. tauri build  ->  an UNSIGNED dev .app the user opens via right-click → Open"
fi

# 3) Apple signing / notarization — THE live-deferred gate (needs Omar).
echo "-- signing + notarization (LIVE-DEFERRED — needs Omar's Apple Developer ID):"
if [[ -n "${APPLE_DEVELOPER_ID:-}" ]]; then
  echo "   APPLE_DEVELOPER_ID set; would: codesign --deep --options runtime --sign \"$APPLE_DEVELOPER_ID\" <app>"
  echo "                          then: xcrun notarytool submit … && xcrun stapler staple <app>"
  echo "   (NOT run here — wire into release once the cert + an app bundle exist.)"
else
  echo "   APPLE_DEVELOPER_ID is NOT set. A signed, one-click public download is BLOCKED on"
  echo "   Omar enrolling an Apple Developer account (\$99/yr) and providing the Developer ID."
  echo "   Until then the download page (/download) ships the dev build with the honest"
  echo "   'right-click → Open' preview banner. This is the only thing between us and a real download."
fi

echo "== done (dev). Real vs. gated printed above; nothing was faked. =="
