#!/bin/sh
# Checks that a refusal from the backend reaches the person carrying the
# SERVER's own sentence, not the client's guess at what went wrong.
#
#   sh app/ios/Tests/run_reset_message_tests.sh
#
# AnticipyBackend.swift is pure Foundation, so the REAL file compiles and runs
# here in about a second — no simulator, no scheme, no signing. Only the network
# is stubbed, by a URLProtocol that URLSession.shared honours.
#
# Exit code is the result. Non-zero means a case came back wrong.
set -e
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

backend="$app/Backend/AnticipyBackend.swift"

# The checks are worthless if the error stopped carrying the sentence at all.
if ! grep -q 'message: Self.serverMessage(data)' "$backend"; then
    echo "send() no longer attaches the server's sentence to the refusal."
    echo "Without it every non-2xx is anonymous again and the screen goes back"
    echo "to reciting one canned reason for three different failures."
    exit 2
fi

# CaptureEnvelope comes along because `pushEvent` takes one: it is what decides
# which capture instant each of the three columns gets, and it is pure
# Foundation like everything else here.
swiftc -O \
    "$app/Audio/CaptureEnvelope.swift" \
    "$backend" \
    "$here/ResetMessageTests.swift" \
    -o "$out/resetmessagetests"
"$out/resetmessagetests"
