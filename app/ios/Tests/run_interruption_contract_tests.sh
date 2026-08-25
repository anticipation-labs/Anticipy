#!/bin/sh
# The interruption contract, checked where it actually lives: PhoneListener.
#
#   sh app/ios/Tests/run_interruption_contract_tests.sh
#
# WHY A SOURCE SCAN AND NOT A SUITE. Every other check in Tests/ compiles a
# pure Foundation file with swiftc and calls it. PhoneListener can never be one
# of those: it owns AVAudioEngine, SFSpeechRecognizer and a UIKit background
# task assertion, so there is no macOS binary that can execute it — and the
# simulator does not model phone calls or Siri, so there is no runtime that can
# produce the events these rules are about either. Every defect below is
# structural: WHERE a call is made, not what a function returns. A scan is the
# only instrument that can see that, exactly as the theme contract is the only
# instrument that can see a colour decided outside the token layer.
#
# WHAT THESE RULES COST IF THEY GO. Each one is a measured failure:
#
#   1+2. The assertion was taken on `.began` and released on `.ended`. Nothing
#        released it where `suspended` actually clears, so a Siri interruption
#        that iOS never delivers an `.ended` for left it held with no
#        interruption in progress — burning background execution on the next
#        backgrounding. And releasing it ON `.ended` spent it before the retake
#        was known to have worked: a call ending with the phone in a pocket
#        finds a 0 Hz input, `suspended` goes straight back to true, and the app
#        now has no audio and no assertion. iOS suspends it, the watchdog
#        freezes, and listening does not return until somebody opens the app.
#        The thirty seconds the assertion exists to buy was exactly the window
#        the retry needed.
#
#   3.   `.appReturned` was recorded before the rebuild it names. Six glances at
#        the app during one call wrote six journal lines claiming listening came
#        back, and minted six recognition tasks that could hear nothing, while
#        it came back zero times.
#
#   1b.  The observer acts on the EDGE. Without that guard the watchdog's
#        assignment every four seconds ends the assertion and takes a new one,
#        so the ~30s iOS is prepared to grant becomes a grant renewed 150 times
#        across a ten-minute call. Nothing leaks and nothing looks wrong, which
#        is why it needs a rule rather than a reader.
#
#   4.   The session-facts line was gated on `!suspended`, which also silenced
#        it on the tick a call ENDS — the one moment the facts are worth having,
#        because the route may have changed underneath.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
f="$here/../Anticipy/Audio/PhoneListener.swift"
[ -f "$f" ] || { echo "missing $f"; exit 2; }
fail=0

# PROSE IS NOT CODE. This file EXPLAINS the defects it fixed, at length, so a
# scan that reads comments would flag the explanation of the very bug it is
# guarding against. Whole-line comments come out before every rule below, the
# same way the theme contract drops them.
code=$(mktemp); trap 'rm -f "$code"' EXIT
grep -v '^ *//' "$f" > "$code"

# The body of a brace block that starts at the first line matching $1 and ends
# at the first line that is exactly $2. Ranges, not brace counting: every block
# below closes at a known indent.
#
# AND A BLOCK THAT DID NOT STOP WHERE IT SHOULD SAYS SO, instead of handing the
# rules a larger piece of the file to be satisfied by. An empty block passing
# every rule and an over-wide block passing every rule are the same defect from
# two sides: rule 5 asks whether a `.noted(` inside `configure` is guarded, and
# a `configure` that swallowed the next method as well can be satisfied by a
# guard that has nothing to do with it. Reindent the closing brace and the range
# runs on to the next line of the same shape — the next member declaration if
# there is one, the end of the file if there is not. Both are reported.
block() {
    awk -v start="$1" -v end="$2" '
        $0 ~ start { inb = 1; opened = NR }
        inb { buf = buf $0 "\n" }
        inb && NR > opened && $0 ~ /^    (private )?(func |var |let |@Published )/ {
            print "OVERRAN"; exit
        }
        inb && $0 == end { printf "%s", buf; closed = 1; exit }
        END { if (inb && !closed) print "UNCLOSED" }
    ' "$code"
}

