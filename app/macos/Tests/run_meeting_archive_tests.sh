#!/bin/sh
set -eu
here=$(cd "$(dirname "$0")" && pwd)
mac="$here/.."
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

# swiftc permits top-level executable code only in a file named main.swift.
cp "$here/MeetingArchiveTests.swift" "$out/main.swift"
xcrun swiftc -O -target arm64-apple-macos26.0 \
    "$mac/Anticipy/Capture/MeetingLinePolicy.swift" \
    "$mac/AnticipyMac/MeetingArchive.swift" \
    "$out/main.swift" \
    -o "$out/archive-tests"
mkdir -p "$out/meetings"
"$out/archive-tests" "$out/meetings"
