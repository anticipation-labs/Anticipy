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
# The call site, and Home. Neither was read by this suite when it was written,
# and that is exactly why a dead feature passed it: see "THE FINALE IS WIRED".
root="$app/AnticipyApp.swift"
home="$app/Views/ContentView.swift"
for f in "$onboard" "$finale" "$auth" "$diag" "$settings" "$root" "$home"; do
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

# 1b. AND IT DOES NOT COUNT OVER THE INTRODUCTION. The welcome beat is the
#     product introducing itself; a counter on it turns that into "step 1 of 5"
#     of a wizard. `design/day-zero.md` refuses wizard dots and so does the
#     audit's own rejected-recommendations list, and the comment above the
#     modifier argues it in writing — but an argument in a comment is the one
#     thing the next agent can delete without anything going red. It is a
#     SwiftUI modifier rather than a pure decision, so it is checked as source.
#
#     Both halves have to hold: invisible AND not announced. An element drawn
#     at zero opacity that still reads "Step 1 of 5" to VoiceOver is a wizard
#     for screen-reader users only, which is worse than the bug.
if ! code "$onboard" | grep -q 'step == Step.welcome ? 0 : 1'; then
    echo "The progress track no longer hides itself on the welcome beat."
    echo "That renders \"Hello   2 of 5\" over the product's own introduction:"
    echo "wizard dots in prose. day-zero.md and the mobile-UX audit both refuse"
    echo "it, and the comment above that line argues it out."
    exit 2
fi
if ! code "$onboard" | grep -q 'accessibilityHidden(step == Step.welcome)'; then
    echo "The track is hidden by opacity but still announced on welcome."
    echo "A counter nobody can see that VoiceOver still reads aloud is a wizard"
    echo "for screen-reader users only."
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
#     The NAME AND EMAIL need the same guard, and did not get it: they were
#     seeded from the account by the same `.task` and re-sent by the same
#     `advance()` one branch below the number's guard. Same false failure, same
#     screen, same connection — "I couldn't save that just now" over an email
#     the account already holds.
#     Checked at the USE, not the declaration. The first draft of this leg
#     grepped for `detailsChanged` alone and a mutation that deleted it from
#     the `if` — leaving the `let` above it — walked straight through green.
#     A computed guard nothing branches on is the same bug wearing a variable
#     name, which is what check 1 says about `beatNames[step]`.
if ! code "$onboard" | grep -q 'detailsSaved, detailsChanged'; then
    echo "The last beat re-sends the name and email unchanged."
    echo "Both are seeded from the account, so somebody who signs in and leaves"
    echo "the first-name box alone re-sends facts already on their record. On a"
    echo "bad connection that holds them at the last page of first run under a"
    echo "save failure over their own saved email. The number got this guard;"
    echo "these two live one branch below it."
    exit 2
fi
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

# 3b. THE FINALE IS WIRED, which is the check whose absence made every other
#     check in this section worthless. `FirstRunEnding` was correct, compiled
#     and green while the call site read `OnboardingFinale { celebrating =
#     false }` — a trailing closure binds to the LAST parameter, so the two
#     facts fell back to their defaults, every ending collapsed to `.listening`
#     and "Give me a day. You'll see." still played over somebody who had
#     declined the microphone. The whole feature was dead and this suite said
#     "all first-run copy checks passed".
#
#     A decision nothing consults is not shipped. Read the call site.
if ! code "$root" | grep -q 'OnboardingFinale(listening:'; then
    echo "AnticipyApp no longer passes the two facts to OnboardingFinale."
    echo "Whatever it passes instead, the ending is decided by defaults again:"
    echo "one sentence over everybody, including the person who just tapped"
    echo "\"Not right now\" on the microphone. FirstRunEnding being right does"
    echo "not matter if nothing asks it."
    exit 2
fi
if ! code "$root" | grep -q 'micBlocked:'; then
    echo "AnticipyApp passes no micBlocked: to OnboardingFinale."
    echo "The \"iOS has my microphone switched off\" ending is unreachable."
    exit 2
