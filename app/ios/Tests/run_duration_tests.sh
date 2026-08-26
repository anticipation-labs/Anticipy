#!/bin/sh
# Checks for PlainDuration — how long something lasted, in units a person
# reads, from the one place every screen that reports a duration reads it from.
#
#   sh app/ios/Tests/run_duration_tests.sh
#
# WHAT THIS LIFT WAS FOR. `duration(_:)` was private inside
# `ListeningDiagnosticsView`. The listening row in Settings and the home card
# are being built to report the same stretch of silence off the same
# `ListenTally.unheardForSeconds`, and the argument all three rest on is that
# screen's own: no threshold decides what counts as too long, so the reader
# judges (`ListeningDiagnosticsView.swift:38-43`). That argument holds only
# while the same seconds read the same way everywhere — "6 hr 20 min" here and
# "6.3 hours" there is three claims about one measurement, and the reader has no
# way to tell which one the phone actually measured.
#
# Two instruments, because a shared formatter can fail in two ways:
#
#   The swiftc suite proves the WORDING — byte-for-byte what shipped, and no
#   adjective, threshold or verdict anywhere in its range.
#
#   The scans prove it is SHARED — that the screen it came from asks it rather
#   than keeping a copy, and that no second spelling of the same units has grown
#   back somewhere else in the app.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
type_file="$app/Audio/PlainDuration.swift"
view="$app/Views/ListeningDiagnosticsView.swift"
tests="$here/PlainDurationTests.swift"
for f in "$type_file" "$view" "$tests"; do
    [ -f "$f" ] || { echo "missing $f"; exit 2; }
done
fail=0

# PROSE IS NOT CODE. These files explain at length the wordings they refuse, so
# whole-line comments come out before every scan, exactly as the control-policy
# and theme-contract runners do it.
strip() { grep -v '^ *//' "$1"; }

# 1. IT MUST STAY A FORMATTER. Wording is not a look. A duration helper that can
#    import SwiftUI is one that can eventually hand back a red string, and the
#    whole no-verdict argument is that nothing here decides a number is bad.
#    swiftc alone does not prove this — SwiftUI compiles on a Mac — so it is
#    asked here.
if strip "$type_file" | grep -qE 'import (SwiftUI|UIKit|AppKit|SwiftData)|Color\.|Theme\.'; then
    echo "PlainDuration has reached for the view layer:"
    strip "$type_file" | grep -nE 'import (SwiftUI|UIKit|AppKit|SwiftData)|Color\.|Theme\.'
    echo "It is wording, not a look. A formatter that can name a colour is one"
    echo "that will eventually return a verdict wearing one, and every screen"
    echo "reporting a duration has been argued into having no verdict at all."
    fail=1
fi

# 2. THE SCREEN IT CAME FROM MUST ASK IT. A green suite over a type the app no
#    longer consults is the failure this repo has recorded eleven times:
#    `ListenResumePolicy` shipped once as an inline guard that could not fire,
#    and `FirstRunOwnership` shipped complete, correct, in the pbxproj, with
#    zero call sites.
if ! strip "$view" | grep -q 'PlainDuration.words('; then
    echo "The diagnostics screen no longer asks PlainDuration how to word seconds."
    echo "The checks below then prove nothing about anything anybody reads: the"
    echo "screen is free to word a stretch of silence its own way again, which is"
    echo "exactly what this type was lifted out of it to stop."
    fail=1
fi

# 3. AND IF IT KEEPS A HELPER OF ITS OWN, THE HELPER MUST BE THE CALL. A private
#    `duration(_:)` forwarding to the shared type is fine and is what ships; the
#    same name with two lines of arithmetic back inside it is the fork this lift
#    undid, and it would be invisible at all five call sites. Call sites that go
#    direct instead are equally fine — leg 4 is what holds that shape.
if strip "$view" | grep -q 'private func duration('; then
    body=$(strip "$view" | awk '
        /private func duration\(/ { inside = 1; next }
        inside && /^    }/ { inside = 0; next }
        inside { gsub(/^[ \t]+|[ \t]+$/, ""); if ($0 != "") printf "%s;", $0 }')
    if [ "$body" != "PlainDuration.words(seconds);" ]; then
        echo "The screen's private duration(_:) is no longer just the shared call:"
        echo "  $body"
        echo "Six lines of arithmetic under a name five call sites already use is"
        echo "the fork this type was lifted out to close, and it reads identical"
        echo "at every one of them."
        fail=1
    fi
fi

# 4. NO SECOND SPELLING OF THE SAME UNITS. A computed number followed by its
#    unit — `"\(minutes) min"` — anywhere but this type is a screen wording the
#    same seconds its own way. Copy that merely contains the word "seconds" is
#    untouched: what is matched is an interpolation handing straight into a
#    unit, which is arithmetic, not a sentence.
drift=$(find "$app" -name '*.swift' ! -name 'PlainDuration.swift' -print \
    | while read -r f; do
        strip "$f" | grep -nE '\)[ ]+(seconds|min|hr)\b' | sed "s|^|$f:|"
      done)
if [ -n "$drift" ]; then
    echo "A second wording of the same seconds has grown back:"
    printf '%s\n' "$drift"
    echo "Ask PlainDuration.words(_:) instead. Three screens report the same"
    echo "ListenTally seconds now, and the argument that no threshold decides"
    echo "what counts as too long only holds while they all read alike."
    fail=1
fi

[ "$fail" = "0" ] || exit 1

out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
swiftc -O "$type_file" "$tests" -o "$out/durationtests"
"$out/durationtests"
