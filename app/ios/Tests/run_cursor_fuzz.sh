#!/bin/sh
# Randomised DIFFERENTIAL fuzz for TranscriptCursor: every generated schedule
# is run through the current cursor AND through the HEAD~1 integer cursor it
# replaced, and the run fails if the new one deletes a word the old one kept.
#
#   sh app/ios/Tests/run_cursor_fuzz.sh              # 100k sequences, fixed seed
#   sh app/ios/Tests/run_cursor_fuzz.sh 500000       # more
#   sh app/ios/Tests/run_cursor_fuzz.sh 100000 1234  # a different seed
#
# Exit code is the result. The seed is printed so any failure reproduces.
set -e
here=$(cd "$(dirname "$0")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
swiftc -O \
    "$here/../Anticipy/Audio/TranscriptCursor.swift" \
    "$here/TranscriptCursorFuzz.swift" \
    -o "$out/cursorfuzz"
"$out/cursorfuzz" "$@"
