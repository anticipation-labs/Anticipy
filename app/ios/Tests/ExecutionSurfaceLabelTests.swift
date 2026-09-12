import Foundation

// executionSurfaceLabel is extracted from the production AgentJob extension.
// CalendarHandPolicy is compiled unchanged. No copied lane switch is tested.
struct ExecutionSurfaceFixture { let lane: String? }
var failures = 0
let cases: [(String?, String)] = [
    ("api", "Hand 3 · Connected app"),
    (" API ", "Hand 3 · Connected app"),
    ("research", "Hand 2 · Research service"),
    (" Research\n", "Hand 2 · Research service"),
    ("device_calendar", "This iPhone · Calendar"),
    (" DEVICE_CALENDAR ", "This iPhone · Calendar"),
    ("browser", "Hand 1 · Browser"),
    (nil, "Hand 1 · Browser"),
    ("", "Hand 1 · Browser")
]
for (lane, expected) in cases {
    let actual = ExecutionSurfaceFixture(lane: lane).executionSurfaceLabel
    let okay = actual == expected
    print("\(okay ? "PASS" : "FAIL"): lane \(lane ?? "nil") → \(actual)")
    if !okay { failures += 1 }
}
exit(failures == 0 ? 0 : 1)
