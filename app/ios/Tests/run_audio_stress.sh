#!/bin/sh
set -eu

here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

if ! grep -q 'OpusFrameAssembler' "$app/BLE/PendantManager.swift"; then
    echo "PendantManager is not wired to the bounded assembler."
    exit 2
fi

swiftc -O \
    "$app/BLE/OpusFrameAssembler.swift" \
    "$here/OpusFrameAssemblerStress.swift" \
    -o "$out/audio-stress"
"$out/audio-stress"

if ! grep -q 'BoundedOpusQueue' "$app/Audio/TranscriberClient.swift"; then
    echo "TranscriberClient is not wired to the bounded outgoing queue."
    exit 2
fi

swiftc -O \
    "$app/Audio/BoundedOpusQueue.swift" \
    "$here/BoundedOpusQueueStress.swift" \
    -o "$out/network-queue-stress"
"$out/network-queue-stress"
