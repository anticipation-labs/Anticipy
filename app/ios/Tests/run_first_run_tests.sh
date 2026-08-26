#!/bin/sh
# The welcome tour belongs to the ACCOUNT, not to the phone.
#
#   sh app/ios/Tests/run_first_run_tests.sh
#
# FirstRunOwnership is pure Foundation, so the real production source is
# compiled straight in rather than copied.
#
# stranger_gate.py leg 4: `hasOnboarded` was stored under the one string
# "hasOnboarded" on every install - one value for the whole PHONE - and nothing
# in signOut, signIn or createAccount cleared it. A stranger handed a phone
# anybody had opened this app on before signed up and landed straight on the
# feed: no microphone primer, so listening was never started and she heard
# nothing all week.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

policy="$app/FirstRunOwnership.swift"
[ -f "$policy" ] || { echo "missing $policy"; exit 2; }

# A DECISION NOBODY ASKS FOR IS A COMMENT. This is not hypothetical: the policy
# below shipped complete, correct and tested by nothing, in the pbxproj, with
# ZERO call sites, while leg 4 stayed red - which is the failure the gate's own
# `_clears` helper was written for ("a mention is not a clear").
root="$app/AnticipyApp.swift"

# The text of one Swift declaration, by counting braces - the same thing
# stranger_gate.py's swift_span does, and for the same reason.
#
# WHY THIS IS NOT A PLAIN grep OVER THE FILE. It was, and the mutation that
# proved it worthless is recorded here: deleting `hasOnboarded = false` from
# signIn left this suite GREEN, because the identical line in
# resumeSignedInAccount still matched. A whole-file grep asks "does this string
# appear anywhere", and the entire question here is WHERE.
span() {
    awk -v sig="$2" '
        !inside && $0 ~ sig { inside = 1 }
        inside {
            print
            opens = gsub(/{/, "{"); depth += opens
            closes = gsub(/}/, "}"); depth -= closes
            if (started && depth <= 0) exit
            if (depth > 0) started = 1
        }
    ' "$1"
}

signin=$(span "$root" 'func signIn[(]')
[ -n "$signin" ] || { echo "AnticipyApp has no func signIn for this suite to read."; exit 2; }
resuming=$(span "$root" 'func resumeSignedInAccount[(]')
[ -n "$resuming" ] || { echo "AnticipyApp has no func resumeSignedInAccount."; exit 2; }
if ! echo "$signin" | grep -q 'FirstRunOwnership.arriving('; then
    echo "signIn does not ask FirstRunOwnership whose tour flag is on this phone."
    echo "sign-in is the ONE moment the person holding the phone can change,"
    echo "and it is reached by sign-up too (signUp ends in signIn). Without"
    echo "this call the flag is one boolean for the whole device again."
    exit 2
fi
if ! echo "$resuming" | grep -q 'FirstRunOwnership.resuming('; then
    echo "Nothing adopts the pre-upgrade flag on a signed-in launch."
    echo "Every existing owner is then made to redo first run for a bug that"
    echo "was never theirs."
    exit 2
fi

# AND THE CLEAR ITSELF HAS TO BE IN SIGN-IN. Asking whether the policy is
# CALLED proves nothing about whether its answer is acted on: a switch whose
# .replay arm writes only the owner id consults the policy and discards it,
# and the stranger still lands on the feed.
if ! echo "$signin" | grep -q 'hasOnboarded = false'; then
    echo "signIn consults FirstRunOwnership and never clears the flag."
    echo "A .replay decision that writes nothing is a policy consulted and"
    echo "discarded - the stranger still lands straight on the feed with no"
    echo "microphone primer, and hears nothing all week."
    exit 2
fi

# ONE STRING, IN ONE PLACE. stranger_gate.py's swift_string_behind exists
# because moving the key into a constant was the shape of an accident: a second
# copy of "hasOnboarded" is a clear that silently clears nothing.
if grep -q '@AppStorage("hasOnboarded")' "$root"; then
    echo "AnticipyApp still binds the raw string \"hasOnboarded\"."
    echo "The clear writes FirstRunOwnership.flagKey; a second copy of the"
    echo "string is how a rename leaves a clear that clears nothing."
    exit 2
fi
if ! grep -q '@AppStorage(FirstRunOwnership.flagKey)' "$root"; then
    echo "The routing flag is no longer bound to FirstRunOwnership.flagKey."
    exit 2
fi

# And the routing must still be what the flag decides, or none of it matters.
#
# FOLLOWED, AS THE MESSAGE BELOW ASKED. This read `else if hasOnboarded {` and
# the chain it was reading is gone: two beats of the walkthrough moved in front
# of the sign-in door, so the routing is a decision over three durable facts
# rather than two nested ifs, and it lives in `FirstRunRoute.decide`. The flag
# is still what sends somebody to Home — it is now one of the arguments rather
# than the second `if` — so the check follows it there. Which screen each of
# the six states opens on is walked by run_first_run_route_tests.sh; what is
# checked HERE is only that the tour flag still reaches the decision at all.
if ! grep -q 'FirstRunRoute.decide(' "$root"; then
    echo "AnticipyApp no longer routes on a first-run decision."
    echo "Whatever decides that now is what these checks should follow."
    exit 2
fi
if ! grep -q 'hasOnboarded: hasOnboarded' "$root"; then
    echo "The routing decision is no longer given the onboarding flag."
    echo "Clearing it in signIn then re-routes nothing: the stranger lands"
    echo "straight on the feed with no microphone primer, which is the whole"
    echo "bug this suite exists for."
    exit 2
fi
if ! grep -q 'case .home:' "$root"; then
    echo "AnticipyApp no longer has a route to Home."
    exit 2
fi
echo "sign-in consults the policy, clears the flag, and routing still reads it"

# swiftc only permits top-level code in a file literally named main.swift.
cp "$here/FirstRunOwnershipTests.swift" "$out/main.swift"
swiftc -O "$policy" "$out/main.swift" -o "$out/firstruntests"
"$out/firstruntests"
