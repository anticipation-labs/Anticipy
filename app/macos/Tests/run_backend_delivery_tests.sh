#!/bin/sh
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
swiftc -parse-as-library \
    "$here/../Anticipy/Capture/MeetingLinePolicy.swift" \
    "$here/../Anticipy/Capture/TranscriptWire.swift" \
    "$here/../AnticipyMac/MacBackend.swift" \
    "$here/BackendDeliveryTests.swift" -o "$out/delivery-tests"
"$out/delivery-tests"
