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
client="$tree/AnticipyMac/PocketBase.swift"
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
# Build 119 shipped with the Railway PocketBase URL baked in, and the phone had
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
    echo "PocketBase.swift no longer defaults to https://api.anticipy.ai."
    echo "That is the one backend the brain reads."
    exit 2
fi
echo "the Mac posts to the brain the phone feeds"

# ---------------------------------------------------------------- the wiring
# The logic checks below are worthless if the app builds its own row beside
# the policy. Prove the thread before proving the type.
if ! code "$client" | grep -q 'TranscriptWire.body('; then
    echo "PocketBase.swift no longer builds the row through TranscriptWire."
    echo "A second row shape beside the tested one is how the Mac drifts from"
    echo "the phone one column at a time."
    exit 2
fi
if ! code "$client" | grep -q 'TranscriptWire.deviceID('; then
    echo "PocketBase.swift no longer stamps the build on device_id."
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
# A refused push must not be a queued push. A token the Worker will not
# verify — the Railway session build 119 left in the Keychain — 403s every
# row, and until this existed every one of them went back on disk forever
# while the menu said "signed in". The door has to reappear.
if ! code "$client" | grep -q 'case 401, 403: result.mark(.refused)'; then
    echo "PocketBase.swift no longer reads a 401/403 as a refusal."
    echo "A refused row is not a delayed row: it is queued behind a token the"
    echo "server will never accept, and nothing on screen says so."
    exit 2
fi
# ...and the refusal has to reach the door. Joined, because the call is wrapped
# across lines; what matters is that the refused pass ends in signOut(), not
# how the closure is laid out.
joined() { code "$client" | tr '\n' ' ' | tr -s ' '; }
if ! joined | grep -q 'if refused { DispatchQueue.main.async { \[weak self\] in self?.signOut() } }'; then
    echo "A refused push no longer signs the Mac out."
    echo "The menu goes on saying 'signed in' about a token the server will"
    echo "never accept, and every line recorded from then on is queued behind it."
    exit 2
fi
echo "the app builds the row through the wire, and a refusal opens the door"

# swiftc only permits top-level code in a file literally named main.swift.
cp "$here/TranscriptWireTests.swift" "$out/main.swift"
swiftc -O "$lines" "$policy" "$out/main.swift" -o "$out/transcriptwiretests"
"$out/transcriptwiretests"
