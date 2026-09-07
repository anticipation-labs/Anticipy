#!/bin/sh
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
cp "$here/ReplyTextDeliveryPolicyTests.swift" "$out/main.swift"
swiftc "$here/../Anticipy/Backend/ReplyTextDeliveryPolicy.swift" "$out/main.swift" -o "$out/test"
"$out/test"
