#!/bin/sh
# The motion contract — what may move, and what must ask first.
#
#   sh app/ios/Tests/run_motion_contract_tests.sh
#
# The 2026-09-06 audit found ContentView animating in fourteen places while
# reading Reduce Motion in NONE, and — the actual finding — no gate anywhere
# enforcing the pairing, so nothing stopped the next screen doing the same.
# Motion sensitivity is a real condition and iOS exposes the setting; forty-one
# places in this app honour it and the busiest screen did not.
#
# This is a whole-tree contract rather than one screen's suite, for the same
# reason the theme contract is: a rule that only covers the file it was written
# for is a rule that migrates.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
views="$here/../Anticipy/Views"
code() { sed 's://.*$::' "$1" | sed 's:///.*$::'; }

# ================== A FILE THAT ANIMATES MUST KNOW ABOUT REDUCE MOTION
# Not every animation has to be suppressed — a press state that fades is fine —
# but a file with animation and no awareness of the setting has not CONSIDERED
# it, and that is what this leg is really asking about.
#
# The threshold is deliberately not 1: a single `.animation()` on a colour is
# not what makes somebody ill. Three or more moving things in one file is a
# screen, and a screen has to have thought about it.
missing=""
for f in $(ls "$views" | grep '\.swift$'); do
    n=$(code "$views/$f" | grep -cE 'withAnimation|\.animation\(' || true)
    [ "$n" -ge 3 ] || continue
    if ! grep -q 'accessibilityReduceMotion\|reduceMotion' "$views/$f"; then
        missing="$missing  $f ($n animations)\n"
    fi
done
if [ -n "$missing" ]; then
    echo "These files animate and never ask about Reduce Motion:"
    printf "$missing"
    echo "Motion sensitivity is a real condition and iOS exposes the setting."
    echo "Read it with @Environment(\\.accessibilityReduceMotion) and decide —"
    echo "suppressing the motion, or keeping it and saying in a comment why it"
    echo "is safe. Deciding is the requirement; the answer is yours."
    exit 2
fi

# ============================ AMBIENT MOTION HONOURS THE OWNER'S SWITCH TOO
# Anything that repeats forever is ambient, and the owner has their own switch
# for it beside the system one. The app combines them as
# `reduceMotion || !ambientMotion` everywhere, and a TimelineView that pauses on
# only half of that is a switch that does not work.
for f in $(ls "$views" | grep '\.swift$'); do
    grep -q 'TimelineView(.animation' "$views/$f" || continue
    # `.animation(paused:` in full, not a bare `paused:` — a substring match
    # was green over `xpaused:`, which is the shape every inert leg in this
    # repo has had.
    # Joined across the line break: `.animation(minimumInterval:` often puts
    # `paused:` on the next line, and a single-line grep reads that as absent.
    # A BOUNDARY before `paused:`, or `xpaused:` matches it as a substring —
    # which is exactly how the first version of this leg passed over a
    # deliberately broken file.
    if ! tr '\n' ' ' < "$views/$f" \
         | grep -qE '\.animation\((paused:|[^)]*[(, ]paused:)'; then
        echo "$f drives a TimelineView that can never pause."
        echo "An animation timeline with no pause runs while the phone is in"
        echo "somebody's pocket."
        exit 2
    fi
done

# ================================================== EVERY CORNER IS A SQUIRCLE
# Apple's corners are continuous curves, not circular arcs. The difference is
# subtle and the brain notices: continuous reads as soft, circular as stamped.
# Thirty-nine of forty-two already were; this keeps the rest from drifting back.
# `-A 1`: a RoundedRectangle whose style sits on the next line is correct, and a
# single-line grep reads it as a stray. Joined before matching.
strays=$(for f in $(ls "$views" | grep '\.swift$'); do
    awk -v file="$f" '
        { buf = prev " " $0
          if (prev ~ /RoundedRectangle\(cornerRadius:/ && buf !~ /style: \.continuous/ \
              && prev !~ /shape: RoundedRectangle/)
              print file ":" NR-1 ": " prev
          prev = $0 }
        END { if (prev ~ /RoundedRectangle\(cornerRadius:/ && prev !~ /style: \.continuous/ \
                  && prev !~ /shape: RoundedRectangle/) print file ":" NR ": " prev }
    ' "$views/$f"
done)
if [ -n "$strays" ]; then
    echo "These rounded rectangles are circular rather than continuous:"
    printf '%s\n' "$strays"
    echo
    echo "Add 'style: .continuous'. It is the squircle Apple uses, and the"
    echo "reason their corners feel soft while cheaper ones feel stamped."
    exit 2
fi

# ======================== THE SHARED ELEMENT NEEDS BOTH HALVES AND ONE SOURCE
# A matched pair with two sources, or one half, animates nothing and logs a
# warning nobody reads.
peek="$views/InsightsView.swift"
if grep -q 'matchedGeometryEffect' "$peek"; then
    # Comments stripped: the note ABOVE each call explains the pair and names
    # both spellings, which a raw grep counts as extra claimants. Every leg in
    # this repo that matched prose instead of code has been wrong.
    sources=$(code "$peek" | grep -c 'isSource: true' || true)
    dests=$(code "$peek" | grep -c 'isSource: false' || true)
    if [ "$sources" != "1" ] || [ "$dests" != "1" ]; then
        echo "The insights shared element has $sources sources and $dests"
        echo "destinations; it needs exactly one of each, or SwiftUI has to"
        echo "guess which rectangle the other is travelling to."
        exit 2
    fi
    grep -q 'hidden: showingInsights' "$views/ContentView.swift" || {
        echo "The peek card does not stand down while the page holds the"
        echo "geometry, so both halves draw at once."
        exit 2
    }
fi
# A sheet cannot carry a matched element across its boundary, so presenting the
# insights page as one silently turns the transition back into a cut.
if grep -q 'sheet(isPresented: $showingInsights)' "$views/ContentView.swift"; then
    echo "The insights page is presented as a sheet again."
    echo "matchedGeometryEffect cannot cross a sheet's presentation boundary —"
    echo "as a sheet this navigation can only ever be a cut."
    exit 2
fi

echo "all motion contract checks passed"