suspended_observer=$(block '@Published var suspended' '    }')
interruption_observer=$(block 'interruptionNotification' '        }')
retake=$(block 'func retakeMicrophone' '    }')
retry=$(block 'func retryCapture' '    }')
configure=$(block 'func configureAndStartEngine' '    }')

# A BLOCK THAT CAME BACK EMPTY IS A RULE THAT CANNOT FAIL. Every rule below
# reads one of these five strings and asks what is inside it, and `case "" in
# *X*)` matches nothing — so a renamed function does not fail this file, it
# empties it and leaves the success sentence at the bottom printing.
#
# Measured, by a reviewer: rename `configureAndStartEngine` to
# `rebuildCaptureChain` and restore the pre-fix churn — an unguarded
# `.noted(facts)` on every watchdog tick, fifteen identical lines a minute, the
# 400-line ring gone in twenty-seven — and this file printed "the facts are
# written when they change" and exited 0. The habit already existed here: rule 4
# guarded `retryCapture` with exactly this check, and an empty `suspended`
# observer happens to fail rule 1 anyway because rule 1 demands a match. It was
# the three asking only what a block does NOT contain — the interruption
# observer, the retake, and `configure` — that had nothing to fail on.
need() {
    case "$2" in
        "") echo "This gate can no longer find $1 in PhoneListener.swift."
            echo "$3"
            echo "Every rule about it below now reads an empty string, matches nothing"
            echo "and passes." ;;
        *UNCLOSED*|*OVERRAN*)
            echo "This gate found $1 in PhoneListener.swift and not the end of it."
            echo "$3"
            echo "The block runs past the next declaration, or off the end of the"
            echo "file, so every rule about it below is answered by whatever the rest"
            echo "of PhoneListener happens to contain rather than by that block." ;;
        *)  return 0 ;;
    esac
    echo "Point the scan at the new name or the new shape, or delete the rule and"
    echo "say why the failure it was written for cannot happen any more."
    fail=1
}
need "the \`suspended\` observer" "$suspended_observer" \
     "That observer is where the background assertion is taken and released."
need "the interruption observer" "$interruption_observer" \
     "That observer is the one place forbidden to touch the assertion."
need "retakeMicrophone()" "$retake" \
     "That is the path a person triggers by opening the app mid-call."
need "retryCapture()" "$retry" \
     "That is the shared body all three 'the mic may be back' paths go through."
need "configureAndStartEngine()" "$configure" \
     "That is the method the 4s watchdog re-enters for the length of a call."
[ "$fail" = "0" ] || exit 1

# 1. THE ASSERTION HAS THE SAME LIFETIME AS THE FLAG. `suspended` means the
#    microphone is not ours; the assertion is the running time bought to get it
#    back. Binding them at the one place the flag changes is what makes "held
#    while, and only while, it is needed" true by construction, instead of true
#    only for the paths somebody remembered.
case "$suspended_observer" in
    *beginBackgroundAssertion\(\)*) ;;
    *) echo "The background assertion is not taken where \`suspended\` becomes true."
       echo "Then a mic that goes away by a route nobody listed — the 0 Hz guard, a"
       echo "failed engine start — has no running time bought for getting it back."
       fail=1 ;;
esac
case "$suspended_observer" in
    *endBackgroundAssertion\(\)*) ;;
    *) echo "The background assertion is not released where \`suspended\` becomes false."
       echo "Capture came back and the assertion is still held with no interruption in"
       echo "progress. iOS grants ~30s of background execution to an app with nothing"
       echo "left to do, and eventually stops granting it."
       fail=1 ;;
esac

