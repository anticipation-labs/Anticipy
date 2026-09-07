#!/bin/sh
# One honest Mac logic gate. Every suite here compiles the real production
# sources with swiftc — no Xcode project, no signing, no device — so it runs
# on any Mac with the Command Line Tools, including the CI runner.
#
#   sh app/macos/Tests/run_all.sh
#
# `set -eu` stops at the first red suite, so order is reachability: the
# suite that guards the LOCAL-FIRST rule runs first, on purpose.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)

# Raw audio never leaves the Mac; the detector offers and cannot record; the
# line policy's envelope is measured, not estimated.
sh "$HERE/run_capture_core_tests.sh"
# Two tracks and a manifest on disk, with provenance kept.
sh "$HERE/run_meeting_archive_tests.sh"
# The row a line becomes, sent to the brain the phone feeds.
sh "$HERE/run_transcript_wire_tests.sh"
