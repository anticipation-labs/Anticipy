#!/bin/sh
# Insights — the screen whose whole proposition is that its numbers are true.
#
#   sh app/ios/Tests/run_insights_tests.sh
#
# Research: research/2026-09-06-insights-retention.md. InsightsPolicy is pure
# Foundation, so the production source compiles straight in. The source facts
# below are the four rules the research says decide whether this feature ships
# honest or ships a lie.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

policy="$app/InsightsPolicy.swift"
view="$app/Views/InsightsView.swift"
home="$app/Views/ContentView.swift"
for f in "$policy" "$view" "$home"; do
    [ -f "$f" ] || { echo "missing $f"; exit 2; }
done

code() { sed 's://.*$::' "$1"; }

# ---------------------------------------------------------------- LAW ONE
# The same grep run_dashboard_tests.sh carries, and for the same reason: this
# is the second file in the app that will be tempted to look at the words.
# "Things picked up" rests on `goal != ""` — a column the brain wrote — and
# never on the client reading text.
if code "$policy" | grep -qE 'NSRegularExpression|range\(of:|localizedCaseInsensitiveContains|hasPrefix\("|hasSuffix\("'; then
    echo "InsightsPolicy reads the WORDS of what somebody said."
    echo
    echo "Law 1: no regex, word list or threshold may decide what a sentence"
    echo "MEANS. Every number on this screen counts rows the brain already"
    echo "judged. A client-side scan here would be the app deciding what was"
    echo "worth catching, which is the one thing it may not do."
    code "$policy" | grep -nE 'NSRegularExpression|range\(of:|localizedCaseInsensitiveContains|hasPrefix\("|hasSuffix\("'
    exit 2
fi

# ------------------------------------------------------------- NO STREAK
# Not a style rule. The ears went deaf for thirty hours and nothing noticed
# (overnight/are_the_ears_live.py exists because of it), so a streak breaks on
# Anticipy's own outage and bills it to the person.
if code "$policy" | grep -qiE 'streak|consecutive|inARow|dayssince.*break'; then
    echo "Something on the insights screen is a streak."
    echo
    echo "A streak is a number that FALLS, and it falls for reasons that are"
    echo "this app's fault: the ears went deaf for thirty hours once and nothing"
    echo "noticed. Days used is monotone and says the same warm thing without"
    echo "ever accusing somebody of missing a day."
    exit 2
fi

# ------------------------------------------------------ NOTHING CONGRATULATES
if code "$policy" | grep -qiE 'congratulat|well done|keep it up|nice work|great job'; then
    echo "The insights screen congratulates somebody."
    echo "This product's voice states what happened. It does not applaud."
    exit 2
fi

# --------------------------------------------------------- NO COUNT-UP, NO BADGE
# Named in the research as the line between a screen somebody is glad to find
# and one they feel worked on.
if code "$view" | grep -qE '\.badge\(|repeatForever|withAnimation.*count|Timer\.publish'; then
    echo "The insights screen animates a number or wears a badge."
    echo "A number rolling up from zero is a small casino, and a badge is a"
    echo "notification that never goes away. Neither belongs on a screen about"
    echo "what actually happened."
    exit 2
fi

# ------------------------------------------------ THE PEEK KEEPS THE DECK'S GUARD
# The card sits where the "Done" heading was, and inherits `if
# !finishedShown.isEmpty` so it is ABSENT rather than empty.
deck=$(awk '/} doneDeck: \{/{g=1} g{print} g&&/^                \} settingsLink: \{/{exit}' "$home")
if ! printf '%s\n' "$deck" | grep -q 'InsightsPeekCard('; then
    echo "The Done section no longer carries the insights peek card."
    exit 2
fi
if ! printf '%s\n' "$deck" | grep -q 'finishedShown.isEmpty'; then
    echo "The peek card escaped the deck's emptiness guard."
    echo "It must be absent rather than empty for an owner with nothing finished."
    exit 2
fi
if ! printf '%s\n' "$deck" | grep -q 'DoneDeck(jobs: finishedShown)'; then
    echo "The swipeable Done deck is gone. The card was meant to sit ABOVE it,"
    echo "not replace it — the individual finished things are the point."
    exit 2
fi

# ---------------------------------------------------- NO WINDOW SOLD AS A LIFETIME
# The likeliest way this feature ships a lie. Home computes its counts from the
# page it holds, so the file that does it has to say so where somebody editing
# it will read it.
if ! grep -qi 'not presented as lifetimes' "$home"; then
    echo "ContentView no longer records that its insight counts are a WINDOW"
    echo "over the page this phone holds rather than lifetimes."
    echo
    echo "That note is the thing standing between this screen and a false total."
    echo "If the counts became real lifetimes, say so there instead of deleting it."
    exit 2
fi

# ------------------------------------------------------------------ THE COLOUR
if code "$view" | grep -q 'Color(hex:'; then
    echo "The insights screen names a colour instead of reading a Theme role."
    exit 2
fi

# --------------------------------------------------------------- the walk
cp "$here/InsightsTests.swift" "$out/main.swift"
swiftc "$policy" "$out/main.swift" -o "$out/insightstests"
"$out/insightstests"