fi
# And the defaults must stay gone. Restoring one makes the old broken call
# compile again, which is how this shipped dead the first time: with a default
# in place, deleting the argument is a silent copy change rather than a build
# error. It also puts the answer in two places, and the second one is invisible
# — flipping `= true` to `= false` there rewrote the last sentence of first run
# for every person alive and turned nothing red.
if code "$finale" | grep -qE '^[[:space:]]*(var|let) (listening|micBlocked)[[:space:]]*='; then
    echo "OnboardingFinale defaults listening/micBlocked again."
    echo "Un-defaulted, a dropped argument is a build error. Defaulted, it is a"
    echo "wrong sentence on the last screen of first run with a green suite"
    echo "over it — which is what happened."
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
if ! code "$auth" | grep -q 'About twenty seconds here and one minute from start to finish'; then
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
if ! code "$onboard" | grep -q 'Review usage and activity'; then
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
primer=$(code "$onboard" | grep -A2 'Review usage and activity')
if printf '%s\n' "$primer" | grep -q '%'; then
    echo "The cost promise carries a percentage."
    echo "ListeningDiagnosticsView's \"NO VERDICT\" note states there is no recorded drain"
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
# 7. THE CITATIONS RESOLVE.
#
# "READ THE COMMENT ABOVE THE LINE BEFORE CHANGING THE LINE" is the mechanism
# this repo leans on hardest — the mobile-UX audit records it killing a third
# of its own findings. That makes a comment pointing at the wrong code worse
# than a comment saying nothing: the next reader follows it, lands on a toolbar
# modifier or a pause menu, concludes the note is nonsense, and reverts a
# correct fix. Five citations written into these files during this group's
# first pass were wrong on the DAY THEY WERE WRITTEN, not merely drifted.
#
# So the comments here now cite QUOTED COPY AND SYMBOL NAMES, never line
# numbers, and the quotations are checked. A line number rots in silence the
# next time somebody inserts a paragraph above it; a quotation that stops
# resolving fails this suite. Comments are the target, so these scan the RAW
# files rather than `code`.
missing_citation() {
    echo "A comment in first run cites \"$2\" in $(basename "$1"), which is not there."
    echo "Either the quoted copy moved and the citation must follow it, or the"
    echo "citation was never right. Both are load-bearing: this repo's rule is"
    echo "to read the comment above the line, and a citation that sends the"
    echo "reader to unrelated code trains them out of doing that."
    exit 2
}
# OnboardingFinale's header rests its whole case on Home contradicting the
# promise one screen later, and on ContentView's own warning about isListening.
for quote in "I'm not listening yet, tap Listen with phone" \
             "the owner's standing wish, not a fact about the"; do
    grep -qF "$quote" "$home" || missing_citation "$home" "$quote"
done
# The number beat's opt-out says "I'll do this in Settings." and names the two
# sections that have to hold those three fields for that to be true.
for quote in 'Section("You")' 'Section("Your number")' \
             "Find out what listening actually did"; do
    grep -qF "$quote" "$settings" || missing_citation "$settings" "$quote"
done
# The cost promise leans on this file shipping in release and refusing a verdict.
for quote in "SHIPS IN RELEASE" "NO VERDICT"; do
    grep -qF "$quote" "$diag" || missing_citation "$diag" "$quote"
done
# And no first-run comment may go back to citing a line number, which is the
# habit rather than the instance. `swift:123` in a comment is the shape.
for f in "$onboard" "$finale" "$auth"; do
    if grep -nE '`[A-Za-z]+\.swift:[0-9]+' "$f"; then
        echo "^ $(basename "$f") cites a line number again."
        echo "Every one of those written in this group's first pass pointed at"
        echo "unrelated code within days, several on the day of writing. Cite"
        echo "the quoted copy or the symbol; those move with the thing they name"
        echo "and this suite can check them."
        exit 2
    fi
done

echo "the track, the last beat, the finale's wiring, the door, the opt-out, the"
echo "cost line and every citation in first run all resolve"

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
