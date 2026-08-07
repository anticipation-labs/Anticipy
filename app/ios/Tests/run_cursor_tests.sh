#!/bin/sh
# Checks for TranscriptCursor — the layer that decides which words the phone
# has already said out loud. TranscriptCursor.swift is pure Foundation on
# purpose, so this needs no simulator, no scheme, no signing and no network: it
# compiles and runs in about a second.
#
#   sh app/ios/Tests/run_cursor_tests.sh
#
# Exit code is the result. Non-zero means a case came back wrong.
set -e
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

# The checks are worthless if the app has quietly stopped using the cursor and
# gone back to counting words. Prove the wiring before proving the logic.
listener="$app/Audio/PhoneListener.swift"
if [ ! -f "$listener" ]; then
    echo "PhoneListener.swift is missing — there is nothing for the cursor to serve."
    exit 2
fi
if ! grep -q 'TranscriptCursor' "$listener"; then
    echo "PhoneListener.swift does not use TranscriptCursor."
    echo "The type can be perfect and the phone will still send one sentence twice."
    exit 2
fi
if grep -qE '^[[:space:]]*(private[[:space:]]+)?var emittedWords' "$listener"; then
    echo "PhoneListener.swift still carries an integer word cursor (emittedWords)."
    echo "Two sources of truth is the bug, not a safety net."
    exit 2
fi
echo "PhoneListener is wired to TranscriptCursor and keeps no word count of its own"

swiftc -O \
    "$app/Audio/TranscriptCursor.swift" \
    "$here/TranscriptCursorTests.swift" \
    -o "$out/cursortests"
"$out/cursortests"
