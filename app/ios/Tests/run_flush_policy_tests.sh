#!/bin/sh
# Checks for TranscriptFlushPolicy — the layer that decides WHEN the phone
# sends what it heard, and WHICH hypothesis it takes the words from.
# Pure Foundation on purpose: no simulator, no scheme, no signing, no network.
#
#   sh app/ios/Tests/run_flush_policy_tests.sh
#
# Exit code is the result. Non-zero means a case came back wrong.
set -e
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

# The checks are worthless if the app has quietly stopped using the policy.
# Prove the wiring before proving the logic.
listener="$app/Audio/PhoneListener.swift"
if [ ! -f "$listener" ]; then
    echo "PhoneListener.swift is missing — there is nothing for the policy to serve."
    exit 2
fi
# `flushReason` subsumes `mustFlushNow`: it answers the same ceiling question
# and also names WHICH clock ran out. The check follows the caller's entry
# point rather than pinning a method name.
if ! grep -q 'flushPolicy.flushReason' "$listener"; then
    echo "PhoneListener.swift never asks whether waiting words must go out."
    echo "Without the ceiling, a person who does not pause is never transcribed."
    exit 2
fi
# And the answer is worthless if the caller cannot tell a cut from an ending.
# Passing nil for the last partial makes .ceiling unreachable for every input
# there is, silently, with no test anywhere going red to say so.
if ! grep -q 'lastPartialAt: lastPartialAt' "$listener"; then
    echo "PhoneListener asks why the flush fired but cannot answer 'a cut'."
    echo "With no last-partial time the ceiling is unreachable, every line is"
    echo "published as a finished thought, and mid-sentence cuts stay orphans."
    exit 2
fi
if ! grep -q 'cursor.observe' "$listener"; then
    echo "PhoneListener never shows the cursor every hypothesis."
    echo "Without observe(), a discarded decode window takes its words with it."
    exit 2
fi
if ! grep -q 'update.banked' "$listener"; then
    echo "PhoneListener ignores the words the cursor banked from a lost window."
    echo "Those are real speech; dropping them is how sentences disappeared."
    exit 2
fi
if grep -vE '^[[:space:]]*//' "$listener" | grep -q 'minNewWords'; then
    echo "PhoneListener still gates a flush on a new-word floor."
    echo "That marked one- and two-word lines as sent without sending them."
    exit 2
fi
if ! grep -q 'cursor.takePending' "$listener"; then
    echo "PhoneListener does not take pending words all-or-nothing."
    exit 2
fi
echo "PhoneListener observes every hypothesis, banks lost windows, and holds no word floor"

swiftc -O \
    "$app/Audio/TranscriptCursor.swift" \
    "$app/Audio/TranscriptFlushPolicy.swift" \
    "$here/TranscriptFlushPolicyTests.swift" \
    -o "$out/flushtests"
"$out/flushtests"
