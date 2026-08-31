#!/bin/sh
# Build a universal, hardened, Developer-ID-signed Anticipy Mac app. When the
# three NOTARY_* variables are supplied, submit that exact archive to Apple,
# staple the accepted ticket, rebuild the zip, and Gatekeeper-check it.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../../.." && pwd)
ios="$repo/app/ios"
output_dir=${1:-"$repo/build/macos"}
identity=${MAC_SIGNING_IDENTITY:-"Developer ID Application: Omar Ebrahim (49T86P9XGW)"}
team=${DEVELOPMENT_TEAM:-"49T86P9XGW"}
derived=$(mktemp -d)
trap 'rm -rf "$derived"' EXIT

mkdir -p "$output_dir"
cd "$ios"
xcodegen generate
xcodebuild -project Anticipy.xcodeproj -scheme AnticipyMac \
    -configuration Release -destination 'generic/platform=macOS' \
    -derivedDataPath "$derived" ARCHS='arm64 x86_64' ONLY_ACTIVE_ARCH=NO \
    DEVELOPMENT_TEAM="$team" CODE_SIGN_STYLE=Manual \
    CODE_SIGN_IDENTITY="$identity" build

app="$derived/Build/Products/Release/AnticipyMac.app"
zip="$output_dir/Anticipy-for-Mac.zip"
codesign --verify --deep --strict --verbose=2 "$app"
test "$(lipo -archs "$app/Contents/MacOS/AnticipyMac")" = "x86_64 arm64"
test -n "$(/usr/libexec/PlistBuddy -c 'Print :NSAudioCaptureUsageDescription' "$app/Contents/Info.plist")"
ditto -c -k --keepParent "$app" "$zip"

if [ -n "${NOTARY_KEY_PATH:-}" ] && [ -n "${NOTARY_KEY_ID:-}" ] \
   && [ -n "${NOTARY_ISSUER_ID:-}" ]; then
    xcrun notarytool submit "$zip" --wait \
        --key "$NOTARY_KEY_PATH" --key-id "$NOTARY_KEY_ID" \
        --issuer "$NOTARY_ISSUER_ID"
    xcrun stapler staple "$app"
    ditto -c -k --keepParent "$app" "$zip"
    xcrun stapler validate "$app"
    spctl -a -vvv -t exec "$app"
fi

shasum -a 256 "$zip"
echo "$zip"
