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

# AND THE FRONT OF THE FEED, which is the half a person actually looks at.
#
# A grouped conversation renders as a ConversationCard; the raw TranscriptRow
# the two checks above protect is behind a tap. `HeardGroup.ear` is folded and
# well checked, `HeardFront.ear` carries it, and until this leg existed NOTHING
# asserted that the card ever drew it. Mutation-tested: replacing the card's
# badge with `if false` left the entire iOS gate green while the feed's front
# lost provenance completely — exactly the write-only life `events.source`
# already had once.
#
# This can only see that the call is there, not that the glyph reaches a pixel.
# That is the same limit the TranscriptRow legs above carry, and it is worth
# saying rather than implying: it catches deletion, not decoration.
card="$app/Views/ConversationCard.swift"
if ! grep -q 'CaptureSourcePolicy.badge(for: front.ear)' "$card"; then
    echo "The conversation card no longer shows which ear heard it."
    echo "That card is the FRONT of the feed; the raw row that also carries the"
    echo "badge is one tap behind it. Comparing a pendant run against a phone-mic"
    echo "run goes back to being two taps per card instead of a glance."
    exit 2
fi
if ! grep -q 'CaptureSourcePolicy.accessibilityLabel' "$card"; then
    echo "The card's ear glyph is no longer labelled for VoiceOver."
    echo "It is a bare icon with no text beside it, so without the label it is"
    echo "the one piece of provenance a screen reader cannot reach at all."
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
