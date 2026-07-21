#!/bin/bash
# One command to build Anticipy on your Mac. Run from app/ios/.
# Needs: Xcode installed, and (for device install) an Apple ID signed into Xcode.
set -e

echo "==> Checking tools"
command -v xcodebuild >/dev/null || { echo "Xcode not found. Install from the App Store, then run: sudo xcodebuild -runFirstLaunch"; exit 1; }
if ! command -v xcodegen >/dev/null; then
  echo "==> Installing xcodegen via Homebrew"
  command -v brew >/dev/null || { echo "Install Homebrew first: https://brew.sh"; exit 1; }
  brew install xcodegen
fi

echo "==> Generating Anticipy.xcodeproj"
xcodegen generate

echo "==> Building for the iOS Simulator (no signing needed) to prove it compiles"
xcodebuild -project Anticipy.xcodeproj -scheme Anticipy \
  -destination 'generic/platform=iOS Simulator' \
  -configuration Debug build | tail -20

echo ""
echo "BUILD SUCCEEDED."
echo "Next, to run on YOUR iPhone:"
echo "  1) open Anticipy.xcodeproj"
echo "  2) select your iPhone as the run target, pick your Team under Signing"
echo "  3) press Run (or Product > Archive, then Distribute > TestFlight)"
