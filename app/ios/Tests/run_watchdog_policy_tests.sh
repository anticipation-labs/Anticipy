#!/bin/sh
# Checks for ListenWatchdogPolicy — what the 4-second watchdog does about the
# state it finds.
# Pure Foundation on purpose: no simulator, no scheme, no signing, no network,
# and no device that has to receive a real phone call.
#
#   sh app/ios/Tests/run_watchdog_policy_tests.sh
#
# Exit code is the result. Non-zero means a case came back wrong.
set -e
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

listener="$app/Audio/PhoneListener.swift"

# The OPPOSITE of the tally's rule, for the opposite reason. The tally must have
# no call sites; this policy must have one. A watchdog that has gone back to
# deciding for itself, with a green suite over here vouching for a function
# nothing calls, is the blind spot open in production wearing a passing test.
if ! grep -q 'ListenWatchdogPolicy.decide(' "$listener"; then
    echo "The watchdog no longer asks ListenWatchdogPolicy what to do."
    echo "The checks below then prove nothing about the running app: they would"
    echo "vouch for a function with no call sites while the watchdog decided"
    echo "for itself again. The call site IS the fix."
    exit 2
fi

# THE WATCHDOG NEVER READS THE TRANSCRIPT STRING. The leg this replaced fired
# only when `self.partial.isEmpty`, and `partial` was assigned on every
# recognizer result and cleared only at the start of a task and on the stop path
# — never by a flush — so after the first utterance of a task it was never empty
# again and the leg was dead for the life of that task. A recognizer that went
# deaf with nothing pending was invisible for the rest of the day.
#
# A flush clears it now: `flushTail` does, so the live caption stops showing
# words that have already gone out as a line. Which is beside the point, and
# saying so is why this note is here rather than a stale count of clear sites: a
# maintainer who greps for "exactly two places", finds three including one in a
# flush, and cannot tell whether the guard is stale or the code drifted has been
# failed by the comment. The rule below does not depend on how many places clear
# the string. It forbids reading it.
#
# `partial` specifically, not `isEmpty`: whether words are UNSENT is a fact the
# policy is entitled to (`hasPending`), and the watchdog reads it off the cursor
# to answer that argument. What it may never do again is decide from the text.
# Asserted on source shape, the way run_journal_tests.sh asserts the audio tap
# closure stays journal-free.
#
# THE RANGE IS ANCHORED ON A FUNCTION NAME, so its rename would hand this rule
# an empty string to search, and a search of nothing finds no `self.partial` and
# reports success. That is the shape that let a renamed `configureAndStartEngine`
# walk a journal regression past `run_interruption_contract_tests.sh`.
body=$(awk '/private func startWatchdog/,/^    }$/' "$listener")
if [ -z "$body" ]; then
    echo "This gate can no longer find startWatchdog's body."
    echo "The rule below then searches an empty string, finds nothing, and calls"
    echo "that a pass — so the watchdog would be free to decide on the transcript"
    echo "text again, which is how a deaf recognizer stayed invisible all day."
    exit 2
fi
if printf '%s' "$body" | grep -vE '^[[:space:]]*//' \
    | grep -qE 'self\.partial([^A-Za-z]|$)'; then
    echo "The watchdog is deciding on the transcript text again."
    echo "'partial' is never empty after the first utterance of a task, so a"
    echo "leg guarded by it can never fire — which is exactly how a deaf"
    echo "recognizer with nothing pending stayed invisible all day."
    echo "Ask ListenWatchdogPolicy, which judges when things last ARRIVED."
    exit 2
fi

# THE `.standDown` ARM MUST STILL SWAP THE REQUEST WHEN THE MICROPHONE COMES
# BACK. The brief for this arm specified exactly two lines — stop the engine,
# reconfigure it — and two lines is a 120-second deaf window after every
# route-changing call. `configureAndStartEngine` reconciles `suspended` itself,
# so "did it come back" is knowable right there; a live request's format was
# fixed by its first buffer, so a call that starts on Bluetooth and ends on
# speaker feeds the new tap into a request that cannot read it. The recognizer
# then produces nothing and leg 6 does not rescue it until the quiet passes 120s.
# Asserted on source shape, like the rule above it, because nothing in a pure
# suite can see a call site.
#
# THROUGH `retryCapture` OR INLINE, either is fine, but the swap must be behind
# a check that capture actually came back. Three paths are the same moment —
# this tick, `.ended` arriving, and the owner opening the app — and they now
# share one body, so this leg follows the arm into it rather than insisting the
# call be spelled out here. Swapping unconditionally is its own defect: it
# cancels a working task to mint one over an input a call still holds.
#
# BOTH RANGES ARE CHECKED BEFORE THEY ARE READ. An empty `arm` still fails this
# leg — through the "never refreshing" branch, which would be the wrong sentence
# for the real problem — and an empty `retry` while `arm` calls `retryCapture`
# does the same. Neither says "the scan lost its anchor", so both say it now.
arm=$(awk '/case \.standDown:/,/case \.rebuild:/' "$listener" | sed '/^[[:space:]]*\/\//d')
retry=$(awk '/private func retryCapture/,/^    }$/' "$listener" | sed '/^[[:space:]]*\/\//d')
if [ -z "$arm" ]; then
    echo "This gate can no longer find the watchdog's \`.standDown\` arm."
    echo "Everything below reads that block, so a lost anchor produces a verdict"
    echo "about an empty string rather than about the code."
    exit 2
fi
if printf '%s' "$arm" | grep -q 'retryCapture' && [ -z "$retry" ]; then
    echo "The \`.standDown\` arm calls retryCapture, and this gate cannot find it."
    echo "The guarantee this leg is about — the request is swapped only once"
    echo "capture is back — lives inside that function, so it would be checked"
    echo "against nothing at all."
    exit 2
fi
if printf '%s' "$arm" | grep -q 'retryCapture'; then
    swapper="$retry"
else
    swapper="$arm"
fi
if printf '%s' "$swapper" | grep -q 'swapRecognition' \
   && ! printf '%s' "$swapper" | grep -q 'suspended'; then
    echo "The watchdog swaps the recognition request without checking that the"
    echo "microphone came back. For the length of a call that is a fresh"
    echo "SFSpeechRecognitionTask every four seconds, none of which can hear"
    echo "anything, and a working one cancelled to make each of them."
    exit 2
fi
if ! printf '%s' "$swapper" | grep -q 'swapRecognition'; then
    echo "The watchdog stands down without ever refreshing the recognition request."
    echo "A call that ends on a different route hands the new tap's format to a"
    echo "request whose format was fixed by its first buffer. The recognizer"
    echo "produces nothing, and the silence rotation does not rescue it for up to"
    echo "120 more seconds — the same deafness this card exists to close, in"
    echo "smaller form, after every call."
    exit 2
fi

swiftc -O \
    "$app/Audio/ListenJournal.swift" \
    "$app/Audio/ListenSessionFacts.swift" \
    "$app/Audio/ListenWatchdogPolicy.swift" \
    "$here/ListenWatchdogPolicyTests.swift" \
    -o "$out/watchdogtests"
"$out/watchdogtests"
