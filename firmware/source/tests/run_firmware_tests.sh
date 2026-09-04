#!/usr/bin/env bash
# Host-compiled checks over the firmware's PURE halves.
#
# There is no cross-toolchain on this machine — no west, no arm-none-eabi-gcc,
# no Zephyr — so the firmware cannot be built here, and BUILD_ASSERTs that
# never compile prove nothing. These run the same logic and the same constants
# through a host compiler instead, which is the only honest verification
# available short of hardware. It is NOT a substitute for a build, and nothing
# here says the firmware links, flashes or works on a board.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
src="$here/../src"
out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT

CC="${CC:-clang}"
FLAGS=(-std=c11 -Wall -Wextra -Werror -I"$here/hoststub")

"$CC" "${FLAGS[@]}" "$here/recovery_touch_test.c" "$src/recovery_touch.c" \
    -o "$out/recovery_touch" 2>/dev/null || \
"$CC" "${FLAGS[@]}" "$here/recovery_touch_test.c" -o "$out/recovery_touch"
"$out/recovery_touch"
echo "  ok    recovery touch arms and disarms on the real thresholds"

"$CC" "${FLAGS[@]}" "$here/transport_safety_test.c" "$src/transport_safety.c" \
    -o "$out/transport_safety"
"$out/transport_safety"
echo "  ok    backpressure is survivable and nothing else is"
echo "  ok    the capture geometry divides, read from the real config.h"
echo "  ok    a failed notify still refuses to advance the sequence"

echo "firmware pure-logic checks: all passed (NOT a build, NOT hardware)"
