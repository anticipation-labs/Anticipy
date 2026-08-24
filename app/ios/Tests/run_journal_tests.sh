#!/bin/sh
# Checks for ListenJournal — the on-device record of what a listening session
# did, and the instrument a manual voice test is read with.
# Pure Foundation on purpose: no simulator, no scheme, no signing, no network.
#
#   sh app/ios/Tests/run_journal_tests.sh
#
# Exit code is the result. Non-zero means a case came back wrong.
#
# The wiring assertions below arrived with the call sites. Until those existed
# a check here would have failed for a reason that was not a defect, and a
# check reporting a failure the code did not commit is worse than no check.
set -e
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

# These checks are worthless if nothing writes to the journal: an unread
# diagnostic is how "the test didn't complete" became undiagnosable in the
# first place. Prove the wiring before proving the logic.
listener="$app/Audio/PhoneListener.swift"
session="$app/AnticipyApp.swift"
if ! grep -q 'ListenJournal.shared.record(.sessionStarted)' "$listener"; then
    echo "A listening session no longer records that it started."
    echo "With no start line, a journal cannot say whether the microphone ever"
    echo "came up, which is the first thing a failed voice test must rule out."
    exit 2
fi
if ! grep -q 'ListenJournal.shared.record(.sessionStopped' "$listener"; then
    echo "Listening stops without saying why."
    echo "'It stopped' is the useless half of the report: the owner stopping it"
    echo "and iOS taking the microphone away read identically."
    exit 2
fi
if ! grep -q 'ListenJournal.shared.record(.recognizerSwapped' "$listener"; then
    echo "A recognizer is replaced without recording what drove it."
    echo "An error, Apple's task limit, a route change and the 120s rotation"
    echo "are indistinguishable afterwards, and they need different fixes."
    exit 2
fi
if ! grep -q '.flushed(reason:' "$listener"; then
    echo "A flush no longer records its reason and word count."
    echo "That pair is the only evidence of the shard rate this work exists to"
    echo "reduce, and the count is all the journal may hold: never the words."
    exit 2
fi
if ! grep -q 'ListenJournal.shared.record(.posted(' "$session"; then
    echo "An event POST no longer records its outcome."
    echo "A session that heard everything and delivered nothing looked exactly"
    echo "like a microphone that heard nothing at all."
    exit 2
fi
# The journal is exportable from Settings, so a transcript copied into it
# leaves the phone on a person's tap. design/LOCAL-FIRST.md governs this.
if grep -vE '^[[:space:]]*//' "$session" | grep -q 'posted(ok: false, detail: "\\(error'; then
    echo "A post failure writes the raw error into the journal."
    echo "BackendError carries the server's own sentence about a request whose"
    echo "payload was the owner's speech. Record the shape, not the message."
    exit 2
fi
echo "the journal is written on start, stop, swap, flush and post"

swiftc -O \
    "$app/Audio/ListenJournal.swift" \
    "$here/ListenJournalTests.swift" \
    -o "$out/journaltests"
"$out/journaltests"
