#!/bin/sh
# What first run says, and whether it is true when it says it.
#
#   sh app/ios/Tests/run_first_run_copy_tests.sh
#
# First run is the one flow in this product that asks for a person's microphone
# all day. Three of its sentences were wrong in a way nobody could see from
# inside a SwiftUI body: the progress track counted the account as zero, the
# last beat re-interrogated somebody for facts it already held, and the finale
# promised "Give me a day. You'll see." to a person who had declined the
# microphone thirty seconds earlier.
#
# The three decisions behind those sentences are now pure types in the real
# production sources, and this suite LIFTS them and compiles them — never copies
# them. A copy is honest exactly until somebody edits one side of it, which is
# the rule run_phone_number_tests.sh and run_field_caption_tests.sh already
# apply to e164 and to FieldCaption.
#
# Exit code is the result. Non-zero means first run is claiming something again.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

onboard="$app/Views/OnboardingView.swift"
finale="$app/Views/OnboardingFinale.swift"
auth="$app/Views/AuthView.swift"
diag="$app/Views/ListeningDiagnosticsView.swift"
settings="$app/Views/SettingsView.swift"
for f in "$onboard" "$finale" "$auth" "$diag" "$settings"; do
    [ -f "$f" ] || { echo "missing $f — these checks would compile nothing"; exit 2; }
done

# Whole-line comments dropped before every source scan, exactly as the theme
# contract and field caption suites do it: these files EXPLAIN the defects they
# fixed, and an explanation is the opposite of a regression.
code() { grep -vE '^[[:space:]]*//' "$1"; }

# ---------------------------------------------------------------- the wiring
#
# The logic below is worthless if the screens have stopped consulting it.

# 1. THE TRACK. Not "does FirstRunTrack exist" — does the label the person reads
#    come from it. `beatNames[step]` left against a five-element array is this
#    fix going half-done: the numbers read 2, 3, 4, 5 while every beat wears the
#    name of the one before it.
for call in 'FirstRunTrack.name(step: step' \
            'FirstRunTrack.ordinal(step: step' \
            'FirstRunTrack.spokenLabel(step: step'; do
    if ! code "$onboard" | grep -qF "$call"; then
        echo "The progress track no longer reads \`$call\`."
        echo "Whatever names and numbers the beats now is what these checks"
        echo "should follow — as written they are reading nothing."
        exit 2
    fi
done
if code "$onboard" | grep -qE 'beatNames\[step\]'; then
    echo "The track indexes beatNames[step] again."
    echo "Against a five-element array that misnames every beat by one: the"
    echo "count says 3 of 5 and the name above it says the beat before."
    exit 2
fi

# 2. THE LAST BEAT. Both halves — the title and the lead — have to come from the
#    type that checks them, or the screen is back to one fixed sentence that is
#    false on the sign-in path.
for call in 'ConfirmBeat.title(' 'ConfirmBeat.lead('; do
    if ! code "$onboard" | grep -qF "$call"; then
        echo "The number beat no longer builds its copy through \`$call\`."
        echo "A fixed sentence there claims an email and a number the account"
        echo "may not have. That is the interrogation this beat replaced,"
        echo "wearing a confirmation's clothes."
        exit 2
    fi
done
# And it must still be a confirmation rather than three open boxes. The row is
# the fix; a page that renders every field open has not shipped it.
if ! code "$onboard" | grep -q 'confirmedRow('; then
    echo "The number beat renders no confirmed row."
    echo "CONSUMER-FEEL-DIRECTION-2026-08-03.md:615-616 specified this beat as"
    echo "a confirmation — \"I'll reach you at\" and a quiet \"Change it\" —"
    echo "and an open TextField holding a value the person never typed on this"
    echo "screen is the half that kept not shipping."
    exit 2
fi
if ! code "$onboard" | grep -q "I'll reach you at"; then
    echo "The number row lost the spec's own words for what it is."
    exit 2
fi

