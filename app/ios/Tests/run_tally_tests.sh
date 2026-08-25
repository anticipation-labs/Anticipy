#!/bin/sh
# Checks for ListenTally — what a day of listening did, folded out of the
# journal the session already wrote.
# Pure Foundation on purpose: no simulator, no scheme, no signing, no network.
#
#   sh app/ios/Tests/run_tally_tests.sh
#
# Exit code is the result. Non-zero means a case came back wrong.
set -e
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

# The tally DERIVES from the journal and must keep deriving. A counter
# incremented at a call site is a second source of truth that drifts the moment
# somebody adds an event and forgets it, and the journal is what a person
# actually exports and reads.
if grep -rn "ListenTally" "$app/Audio/PhoneListener.swift" 2>/dev/null; then
    echo "PhoneListener now writes to ListenTally directly."
    echo "The tally is a fold over what the journal already recorded. A parallel"
    echo "counter at the call sites drifts from the journal the first time an"
    echo "event is added without it, and the journal is the exported artifact."
    exit 2
fi

swiftc -O \
    "$app/Audio/ListenJournal.swift" \
    "$app/Audio/ListenTally.swift" \
    "$here/ListenTallyTests.swift" \
    -o "$out/tallytests"
"$out/tallytests"
