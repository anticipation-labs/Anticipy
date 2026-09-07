#!/bin/sh
# Which screen opens, and what the permission rows may say. Pure Foundation.
#
#   sh app/macos/Tests/run_onboarding_route_tests.sh
set -eu
here=$(cd "$(dirname "$0")" && pwd)
mac="$here/.."
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

cp "$here/OnboardingRouteTests.swift" "$out/main.swift"
xcrun swiftc -O -target arm64-apple-macos26.0 \
    "$mac/Anticipy/Library/OnboardingRoute.swift" \
    "$out/main.swift" \
    -o "$out/route-tests"
"$out/route-tests"
