// What the OS said about the battery, and whether it is worth writing down.
//
// Two failures are being prevented here, and both have already happened in this
// repo in another shape.
//
// 1. THE SENTINEL. `UIDevice.current.batteryLevel` is -1.0 whenever monitoring
//    was never switched on, and the simulator returns it forever. `Int(-1.0 *
//    100)` is -100, and `max(0, …)` of it is 0 — so the naive call site reports
//    a phone sitting at zero per cent all day, or a fold that "measures" a
//    hundred points of drain the first time a real reading arrives. A number
//    that cannot be read must come back as NOTHING, the way
//    `CaptureSourcePolicy` returns nil rather than guessing at an ear.
//
// 2. THE CHURN. The 4-second watchdog is what reads this. A line per tick is
//    fifteen a minute, which is exactly the rate that evicted the 400-line ring
//    in twenty-seven minutes and turned a dead day into a blank, healthy
//    report. A reading is written when it CHANGES and at no other time.
//
// Run: sh app/ios/Tests/run_battery_tests.sh
import Foundation

// Compiled against the REAL production source by the runner — this is pure
// Foundation, so there is no copy of it to drift.
var failures = 0
func check(_ name: String, _ ok: Bool) {
    print("\(ok ? "PASS" : "FAIL"): \(name)")
    if !ok { failures += 1 }
}

// ------------------------------------------------------- an ordinary reading
if let r = BatteryReadingPolicy.reading(level: 0.47, stateIsKnown: true, onPower: false) {
    check("a level of 0.47 reads as 47 per cent", r.percent == 47)
    check("and it knows the phone was not on power", r.onPower == false)
} else {
    check("an ordinary reading survives", false)
}

check("on power is carried through",
      BatteryReadingPolicy.reading(level: 0.47, stateIsKnown: true, onPower: true)?.onPower == true)

// Rounded, not truncated. `Int(0.479 * 100)` is 47 on a phone that is at 48,
// and the whole point of the number is that it can be compared with the next
// one an hour later.
//
// 0.479 rather than a half-way value: binary32 cannot hold 0.475 and stores
// 0.4749999940, so 0.475 would be testing the float format rather than this
// rule. 0.479 is 47 truncated and 48 rounded, which is the difference asserted.
check("a level rounds to the nearest point, rather than truncating",
      BatteryReadingPolicy.reading(level: 0.479, stateIsKnown: true, onPower: false)?.percent == 48)
check("and rounds down when it should",
      BatteryReadingPolicy.reading(level: 0.474, stateIsKnown: true, onPower: false)?.percent == 47)

// ------------------------------------------------------------- the sentinel
// The one this file exists for. -1.0 is what iOS returns when battery
// monitoring is off, and it is what the simulator returns always.
check("the -1 sentinel is not a reading",
      BatteryReadingPolicy.reading(level: -1.0, stateIsKnown: true, onPower: false) == nil)
check("no negative level is a reading",
      BatteryReadingPolicy.reading(level: -0.5, stateIsKnown: true, onPower: false) == nil)
// batteryState .unknown means the OS cannot say whether the phone is on power,
// and "on power" is what decides whether the next interval may be measured at
// all. A level with no state behind it is not usable.
check("a level with an unknown power state is not a reading",
      BatteryReadingPolicy.reading(level: 0.47, stateIsKnown: false, onPower: false) == nil)

// A genuinely empty battery is a real reading and must not be confused with the
// sentinel — this is the difference between "flat" and "we cannot see".
check("a flat battery is still a reading",
      BatteryReadingPolicy.reading(level: 0.0, stateIsKnown: true, onPower: true)?.percent == 0)
check("a full battery reads as 100",
      BatteryReadingPolicy.reading(level: 1.0, stateIsKnown: true, onPower: true)?.percent == 100)
// Above 1.0 is nonsense rather than unreadable — a percentage over 100 in a
// report is a defect a person cannot act on, so it is clamped.
check("a level above full clamps to 100",
      BatteryReadingPolicy.reading(level: 1.4, stateIsKnown: true, onPower: true)?.percent == 100)

// --------------------------------------------------------- what gets written
let unplugged47 = BatteryReadingPolicy.Reading(percent: 47, onPower: false)
let unplugged46 = BatteryReadingPolicy.Reading(percent: 46, onPower: false)
let plugged47 = BatteryReadingPolicy.Reading(percent: 47, onPower: true)

check("the first reading of a session is always written",
      BatteryReadingPolicy.shouldRecord(unplugged47, lastRecorded: nil))
// THE CHURN RULE. Fifteen identical lines a minute for the length of a phone
// call is what evicted the ring and hid the interruption that explained the
// day.
check("an unchanged reading is not written again",
      !BatteryReadingPolicy.shouldRecord(unplugged47, lastRecorded: unplugged47))
check("a point spent is written",
      BatteryReadingPolicy.shouldRecord(unplugged46, lastRecorded: unplugged47))
// Plugging in at the same percentage changes nothing about the number and
// everything about what may be done with it: the interval that follows is not
// drain and must not be counted as any.
check("going on or off power is written even at the same percentage",
      BatteryReadingPolicy.shouldRecord(plugged47, lastRecorded: unplugged47))
check("and coming off power is too",
      BatteryReadingPolicy.shouldRecord(unplugged47, lastRecorded: plugged47))

if failures > 0 {
    print("BatteryReadingPolicyTests: \(failures) failed")
    exit(1)
}
print("BatteryReadingPolicyTests: all passed")
