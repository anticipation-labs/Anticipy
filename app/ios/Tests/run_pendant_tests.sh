#!/bin/sh
# Checks for PendantRadioPolicy — what "tap connect" does when the Bluetooth
# radio is not ready yet. PendantRadioPolicy.swift is pure Foundation on
# purpose, so this needs no simulator, no scheme, no signing, no radio and no
# pendant: it compiles and runs in about a second.
#
#   sh app/ios/Tests/run_pendant_tests.sh
#
# Exit code is the result. Non-zero means a case came back wrong.
set -e
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

# The cases below are worthless if PendantManager has quietly gone back to
# deciding this inline. Prove the wiring before proving the logic — the same
# order run_cursor_tests.sh uses, and for the same reason.
mgr="$app/BLE/PendantManager.swift"
if [ ! -f "$mgr" ]; then
    echo "PendantManager.swift is missing — there is no radio to have a policy about."
    exit 2
fi
if ! grep -q 'PendantRadioPolicy' "$mgr"; then
    echo "PendantManager.swift does not use PendantRadioPolicy."
    echo "The policy can be perfect and the first tap will still do nothing."
    exit 2
fi
# The exact line that made the first tap dead: a guard that returns when the
# radio is not on yet, throwing the request away instead of remembering it.
if grep -qE 'guard central\??\.state == \.poweredOn else \{ *return' "$mgr"; then
    echo "PendantManager.swift still drops the request when the radio is warming up."
    echo "That is the dead first tap (docs ex 87): ensureCentral() builds the"
    echo "central, its state is .unknown for a moment, and this guard returns."
    exit 2
fi
if ! grep -q 'connectRequested' "$mgr"; then
    echo "PendantManager.swift keeps no record that the owner asked to connect."
    echo "Without it, a tap made before the radio was ready is forgotten."
    exit 2
fi
echo "PendantManager routes radio state through PendantRadioPolicy and remembers the request"

swiftc -O \
    "$app/BLE/PendantRadioPolicy.swift" \
    "$here/PendantRadioPolicyTests.swift" \
    -o "$out/pendanttests"
"$out/pendanttests"
