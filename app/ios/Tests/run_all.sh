#!/bin/sh
# One honest iOS logic gate. These suites compile the real pure-Foundation
# production sources directly, so they need no simulator, signing, or duplicate
# XCTest implementation. The app build is a separate release gate.
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)

sh "$HERE/run_cursor_tests.sh"
sh "$HERE/run_heard_tests.sh"
sh "$HERE/run_flush_policy_tests.sh"
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
sh "$HERE/run_enrollment_offer_tests.sh"
sh "$HERE/run_job_receipt_tests.sh"
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
