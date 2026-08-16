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
if ! grep -q 'flushPolicy.mustFlushNow' "$listener"; then
    echo "PhoneListener.swift never asks whether waiting words must go out."
    echo "Without the ceiling, a person who does not pause is never transcribed."
    exit 2
fi
if ! grep -q 'TranscriptFlushPolicy.source' "$listener"; then
    echo "PhoneListener.swift takes words from the latest hypothesis only."
    echo "A collapsed revision will delete speech that was genuinely heard."
    exit 2
fi
if ! grep -q 'TranscriptFlushPolicy$' "$listener" && ! grep -q 'finalMinNewWords' "$listener"; then
    echo "PhoneListener.swift still hard-codes the final-result floor."
    exit 2
fi
if ! grep -q 'richestPartial = self.partial' "$listener"; then
    echo "PhoneListener.swift never records the fullest hypothesis it heard."
    exit 2
fi
echo "PhoneListener is wired to TranscriptFlushPolicy for timing, source and floor"

swiftc -O \
    "$app/Audio/TranscriptCursor.swift" \
    "$app/Audio/TranscriptFlushPolicy.swift" \
    "$here/TranscriptFlushPolicyTests.swift" \
    -o "$out/flushtests"
"$out/flushtests"
