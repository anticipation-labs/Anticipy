#!/bin/sh
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
IOS=$(cd "$HERE/.." && pwd)

python3 "$HERE/ConsumerExperienceContractTests.py" "$IOS"