# 1b. AND ON THE EDGE, NOT ON EVERY WRITE. `configureAndStartEngine` assigns
#     `suspended` on every one of the 4-second watchdog's ticks, so without the
#     edge guard a ten-minute call re-enters `beginBackgroundAssertion()` 150
#     times. Each entry ends the identifier it is holding and takes a fresh one,
#     so nothing leaks and nothing looks wrong — and the roughly thirty seconds
#     iOS is willing to grant has quietly become a grant renewed every four
#     seconds for as long as the call lasts. The cap the assertion exists to
#     respect, removed with no symptom, past a green gate. Rules 1 and 2 above
#     only ask that both calls appear somewhere inside this observer, which they
#     still would.
case "$suspended_observer" in
    *"guard suspended != oldValue"*) ;;
    *) echo "The \`suspended\` observer acts on every write, not on the edge."
       echo "The watchdog assigns this flag every four seconds for the whole of a"
       echo "call, so each tick ends the assertion and takes another one: a 30s"
       echo "grant renewed 150 times over a ten-minute call, which is not what iOS"
       echo "grants and not what the comment above the observer promises."
       fail=1 ;;
esac

# 2. AND NOTHING ELSE MAY TOUCH IT. `.ended` is the notification whose own
#    comment three lines away says iOS sometimes never sends it. An assertion
#    released there is released on a promise, before the retake it is paying
#    for has been shown to work.
case "$interruption_observer" in
    *BackgroundAssertion*)
        echo "The interruption notification takes or releases the assertion itself."
        echo "\`.ended\` is not proof the microphone is back: the retake that follows"
        echo "can find a 0 Hz input and set \`suspended\` straight back to true, and"
        echo "the app is then holding no assertion in the exact state it was bought"
        echo "for. Let \`suspended\`'s observer own it."
        fail=1 ;;
esac

# 3. NOTHING IS RECORDED BEFORE THE THING IT CLAIMS HAPPENED. `.appReturned`
#    answers "how often did she only come back because he opened the app?", and
#    an answer written on ATTEMPT is that question answered in the flattering
#    direction.
case "$retake" in
    *ListenJournal*)
        echo "retakeMicrophone() writes to the journal itself."
        echo "It runs before the rebuild it describes, and the rebuild can return at"
        echo "the 0 Hz guard having done nothing. Six glances at the app during one"
        echo "call then read as six recoveries that never happened. Let the swap"
        echo "record it, on the far side of a capture that actually came back."
        fail=1 ;;
esac

# 4. ...AND THE RETAKE ITSELF ONLY REBUILDS THE REQUEST WHEN THERE IS SOMETHING
#    TO HEAR. A fresh SFSpeechRecognitionTask over an input a call still holds
#    is a task that can hear nothing, and the old one is cancelled to make it.
# `retryCapture` existing at all is asserted by `need` above, which is where
# that check moved when the other four blocks got the same guard. There is no
# shared retry between the watchdog's stand-down and the owner coming back
# without it, and both are "the microphone may be ours again".
case "$retry" in
    *'guard !suspended'*) ;;
    *) echo "retryCapture() swaps the recognition request without checking that"
       echo "capture came back. That is a dead task minted per attempt."
       fail=1 ;;
esac
case "$retake" in
    *retryCapture\(*) ;;
    *) echo "retakeMicrophone() no longer goes through the shared retry, so the"
       echo "guarantee above says nothing about the path a person actually triggers."
       fail=1 ;;
esac

# 5. THE SESSION FACTS ARE WRITTEN ON CHANGE, NOT ON A FLAG. Gating them on
#    `!suspended` killed the churn — 210 identical lines in a 14-minute call,
#    evicting the 400-line ring — and also killed the line on the tick the call
#    ENDS, which is the one moment the session is worth describing, because the
#    route may have changed under it.
facts_guarded=$(printf '%s\n' "$configure" | awk '
    /\.noted\(/ {
        if (p1 !~ /lastSessionFacts/ && p2 !~ /lastSessionFacts/ && p3 !~ /lastSessionFacts/)
            print "unguarded"
    }
    { p3 = p2; p2 = p1; p1 = $0 }')
[ -z "$facts_guarded" ] || {
    echo "The session-facts line is not written on CHANGE."
    echo "A \`!suspended\` gate stops the churn by silencing the whole outage,"
    echo "including the tick capture comes back on a route that may be new."
    fail=1
}

[ "$fail" = "0" ] || exit 1
echo "interruption contract: the assertion lives as long as the outage, the"
echo "retake records only what happened, and the facts are written when they change"
