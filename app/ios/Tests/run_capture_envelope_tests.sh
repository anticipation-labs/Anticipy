#!/bin/sh
# Checks for CaptureEnvelope — the two instants that bracket a line of speech.
# Pure Foundation on purpose: no simulator, no scheme, no signing, no network.
#
#   sh app/ios/Tests/run_capture_envelope_tests.sh
#
# Exit code is the result. Non-zero means a case came back wrong.
#
# THE DEFECT THIS SUITE GUARDS, stated once so nobody softens a leg below back
# toward it: `pushEvent` used to write ONE instant into `capture_started_at`,
# `spoken_at` and `capture_ended_at` alike. Every one of the 137 stored
# production rows carries a `capture_started_at`, and every one of them is the
# postmark — p50 0.053 s from arrival. Presence was never the problem, so no
# check here and no leg in `overnight/turn_envelope_gate.py` may test for it.
set -e
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

listener="$app/Audio/PhoneListener.swift"
session="$app/AnticipyApp.swift"
backend="$app/Backend/AnticipyBackend.swift"
for f in "$listener" "$session" "$backend"; do
    if [ ! -f "$f" ]; then
        echo "$f is missing — there is nothing for the envelope to travel through."
        exit 2
    fi
done

# ---------------------------------------------------------------- the wiring
# The logic checks below are worthless if the two instants never leave the
# flush. Prove the thread before proving the type: this is the half that a
# pure suite CANNOT see, and it is the half that broke.

# 1. BOTH ENDS LEAVE `deliver`. The flush has always had `wordsAppearedAt` and
#    `now` in the same scope and handed on only `now`. A closure that carries
#    one Date can only ever carry one instant, so the signature is the fact.
if ! grep -q 'var onLine: ((_ line: String, _ startedAt: Date, _ endedAt: Date, _ continuesPrevious: Bool) -> Void)?' "$listener"; then
    echo "PhoneListener's line callback no longer carries two instants."
    echo "One Date cannot say when the words appeared AND when the flush fired,"
    echo "so the backend aliases whichever one it gets onto all three columns"
    echo "and every capture span collapses to zero."
    exit 2
fi
if ! grep -q 'var onSpeaker: ((_ line: String, _ speaker: String?, _ startedAt: Date, _ endedAt: Date, _ continuesPrevious: Bool) -> Void)?' "$listener"; then
    echo "PhoneListener's speaker callback no longer carries two instants."
    echo "The tagged path is the one MOST lines take once enrollment is done."
    exit 2
fi

# 2. AND THE START IS `wordsAppearedAt`, NOT THE FLUSH INSTANT. This is the
#    whole card. Passing `now` twice satisfies every signature above, compiles,
#    and reproduces the exact bug with a wider callback.
if ! grep -q 'onSpeaker(line, tag, wordsAppearedAt, now, continuesPrevious)' "$listener"; then
    echo "The tagged delivery site does not send the moment the words appeared."
    echo "Sending the flush instant as the start is the original defect with a"
    echo "wider signature: capture_started_at goes on being the postmark."
    exit 2
fi
if ! grep -q 'onLine?(line, wordsAppearedAt, now, continuesPrevious)' "$listener"; then
    echo "The untagged delivery site does not send the moment the words appeared."
    exit 2
fi

# 3. THE PARTING TAIL IS THE FOURTH DELIVERY SITE AND IT BYPASSES `deliver`.
#    It is the last line of every session, it used to call `onLine?(tail,
#    Date(), ...)` — teardown time, twice over — and being outside `deliver` it
#    is exactly the site a signature-driven refactor fixes by hand and forgets.
if grep -q 'onLine?(tail, Date()' "$listener"; then
    echo "The parting tail still stamps itself at teardown time."
    echo "It is the last line of every session and it does not go through"
    echo "deliver(), so widening the callback did not reach it. It must carry"
    echo "the same two instants as every other line."
    exit 2
fi
if ! grep -q 'onLine?(tail, partingStartedAt, partingEndedAt' "$listener"; then
    echo "The parting tail does not name both of its instants."
    exit 2
fi

# 4. THE QUEUE CARRIES THE END, AND IS STILL READABLE BY A BUILD THAT PREDATES
#    IT. `unsent`'s getter falls back to `?? []` when the decode fails — a
#    non-optional field here does not warn, it silently DELETES everything a
#    person said while offline on the first launch after the update.
if ! grep -q 'var endedAt: Date? = nil' "$session"; then
    echo "The offline queue's end instant is not an optional with a default."
    echo "A required field cannot decode a queue the previous build wrote, and"
    echo "the getter answers a failed decode with an empty array — so the first"
    echo "launch after this update would throw away every buffered line."
    exit 2
fi
if ! grep -q 'endedAt: line.endedAt' "$session"; then
    echo "The offline flush does not re-send the end instant it stored."
    echo "Storing a field nothing reads back is the same as not storing it."
    exit 2
fi

# 5. ONE CONSTRUCTION RULE FOR BOTH PATHS. If the live push builds its envelope
#    one way and the queue flush another, a buffered line and a live line stop
#    meaning the same thing — and the buffered ones are precisely the rows the
#    boundary work exists for.
if ! grep -q 'CaptureEnvelope.of(startedAt: capturedAt, endedAt: endedAt)' "$session"; then
    echo "The session no longer builds its envelope through the shared rule."
    exit 2
fi

# 6. AND THE BACKEND STAMPS NOTHING ITSELF. The aliasing lived here: three
#    `body[...] = stamp` lines off one variable. If any of those columns is
#    written outside the envelope, the type is decoration.
if grep -qE '^[^/]*body\["(capture_started_at|capture_ended_at|spoken_at)"\]' "$backend"; then
    echo "AnticipyBackend still stamps a capture column by hand:"
    grep -nE '^[^/]*body\["(capture_started_at|capture_ended_at|spoken_at)"\]' "$backend"
    echo ""
    echo "That is where one instant became three columns. The envelope decides"
    echo "which instant each column gets, or it decides nothing."
    exit 2
fi
if ! grep -q 'capture.wireFields(stamp:' "$backend"; then
    echo "AnticipyBackend does not write the capture columns from the envelope."
    exit 2
fi

# 7. THE WIRE CLOCK KEEPS FRACTIONAL SECONDS. A whole-second ISO8601 formatter
#    renders two instants 300 ms apart as the same string, and the row arrives
#    indistinguishable from the aliasing bug — with every Swift check still
#    green. CaptureEnvelopeTests proves that hazard is real against both
#    formatters; this is the leg that proves production picked the right one.
if ! grep -A4 'static let anticipyUTC' "$backend" | grep -q 'withFractionalSeconds'; then
    echo "The wire clock no longer keeps fractional seconds."
    echo "Two instants a few hundred milliseconds apart then go out as the same"
    echo "string, and a genuinely bracketed line is indistinguishable on the"
    echo "wire from the collapsed one this work removes."
    exit 2
fi
echo "the envelope reaches the wire: four delivery sites, the queue, one clock"

swiftc -O \
    "$app/Audio/CaptureEnvelope.swift" \
    "$here/CaptureEnvelopeTests.swift" \
    -o "$out/envelopetests"
"$out/envelopetests"
