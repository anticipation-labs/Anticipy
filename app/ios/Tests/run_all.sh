#!/bin/sh
# One honest iOS logic gate. These suites compile the real pure-Foundation
# production sources directly, so they need no simulator, signing, or duplicate
# XCTest implementation. The app build is a separate release gate.
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)

sh "$HERE/run_cursor_tests.sh"
sh "$HERE/run_heard_tests.sh"
sh "$HERE/run_flush_policy_tests.sh"
# WHEN the words started and WHEN the flush produced them — two instants, not
# one number written into three columns. Placed next to the flush policy
# because it is the other half of the same moment: that one decides when a line
# leaves, this one decides what the line says about the time it took.
sh "$HERE/run_capture_envelope_tests.sh"
sh "$HERE/run_end_errand_tests.sh"
sh "$HERE/run_reset_message_tests.sh"
sh "$HERE/run_line_source_tests.sh"
sh "$HERE/run_capture_source_tests.sh"
# The three stranger-gate legs that live in this tree: whose first run this is,
# whether enrolment is ever offered, and whether the card shows the receipt the
# server actually verified.
#
# Placed HERE, early, deliberately: `set -eu` stops this file at the first
# failure, and run_watchdog_policy_tests.sh below is red on a compile error
# (ListenSessionFacts is not passed to its swiftc invocation), so everything
# after it is unreachable today. That is pre-existing and not fixed here, but a
# suite nobody can reach is a suite nobody has.
sh "$HERE/run_first_run_tests.sh"
# Whose phone is this — the same question one step earlier. First-run ownership
# decides whether the TOUR replays for a new account; this decides whether the
# five device-local answers to "who are you" go with the account that left.
# Placed beside it, and early, for the reachability reason above.
sh "$HERE/run_owner_mirror_tests.sh"
sh "$HERE/run_enrollment_offer_tests.sh"
sh "$HERE/run_job_receipt_tests.sh"
# The same card from the other end. That one asks what the server proved
# before it says "done"; this asks which section a job reaches at all — and
# whether a job the owner STOPPED reaches one. `cancelled` matched none of
# Home's three filters, so a stop deleted the row from the screen along with
# the only sentence saying it might have gone through anyway. Early, for the
# reachability reason above.
sh "$HERE/run_home_feed_tests.sh"
# The phone as a HAND, for one verb. Placed beside the receipt because it is the
# same argument from the other end: that one asks what the server proved before
# the card says "done", this one asks what has to be true before the phone
# touches the calendar at all. Its load-bearing leg is that the undo resolves
# from an id WE minted — EKEvent.eventIdentifier is assigned by EventKit ON
# SAVE, and an undo that needs it is the shape the Shelf 2 spec excludes by
# name. Early, like the three above it: `set -eu` stops this file at the first
# failure, so a suite placed late is a suite that may never run.
sh "$HERE/run_calendar_hand_tests.sh"
# LOCAL-FIRST rule 1, the iOS half: no vendor socket, no vendor credential, no
# retry loop against a permanent refusal, and copy that says what is true.
sh "$HERE/run_local_ears_tests.sh"
sh "$HERE/run_stale_extension_tests.sh"
sh "$HERE/run_reachable_number_tests.sh"
sh "$HERE/run_notifier_tests.sh"
sh "$HERE/run_context_grant_tests.sh"
sh "$HERE/run_interview_tests.sh"
sh "$HERE/run_supervised_read_tests.sh"
sh "$HERE/run_theme_contract_tests.sh"
sh "$HERE/run_journal_tests.sh"
sh "$HERE/run_tally_tests.sh"
sh "$HERE/run_battery_tests.sh"
sh "$HERE/run_watchdog_policy_tests.sh"
sh "$HERE/run_resume_policy_tests.sh"
sh "$HERE/run_control_policy_tests.sh"
# The call sense. A call is a hole in the day where the ears go deaf, and today
# it looks exactly like silence: this decides, from CallKit's call list and the
# clock alone, when the microphone is gone to a call, when it is back, and where
# the conversation boundaries were. Its law legs live in the runner — no
# duration threshold, no identity, and no claim about FaceTime that a device has
# not made.
sh "$HERE/run_call_presence_tests.sh"
sh "$HERE/run_interruption_contract_tests.sh"
# Not a logic suite: it asks whether the build number still identifies these
# bytes. Last, because it is the one leg that reads git rather than source, and
# a red one here means "bump it before you commit", not "the code is wrong".
sh "$HERE/run_build_number_tests.sh"

echo "iOS logic gate: all suites passed"
