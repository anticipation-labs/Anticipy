#!/bin/sh
# Checks for the Mac's mouth: the row one transcript line becomes, and whether
# the app still sends it to the brain the phone feeds.
#
# Pure Foundation on purpose: no Xcode project, no signing, no network. The
# same tradition as run_capture_core_tests.sh beside it.
#
#   sh app/macos/Tests/run_transcript_wire_tests.sh
#
# Exit code is the result. Non-zero means a case came back wrong.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
tree=$(cd "$here/.." && pwd)
policy="$tree/Anticipy/Capture/TranscriptWire.swift"
lines="$tree/Anticipy/Capture/MeetingLinePolicy.swift"
client="$tree/AnticipyMac/MacBackend.swift"
app="$tree/AnticipyMac/MacApp.swift"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

for f in "$policy" "$lines" "$client" "$app"; do
    if [ ! -f "$f" ]; then
        echo "$f is missing. If it was renamed, rename it here too — an empty"
        echo "search satisfies every rule below by matching nothing."
        exit 2
    fi
done

code() { grep -vE '^[[:space:]]*//' "$1"; }

# ------------------------------------------------------------ the right brain
# Build 119 shipped with the retired Railway URL baked in, and the phone had
# already moved to the Worker at api.anticipy.ai (AnticipyApp.swift migrates
# installs off the old URL). Recordings went to a backend on its way out. The
# runner excludes ITSELF from the search, because the old name lives here.
stale=$(grep -rl 'railway\.app' "$tree" 2>/dev/null \
    | grep -v 'run_transcript_wire_tests.sh' || true)
if [ -n "$stale" ]; then
    echo "The retired Railway backend is still named under app/macos:"
    echo "$stale"
    echo ""
    echo "The phone posts to https://api.anticipy.ai and nothing reads the"
    echo "old backend any more. A Mac that posts there is a Mac whose"
    echo "meetings reach nobody."
    exit 2
fi
if ! code "$client" | grep -q 'URL(string: "https://api.anticipy.ai")'; then
    echo "MacBackend.swift no longer defaults to https://api.anticipy.ai."
    echo "That is the one backend the brain reads."
    exit 2
fi
echo "the Mac posts to the brain the phone feeds"

# ---------------------------------------------------------------- the wiring
# The logic checks below are worthless if the app builds its own row beside
# the policy. Prove the thread before proving the type.
if ! code "$client" | grep -q 'TranscriptWire.body('; then
    echo "MacBackend.swift no longer builds the row through TranscriptWire."
    echo "A second row shape beside the tested one is how the Mac drifts from"
    echo "the phone one column at a time."
    exit 2
fi
if ! code "$client" | grep -q 'TranscriptWire.deviceID('; then
    echo "MacBackend.swift no longer stamps the build on device_id."
    echo "overnight/are_the_ears_live.py names the build that last spoke from"
    echo "that column; a random id there says nothing about which bytes heard."
    exit 2
fi
if ! code "$app" | grep -q 'speaker: TranscriptWire.speaker(for: line.channel)'; then
    echo "MacApp.swift no longer asks the wire which side of the call spoke."
    echo "The brain reads speaker to tell the owner's words from overheard"
    echo "ones; an unlabelled far-side line reads as a promise the owner made."
    exit 2
fi
if code "$client" "$app" | grep -qE '"mac_mic"|"mac_system"'; then
    echo "A per-channel source is back. The ear is \"mac\"; the side is speaker."
    echo "The ears gate counts source=\"mac\" and cannot see a row stamped"
    echo "anything else."
    exit 2
fi
# Refusal, retry and account-switch behavior are exercised against the real
# MacBackend with a URLProtocol server in run_backend_delivery_tests.sh.
echo "the app builds the row through the wire"

# swiftc only permits top-level code in a file literally named main.swift.
cp "$here/TranscriptWireTests.swift" "$out/main.swift"
swiftc -O "$lines" "$policy" "$out/main.swift" -o "$out/transcriptwiretests"
"$out/transcriptwiretests"
