#!/bin/sh
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
cp "$here/NativeCalendarExecutionTests.swift" "$out/main.swift"
swiftc "$here/../Anticipy/Backend/CalendarHandPolicy.swift" \
  "$here/../Anticipy/Backend/NativeCalendarExecution.swift" "$out/main.swift" -o "$out/test"
export NATIVE_CALENDAR_WIRE_FIXTURE="${NATIVE_CALENDAR_WIRE_FIXTURE:-$out/wire.json}"
"$out/test"
node --experimental-strip-types "$here/../../../migration/workers/test/native-calendar-wire.test.ts" \
  "$NATIVE_CALENDAR_WIRE_FIXTURE"
