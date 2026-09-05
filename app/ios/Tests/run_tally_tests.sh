#!/bin/sh
# Checks for ListenTally — what a day of listening did, folded out of the
# journal the session already wrote.
# Pure Foundation on purpose: no simulator, no scheme, no signing, no network.
#
#   sh app/ios/Tests/run_tally_tests.sh
#
# Exit code is the result. Non-zero means a case came back wrong.
set -e
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

# The tally DERIVES from the journal and must keep deriving. A counter
# incremented at a call site is a second source of truth that drifts the moment
# somebody adds an event and forgets it, and the journal is what a person
# actually exports and reads.
if grep -rn "ListenTally" "$app/Audio/PhoneListener.swift" 2>/dev/null; then
    echo "PhoneListener now writes to ListenTally directly."
    echo "The tally is a fold over what the journal already recorded. A parallel"
    echo "counter at the call sites drifts from the journal the first time an"
    echo "event is added without it, and the journal is the exported artifact."
    exit 2
fi

# THE SCREEN MUST HAND OVER ITS CLOCK. `ListenTally.of` is pure and takes the
# reading moment as an argument, defaulted so the checks below keep their
# meaning. On the day this whole type exists for, the journal's last line IS the
# failure — a call took the microphone at 09:00, nothing restarted listening,
# and there are no later events — so a caller that passes no clock gets "58 min"
# for a phone that has heard nothing in eleven hours. Every check in the suite
# can be green over that: they measure the fold, and this measures the wiring.
view="$app/Views/ListeningDiagnosticsView.swift"
if ! grep -vE '^[[:space:]]*//' "$view" | tr '\n' ' ' \
    | grep -q 'ListenTally\.of([^)]*now:'; then
    echo "The diagnostics screen folds the day without saying when it is being read."
    echo "The last line of a journal from a phone that went deaf at nine in the"
    echo "morning is the nine o'clock stop. Measured to that, the answer is the"
    echo "58 quiet minutes BEFORE the call, and the eleven deaf hours after it"
    echo "are unmeasurable by construction. Pass the clock."
    exit 2
fi

# AND THE BATTERY FOLD MUST REACH A PERSON, IN BOTH HALVES. `4%` on its own
# invites the reader to supply a threshold out of nothing; `4% over 2 hr 10 min`
# is a measurement they can put against tomorrow's. The window is also the only
# thing that says the number does NOT cover the whole day — readings bracket the
# stretches between them and nothing else.
wording=$(awk '/private var batteryWording/,/^    }$/' "$view" | sed '/^[[:space:]]*\/\//d')
if [ -z "$wording" ]; then
    echo "This gate can no longer find the screen's battery wording."
    echo "An empty block satisfies every rule below by containing nothing, which"
    echo "is how three separate gate rules were found this week passing by"
    echo "matching nothing. If it was renamed, rename it here too."
    exit 2
fi
# THE SENTENCE, NOT THE BLOCK. The first version of these two legs grepped the
# whole function, and `if tally.batteryMeasuredSeconds == 0` — a GUARD, three
# lines above — satisfied the window rule on its own. Mutation-tested: dropping
# the window from the returned sentence left the leg green. So both legs read
# the `return` lines, which are the only thing a person ever sees.
said=$(printf '%s\n' "$wording" | grep -E '^[[:space:]]*return')
if ! printf '%s\n' "$said" | grep -q 'batterySpentPoints'; then
    echo "The Listening screen no longer shows what the battery spent."
    echo "The fold then measures a cost nobody can read, which is the same as"
    echo "not measuring it: PhoneListener writes readings all day, the tally"
    echo "folds them, and the number dies inside a struct."
    exit 2
fi
if ! printf '%s\n' "$said" | grep 'batterySpentPoints' \
    | grep -q 'batteryMeasuredSeconds'; then
    echo "The battery number is shown without the window it was spent over."
    echo "\"4%\" is not a measurement. It also silently claims to cover the whole"
    echo "day, when what was measured is only the stretches between readings"
    echo "with the phone off a charger."
    exit 2
fi
# THE RATE, BESIDE THE WINDOW. `batteryPointsPerHour` is the two numbers
# divided, and the screen may show it only with the window it rests on in the
# same sentence — a rate alone invites a five-minute sample to be read as a
# day's. Same rule as the two legs above: the RETURN line is what is judged.
rate=$(awk '/private func batteryRateWording/,/^    }$/' "$view" | sed '/^[[:space:]]*\/\//d')
if [ -z "$rate" ]; then
    echo "This gate can no longer find the screen's battery-rate wording."
    echo "If it was renamed, rename it here too; an empty block would satisfy"
    echo "every rule below by containing nothing."
    exit 2
fi
if ! printf '%s\n' "$rate" | grep -E '^[[:space:]]*return' | grep -q 'batteryMeasuredSeconds'; then
    echo "The battery rate is shown without the window it was measured over."
    echo "\"2% an hour\" from five minutes and from ten hours read identically,"
    echo "and only one of them is worth putting against tomorrow's."
    exit 2
fi
if ! grep -vE '^[[:space:]]*//' "$view" | tr '\n' ' ' \
    | grep -q 'tally\.batteryPointsPerHour'; then
    echo "The Listening screen no longer shows drain per hour of listening."
    exit 2
fi
wording=$(printf '%s\n%s\n' "$wording" "$rate")

# NO VERDICT ABOUT THE BATTERY, asserted on the words a person would read.
#
# There is not one recorded drain figure in this repo to draw a comparison
# from, so a "high"/"normal" here would be a rule written while the sense is
# unmeasured — tape by Law 5's definition, and the shape this codebase spent
# three months in a loop over. Report the number and what happened during it.
#
# A backstop, not a proof: it can only catch a verdict spelled one of these
# ways. It is here because that is the shape somebody adds at 2am when a tester
# asks "so is that bad?", and because the alternative is a comment nobody can
# check.
if printf '%s\n' "$wording" \
    | grep -qiE '"[^"]*(high|heavy|low battery|normal|healthy|fine|bad|good|too much|a lot|excessive)[^"]*"'; then
    echo "The Listening screen judges the battery instead of reporting it:"
    printf '%s\n' "$wording" | grep -iE '"[^"]*(high|heavy|low battery|normal|healthy|fine|bad|good|too much|a lot|excessive)[^"]*"'
    echo ""
    echo "No drain has ever been measured on this product, so any threshold"
    echo "behind that word is invented. Say what was spent and over how long;"
    echo "the counts on the same screen say what the phone was doing while it"
    echo "spent it, and a person judges."
    exit 2
fi
echo "the battery is reported with its window, and not graded"

# WHICH EAR REACHES A PERSON. The fold keys the day's delivered lines by the
# ear that heard them; a screen that does not draw the dictionary leaves the
# card's "the feed showing which ear" answered only line by line, and the
# number that says "the pendant heard 40, the phone 300" dies in a struct.
if ! grep -vE '^[[:space:]]*//' "$view" | tr '\n' ' ' \
    | grep -q 'tally\.linesDeliveredByEar'; then
    echo "The Listening screen no longer shows the day's lines by ear."
    exit 2
fi
echo "the day's lines are shown by the ear that heard them"

swiftc -O \
    "$app/Audio/ListenJournal.swift" \
    "$app/Audio/ListenSessionFacts.swift" \
    "$app/Audio/ListenTally.swift" \
    "$here/ListenTallyTests.swift" \
    -o "$out/tallytests"
"$out/tallytests"
