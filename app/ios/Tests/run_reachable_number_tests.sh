#!/bin/sh
# A text is the only way this product can reach anyone. Pure Foundation.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
swift "$HERE/ReachableNumberTests.swift"
