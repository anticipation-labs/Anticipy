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

# NO WIRING ASSERTION HERE ANY MORE, and its removal is the point.
#
# This used to read: `grep BoundedOpusQueue TranscriberClient.swift` — a test
# asserting that the speech-vendor websocket client was wired to the outgoing
# frame queue. TranscriberClient streamed the pendant's raw Opus frames to a
# third party, which is design/LOCAL-FIRST.md rule 1 broken in its first line,
# and it has been DELETED. A test pinning a violation in place is how the
# violation survives review: the same shape as the backend test removed in
# 2b27f4ce, which asserted the vendor exchange was still there.
#
# The queue itself stays and is still stressed below. It has no consumer today
# and that is honest rather than dead: an on-device Opus path needs exactly
# this bounded queue, and deleting a tested component to tidy up a reference
# count would throw the working half away with the broken one.

swiftc -O \
    "$app/Audio/BoundedOpusQueue.swift" \
    "$here/BoundedOpusQueueStress.swift" \
    -o "$out/network-queue-stress"
"$out/network-queue-stress"
