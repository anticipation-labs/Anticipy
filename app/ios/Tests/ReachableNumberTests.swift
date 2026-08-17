import Foundation

// The product has no notifications at all: a text is the ONLY way it can ever
// reach a customer. Sign-up asked for email and password only, so a customer
// could arrive with no number, and every question the product needed to ask
// them went nowhere -- work parked forever, in silence, with nothing on any
// screen explaining it. This is the gate that makes the promise under that
// field ("your number is how I reach you") true.

var failures = 0
func check(_ name: String, _ ok: Bool) {
    print("\(ok ? "PASS" : "FAIL"): \(name)")
    if !ok { failures += 1 }
}

func looksReachable(_ raw: String) -> Bool {
    let digits = raw.filter(\.isNumber)
    guard digits.count >= 10, digits.count <= 15 else { return false }
    return !digits.allSatisfy { $0 == digits.first }
}

// How people really type numbers.
for good in ["+1 604 555 0142", "(604) 555-0142", "604.555.0142", "6045550142",
             "+44 20 7946 0958", "+1-604-555-0142"] {
    check("accepts \(good)", looksReachable(good))
}

// The cases that made a customer unreachable.
check("rejects an empty field", !looksReachable(""))
check("rejects whitespace", !looksReachable("   "))
check("rejects a half-typed number", !looksReachable("604555"))
check("rejects letters", !looksReachable("call me"))
check("rejects an obvious placeholder", !looksReachable("0000000000"))
check("rejects 1111111111", !looksReachable("1111111111"))
check("rejects something absurdly long", !looksReachable("12345678901234567890"))

if failures > 0 { print("ReachableNumberTests: \(failures) failed"); exit(1) }
print("ReachableNumberTests: all passed")