# 2b. AND THE SEED MUST SURVIVE. Two of the three boxes are conditional now, so
#     a `.task` left hanging off a TextField would never run for the person
#     whose facts are already on file — which is everybody this beat is for.
#     `DiallingCode` is separately required by run_phone_number_tests.sh; what
#     is checked here is that the seed also records that an account's own number
#     is ALREADY SAVED, because `advance()` otherwise re-sends it and reports
#     "I couldn't save that just now" over a number already on the record.
if ! code "$onboard" | grep -q 'phoneSaved = hasStoredPhone'; then
    echo "The number beat no longer knows its seeded number is already saved."
    echo "advance() then re-sends it on every first run, and on a bad"
    echo "connection holds the person at the last page of the walkthrough with"
    echo "a save failure over a number that is already on their account —"
    echo "directly underneath a sentence saying so."
    exit 2
fi

# 3. THE FINALE. It must render the decided sentence, not a literal. The literal
#    is the bug: one sentence played over everybody.
if ! code "$finale" | grep -q 'ending.sentence'; then
    echo "OnboardingFinale no longer renders FirstRunEnding's sentence."
    echo "A literal there is the defect this type exists for: \"Give me a day."
    echo "You'll see.\" over somebody who declined the microphone."
    exit 2
fi
if code "$finale" | grep -q 'text: "Give me a day'; then
    echo "The finale has a hardcoded ending again."
    exit 2
fi

# 4. THE DOOR'S ANCHOR. Ten seconds was the only number a stranger was ever
#    given, so it became the ruler for four beats and two iOS alerts as well as
#    for the screen it was written about.
if code "$auth" | grep -q 'about ten seconds'; then
    echo "The door still budgets itself at ten seconds."
    echo "CONSUMER-FEEL-DIRECTION-2026-08-03.md §5 runs the door 0:00 to 0:20"
    echo "and reaches Home at 1:00. Ten seconds understates its own screen by"
    echo "half before it understates the rest by six times."
    exit 2
fi
if ! code "$auth" | grep -q 'Twenty seconds here, about a minute in all'; then
    echo "The door no longer anchors the whole run."
    exit 2
fi

# 5. THE LABEL THAT PROMISED A SECOND PASS. "Skip for now" ended first run: its
#    branch sets phoneSkipped, saves, and calls finish().
if code "$onboard" | grep -q 'Skip for now'; then
    echo "The number beat's opt-out says \"Skip for now\" again."
    echo "That branch calls finish() — it ends first run. \"For now\" promises"
    echo "a second pass that does not exist."
    exit 2
fi
if ! code "$onboard" | grep -q "I'll do this in Settings"; then
    echo "The number beat's opt-out no longer names the page it defers to."
    exit 2
fi
# And the microphone's opt-out is NOT the one being renamed. It is a full-width,
# unguilty button and it was already right.
if ! code "$onboard" | grep -q 'Not right now'; then
    echo "The microphone beat lost its opt-out."
    exit 2
fi

# 6. THE COST, WITH THE RECEIPT FOR IT. Every clause of the fifth promise has to
#    name a row that exists, or the consent screen is making a promise about a
#    screen that cannot keep it.
if ! code "$onboard" | grep -q 'You can see exactly what I cost'; then
    echo "The microphone primer no longer says what listening costs."
    echo "\"I keep going in the background\" is the largest cost in the product"
    echo "and it is stated with no bound; the phone has been measuring the real"
    echo "one all along and this screen never said so."
    exit 2
fi
for row in 'Battery used while listening' 'Time spent listening' 'The log'; do
    if ! grep -qF "$row" "$diag"; then
        echo "ListeningDiagnosticsView no longer shows \"$row\"."
        echo "The microphone primer promises a person can see it. A promise"
        echo "about a row that does not exist is the reason that promise was"
        echo "checked here rather than trusted."
        exit 2
    fi
done
if ! code "$settings" | grep -q 'ListeningDiagnosticsView()'; then
    echo "Settings no longer reaches ListeningDiagnosticsView."
    echo "The primer says \"Settings shows\" — that has to be a route, not a"
    echo "file that exists."
    exit 2
