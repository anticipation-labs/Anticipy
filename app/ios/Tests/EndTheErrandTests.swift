import Foundation

// Checks for the end-of-errand decision — the one place in the app that can
// turn a typed answer into a cancelled job with the owner's own sentence filed
// as the reason they called it off. Getting this wrong is not cosmetic: the
// ledger then reads as if they stopped work they never stopped.
//
// READ THIS BEFORE YOU READ A SINGLE ASSERTION. The rule under test is
// REGISTERED TAPE — a Law-1 violation shipping under Law 2 with a marker in
// AnticipyApp.swift, an entry in overnight/tape_gate.py and a bullet in
// HARNESS-LAWS.md. Nothing below is a statement that this is how answers
// SHOULD be routed. A suite that pins a violation in place while reading as a
// specification is a known failure mode in this repo — it has been found four
// times — so every section here says which of three things it is:
//
//   proceeds(...)  the invariant that SURVIVES the fix. When the tape is
//                  deleted every one of these still holds, trivially, because
//                  everything goes to the brain. Keep them.
//   ends(...)      what the tape currently catches. These are a REGRESSION PIN
//                  on the tape (Law 2 is explicit that a pin is not an
//                  expiry — the expiry is tape_gate leg 2). They die WITH the
//                  tape, in the same diff.
//   costs(...)     what the tape gets WRONG today, measured 2026-08-25 and
//                  written down rather than argued about. Every one is a live
//                  answer being destroyed. They die with the tape too, and
//                  their disappearance is the point of deleting it.
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

    /// The rule ends the errand here AND IT IS WRONG TO. A measured cost of
    /// the tape, pinned so it cannot drift unnoticed and cannot be forgotten
    /// when the removal is argued.
    ///
    /// If this fails because you DELETED the rule: that is the fix landing.
    /// Delete this whole section — it is a record of damage, never a
    /// requirement. If it fails because you edited the phrase lists, you have
    /// changed the blast radius of tape that is supposed to be on its way out.
    static func costs(_ answer: String, _ lost: String) {
        checks += 1
        if EndOfErrand.answerThatEndsTheErrand(answer) == nil {
            failures.append("no longer eaten — if the tape is gone, delete this case\n      \u{201C}\(answer)\u{201D} (was losing: \(lost))")
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
        // WHAT THE TAPE CURRENTLY CATCHES — a regression pin on the tape, not
        // a specification of correct routing. Law 2 is explicit that a pin is
        // not an expiry; the expiry is tape_gate leg 2, and it is red. These
        // die in the same diff that deletes the rule.
        //
        // WHAT THIS SECTION DOES NOT DO, because it said otherwise until
        // 2026-08-25 and the claim was measured false. It used to read "these
        // cases exist so the phrase lists cannot be quietly widened or
        // narrowed while they are on their way out." They cannot do that.
        // They are eighteen samples of a 116-word vocabulary, and samples do
        // not fence. Measured: each of the 50 phrases in `whole`, `declines`
        // and `handled` was deleted in turn and the mutated rule compiled —
        // 24 of those deletions change what the app does and leave this file
        // at 48/48, exit 0. Deleting "cancel" from `whole` is one of them, and
        // a bare typed "cancel" then stops ending anything. Widening is worse
        // and was equally unseen: one line, "yes", added to `declines` files
        // the owner's approval as their cancellation, all green.
        //
        // The fence is in run_end_errand_tests.sh, which extracts every string
        // literal from the shipping rule and compares all 116 to a golden
        // list. That goes red in both directions, for all five lists, and for
        // the sentences the owner is shown. This section is what the tape
        // catches; that leg is what the tape is ALLOWED TO SAY.
        //
        // `ends("no", …)` used to head this list. It has moved down to
        // costs(): a stuck card's ordinary shape is a yes/no question, so a
        // bare "no" is at least as likely to be an ANSWER as a cancellation,
        // and calling that a stop the tape "must still land" was this suite
        // asserting the violation was correct.
        // ------------------------------------------------------------------
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

        // ------------------------------------------------------------------
        // THE COST OF THE TAPE, MEASURED. Not hypotheticals — every line here
        // was run against the shipping rule on 2026-08-25.
        //
        // The comments on the rule argue that position saves it: a stop leads
        // its clause and only filler may follow, so "leave it with the
        // concierge" is an instruction and survives. That is true INSIDE a
        // clause. It is false across them. The answer is split on , ; : ! ? and
        // dashes, and `clauses.contains(where:)` ends the errand if ANY ONE
        // clause leads with a stop — whatever the other clauses say. So the
        // substring-anywhere bug the comments describe killing is still here,
        // one level up, and it destroys exactly the information a parked run
        // is parked for.
        //
        // It cannot be repaired with another rule: separating explanation
        // ("never mind, I'll call them myself") from instruction ("cancel it,
        // and book the 8pm instead") is a question about MEANING, which is the
        // reason this whole function is registered tape.
        // ------------------------------------------------------------------
        costs("already sent, the code is 4821",
              "the verification code the parked run is stopped for")
        costs("handled it, but they need the card number",
              "he is saying it is BLOCKED, and the job is cancelled instead")
        costs("took care of it: use gate 7",
              "the gate number, and the errand")
        costs("already booked, table for 4 under Cruz",
              "the party size and the name the booking is under")
        costs("already did it \u{2014} confirmation is XR44Q",
              "the confirmation number; an em dash splits clauses too")
        costs("cancel it, and book the 8pm instead",
              "the instruction to book the 8pm — cancelled, never booked")
        costs("drop it, book Earls instead",
              "the replacement errand, in the same breath as the stop")

        // A yes/no question is the ordinary shape of a stuck card ("Should I
        // use the Visa ending 4412?"). A bare "no" answers it. The rule reads
        // the same three letters as a cancellation, because "no" sits in
        // `whole` — and the brain's own notes record a bare \bno\b cancelling
        // a held booking, which is the identical mistake one process over.
        costs("no", "an answer to her yes/no question, read as a cancellation")

        // The line between `whole` (exact answer only) and `declines` (may
        // lead a clause) is invisible from outside and changes the outcome.
        // Pinned as a pair so the arbitrariness is on the record, not so it
        // is preserved.
        ends("stop", "bare, it is in `whole`")
        proceeds("ok stop", "one filler word in front of it and `whole` misses")
        ends("ok stop it", "but `stop it` is in `declines`, so this one dies")

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
