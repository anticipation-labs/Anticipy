#!/bin/sh
# Checks for HeardGroup — the layer that turns the wall of heard lines into
# one card per conversation. HeardGroup.swift is pure Foundation on purpose, so
# this needs no simulator, no scheme, no signing and no network: it compiles
# and runs in about a second.
#
#   sh app/ios/Tests/run_heard_tests.sh
#
# Exit code is the result. Non-zero means a case came back wrong.
set -e
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

# The tests stand in a fake AnticipySession.TranscriptLine, because the real one
# lives inside a @MainActor class that drags in SwiftUI, Combine, the network
# layer and the microphone. A stand-in is only honest while it matches, so the
# two declarations are compared field for field before anything is compiled.
fields() {
    awk '/struct TranscriptLine/,/^ *}$/' "$1" \
        | sed 's,//.*,,' \
        | grep -E '^[[:space:]]*(let|var) ' \
        | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
}
fields "$app/AnticipyApp.swift" > "$out/real.txt"
fields "$here/HeardGroupTests.swift" > "$out/stub.txt"
if ! diff -u "$out/real.txt" "$out/stub.txt" > "$out/drift.txt"; then
    echo "TranscriptLine has drifted from the stand-in these checks compile against:"
    cat "$out/drift.txt"
    echo "Update Tests/HeardGroupTests.swift to match, then re-run."
    exit 2
fi
echo "TranscriptLine stand-in matches the real declaration ($(wc -l < "$out/real.txt" | tr -d ' ') fields)"

# CaptureSourcePolicy rides along because HeardGroup.ear asks it which sources
# earn a badge — deciding that in two places is how a "Pendant" label ends up on
# a phone-mic conversation.
swiftc -O \
    "$app/Audio/CaptureSourcePolicy.swift" \
    "$app/Views/HeardGroup.swift" \
    "$here/HeardGroupTests.swift" \
    -o "$out/heardtests"
"$out/heardtests"
