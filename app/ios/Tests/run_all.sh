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
sh "$HERE/run_stale_extension_tests.sh"
sh "$HERE/run_reachable_number_tests.sh"
sh "$HERE/run_notifier_tests.sh"
sh "$HERE/run_context_grant_tests.sh"
sh "$HERE/run_interview_tests.sh"
sh "$HERE/run_supervised_read_tests.sh"
sh "$HERE/run_theme_contract_tests.sh"

echo "iOS logic gate: all suites passed"
