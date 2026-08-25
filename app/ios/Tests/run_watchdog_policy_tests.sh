#!/bin/sh
# Checks for ListenWatchdogPolicy — what the 4-second watchdog does about the
# state it finds.
# Pure Foundation on purpose: no simulator, no scheme, no signing, no network,
# and no device that has to receive a real phone call.
#
#   sh app/ios/Tests/run_watchdog_policy_tests.sh
#
# Exit code is the result. Non-zero means a case came back wrong.
set -e
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

listener="$app/Audio/PhoneListener.swift"

# The OPPOSITE of the tally's rule, for the opposite reason. The tally must have
# no call sites; this policy must have one. A watchdog that has gone back to
# deciding for itself, with a green suite over here vouching for a function
# nothing calls, is the blind spot open in production wearing a passing test.
if ! grep -q 'ListenWatchdogPolicy.decide(' "$listener"; then
    echo "The watchdog no longer asks ListenWatchdogPolicy what to do."
    echo "The checks below then prove nothing about the running app: they would"
    echo "vouch for a function with no call sites while the watchdog decided"
    echo "for itself again. The call site IS the fix."
    exit 2
fi

# THE WATCHDOG NEVER READS THE TRANSCRIPT STRING. The leg this replaced fired
# only when `self.partial.isEmpty`, and `partial` is assigned on every
# recognizer result and cleared nowhere a flush can reach — so after the first
# utterance of a task it was never empty again and the leg was dead for the life
# of that task. A recognizer that went deaf with nothing pending was invisible
# for the rest of the day.
#
# `partial` specifically, not `isEmpty`: whether words are UNSENT is a fact the
# policy is entitled to (`hasPending`), and the watchdog reads it off the cursor
# to answer that argument. What it may never do again is decide from the text.
# Asserted on source shape, the way run_journal_tests.sh asserts the audio tap
# closure stays journal-free.
body=$(awk '/private func startWatchdog/,/^    }$/' "$listener")
if printf '%s' "$body" | grep -vE '^[[:space:]]*//' \
    | grep -qE 'self\.partial([^A-Za-z]|$)'; then
    echo "The watchdog is deciding on the transcript text again."
    echo "'partial' is never empty after the first utterance of a task, so a"
    echo "leg guarded by it can never fire — which is exactly how a deaf"
    echo "recognizer with nothing pending stayed invisible all day."
    echo "Ask ListenWatchdogPolicy, which judges when things last ARRIVED."
    exit 2
fi

swiftc -O \
    "$app/Audio/ListenJournal.swift" \
    "$app/Audio/ListenWatchdogPolicy.swift" \
    "$here/ListenWatchdogPolicyTests.swift" \
    -o "$out/watchdogtests"
"$out/watchdogtests"
