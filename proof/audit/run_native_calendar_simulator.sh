#!/bin/sh
# Real EventKit write/readback/undo on a NEW simulator, never a user's calendar.
set -eu
repo=$(cd "$(dirname "$0")/../.." && pwd)
out=$(mktemp -d)
device=""
cleanup() {
  if [ -n "$device" ]; then
    xcrun simctl shutdown "$device" >/dev/null 2>&1 || true
    xcrun simctl delete "$device" >/dev/null 2>&1 || true
  fi
  rm -rf "$out"
}
trap cleanup EXIT
mkdir -p "$out/CalendarProbe.app"
cat > "$out/CalendarProbe.app/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>ai.anticipy.calendar-isolated-proof</string>
<key>CFBundleExecutable</key><string>CalendarProbe</string>
<key>CFBundleName</key><string>CalendarProbe</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleVersion</key><string>1</string>
<key>CFBundleShortVersionString</key><string>1.0</string>
<key>MinimumOSVersion</key><string>17.0</string>
<key>NSCalendarsFullAccessUsageDescription</key><string>This isolated test writes and removes only its own fixture calendar.</string>
<key>UILaunchScreen</key><dict/>
</dict></plist>
EOF
xcrun swiftc -sdk "$(xcrun --sdk iphonesimulator --show-sdk-path)" \
  -target arm64-apple-ios17.0-simulator -parse-as-library \
  "$repo/app/ios/Anticipy/Backend/CalendarHandPolicy.swift" \
  "$repo/app/ios/Anticipy/Backend/NativeCalendarExecution.swift" \
  "$repo/app/ios/Anticipy/Backend/NativeCalendarHand.swift" \
  "$repo/app/ios/Anticipy/ContextGrant.swift" "$repo/app/ios/Anticipy/LifeContext.swift" \
  "$repo/proof/audit/NativeCalendarSimulatorProbe.swift" \
  -o "$out/CalendarProbe.app/CalendarProbe"
device=$(xcrun simctl create 'Anticipy Calendar Isolated Proof' \
  com.apple.CoreSimulator.SimDeviceType.iPhone-17 \
  com.apple.CoreSimulator.SimRuntime.iOS-26-5)
xcrun simctl boot "$device"
xcrun simctl bootstatus "$device" -b
xcrun simctl install "$device" "$out/CalendarProbe.app"
# OS prompt UX is not measured here. Full access is pre-granted only on this
# isolated simulator so the test measures actual EventKit effects and readback.
xcrun simctl privacy "$device" grant calendar ai.anticipy.calendar-isolated-proof
xcrun simctl launch "$device" ai.anticipy.calendar-isolated-proof
container=$(xcrun simctl get_app_container "$device" ai.anticipy.calendar-isolated-proof data)
attempt=0
while [ ! -f "$container/Documents/calendar-proof.json" ] && [ "$attempt" -lt 60 ]; do
  sleep 1
  attempt=$((attempt + 1))
done
test -f "$container/Documents/calendar-proof.json"
destination="${1:-$repo/work/audit/native-calendar-simulator.json}"
cp "$container/Documents/calendar-proof.json" "$destination"
/usr/bin/plutil -extract passed raw -o - "$destination" | /usr/bin/grep -qx true
cat "$destination"
