#!/bin/sh
# What the phone spent while it was listening — the sense, not the verdict.
#
#   sh app/ios/Tests/run_battery_tests.sh
#
# BatteryReadingPolicy is pure Foundation, so the real production source is
# compiled straight in rather than lifted or copied. No simulator, no scheme,
# no signing, no network.
#
# Exit code is the result. Non-zero means a case came back wrong.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

policy="$app/Audio/BatteryReadingPolicy.swift"
[ -f "$policy" ] || { echo "missing $policy"; exit 2; }
listener="$app/Audio/PhoneListener.swift"

# ------------------------------------------------------------- the wiring
# THE ONE LINE THAT DECIDES WHETHER ANY OF THIS MEASURES ANYTHING.
# `UIDevice.current.batteryLevel` returns -1.0 until battery monitoring is
# switched on, and it is off by default in every app. Without this line the
# policy correctly refuses every reading, the journal stays empty of them, the
# fold reports zero, and the screen says "Not recorded" forever — a whole
# instrument that is green end to end and measuring nothing. That is the exact
# shape of the three gate rules found this week passing by matching nothing, so
# it gets a leg of its own.
if ! grep -vE '^[[:space:]]*//' "$listener" \
    | grep -q 'isBatteryMonitoringEnabled = true'; then
    echo "Nothing switches battery monitoring on."
    echo "UIDevice.current.batteryLevel is -1.0 until it is enabled, so every"
    echo "reading is refused as unreadable, the journal records none, and the"
    echo "Listening screen reports \"Not recorded\" on a phone that is spending"
    echo "battery all day. The instrument would be green and blind."
    exit 2
fi

# And the raw pair must go through the policy rather than being cast at the call
# site. `Int(level * 100)` on the sentinel is -100; `max(0,)` of that is 0. Both
# are a number this screen would print.
if ! grep -vE '^[[:space:]]*//' "$listener" | tr '\n' ' ' \
    | grep -q 'BatteryReadingPolicy\.reading('; then
    echo "PhoneListener no longer asks BatteryReadingPolicy what the OS said."
    echo "The -1.0 sentinel then reaches the journal as a percentage: -100, or 0"
    echo "once somebody clamps it, and a phone reported flat all day."
    exit 2
fi

# swiftc only permits top-level code in a file literally named main.swift, so
# the suite is copied under that name rather than wrapped in a type it does not
# need — the same reason run_capture_source_tests.sh does it.
cp "$here/BatteryReadingPolicyTests.swift" "$out/main.swift"
swiftc -O "$policy" "$out/main.swift" -o "$out/batterytests"
"$out/batterytests"