fi
# NO PERCENTAGE AND NO WINDOW IT DOES NOT HAVE. ListenTally.of folds every event
# still on disk and ListenJournal rotates on BYTES, never at midnight, so those
# rows can span days. The primer may not borrow a scope the arithmetic under it
# has not got, and it may not invent a drain figure this repo has never recorded.
primer=$(code "$onboard" | grep -A2 'You can see exactly what I cost')
if printf '%s\n' "$primer" | grep -q '%'; then
    echo "The cost promise carries a percentage."
    echo "ListeningDiagnosticsView:59-64 states there is not one recorded drain"
    echo "figure in this repo to draw a line from. An invented number on the"
    echo "consent screen is what law 1 exists to stop."
    exit 2
fi
if printf '%s\n' "$primer" | grep -q 'today'; then
    echo "The cost promise says \"today\"."
    echo "ListenTally.of folds every event still on disk and ListenJournal"
    echo "rotates at 256KB, not at midnight — on a quiet phone those rows cover"
    echo "several days. The screen's \"Today\" heading is a heading, not a"
    echo "window."
    exit 2
fi
echo "the track, the last beat, the door, the opt-out and the cost line are all wired"

# ------------------------------------------------------------- the real types
#
# LIFTED and compiled, never copied. Brace-matched from the declaration so no
# marker comment can rot away from the thing it claims to bracket.
# The declaration may carry a conformance clause — `enum FirstRunEnding:
# Equatable {` — so the match ends at the first character that can legally
# follow the name. A pattern anchored on `{` alone silently lifted nothing.
lift() {
    awk -v decl="^enum $2[ :{]" '
        $0 ~ decl { grab = 1 }
        grab {
            print
            n = gsub(/\{/, "{"); m = gsub(/\}/, "}")
            depth += n - m
            if (depth <= 0 && seen) { exit }
            if (n > 0) seen = 1
        }
    ' "$1"
}

{
    echo "import Foundation"
    for pair in "$onboard:FirstRunTrack" "$onboard:ConfirmBeat" "$finale:FirstRunEnding"; do
        file=${pair%:*}
        name=${pair##*:}
        lift "$file" "$name" > "$out/$name.swift"
        if ! grep -qE "^enum $name[ :{]" "$out/$name.swift"; then
            echo "Found no \`enum $name\` in $(basename "$file")." >&2
            echo "Either the type moved or this extraction broke; either way" >&2
            echo "these checks are compiling nothing, which is worse than" >&2
            echo "having none." >&2
            exit 2
        fi
        # A brace-match that stopped early compiles a fragment; one that ran
        # away swallows the rest of the file. Both are caught by the count.
        opens=$(tr -cd '{' < "$out/$name.swift" | wc -c | tr -d ' ')
        closes=$(tr -cd '}' < "$out/$name.swift" | wc -c | tr -d ' ')
        if [ "$opens" != "$closes" ] || [ "$opens" = "0" ]; then
            echo "Extracted $name has $opens '{' and $closes '}' — the lift is" >&2
            echo "not bracketing the type. These checks would test a fragment." >&2
            exit 2
        fi
        echo "// lifted $name from $(basename "$file")" >&2
        cat "$out/$name.swift"
    done
} > "$out/policies.swift"

echo "lifted $(wc -l < "$out/policies.swift" | tr -d ' ') lines of first-run copy policy"

# The lift is a law leg in its own right: compiled against Foundation ALONE, so
# the moment one of these decisions reaches for a Color, a Font or a View this
# suite stops building. Whether a sentence is TRUE has to be answerable without
# a screen, or nobody is answering it.
#
# COMPILED AS `main.swift`: swiftc allows top-level code in a file of that name
# and nowhere else. See run_phone_number_tests.sh for the whole argument.
cp "$here/FirstRunCopyTests.swift" "$out/main.swift"
swiftc -O "$out/policies.swift" "$out/main.swift" -o "$out/firstruncopytests"
"$out/firstruncopytests"
