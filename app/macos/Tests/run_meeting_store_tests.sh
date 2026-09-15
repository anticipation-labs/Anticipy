#!/bin/sh
set -eu
here=$(cd "$(dirname "$0")" && pwd)
mac="$here/.."
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
xcrun swiftc -parse-as-library -target arm64-apple-macos26.0 \
    "$mac/Anticipy/Capture/MeetingLinePolicy.swift" \
    "$mac/Anticipy/Library/MeetingLibrary.swift" \
    "$mac/AnticipyMac/MeetingArchive.swift" \
    "$mac/AnticipyMac/MeetingStore.swift" \
    "$here/MeetingStoreTests.swift" -o "$out/store-tests"
"$out/store-tests"
