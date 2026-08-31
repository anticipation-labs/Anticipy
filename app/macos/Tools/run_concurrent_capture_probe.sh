#!/bin/sh
# The concurrent-capture experiment, as a thing anyone can re-run.
#
# It answers ONE question, and the question decides the shape of the Mac card
# (spec §13 first bullet, §15 item 1): can this app capture the MICROPHONE while
# a meeting app holds the input device? If it cannot, §3.4's whole attribution
# advantage collapses.
#
# Build only; it compiles into a temp dir and leaves nothing behind.
#
#   sh app/macos/Tools/run_concurrent_capture_probe.sh              # self-contained
#   sh app/macos/Tools/run_concurrent_capture_probe.sh --with-zoom  # REAL Zoom
#
# --with-zoom is the faithful version and it needs a HUMAN. See the banner it
# prints. Full write-up: research/2026-08-25-macos-concurrent-capture.md
set -e
here=$(cd "$(dirname "$0")" && pwd)
out=$(mktemp -d)
cleanup() {
    if [ -s "$out/pids" ]; then
        while read -r p; do
            # Helpers are expected to have exited already or to end by signal.
            # Cleanup must never replace the capture probe's own verdict with
            # 143 (SIGTERM) when the measured gate actually passed.
            kill "$p" 2>/dev/null || true
            wait "$p" 2>/dev/null || true
        done < "$out/pids"
    fi
    rm -rf "$out"
}
trap cleanup EXIT

echo "=== machine ==="
sw_vers | sed 's/^/  /'
echo "  process taps need macOS 14.2+ (AudioHardwareCreateProcessTap,"
echo "  API_AVAILABLE(macos(14.2)) in CoreAudio/AudioHardwareTapping.h)"
echo ""

for f in audioprocs dual holder; do
    swiftc -O "$here/$f.swift" -o "$out/$f" 2>/dev/null \
        || { echo "FAILED to build $f"; exit 3; }
done
: > "$out/pids"

if [ "$1" = "--with-zoom" ]; then
    cat <<'BANNER'
========================================================================
  THIS IS THE PART A HUMAN HAS TO DO, AND IT CANNOT BE AUTOMATED.

  Zoom does NOT open the microphone while it merely sits on screen —
  measured 2026-08-25, launching it changed nothing in the process
  list. It opens the input device only inside a meeting or its audio
  test, and both need a click nobody but you can make.

  So, right now, before this script continues:

    1. Open Zoom.
    2. Join ANY meeting  (https://zoom.us/test is Zoom's own echo test
       and needs no account), or open
       Settings -> Audio -> "Test Mic".
    3. Make sure Zoom is using the microphone -- you should see its
       input level meter moving.
    4. Then press Return here, and TALK while it runs.

  What proves it: the line "us.zoom.xos" (or a Zoom helper) appearing
  with in=1 in the table below, AT THE SAME TIME as NEAR reporting a
  non-zero peak. Non-zero NEAR peak while Zoom holds input is the
  whole answer.
========================================================================
BANNER
    printf "  press Return when Zoom is in a meeting and hearing you: "
    read _ignored
else
    echo "=== self-contained proxy: a separate process holding the input"
    echo "=== device on the Voice-Processing IO path (what Zoom/Meet/Teams use)"
    "$out/holder" vpio > "$out/holder.log" 2>&1 &
    echo $! >> "$out/pids"
    sleep 3
    sed 's/^/  holder: /' "$out/holder.log" | head -5
fi

echo ""
echo "=== who holds which stream (the §6.2 detection signal) ==="
"$out/audioprocs" | sed 's/^/  /'
echo ""
echo "=== NEAR + FAR, concurrently, for 15 seconds ==="
echo "    NEAR = the microphone, via AVAudioEngine"
echo "    FAR  = a Core Audio process tap over every process"
echo ""
# Produce a small, known system-output signal throughout tap startup. The old
# probe opened FAR successfully but could report zero callbacks simply because
# its proxy held the microphone without playing anything. This makes FAR a
# measured live gate rather than an inference from an OSStatus.
(
    i=0
    while [ "$i" -lt 10 ]; do
        afplay -v 0.12 /System/Library/Sounds/Submarine.aiff
        sleep 0.4
        i=$((i + 1))
    done
) > /dev/null 2>&1 &
echo $! >> "$out/pids"
set +e
"$out/dual" --seconds 15
rc=$?
set -e
echo ""
echo "READ IT LIKE THIS:"
echo "  NEAR buffers rising  AND  NEARpk non-zero   -> the mic was captured"
echo "     while another process held it. That is the answer the card needs."
echo "  A non-zero buffer count with a peak of exactly 0.0000 is NOT a"
echo "     success. On macOS a MISSING PRIVACY GRANT delivers a perfectly"
echo "     shaped stream of zeros and returns noErr. Grant System Audio"
echo "     Recording / Microphone in Privacy & Security and run it again."
exit $rc
