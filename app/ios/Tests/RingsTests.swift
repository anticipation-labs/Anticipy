import Foundation

// COMPLETION DRIVE, walked. Compiled by run_rings_tests.sh against the
// production policy; this file is that suite's main.swift.

var failures = 0
func check(_ ok: Bool, _ name: String, _ detail: @autoclosure () -> String = "") {
    if ok { print("PASS: \(name)") } else { failures += 1; print("FAIL: \(name) \(detail())") }
}
typealias R = RingsPolicy

// ======================================================= A RING CANNOT FALL
// The whole reason a ring is honest here and a streak was not. Both loops count
// things the owner FINISHED, so nothing a server does can take one back.
for total in 1...8 {
    var last = -1.0
    for done in 0...total {
        let f = R.face(.whatSheKnows, done: done, total: total)
        check(f.fraction >= last, "a ring only ever grows", "\(done)/\(total)")
        last = f.fraction
    }
}
// And it cannot overflow, whatever the server says.
check(R.face(.whatSheKnows, done: 9, total: 3).fraction == 1.0,
      "five of three draws a closed ring, not one and two-thirds")
check(R.face(.whatSheKnows, done: -4, total: 3).fraction == 0.0,
      "and a negative count cannot draw a backwards arc")

// ==================================================== ABSENT, NEVER EMPTY
// A heading over nothing is the failure InsightsPolicy spends its whole file
// avoiding: an empty state says "it doesn't work" where a missing one says
// "not yet".
check(R.decide(.whatSheKnows, done: 0, total: 0, daysSinceClosed: nil) == .hide(.nothingToCount),
      "zero out of zero is not a ring")
check(R.rings(knows: (0, 0, nil), reaches: nil).isEmpty,
      "and the section is absent entirely when there is nothing to count")
if case .draw = R.decide(.whatSheKnows, done: 0, total: 6, daysSinceClosed: nil) {
    check(true, "but zero out of six IS a ring — that is the open loop")
} else { check(false, "zero out of six IS a ring") }

// ============================================ A CLOSED RING STOPS BEING NEWS
check(R.decide(.whatSheKnows, done: 6, total: 6, daysSinceClosed: 1) != .hide(.longSinceClosed),
      "closing it is worth seeing the same day")
check(R.decide(.whatSheKnows, done: 6, total: 6, daysSinceClosed: 99) == .hide(.longSinceClosed),
      "a full circle three months later is furniture")
check(R.decide(.whatSheKnows, done: 6, total: 6, daysSinceClosed: nil) != .hide(.longSinceClosed),
      "and an unrecorded closing date keeps it rather than guessing")

// ======================================== THE SECOND RING DEGRADES HONESTLY
// Home cannot see the connected-apps count, and a screen that cannot see a
// number must not invent a denominator for it.
check(R.rings(knows: (2, 6, nil), reaches: nil).count == 1,
      "an uncountable loop is hidden, not guessed")
check(R.rings(knows: (2, 6, nil), reaches: (1, 3, nil)).count == 2,
      "and drawn the moment somebody can actually count it")
check(R.rings(knows: (2, 6, nil), reaches: nil).first?.ring == .whatSheKnows,
      "the loop that survives is the one with real numbers")

// ================================================ NUMBERS, NOT PERCENTAGES
// "2 of 3" and "67%" are the same ratio and not the same fact: a percentage
// hides how small the whole thing is.
let f = R.face(.whatSheKnows, done: 2, total: 6)
check(f.done == 2 && f.total == 6, "the face carries both numbers")
check(!f.because.contains("%"), "and says no percentage", f.because)

// ================================================== IT NEVER CONGRATULATES
// The same rule run_insights_tests.sh holds for the screen this sits on.
for ring in R.Ring.allCases {
    for (d, t) in [(0, 5), (3, 5), (5, 5)] {
        let face = R.face(ring, done: d, total: t)
        let words = (face.title + " " + face.because).lowercased()
        for banned in ["congratulat", "well done", "keep it up", "nice work",
                       "great job", "streak", "score", "level up", "unlock", "!"] {
            check(!words.contains(banned), "nothing here applauds or gamifies",
                  "\(ring) \(d)/\(t): \(banned)")
        }
    }
}
// The consequence is stated, not dangled.
check(R.face(.whatSheKnows, done: 1, total: 6).because
        != R.face(.whatSheKnows, done: 6, total: 6).because,
      "an open loop and a closed one do not say the same thing")

// ===================================================== EVERY HIDE HAS WORDS
for d in [R.decide(.whatSheKnows, done: 0, total: 0, daysSinceClosed: nil),
          R.decide(.whatSheKnows, done: 6, total: 6, daysSinceClosed: 99),
          R.decide(.whatSheKnows, done: 2, total: 6, daysSinceClosed: nil)] {
    check(!R.words(d).isEmpty, "a decision can always be printed", R.words(d))
}

print(failures == 0 ? "\nAll ring checks passed." : "\n\(failures) ring check(s) failed.")
exit(failures == 0 ? 0 : 1)
