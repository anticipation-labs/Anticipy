#!/bin/sh
# What the Settings interview section offers, what it says she holds, and the
# one number on that screen the phone actually measured.
#
#   sh app/ios/Tests/run_interview_invite_tests.sh
#
# THREE DEFECTS, ONE SCREEN, and they share a shape: a sentence that was written
# once and then never asked what was true.
#
#   The button was two-way on `isComplete`, so it read "Let me ask you six
#   questions" directly above a caption reading "You've answered 4 of 6". Two
#   halves of one section, reading one `InterviewProgress`, disagreeing.
#
#   That caption's opening read "You haven't told me anything about your life
#   yet" under a heading reading "What I know about you" — on a screen holding
#   her first name, her number, and every source she has been let into.
#
#   And the listening headline says "I'm listening on this phone." off
#   `capturing`, which is `isListening && !suspended` — the app's own intent
#   flags. That is the exact shape of the thirty deaf hours CLAUDE.md records:
#   intent said yes the whole time. The measured half was one tap deeper.
#
# Two instruments, because these can fail in two different ways:
#
#   The swiftc suite proves the WORDING — every combination, and the law legs
#   that no table of answers can carry: never naming a grant she does not hold,
#   never naming an absence, and never a fraction anywhere.
#
#   The scans prove the SCREEN STILL ASKS — that the button, the caption and the
#   listening row are wired to what is true rather than to a constant, and that
#   no threshold, colour or verdict has grown onto the measured number.
#
# Exit code is the result. Non-zero means the section is telling somebody
# something about themselves that is not so.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
settings="$app/Views/SettingsView.swift"
interview="$app/Interview.swift"
duration="$app/Audio/PlainDuration.swift"
tally="$app/Audio/ListenTally.swift"
tests="$here/InterviewInviteTests.swift"
for f in "$settings" "$interview" "$duration" "$tally" "$tests"; do
    [ -f "$f" ] || { echo "missing $f — these checks would read nothing"; exit 2; }
done
fail=0

# PROSE IS NOT CODE. This file argues at length about the sentences it refuses,
# and an explanation is the opposite of a regression. Whole-line comments come
# out before every scan, exactly as the field-caption and duration runners do it.
strip() { grep -v '^ *//' "$1"; }

out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
strip "$settings" > "$out/settings.code.swift"

# ======================================================================
# FIX 6 — the button counts what is left
# ======================================================================

# 1. THE BUTTON ASKS THE POLICY. A green suite over a type the screen no longer
#    consults is the failure this repo has recorded repeatedly — most recently
#    `FirstRunOwnership`, which shipped complete, correct, in the pbxproj, and
#    with zero call sites.
if ! grep -q 'InterviewInvitation\.buttonLabel(' "$out/settings.code.swift"; then
    echo "Settings' interview button no longer asks InterviewInvitation for its label."
    echo "Everything below then proves nothing about anything anybody reads."
    fail=1
fi

# 2. AND IT COUNTS WHAT IS ACTUALLY LEFT. `isComplete` is a bool; it cannot tell
#    four-answered from none-answered, which IS the defect. `remaining.count`
#    is the only reading on this screen that can.
if ! grep -q 'InterviewProgress()\.remaining\.count' "$out/settings.code.swift"; then
    echo "Settings' interview button no longer reads remaining.count."
    echo "A bool cannot tell four-answered from none-answered, and telling those"
    echo "apart is the whole of this fix: the two-way label offered six questions"
    echo "to somebody who had answered four."
    fail=1
fi

# 3. THE TWO-WAY TERNARY IS NOT BACK. Matched on the label string rather than on
#    `isComplete`, which is still legitimately read by the button's ACTION — the
#    tap reopens every question when they are all answered, and must go on doing
#    so.
if grep -q '? "Go over my questions again"' "$out/settings.code.swift"; then
    echo "The two-way label ternary is back on the interview button."
    echo "It cannot see the middle, which is where the contradiction lived."
    fail=1
fi

# 4. THE REOPEN SURVIVES. Offering "go over them again" and then opening a
#    screen with nothing to ask is an offer that does nothing, and the button's
#    own comment has said so since it was written.
if ! grep -q 'reopenAll()' "$out/settings.code.swift"; then
    echo "Settings' interview button no longer reopens the questions when complete."
    echo "'Go over my questions again' would then open a screen with nothing on it."
    fail=1
fi

