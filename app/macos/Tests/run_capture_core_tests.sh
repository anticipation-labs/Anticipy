#!/bin/sh
# Checks for the Mac meeting recorder's capture core — what makes the app OFFER
# to record, and whether the stream it then opens is carrying audio or zeros.
#
# Pure Foundation on purpose: no Xcode project, no app shell, no signing, no
# device, no network. The same tradition as app/ios/Tests/run_tally_tests.sh.
#
#   sh app/macos/Tests/run_capture_core_tests.sh
#
# Exit code is the result. Non-zero means a case came back wrong.
set -e
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
tree="$here/.."
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

# ---------------------------------------------------------------- LOCAL-FIRST
# RAW AUDIO NEVER LEAVES A DEVICE (design/LOCAL-FIRST.md rule 1), and the spec's
# gate leg 4 makes that a property of the source tree rather than a code review.
# This is the leg most likely to be softened by a future agent in a hurry, and
# it is deterministic — legal under LAW 1's gates-and-evals carve-out.
#
# The runner excludes ITSELF from the search, because the names live here.
vendors='deepgram\|assemblyai\|rev\.ai\|speechmatics\|api\.openai\.com/v1/audio\|whisper'
hits=$(grep -ril "$vendors" "$tree" 2>/dev/null | grep -v 'run_capture_core_tests.sh' || true)
if [ -n "$hits" ]; then
    echo "A cloud speech vendor is named under app/macos:"
    echo "$hits"
    echo ""
    echo "LOCAL-FIRST rule 1 is the shortest sentence in this repo: raw audio"
    echo "never leaves a device. This product has already had one cloud"
    echo "transcriber deleted for breaking it. Transcription on the Mac is"
    echo "on-device or it does not happen."
    exit 2
fi

# ------------------------------------------------- the offer is not a recording
# The card is explicit: detection may be automatic, recording starts explicitly
# (spec §6.1, §6.3, App Review 2.5.14, Brief moment 18). The way that survives
# the next agent is for the detector to have no vocabulary for starting.
offer="$app/Capture/MeetingOfferPolicy.swift"
if [ ! -f "$offer" ]; then
    echo "MeetingOfferPolicy.swift is gone. If it was renamed, rename it here too."
    echo "An empty search satisfies every rule below by matching nothing."
    exit 2
fi
if grep -vE '^[[:space:]]*//' "$offer" \
    | grep -qiE 'startRecording|beginCapture|startCapture|autoRecord|installTap|AVAudioEngine'; then
    echo "The meeting DETECTOR has learned how to start a recording:"
    grep -vE '^[[:space:]]*//' "$offer" \
        | grep -inE 'startRecording|beginCapture|startCapture|autoRecord|installTap|AVAudioEngine'
    echo ""
    echo "This type decides whether to raise a banner. The click that starts"
    echo "capture belongs to the owner, once, per meeting — because there is a"
    echo "second person in every one of these recordings and roughly a dozen"
    echo "states require their consent. A detector that can start is an"
    echo "auto-recorder one refactor from existing."
    exit 2
fi

# NO BUNDLE LIST DECIDES WHAT A MEETING IS. Bundle identifiers label the banner
# and key the owner's never-offer list; §6.2 says why the treadmill version is
# wrong. This is the line somebody adds at 2am when a tester asks "why didn't it
# notice Teams?", and it is the shape LAW 1 exists to stop.
namepred='(zoom|teams|webex|googlemeet|hangouts|slack|discord)[^)]*\)?[[:space:]]*(==|\.contains|\.hasPrefix|\.hasSuffix)'
if grep -vE '^[[:space:]]*//' "$offer" | grep -qiE "$namepred"; then
    echo "A meeting-app name has become a predicate in the detector:"
    # The SAME pattern that fired, so the reader is shown the offending line and
    # not every line that happens to contain the letters "meet".
    grep -vE '^[[:space:]]*//' "$offer" | grep -inE "$namepred"
    echo ""
    echo "The signal is input+output on one process — what the OS actually"
    echo "knows. A name list is a maintenance treadmill that fails on the app"
    echo "nobody thought of and fires on the one that changed its identifier."
    exit 2
fi
echo "the detector offers and cannot record, and no app name is a predicate"

# ------------------------------------------- silence is measured, not estimated
# The whole reason CaptureStreamHealth exists is that an ungranted stream
# measured EXACTLY 0.0 while a granted quiet room measured 0.0019. A tolerance
# here would swallow the quiet room and the alarm would never fire — or would
# fire constantly. The comparison must be identity with zero.
hp="$app/Capture/CaptureStreamHealth.swift"
if [ ! -f "$hp" ]; then
    echo "CaptureStreamHealth.swift is gone. If it was renamed, rename it here too."
    exit 2
fi
if ! grep -vE '^[[:space:]]*//' "$hp" | grep -q 'peakAmplitude == 0'; then
    echo "The silence test is no longer identity with zero."
    echo ""
    echo "Measured 2026-08-25: a capture with no privacy grant read 0.0000; the"
    echo "same code in a quiet room with the grant read 0.0019. Any tolerance"
    echo "large enough to feel safe swallows the quiet room, and the app then"
    echo "tells an owner mid-meeting that their microphone is off. The"
    echo "difference being detected is zero versus not-zero, and nothing else."
    exit 2
fi
echo "silence is identity with zero, as measured"

# swiftc only permits top-level code in a file literally named main.swift.
cp "$here/CaptureCoreTests.swift" "$out/main.swift"
swiftc -O \
    "$app/Capture/MeetingOfferPolicy.swift" \
    "$app/Capture/CaptureStreamHealth.swift" \
    "$app/Capture/MeetingLinePolicy.swift" \
    "$out/main.swift" \
    -o "$out/capturecoretests"
"$out/capturecoretests"
