#!/bin/sh
# Actual constructor paths, not the existence of otherwise uncalled controls.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
python3 "$here/actual_home_recovery_tests.py"
