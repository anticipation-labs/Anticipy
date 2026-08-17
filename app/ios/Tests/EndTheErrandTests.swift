import Foundation

// Checks for the end-of-errand decision — the one place in the app that can
// turn a typed answer into a cancelled job with the owner's own sentence filed
// as the reason they called it off. Getting this wrong is not cosmetic: the
// ledger then reads as if they stopped work they never stopped.
//
// The rule is NOT duplicated here. run_end_errand_tests.sh lifts the real
// source out of AnticipyApp.swift between its ANCHOR markers and compiles it
// into `EndOfErrand`, so these cases run against the shipping code and there is
// no second copy to drift.

@main
enum Cases {
    static var failures: [String] = []
    static var checks = 0

    /// The answer must NOT end the errand: it carries an instruction.
    static func proceeds(_ answer: String, _ why: String) {
        checks += 1
        if let ended = EndOfErrand.answerThatEndsTheErrand(answer) {
            failures.append("\(why)\n      \u{201C}\(answer)\u{201D} killed the job: \(ended)")
        }
    }

    /// The answer IS a stop and must end the errand.
    static func ends(_ answer: String, _ why: String) {
        checks += 1
        if EndOfErrand.answerThatEndsTheErrand(answer) == nil {
            failures.append("\(why)\n      \u{201C}\(answer)\u{201D} was let through as an instruction")
        }
    }

    static func expect(_ condition: Bool, _ why: String) {
        checks += 1
        if !condition { failures.append(why) }
    }

    static func main() {
        // ------------------------------------------------------------------
        // The regressions this rule exists for. Every one is a SHORT answer,
        // which is why capping the answer at eight words caught none of them.
        // ------------------------------------------------------------------
        proceeds("leave it with the concierge",
                 "a delivery instruction, not a decline")
        proceeds("drop it off at reception after 5",
                 "where to leave the parcel, not a decline")
        proceeds("skip it only if there's a booking fee",
                 "a condition handed back to her, not a decline")
        proceeds("stop it from auto-renewing",
                 "the thing he wants DONE, not a decline")
        proceeds("cancel it if the fee is more than $20",
                 "a conditional cancellation is a judgment call, not a stop")
        proceeds("it's not already booked yet, go ahead",
                 "a NEGATED phrase filed his go-ahead as him having done it")
        proceeds("no, don't cancel it, go ahead",
                 "an explicit refusal to cancel must not cancel")
        proceeds("please don't bother them at work, just email instead",
                 "how to reach them, not a stop")
        proceeds("already booked a table for 4 at 7",
                 "facts she still needs, not a hand-off")
        proceeds("i already sent them the email you asked for",
                 "reports one step done; the errand continues")
        proceeds("tell sarah i'm dropping it off tomorrow",
                 "a message to relay that happens to contain 'drop it'")
        proceeds("i told them to leave it, so go ahead and confirm",
                 "'leave it' inside reported speech, ending in a go-ahead")
        proceeds("if they're full, skip it",
                 "conditional, whichever order the clauses arrive in")

        // ------------------------------------------------------------------
        // Real stops must still land — including the long ones the word cap
        // used to throw away.
        // ------------------------------------------------------------------
        ends("no", "the bare no")
        ends("Never mind.", "punctuation and case are not content")
        ends("nevermind", "written as one word")
        ends("stop it", "the bare form of a phrase that also appears mid-sentence")
        ends("skip it", "same")
        ends("leave it", "same")
        ends("ok, forget it", "an opener in front of a stop is still a stop")
        ends("actually, forget it", "same")
        ends("no, forget it", "same")
        ends("cancel it please", "trailing courtesy is not content")
        ends("don't bother, I got it", "a stop leading the answer")
        ends("no longer need this", "a decline that opens with the word 'no'")
        ends("i already booked it", "he handled it himself")
        ends("already sent it, thanks", "same, with a trailing thanks")
        ends("i did it already", "same")
        ends("took care of it", "same")
        ends("sorted it", "same")
        ends("never mind, I'll call them myself and book the table for six",
             "a stop is a stop however much explanation follows it")
        ends("Not anymore", "whole-answer form")

        // ------------------------------------------------------------------
        // The two verdicts are different sentences, and both quote the owner
        // verbatim — that quote is what the job's result field stores.
        // ------------------------------------------------------------------
        let handoff = EndOfErrand.answerThatEndsTheErrand("i already booked it")
        expect(handoff?.hasPrefix("You handled it yourself") == true,
               "a hand-off must not be filed as calling it off: \(handoff ?? "nil")")
        expect(handoff?.contains("i already booked it") == true,
               "the stored result must quote what he actually typed: \(handoff ?? "nil")")
        let called = EndOfErrand.answerThatEndsTheErrand("forget it")
        expect(called?.hasPrefix("You called it off") == true,
               "a decline must not be filed as him having done it: \(called ?? "nil")")

        // An empty or punctuation-only answer decides nothing.
        proceeds("", "an empty answer is not a stop")
        proceeds("   ", "whitespace is not a stop")
        proceeds("...", "punctuation is not a stop")

        print("\(checks - failures.count)/\(checks) checks passed")
        if !failures.isEmpty {
            for f in failures { print("FAIL  \(f)") }
            print("\(failures.count) FAILED")
            exit(1)
        }
        print("end-of-errand: all green")
        exit(0)
    }
}
