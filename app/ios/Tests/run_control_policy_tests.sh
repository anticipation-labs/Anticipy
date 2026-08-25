#!/bin/sh
# Checks for ListenControlPolicy — what the listening control says, what
# tapping it does, and what the rest of the screen may claim while it says it.
#
#   sh app/ios/Tests/run_control_policy_tests.sh
#
# THE DOOR THIS CLOSES. The button's label was made honest — "Waiting for the
# microphone" while a call held the input — and its ACTION was left alone. So
# the biggest type on the home screen became a passive status sentence sitting
# on a control whose tap calls `stopListening()`. An owner who opens the app
# during a call, sees a pulsing dot beside a sentence, and taps it to hurry
# things along has turned listening off for the rest of the day, and nothing in
# the app brings it back. That is the exact ending the interruption work set out
# to close, reached through a door that work installed.
#
# Two instruments, because the defect has two halves:
#
#   The swiftc suite below proves the DECISION — that no state produces a label
#   promising one thing while the tap does another.
#
#   The scans prove the SCREEN still asks it, and that the four other places
#   which spelled "she is hearing you right now" out of `isListening` alone —
#   two breathing dots, the settings headline, the idle briefing line — go
#   through the one fact instead. They lied together during every call.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
content="$app/Views/ContentView.swift"
settings="$app/Views/SettingsView.swift"
listener="$app/Audio/PhoneListener.swift"
for f in "$content" "$settings" "$listener"; do
    [ -f "$f" ] || { echo "missing $f"; exit 2; }
done
fail=0

# PROSE IS NOT CODE, and these files explain at length the lies they stopped
# telling. Whole-line comments come out first, exactly as the theme contract
# drops them before every scan.
strip() { grep -v '^ *//' "$1"; }
cv=$(mktemp); sv=$(mktemp); pl=$(mktemp)
trap 'rm -f "$cv" "$sv" "$pl"' EXIT
strip "$content" > "$cv"; strip "$settings" > "$sv"; strip "$listener" > "$pl"

# 1. THE CONTROL MUST STILL ASK. A green suite over a decision the screen no
#    longer consults is the same failure this policy exists to stop, wearing a
#    passing test — `ListenResumePolicy` already shipped once as an inline
#    guard that silently could not fire.
grep -q 'ListenControlPolicy.face(' "$cv" || {
    echo "The listening control no longer asks ListenControlPolicy what to show."
    echo "The checks below then prove nothing about the running app: the label and"
    echo "the tap are free to disagree again, which is how a status sentence ended"
    echo "up on the control that ends the day."
    fail=1
}
grep -q 'ListenControlPolicy.capturing(' "$pl" || {
    echo "PhoneListener.capturing no longer reads the policy, so 'the microphone is"
    echo "ours right now' is spelled out by hand again in whichever views want it."
    fail=1
}

# 2. NO LIVE INDICATOR MAY BE REACHED THROUGH `isListening`. `isListening` is
#    the owner's standing WISH; it stays true for the whole of a phone call.
#    Breathing means "she is doing something right now" — its own comment says
#    so — and during a call she is not. `capturing` is the fact.
#
#    Scoped to these two files on purpose. OnboardingView's dot sits in the
#    `isListening` arm of a three-way branch about whether PERMISSION landed,
#    and moving it to `capturing` would drop somebody who had just granted the
#    microphone into the copy that asks them to grant it. Same words, different
#    question, and a rule that cannot tell them apart would be a worse rule.
hits=$(awk '
    /^ *\/\// { next }
    /BreathingDot\(|WaveBars\(/ {
        if (p1 ~ /listener\.isListening/ || p2 ~ /listener\.isListening/ || p3 ~ /listener\.isListening/)
            printf "%s:%d:%s\n", FILENAME, NR, $0
    }
    { p3 = p2; p2 = p1; p1 = $0 }' "$content" "$settings")
if [ -n "$hits" ]; then
    echo "A live-listening indicator is gated on \`isListening\`, which is true for"
    echo "the whole of a phone call. Ask \`listener.capturing\`:"
    echo "$hits"
    fail=1
fi

# 3. HER OWN VOICE. Two sentences claim, in the first person, that she is
#    hearing you: the headline of the listening/privacy screen, and the idle
#    line of the home briefing. Suspended, the briefing read "Something else
#    has the microphone right now. All quiet on my end. I've got the watch."
grep -q 'listener.capturing' "$sv" || {
    echo "SettingsView's listening state does not consult \`capturing\`, so"
    echo "\"I'm listening on this phone.\" is the headline of the privacy screen"
    echo "while a call holds the input."
    fail=1
}
idle_ungated=$(awk '
    /^ *\/\// { next }
    /idleLine/ && !/private var idleLine/ {
        if ($0 !~ /listener\.capturing/ && p1 !~ /listener\.capturing/ && p2 !~ /listener\.capturing/)
            print "ungated"
    }
    { p2 = p1; p1 = $0 }' "$content")
[ -z "$idle_ungated" ] || {
    echo "The briefing's idle line is not gated on \`capturing\`. \"I've got the"
    echo "watch\" over a microphone something else is holding is the claim the"
    echo "sentence above it has just denied."
    fail=1
}

[ "$fail" = "0" ] || exit 1

out=$(mktemp -d)
trap 'rm -f "$cv" "$sv" "$pl"; rm -rf "$out"' EXIT
swiftc -O \
    "$app/Audio/ListenControlPolicy.swift" \
    "$here/ListenControlPolicyTests.swift" \
    -o "$out/controltests"
"$out/controltests"
