#!/bin/sh
# Chrome running an old extension is a fact the product should state, not a
# question he has to ask a person. Pure Foundation: no simulator needed.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
swift "$HERE/StaleExtensionTests.swift"
