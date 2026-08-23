#!/bin/sh
# Which ear heard a line — and when the app must say nothing at all.
#
#   sh app/ios/Tests/run_capture_source_tests.sh
#
# CaptureSourcePolicy is pure Foundation, so the real production source is
# compiled straight in rather than lifted or copied.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

policy="$app/Audio/CaptureSourcePolicy.swift"
[ -f "$policy" ] || { echo "missing $policy"; exit 2; }

# The checks below are worthless if the feed has quietly stopped consulting the
# policy. Prove the wiring before proving the logic — this is the exact failure
# `source` already suffered once: written on every event for weeks, read by
# nothing, and no test noticed because nothing asserted the read.
row="$app/Views/ContentView.swift"
if ! grep -q 'CaptureSourcePolicy.badge(for: line.source)' "$row"; then
    echo "TranscriptRow no longer asks CaptureSourcePolicy which ear heard the line."
    echo "events.source goes back to being write-only, and comparing a pendant"
    echo "run against a phone-mic run becomes invisible again."
    exit 2
fi
if ! grep -q 'CaptureSourcePolicy.accessibilityLabel' "$row"; then
    echo "The badge is no longer labelled for VoiceOver."
    exit 2
fi

# And worthless too if the line never carries the value up from the server.
if ! grep -q 'let source: String?' "$app/Backend/AnticipyBackend.swift"; then
    echo "BrainEvent stopped decoding events.source, so nothing can render it."
    exit 2
fi
if ! grep -q 'source: (\$0.source?.isEmpty == false)' "$app/AnticipyApp.swift"; then
    echo "The poll no longer carries source onto TranscriptLine."
    exit 2
fi
echo "the feed consults the policy, and source arrives from the server"
# swiftc only permits top-level code in a file literally named main.swift, so
# the suite is copied under that name rather than wrapped in a type it does not
# need. Every other suite here is a single-file `swift` run; this one compiles
# two files, which is what makes the rule apply.
cp "$here/CaptureSourcePolicyTests.swift" "$out/main.swift"
swiftc -O "$policy" "$out/main.swift" -o "$out/capturesourcetests"
"$out/capturesourcetests"
