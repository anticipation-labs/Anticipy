#!/bin/sh
# Checks for the end-of-errand decision — the rule that decides whether a typed
# answer cancels the job and files the owner's own words as the reason.
#
#   sh app/ios/Tests/run_end_errand_tests.sh
#
# The rule lives inside AnticipySession, which drags in SwiftUI, Combine, the
# network layer and the microphone — none of which this decision touches. So
# rather than duplicate it (a copy is only honest until someone edits one side),
# this lifts the REAL source out of AnticipyApp.swift between its ANCHOR
# markers and compiles it alone. `Self.` resolves to the wrapper here exactly as
# it resolves to AnticipySession there.
#
# Exit code is the result. Non-zero means a case came back wrong.
set -e
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

src="$app/AnticipyApp.swift"

# The checks are worthless if the app has quietly stopped consulting the rule
# before it approves an answer. Prove the wiring before proving the logic.
if ! grep -q 'Self.answerThatEndsTheErrand' "$src"; then
    echo "confirm() no longer asks whether the answer ended the errand."
    echo "Without it every non-empty answer requeues the run — which is how"
    echo "'skip it, I don't need the batteries' relaunched the errand and got"
    echo "those words Bing-searched into a CAPTCHA."
    exit 2
fi
if grep -vE '^[[:space:]]*//' "$src" | grep -q 'wordCount <= 8'; then
    echo "The rule is gating on answer LENGTH again."
    echo "Every regression it was added for is short: 'leave it with the"
    echo "concierge', 'stop it from auto-renewing'. Length was never the"
    echo "condition; position is."
    exit 2
fi

# The END rule comes first: the closing marker contains the opening marker as a
# substring, so testing for the opening one first re-armed it and swallowed the
# rest of the file.
awk '/END ANCHOR: end-of-errand decision/{f=0;next} /ANCHOR: end-of-errand decision/{f=1;next} f' \
    "$src" > "$out/rule.swift"
if [ ! -s "$out/rule.swift" ]; then
    echo "Found no code between the ANCHOR markers in AnticipyApp.swift."
    echo "Either the markers moved or the rule did; these checks are compiling"
    echo "nothing, which is worse than not having them."
    exit 2
fi
if ! grep -q 'func answerThatEndsTheErrand' "$out/rule.swift"; then
    echo "The anchored region no longer contains answerThatEndsTheErrand."
    exit 2
fi
echo "confirm() consults the rule, and the anchored region is $(wc -l < "$out/rule.swift" | tr -d ' ') lines"

{
    echo "import Foundation"
    echo "enum EndOfErrand {"
    cat "$out/rule.swift"
    echo "}"
} > "$out/EndOfErrand.swift"

swiftc -O \
    "$out/EndOfErrand.swift" \
    "$here/EndTheErrandTests.swift" \
    -o "$out/enderrandtests"
"$out/enderrandtests"
