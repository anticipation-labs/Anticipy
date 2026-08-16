#!/bin/sh
# What one recognizer callback costs, measured rather than asserted.
# TranscriptCursor runs on the main thread inside the speech callback, so the
# number that matters is whether the mean moves as the request gets longer.
#
#   sh app/ios/Tests/run_cursor_bench.sh
#
# Prints; never fails. There is no threshold here on purpose — a timing gate on
# a shared machine is a flaky test, and the shape of the curve is the finding.
set -e
here=$(cd "$(dirname "$0")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
swiftc -O \
    "$here/../Anticipy/Audio/TranscriptCursor.swift" \
    "$here/TranscriptCursorBench.swift" \
    -o "$out/cursorbench"
"$out/cursorbench"