# 5. THE SPELLED NUMERAL, WHICH IS THE ONE THING THE SWIFT SUITE CANNOT CHECK.
#    Two sentences in SettingsView spell "six" in prose — the untouched opening
#    offer and the untouched holdings tail. Both are true only while the script
#    holds exactly six questions, and neither has any way to find out. This is
#    that check, and it is deliberately red rather than clever: if a seventh
#    question ships, these words are wrong on somebody's screen and a person has
#    to choose the new ones.
script_count=$(awk '
    /static let script: \[InterviewQuestion\] = \[/ { grab = 1 }
    grab && /^            id: "/ { n += 1 }
    grab && /^    \]$/ { print n; exit }
' "$interview")
if [ -z "$script_count" ]; then
    echo "Could not count InterviewQuestion.script — the extraction has broken."
    echo "Either the array moved or its shape changed; either way the 'six' in"
    echo "Settings' prose is now unchecked, which is worse than having no check."
    fail=1
elif [ "$script_count" != "6" ]; then
    echo "InterviewQuestion.script now holds $script_count questions, not six."
    echo "SettingsView spells 'six' in prose twice — the opening button label"
    echo "and the tail of the holdings line — and both are now false. A spelled"
    echo "numeral cannot check itself, so this leg is the only thing that ever"
    echo "will. Change the words in InterviewInvitation, then this number here."
    fail=1
fi

# ======================================================================
# FIX 17 — the line opens with what she genuinely holds
# ======================================================================

# 6. THE CAPTION ASKS THE POLICY, and asks it about all four holdings. A call
#    that has quietly lost an argument goes on compiling and goes on being
#    wrong: drop `calendar:` and she stops mentioning a grant she holds, which
#    is the same silence this fix was written to end.
empty_branch=$(awk '
    /InterviewInvitation\.nothingAnswered\(/ { grab = 1; buf = ""; depth = 0 }
    grab {
        buf = buf $0 " "
        n = gsub(/\(/, "("); m = gsub(/\)/, ")")
        depth += n - m
        if (depth <= 0) { print buf; exit }
    }
' "$out/settings.code.swift")
if [ -z "$empty_branch" ]; then
    echo "Settings' interview caption no longer asks InterviewInvitation what she holds."
    echo "It would then be back to 'You haven't told me anything about your life"
    echo "yet' under a heading reading 'What I know about you', four sections"
    echo "below a field holding somebody's first name."
    fail=1
else
    for arg in 'name: !session\.ownerFirstName\.isEmpty' \
               'number: !session\.ownerPhone\.isEmpty' \
               'calendar: grants\.granted(\.calendar)' \
               'contacts: grants\.granted(\.contacts)'; do
        printf '%s\n' "$empty_branch" | grep -q "$arg" || {
            echo "Settings' holdings line no longer reads: $arg"
            echo "A holding that stops being read is a grant she stops mentioning,"
            echo "or worse, a field she claims and does not have."
            fail=1; }
    done
    # READ FROM THE SESSION, NOT FROM THE FIELDS. `firstName` and `phoneField`
    # are @State seeded on appear and can hold typing nobody has saved. This
    # sentence is about what she HOLDS.
    if printf '%s\n' "$empty_branch" | grep -qE '(name|number): !?(firstName|phoneField)'; then
        echo "Settings' holdings line reads an unsaved text field instead of the session."
        echo "Those fields hold typing that has not been saved, so she would claim"
        echo "to know a name that exists only on the keyboard in front of somebody."
        fail=1
    fi
fi

# 7. THE FRACTION BRANCHES SURVIVE UNTOUCHED. This fix was scoped to the ONE
#    false sentence. The two branches that report a real count were already
#    true, and `interviewState`'s own standing order is that this stays a
#    sentence rather than a bar — replacing them with a meter is the failure
#    mode on the other side of this fix.
if ! grep -q "You've answered .(answered) of .(InterviewQuestion.script.count)" \
        "$out/settings.code.swift"; then
    echo "Settings' answered-count sentence has changed or gone."
    echo "This fix was scoped to the empty branch, which was the false one. The"
    echo "counted branches were already true, and the standing order on this"
    echo "line is that it stays a sentence and never becomes a fraction on a bar."
    fail=1
fi

# ======================================================================
# FIX 8 — the measured silence, on the row people open
# ======================================================================

# 8. THE ROW EXISTS AND ASKS THE SHARED FORMATTER. Not six lines of arithmetic:
#    the diagnostics screen reports these same `unheardForSeconds`, and the
#    no-verdict argument both screens rest on holds only while "6 hr 20 min"
#    here is not "6.3 hours" there.
if ! grep -q 'Nothing heard for .(PlainDuration\.words(' "$out/settings.code.swift"; then
    echo "Settings no longer reports how long the phone has heard nothing,"
    echo "or has stopped asking PlainDuration how to word it."
    echo "The headline above that row is built from \`capturing\`, which is"
    echo "\`isListening && !suspended\` — the app's own intent flags. It says"
    echo "\"I'm listening on this phone.\" for exactly the thirty deaf hours"
    echo "CLAUDE.md records. This line is the measured half."
    fail=1
fi

# 9. IT IS COMPUTED IN A `.task`, OFF THE MAIN THREAD. `persistedEvents` reads
#    up to 512KB through a synchronous `queue.sync` and parses every line. The
#    `onAppear` beside it is three field reads; putting this there would hitch
#    the first frame of the one screen people open when they want listening to
#    STOP.
if ! grep -q '\.task { unheard = await ' "$out/settings.code.swift"; then
    echo "The unheard fold is no longer computed in a .task."
    echo "persistedEvents is file I/O plus a parse of every line. In onAppear it"
    echo "hitches the first frame of the screen somebody opens to stop listening."
    fail=1
fi
if ! grep -q 'Task\.detached' "$out/settings.code.swift"; then
    echo "The unheard fold no longer runs off the main actor."
    echo "A .task body is main-actor bound; the disk read has to leave it."
    fail=1
fi
if grep -qE 'onAppear.*persistedEvents|onAppear.*ListenTally\.of' "$out/settings.code.swift"; then
    echo "The unheard fold has moved back into an onAppear."
    fail=1
fi

# 10. IT PASSES `now:`. A fold that can only measure to the journal's own last
#     line answers "58 min" for a phone that has been deaf since breakfast,
#     because on that day the last line IS the failure — a call took the
#     microphone at nine and nothing wrote another line after it. A reassuring
#     wrong number is worse than no number, because it is believed.
if ! grep -q 'ListenTally\.of(ListenJournal\.shared\.persistedEvents,' "$out/settings.code.swift"; then
    echo "Settings no longer folds the persisted journal for the unheard stretch."
    fail=1
fi
if ! grep -q 'now: Date()' "$out/settings.code.swift"; then
    echo "The unheard fold no longer passes \`now:\`."
    echo "Without it the fold measures to the journal's last line, and on the one"
    echo "day this row exists for that line is the stop itself: a phone deaf"
    echo "since breakfast reports the 58 minutes before the call and nothing"
    echo "after it. run_tally_tests.sh holds the same argument on the other side."
    fail=1
fi

# 11. NO THRESHOLD DECIDES THAT THE NUMBER IS WORTH MENTIONING. Above zero is
#     the only gate, and zero is not a threshold — it is the owner's own off
#     switch, because ListenTally hard-zeroes this under `.stoppedByOwner`.
#     Anything else compared against this number is a rule deciding when silence
#     becomes a finding, written while there is no recorded normal to draw it
#     from. That is law 1, on the one screen that reports the senses.
if ! grep -q 'if unheard > 0 {' "$out/settings.code.swift"; then
    echo "The unheard row is no longer gated on \`unheard > 0\`."
    echo "Either it now renders over somebody's own deliberate silence, or a"
    echo "threshold has been put in front of it. Both are the same defect: a rule"
    echo "deciding when a measurement is worth saying."
    fail=1
fi
thresholds=$(grep -nE 'unheard[^A-Za-z][^/]*[<>]=?[[:space:]]*[1-9]' "$out/settings.code.swift" || true)
if [ -n "$thresholds" ]; then
    echo "A threshold has grown onto the unheard number:"
    printf '%s\n' "$thresholds"
    echo "There is no recorded normal in this repo to draw a line from, so any"
    echo "line here is invented. A phone that has heard nothing for eleven hours"
    echo "and one that has heard nothing for four minutes both say so, and the"
    echo "reader judges."
    fail=1
fi

# 12. AND NO COLOUR OR VERDICT ON IT. `alarm` is this app's word for a thing
#     that is wrong, and `accent` is its word for a thing that went right;
#     either one on this row is the screen deciding for the reader. The sentence
#     takes the same weight the diagnostics screen gives it and stops.
verdict=$(awk '
    /if unheard > 0 \{/ { grab = 1; depth = 0; seen = 0 }
    grab {
        buf = buf $0 " "
        n = gsub(/\{/, "{"); m = gsub(/\}/, "}")
        depth += n - m
        if (n > 0) seen = 1
        if (seen && depth <= 0) { print buf; exit }
    }
' "$out/settings.code.swift")
if [ -n "$verdict" ]; then
    if printf '%s\n' "$verdict" | grep -qE 'Theme\.(alarm|accent)|\.red|\.orange|\.green'; then
        echo "The unheard row has been given a colour that judges it:"
        printf '%s\n' "$verdict"
        echo "alarm is this app's word for a thing that is wrong. Nothing on this"
        echo "screen can know that six hours of quiet is wrong — there is no"
        echo "recorded normal — so the row reports and the reader judges."
        fail=1
    fi
    for banned in "too long" "you missed" "you're missing" "check this" \
                  "something's wrong" "deaf" "!"; do
        if printf '%s\n' "$verdict" | grep -qiF "$banned"; then
            echo "The unheard row has grown a verdict: \"$banned\""
            echo "It names a magnitude and stops. The reader judges."
            fail=1
        fi
    done
fi

# 13. NO BADGE, METER, GAUGE OR COUNTDOWN ANYWHERE ON THIS SCREEN. The audit
#     that produced these three fixes is explicit that loss aversion applied
#     literally would destroy an app that asks for a microphone all day. Scoped
#     to this file, which is the one these checks own.
#
#     "percent" IS DELIBERATELY NOT IN THIS PATTERN. The pendant row renders
#     `PendantBatteryPolicy.detail(percent:)`, and that is a hardware reading
#     off a physical battery with its own policy type and its own tests — the
#     same class of number as the battery figure the diagnostics screen prints
#     beside what bought it. What the audit bans is a percentage INVENTED to
#     score somebody's progress, and no grep can tell those apart; the legs
#     above are what hold that line, by pinning the two places on this screen
#     where a score would actually have gone.
shapes=$(grep -nE 'ProgressView|\.badge\(|Gauge\(|Countdown|countdown' \
    "$out/settings.code.swift" || true)
if [ -n "$shapes" ]; then
    echo "A meter, badge, gauge, percentage or countdown has appeared in Settings:"
    printf '%s\n' "$shapes"
    echo "None of these fixes needs one, and the section they touch has been"
    echo "argued out of having one twice."
    fail=1
fi

[ "$fail" = "0" ] || exit 1

# ======================================================================
# THE REAL TYPE
# ======================================================================
#
# LIFTED from SettingsView.swift and compiled, never copied — the same rule
# run_field_caption_tests.sh applies to FieldCaption and run_phone_number_tests.sh
# applies to e164, for the same reason: a copy is honest exactly until somebody
# edits one side of it.
#
# The lift is a law leg in its own right. It is compiled against Foundation
# ALONE, so the moment this enum reaches for a Color, a Font or a View the suite
# stops building. Deciding what is true of somebody's account has to be
# answerable without a screen, or it cannot be tested without one.
awk '
    /^enum InterviewInvitation \{/ { grab = 1 }
    grab {
        print
        n = gsub(/\{/, "{"); m = gsub(/\}/, "}")
        depth += n - m
        if (depth <= 0 && seen) { exit }
        if (n > 0) seen = 1
    }
' "$settings" > "$out/lifted.swift"

if ! grep -q '^enum InterviewInvitation {' "$out/lifted.swift"; then
    echo "Found no \`enum InterviewInvitation\` in SettingsView.swift."
    echo "Either the type moved or this extraction broke; either way these checks"
    echo "are compiling nothing, which is worse than having none."
    exit 2
fi
# A brace match that stopped early compiles a fragment; one that ran away
# swallows the rest of the file. The closing-brace count catches both.
opens=$(tr -cd '{' < "$out/lifted.swift" | wc -c | tr -d ' ')
closes=$(tr -cd '}' < "$out/lifted.swift" | wc -c | tr -d ' ')
if [ "$opens" != "$closes" ] || [ "$opens" = "0" ]; then
    echo "The extracted InterviewInvitation has $opens '{' and $closes '}' — the"
    echo "extraction is not bracketing the enum. These checks would test a fragment."
    exit 2
fi
for name in 'static func buttonLabel' 'static func nothingAnswered' \
            'static func sentenceList'; do
    grep -q "$name" "$out/lifted.swift" || {
        echo "The extracted InterviewInvitation is missing \`$name\` — the lift is short."
        exit 2; }
done
# COMPILED AGAINST FOUNDATION ALONE. If the enum has reached for SwiftUI, this
# is where it stops.
if grep -qE 'import (SwiftUI|UIKit|AppKit)|Theme\.|Color\.|Font\.' "$out/lifted.swift"; then
    echo "InterviewInvitation has reached for the view layer:"
    grep -nE 'import (SwiftUI|UIKit|AppKit)|Theme\.|Color\.|Font\.' "$out/lifted.swift"
    echo "It decides what is TRUE of somebody's account. A decision that needs a"
    echo "screen to make cannot be tested without one, and would then be tested"
    echo "by nobody."
    exit 2
fi
echo "lifted InterviewInvitation from SettingsView.swift: $(wc -l < "$out/lifted.swift" | tr -d ' ') lines"

{
    echo "import Foundation"
    cat "$out/lifted.swift"
} > "$out/InterviewInvitation.swift"

swiftc -O "$out/InterviewInvitation.swift" "$tests" -o "$out/interviewinvitetests"
"$out/interviewinvitetests"
