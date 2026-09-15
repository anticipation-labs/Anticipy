#!/bin/sh
# Bounded production assembler regressions; no hardware, decoding or network.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
swiftc -O \
    "$here/../Anticipy/BLE/OpusFrameAssembler.swift" \
    "$here/OpusFrameAssemblerTransportTests.swift" \
    -o "$out/transport-tests"
"$out/transport-tests"
