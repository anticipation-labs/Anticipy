#!/bin/bash
# Build script for Anticipy Chrome Extension
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="$SCRIPT_DIR/../dist"
EXT_DIR="$DIST_DIR/anticipy-extension"

echo "Building Anticipy Chrome Extension..."

# Clean
rm -rf "$EXT_DIR" "$DIST_DIR/anticipy-extension.zip"
mkdir -p "$EXT_DIR"

# Copy files
cp "$SCRIPT_DIR/manifest.json" "$EXT_DIR/"
cp "$SCRIPT_DIR/background.js" "$EXT_DIR/"
cp "$SCRIPT_DIR/agent.js" "$EXT_DIR/"
cp "$SCRIPT_DIR/content.js" "$EXT_DIR/"
cp "$SCRIPT_DIR/world_patch.js" "$EXT_DIR/"
cp "$SCRIPT_DIR/engine_handshake.js" "$EXT_DIR/"
cp "$SCRIPT_DIR/popup.html" "$EXT_DIR/"
cp "$SCRIPT_DIR/popup.js" "$EXT_DIR/"
cp -r "$SCRIPT_DIR/icons" "$EXT_DIR/"

# Create zip
cd "$DIST_DIR"
zip -r anticipy-extension.zip anticipy-extension/

# Also copy zip to public/ for web download
PUBLIC_DIR="$SCRIPT_DIR/../public"
if [ -d "$PUBLIC_DIR" ]; then
  cp "$DIST_DIR/anticipy-extension.zip" "$PUBLIC_DIR/anticipy-extension.zip"
  echo "  Copied to: $PUBLIC_DIR/anticipy-extension.zip"
fi

echo ""
echo "Build complete!"
echo "  Extension: $EXT_DIR"
echo "  Zip: $DIST_DIR/anticipy-extension.zip"
echo ""
echo "To install:"
echo "  1. Open chrome://extensions/"
echo "  2. Enable 'Developer mode' (top right)"
echo "  3. Click 'Load unpacked'"
echo "  4. Select: $EXT_DIR"
