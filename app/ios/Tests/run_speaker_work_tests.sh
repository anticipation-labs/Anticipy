#!/bin/sh
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
cp "$here/SpeakerWorkTests.swift" "$out/main.swift"
swiftc -O "$here/../Anticipy/Audio/VoiceRoster.swift" \
    "$here/../Anticipy/Audio/SpeakerTagger.swift" "$out/main.swift" -o "$out/speaker-work"
"$out/speaker-work"
