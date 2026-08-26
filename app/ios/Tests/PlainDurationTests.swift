import Foundation

// Checks for PlainDuration — how long something lasted, in units a person
// reads, from the one place three screens are about to read it from.
//
// WHY EXACT STRINGS. This type is a lift: `duration(_:)` was private inside
// `ListeningDiagnosticsView`, and the listening row in Settings and the home
// card are being built against the same `ListenTally` seconds this week. The
// argument those screens rest on is `ListeningDiagnosticsView.swift:38-43` —
// no threshold decides what counts as too long, so the reader judges — and that
// argument only holds while the same seconds read the same way on all three.
// The moment "6 hr 20 min" here is "6.3 hours" there, a person is comparing
// three claims about one measurement. So the table below is byte-for-byte what
// shipped, and a wording change has to come here and be argued for, which is
// the entire reason the function stopped being private.
//
// The sweeps at the end are the shape of the promise rather than a list of
// answers: every positive number of seconds renders as counted units and
// nothing else — no adjective, no threshold, no verdict can hide in a string
// that parses back to the number it came from.
//
// Pure Foundation, like ListenControlPolicy and ListenResumePolicy: swiftc
// alone, no simulator, no signing. The runner refuses this file a SwiftUI
// import, because a formatter that can reach for a Color is one that will
// eventually return a red one.

@main
struct PlainDurationTests {
    static func main() {
        var checks = 0
        var failures: [String] = []

        func check(_ name: String, _ ok: Bool) {
            checks += 1
            if ok {
                print("  ok    \(name)")
            } else {
                failures.append(name)
                print("  FAIL  \(name)")
            }
        }

        func says(_ seconds: Int, _ expected: String) {
            let got = PlainDuration.words(seconds)
            check("\(seconds) reads \"\(expected)\"" + (got == expected ? "" : " — got \"\(got)\""),
                  got == expected)
        }

        // ------------------------------------------- 1. the five that ship today
        // Named in the brief for this lift, because two other screens quote
        // them. These five are the contract.
        says(0, "none")
        says(44, "44 seconds")
        says(180, "3 min")
        says(7200, "2 hr")
        says(7800, "2 hr 10 min")

        // --------------------------------------------------- 2. the two nothings
        // "none" is an answer to "how long", not a count of zero seconds. Below
        // zero can only be a clock that moved backwards, and there is no honest
        // duration in that either.
        says(-1, "none")
        says(-86400, "none")

        // ------------------------------------------------------ 3. every seam
        // Where one unit hands over to the next, in both directions, because an
        // off-by-one here is invisible on screen and permanent in the log.
        says(1, "1 seconds")   // today's wording, preserved by the lift on
                               // purpose: a grammar fix smuggled in under a
                               // refactor is a copy change nobody reviewed. It
                               // is now one line in one file when somebody
                               // decides to make that call.
        says(59, "59 seconds")
        says(60, "1 min")
        says(119, "1 min")
        says(120, "2 min")
        says(3599, "59 min")
        says(3600, "1 hr")
        says(3660, "1 hr 1 min")
        says(7859, "2 hr 10 min")

        // ------------------------------------------- 4. no unit above the hour
        // A day never arrives to soften a long silence. The thirty deaf hours
        // this repo actually recorded read as thirty hours; "1 day 6 hr" is a
        // smaller-sounding sentence about the same failure, and rounding a
        // stretch of deafness into a friendlier unit is the reassuring wrong
        // number `ListenTally`'s own comments were written against.
        says(86400, "24 hr")
        says(108000, "30 hr")
        says(604800, "168 hr")

        // -------------------------------------------------- 5. it never rounds
        // The number shown is never larger than what the phone measured, and is
        // short of it by less than the minute it is counting in. Rounding up
        // invents silence nobody had.
        says(89, "1 min")
        says(3659, "1 hr")

        // ------------------------------------------- 6. the shape of any answer
        // A parser, not a word list: it accepts "<count> <unit>" pairs and
        // nothing else. An adjective, a verdict, a percentage or a bare number
        // with no unit all fail to parse, which is how this sweep can say
        // "there is no threshold hiding in here" over the whole range rather
        // than over the fifteen cases above.
        func secondsBack(_ text: String) -> Int? {
            let parts = text.split(separator: " ").map(String.init)
            guard parts.count == 2 || parts.count == 4 else { return nil }
            var total = 0
            var index = 0
            while index < parts.count {
                guard let count = Int(parts[index]), count > 0 else { return nil }
                switch parts[index + 1] {
                case "seconds": total += count
                case "min": total += count * 60
                case "hr": total += count * 3600
                default: return nil
                }
                index += 2
            }
            return total
        }

        var unparseable: [String] = []
        var overstated: [String] = []
        var shortByAMinuteOrMore: [String] = []
        var notADigitFirst: [String] = []
        for seconds in 1...200_000 {
            let text = PlainDuration.words(seconds)
            if text.first?.isNumber != true { notADigitFirst.append("\(seconds): \(text)") }
            guard let back = secondsBack(text) else {
                unparseable.append("\(seconds): \(text)")
                continue
            }
            if back > seconds { overstated.append("\(seconds): \(text)") }
            if seconds - back >= 60 { shortByAMinuteOrMore.append("\(seconds): \(text)") }
        }
        check("every positive length is counted units and nothing else"
              + (unparseable.isEmpty ? "" : " — \(unparseable.prefix(3))"),
              unparseable.isEmpty)
        check("every positive length starts with a digit, never a word"
              + (notADigitFirst.isEmpty ? "" : " — \(notADigitFirst.prefix(3))"),
              notADigitFirst.isEmpty)
        check("it never claims more time than it was given"
              + (overstated.isEmpty ? "" : " — \(overstated.prefix(3))"),
              overstated.isEmpty)
        check("it is never short by a minute or more"
              + (shortByAMinuteOrMore.isEmpty ? "" : " — \(shortByAMinuteOrMore.prefix(3))"),
              shortByAMinuteOrMore.isEmpty)

        // Nothing below zero says anything but "none", over a range rather than
        // the two cases above: a screen that renders "-3 seconds" has published
        // a clock bug as a measurement.
        var negativesThatSaidSomethingElse: [String] = []
        for seconds in -20_000 ... 0 where PlainDuration.words(seconds) != "none" {
            negativesThatSaidSomethingElse.append("\(seconds): \(PlainDuration.words(seconds))")
        }
        check("nothing at or below zero reports a length"
              + (negativesThatSaidSomethingElse.isEmpty ? "" : " — \(negativesThatSaidSomethingElse.prefix(3))"),
              negativesThatSaidSomethingElse.isEmpty)

        // ------------------------------------------------ 7. it reads longer up
        // Two lengths in order never read out of order. This is what stops a
        // future rewrite from producing "59 min" for an hour and a half.
        var wentBackwards: [String] = []
        var previous = 0
        for seconds in stride(from: 1, through: 400_000, by: 7) {
            let back = secondsBack(PlainDuration.words(seconds)) ?? -1
            if back < previous { wentBackwards.append("\(seconds): \(PlainDuration.words(seconds))") }
            previous = back
        }
        check("a longer stretch never reads as a shorter one"
              + (wentBackwards.isEmpty ? "" : " — \(wentBackwards.prefix(3))"),
              wentBackwards.isEmpty)

        print("")
        if failures.isEmpty {
            print("PlainDuration: all \(checks) checks passed")
        } else {
            print("PlainDuration: \(failures.count) of \(checks) checks FAILED")
            for name in failures { print("  - \(name)") }
            exit(1)
        }
    }
}
