#!/bin/sh
# The notification organ the app was missing. Pure logic; no simulator.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
swift "$HERE/NotifierTests.swift"
