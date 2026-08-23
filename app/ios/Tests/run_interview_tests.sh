#!/bin/sh
# The interview: a conversation not a survey, and a skip that records nothing.
#
#   sh app/ios/Tests/run_interview_tests.sh
#
# Interview.swift is pure Foundation, so the real production source is compiled
# straight in rather than lifted or copied.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

script="$app/Interview.swift"
[ -f "$script" ] || { echo "missing $script"; exit 2; }

# The assertions below are worthless if nothing consults the script. Prove the
# wiring first — this is the exact failure `events.source` already suffered:
# written for weeks, read by nothing, and no test noticed.
view="$app/Views/InterviewView.swift"
if ! grep -q 'InterviewProgress().remaining' "$view"; then
    echo "InterviewView no longer asks InterviewProgress what is still open."
    echo "It would re-ask questions the person has already answered."
    exit 2
fi
if ! grep -q 'session.sendInterviewAnswer' "$view"; then
    echo "InterviewView no longer sends answers anywhere, so nothing is remembered."
    exit 2
fi
# A skip must not write. The only write path is sendInterviewAnswer, and it must
# refuse an empty answer.
if ! grep -q 'guard !text.isEmpty else { return false }' "$app/AnticipyApp.swift"; then
    echo "sendInterviewAnswer no longer refuses an empty answer."
    echo "A skip would become an empty fact — brief 08:30 forbids exactly that."
    exit 2
fi
# Interview facts must not be triaged into errands.
if ! grep -q 'kind: "profile",' "$app/AnticipyApp.swift"; then
    echo "Interview answers are no longer posted as kind:profile."
    exit 2
fi
# And there has to be a way back in, because the Home card takes "not now"
# permanently.
if ! grep -q 'showInterview = true' "$app/Views/SettingsView.swift"; then
    echo "Settings no longer opens the interview, so a declined offer is final."
    exit 2
fi
echo "the view reads the script, sends answers, refuses blanks, and Settings can reopen it"

# The server half has to turn those events into facts.
worker="$here/../../../brain/worker.py"
if [ -f "$worker" ]; then
    grep -q 'fetch_unprocessed(kind="profile"' "$worker" || {
        echo "brain/worker.py no longer polls profile events; answers never land."; exit 2; }
    grep -q 'source="import"' "$worker" || {
        echo "imported facts lost their provenance."; exit 2; }
fi

# swiftc only permits top-level code in a file literally named main.swift.
cp "$here/InterviewTests.swift" "$out/main.swift"
swiftc -O "$script" "$out/main.swift" -o "$out/interviewtests"
"$out/interviewtests"
