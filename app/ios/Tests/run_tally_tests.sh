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

# THE SCREEN MUST HAND OVER ITS CLOCK. `ListenTally.of` is pure and takes the
# reading moment as an argument, defaulted so the checks below keep their
# meaning. On the day this whole type exists for, the journal's last line IS the
# failure — a call took the microphone at 09:00, nothing restarted listening,
# and there are no later events — so a caller that passes no clock gets "58 min"
# for a phone that has heard nothing in eleven hours. Every check in the suite
# can be green over that: they measure the fold, and this measures the wiring.
view="$app/Views/ListeningDiagnosticsView.swift"
if ! grep -vE '^[[:space:]]*//' "$view" | tr '\n' ' ' \
    | grep -q 'ListenTally\.of([^)]*now:'; then
    echo "The diagnostics screen folds the day without saying when it is being read."
    echo "The last line of a journal from a phone that went deaf at nine in the"
    echo "morning is the nine o'clock stop. Measured to that, the answer is the"
    echo "58 quiet minutes BEFORE the call, and the eleven deaf hours after it"
    echo "are unmeasurable by construction. Pass the clock."
    exit 2
fi

swiftc -O \
    "$app/Audio/ListenJournal.swift" \
    "$app/Audio/ListenTally.swift" \
    "$here/ListenTallyTests.swift" \
    -o "$out/tallytests"
"$out/tallytests"
