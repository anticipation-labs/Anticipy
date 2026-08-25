#!/bin/sh
# Checks for ListenResumePolicy — what happens when the owner opens the app
# again after iOS took the microphone away.
# Pure Foundation on purpose: no simulator, no scheme, no signing, no network,
# and no device that has to receive a real phone call.
#
#   sh app/ios/Tests/run_resume_policy_tests.sh
#
# Exit code is the result. Non-zero means a case came back wrong.
set -e
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

# THIS POLICY MUST HAVE A CALL SITE, for the same reason ListenWatchdogPolicy
# must. The decision it owns already shipped once as an inline guard that
# silently became a no-op — `!listener.isListening` over a flag no interruption
# ever cleared — and nothing anywhere went red for it. A green suite over a
# function `resumeListeningIfWanted` no longer asks would be that failure
# exactly, wearing a passing test.
if ! grep -q 'ListenResumePolicy.decide(' "$app/AnticipyApp.swift"; then
    echo "resumeListeningIfWanted no longer asks ListenResumePolicy what to do."
    echo "The checks below then prove nothing about the running app. This is the"
    echo "same decision that spent a release as an inline guard which could not"
    echo "fire: a phone call left isListening true, so the app's only route back"
    echo "to listening was the owner toggling the switch by hand."
    exit 2
fi

swiftc -O \
    "$app/Audio/ListenResumePolicy.swift" \
    "$here/ListenResumePolicyTests.swift" \
    -o "$out/resumetests"
"$out/resumetests"
