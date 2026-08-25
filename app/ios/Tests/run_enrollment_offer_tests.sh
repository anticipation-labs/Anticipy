#!/bin/sh
# Enrollment is OFFERED, not merely findable - and only when it can work.
#
#   sh app/ios/Tests/run_enrollment_offer_tests.sh
#
# EnrollmentOfferPolicy is pure Foundation, so the real production source is
# compiled straight in rather than copied.
#
# stranger_gate.py leg 5: enrollment had exactly one presentation site and
# first run was not among them. To reach it a stranger had to tap the slider
# glyph in the Home toolbar and scroll past Listening, Pendant and You, with
# nobody suggesting it. That is why `speaker` is 0% across 221 production
# events with the cause recorded as "enrollment unreachable".
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

policy="$app/Audio/EnrollmentOfferPolicy.swift"
[ -f "$policy" ] || { echo "missing $policy"; exit 2; }

invite="$app/Views/EnrollmentInvite.swift"
onboarding="$app/Views/OnboardingView.swift"
enroll="$app/Views/VoiceEnrollView.swift"
[ -f "$invite" ] || { echo "missing $invite"; exit 2; }
[ -f "$enroll" ] || { echo "missing $enroll"; exit 2; }

# PUT ON SCREEN, which in SwiftUI means CONSTRUCTED. The first version of the
# gate leg this suite backs asked whether first run's source contained the WORD
# `SettingsView`, so a comment saying "enrollment still lives in SettingsView()"
# turned it green while enrollment stayed three scrolls deep. A bare mention is
# not a presentation.
if ! grep -q 'VoiceEnrollView(' "$invite"; then
    echo "EnrollmentInvite does not construct VoiceEnrollView."
    echo "An invite that cannot put the enrolment screen on the phone is a"
    echo "page of prose about a feature nobody can reach."
    exit 2
fi
if ! grep -q 'EnrollmentInvite(' "$onboarding"; then
    echo "First run no longer puts EnrollmentInvite on screen."
    echo "Enrollment goes back to one presentation site - a sheet three"
    echo "scrolls down in Settings - and speaker stays 0%."
    exit 2
fi

# AND IT MUST STAY HONEST. sherpa-onnx is unlinked (project.yml, d3ccb133), so
# SpeakerTagger.available is FALSE in the shipping build and enrollment cannot
# enrol anybody. A first-run beat that asks for twelve seconds of reading and
# can never produce a profile is worse than no beat at all: it spends the one
# budget first run has to teach a stranger the product is broken.
#
# This is the check that stops the gate leg being satisfied by a lie.
#
# SCOPED TO finish(), AND WITH COMMENTS STRIPPED, because the loose version was
# tried and is worthless. Replacing the whole policy call with `if true` left a
# plain `grep EnrollmentOfferPolicy "$onboarding"` GREEN - the doc comment two
# lines above still named it. That is the same defect stranger_gate.py's own
# header records five times over: a note naming a thing retires the check that
# tracks whether the thing happens. A comment is not a call.
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
finish_body=$(span "$onboarding" 'private func finish[(]' | sed 's|//.*||')
[ -n "$finish_body" ] || {
    echo "OnboardingView has no finish() for this suite to read."
    echo "Whatever ends the walkthrough now is what these checks should follow."
    exit 2
}
if ! echo "$finish_body" | grep -q 'EnrollmentOfferPolicy.presents('; then
    echo "First run does not ask EnrollmentOfferPolicy whether to offer."
    echo "Without it the invite appears on a build whose engine is unlinked"
    echo "(sherpa-onnx is out, d3ccb133), and the stranger spends twelve"
    echo "seconds reading into a dead end - which is worse than not asking."
    exit 2
fi
if ! grep -q 'speakerTagger.available' "$invite"; then
    echo "EnrollmentInvite no longer checks whether the engine is there."
    echo "The invite can outlive the decision that raised it - the tagger is"
    echo "read at present time, not when onboarding started."
    exit 2
fi
# VoiceEnrollView's own honest state has to survive too: it is the thing the
# invite hands over to, and its `unavailable` phase is what makes a mistaken
# offer recoverable instead of a spinning dot.
if ! grep -q 'case .unavailable' "$enroll"; then
    echo "VoiceEnrollView no longer has an unavailable phase."
    echo "That phase is what an offer raised on a phone whose engine died"
    echo "between the check and the tap lands on."
    exit 2
fi
echo "first run offers enrolment through EnrollmentInvite, and only when it works"

# swiftc only permits top-level code in a file literally named main.swift.
cp "$here/EnrollmentOfferPolicyTests.swift" "$out/main.swift"
swiftc -O "$policy" "$out/main.swift" -o "$out/enrollmentoffertests"
"$out/enrollmentoffertests"
