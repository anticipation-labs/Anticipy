#!/bin/sh
# Completion drive — the honest alternative to a streak.
#
#   sh app/ios/Tests/run_rings_tests.sh
#
# Apple's rings changed the behaviour of 160,000 people on one principle: the
# brain treats an incomplete shape as demanding completion. Anticipy already had
# loops of that shape and drew them as shrinking lists.
#
# A STREAK WAS REJECTED FOR THIS PRODUCT ON EVIDENCE: the ears went deaf for
# thirty hours and nothing noticed, so a streak would have broken on Anticipy's
# own outage and billed it to the owner. Every leg below is about keeping the
# rings on the other side of that line.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

policy="$app/RingsPolicy.swift"
view="$app/Views/InsightsView.swift"
home="$app/Views/ContentView.swift"
for f in "$policy" "$view" "$home"; do [ -f "$f" ] || { echo "missing $f"; exit 2; }; done
code() { sed 's://.*$::' "$1" | sed 's:///.*$::'; }

# =============================================== NO RING COUNTS ATTENTION
# The line between a loop worth closing and a loop that has taken you hostage.
# These measure whether something got DONE, never whether somebody showed up.
if code "$policy" | grep -qiE 'appOpen|opens|sessionCount|daysElapsed|timeSpent|streak|consecutive|inARow|lastSeen|visits'; then
    echo "A ring is being derived from attention rather than from work."
    echo
    echo "Opens, sessions, elapsed days and time spent all measure whether the"
    echo "owner showed up. A product that scores its owner for opening it has"
    echo "started working ON them rather than FOR them — and a number of that"
    echo "shape can FALL, which is the streak this product already refused."
    code "$policy" | grep -niE 'appOpen|opens|sessionCount|daysElapsed|timeSpent|streak|consecutive|inARow|lastSeen|visits'
    exit 2
fi

# ==================================================== AND NOTHING APPLAUDS
if code "$policy" | grep -qiE 'congratulat|well done|keep it up|nice work|great job|level up|unlock|badge|reward|points'; then
    echo "A ring congratulates, or dangles a reward."
    echo "This screen states what is true about the product. It does not"
    echo "applaud, and there is nothing here to win."
    exit 2
fi

# ================================================= ABSENT, NEVER EMPTY
if ! code "$policy" | grep -q 'case nothingToCount'; then
    echo "A ring with nothing to count no longer has a way to be ABSENT."
    echo "An empty ring says 'it does not work'; a missing one says 'not yet'."
    exit 2
fi
if ! code "$view" | grep -q 'if !faces.isEmpty'; then
    echo "RingsSection draws its heading over a possibly-empty list."
    exit 2
fi

# ============================================= THE ARC DOES NOT ANIMATE UP
# run_insights_tests.sh forbids a number rolling up from zero on this screen —
# "a number rolling up from zero is a small casino" — and an arc sweeping up
# from zero is the same gesture drawn as a shape.
if code "$view" | grep -q 'struct RingView' && \
   code "$view" | sed -n '/struct RingView/,/^}/p' | grep -qE 'withAnimation|\.animation\(|onAppear'; then
    echo "The ring animates itself on appear."
    echo "An arc sweeping up from zero is a number rolling up from zero, drawn"
    echo "as a shape. The same rule forbids both: the value is simply true from"
    echo "the first frame."
    exit 2
fi

# ==================================== THE SECOND RING IS NOT GUESSED
# Home cannot see the connected-apps count. A screen that cannot see a number
# must not invent a denominator for it.
if code "$home" | grep -qE 'reaches: \(done: .*catalog|reaches: \(done: [0-9]'; then
    echo "The connected-apps ring is being drawn from a guessed total."
    echo "'The apps that matter for your goals' is a judgment, and a judgment"
    echo "belongs to the model that has the goals, never to a ring."
    exit 2
fi

# ---------------------------------------------------------------- the walk
cp "$here/RingsTests.swift" "$out/main.swift"
swiftc "$policy" "$out/main.swift" -o "$out/ringstests"
"$out/ringstests"
