#!/bin/sh
# The library reads what the recorder wrote. This compiles the REAL recorder
# (MeetingArchive) beside the library policy so the manifest shape is proven
# by the two meeting, not by a fixture somebody typed.
#
#   sh app/macos/Tests/run_meeting_library_tests.sh
set -eu
here=$(cd "$(dirname "$0")" && pwd)
mac="$here/.."
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

# swiftc permits top-level executable code only in a file named main.swift.
cp "$here/MeetingLibraryTests.swift" "$out/main.swift"
xcrun swiftc -O -target arm64-apple-macos26.0 \
    "$mac/Anticipy/Capture/MeetingLinePolicy.swift" \
    "$mac/Anticipy/Library/MeetingLibrary.swift" \
    "$mac/AnticipyMac/MeetingArchive.swift" \
    "$out/main.swift" \
    -o "$out/library-tests"
mkdir -p "$out/meetings"
"$out/library-tests" "$out/meetings"
