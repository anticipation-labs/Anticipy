import Foundation

// Checks for InterviewInvitation — what the Settings interview section OFFERS,
// and what it says she already holds.
//
// WHAT THIS IS ABOUT. One section of one screen was telling a person two things
// about themselves, and on the same visit both could be false. The button was
// two-way on `isComplete`, so it read "Let me ask you six questions" directly
// above a caption reading "You've answered 4 of 6" — only the caption ever
// counted. And that caption's own opening read "You haven't told me anything
// about your life yet", under a heading reading "What I know about you", on a
// screen that reads back her first name, her number and every source she has
// been let into.
//
// WHY THE STRINGS ARE EXACT. This is copy, not arithmetic, and the whole reason
// it was lifted out of the view is that a wording change should have to arrive
// here and be argued for. Two of these sentences spell "six" in prose; the
// runner around this file is what keeps that honest against
// `InterviewQuestion.script`, because a spelled numeral cannot check itself.
//
// THE SWEEPS AT THE END ARE THE LAW LEGS, and they are the half worth reading.
// A sentence that names a source somebody has not granted is a claim about
// their account that is simply untrue; a sentence carrying a fraction or a
// percentage is the meter this section has been argued out of having twice.
// Neither can be caught by a table of expected answers, so both are asked of
// every combination the type can produce.
//
// Pure Foundation. The runner lifts the enum out of SettingsView.swift and
// compiles it with nothing but this file, so a decision that reaches for a
// Color or a View stops building rather than shipping untested.

@main
struct InterviewInviteTests {
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

        func equal(_ name: String, _ got: String, _ want: String) {
            checks += 1
            if got == want {
                print("  ok    \(name)")
            } else {
                failures.append(name)
                print("  FAIL  \(name)")
                print("          got:  \(got)")
                print("          want: \(want)")
            }
        }

        // The script this screen is about. Held as a constant here rather than
        // read from `InterviewQuestion`, which is a different file and not on
        // this compile line — the runner is what ties the two together.
        let six = 6

        print("")
        print("The button, three ways")

        // ------------------------------------------------------------ the button

        // Complete. The tap reopens every question, so the label must not
        // promise new ones — offering "go over them again" and then opening a
        // screen with nothing to ask is an offer that does nothing.
        equal("all answered offers a second pass",
              InterviewInvitation.buttonLabel(remaining: 0, total: six),
              "Go over my questions again")

        // Untouched. Today's words, character for character.
        equal("none answered keeps the shipped sentence",
              InterviewInvitation.buttonLabel(remaining: 6, total: six),
              "Let me ask you six questions")

        // The middle, which did not exist. This is the case that used to read
        // "Let me ask you six questions" over "You've answered 4 of 6".
        equal("two left",
              InterviewInvitation.buttonLabel(remaining: 2, total: six),
              "Let me ask you 2 more questions")
        equal("five left",
              InterviewInvitation.buttonLabel(remaining: 5, total: six),
              "Let me ask you 5 more questions")

        // Singular, because "1 more questions" is the kind of sentence that
        // tells a reader nobody looked at this screen.
        equal("one left is singular",
              InterviewInvitation.buttonLabel(remaining: 1, total: six),
              "Let me ask you 1 more question")

        // Defensive both ends. Neither is reachable through
        // `InterviewProgress.remaining`, which is a filter of the script — but
        // a label is not the place to discover that, and the alternative to a
        // clamp here is "Let me ask you 0 more questions" on somebody's screen.
        equal("a negative count still reads as complete",
              InterviewInvitation.buttonLabel(remaining: -1, total: six),
              "Go over my questions again")
        equal("an overrun count lands on the offer, not on a bigger number",
              InterviewInvitation.buttonLabel(remaining: 7, total: six),
              "Let me ask you six questions")

        // THE CONTRADICTION ITSELF, asked directly. The defect was one specific
        // string appearing while some questions were answered.
        var saidSixWhileAnswered: [Int] = []
        for remaining in 1..<six
        where InterviewInvitation.buttonLabel(remaining: remaining, total: six)
                .contains("six") {
            saidSixWhileAnswered.append(remaining)
        }
        check("never offers six once anything has been answered "
              + "(said it at: \(saidSixWhileAnswered))",
              saidSixWhileAnswered.isEmpty)

        // AND THE COUNT MUST BE THE REAL ONE. A label that says a number has to
        // say the number it was handed, or it is a third claim on a screen that
        // already had two.
        var wrongNumber: [Int] = []
        for remaining in 1..<six
        where !InterviewInvitation.buttonLabel(remaining: remaining, total: six)
                .contains("\(remaining)") {
            wrongNumber.append(remaining)
        }
        check("every counted label carries its own count (missing at: \(wrongNumber))",
              wrongNumber.isEmpty)

        print("")
        print("The button stays an offer")

        // THE DEPARTURE FROM THE AUDIT, PINNED. The audit asked for "2 questions
        // left". This file's own Appearance row rejects that shape in writing —
        // it "names what the tap DOES rather than what the app currently is",
        // because "a control that reads 'Light' while the screen is light is a
        // status line people tap expecting nothing to happen". So every label
        // this type can return has to open with a verb, and the caption below
        // the button stays the only place the count is merely reported.
        var notAnOffer: [String] = []
        for remaining in -2...(six + 2) {
            let label = InterviewInvitation.buttonLabel(remaining: remaining, total: six)
            if !label.hasPrefix("Let me ask") && !label.hasPrefix("Go over") {
                notAnOffer.append("\(remaining) → \(label)")
            }
        }
        check("every label names the action rather than the state "
              + "(status lines: \(notAnOffer))",
              notAnOffer.isEmpty)

        // NO SCORE ON A BUTTON. "4 of 6" and "67%" are the shapes this section
        // has now been argued out of twice.
        var scored: [String] = []
        for remaining in -2...(six + 2) {
            let label = InterviewInvitation.buttonLabel(remaining: remaining, total: six)
            if label.contains("%") || label.contains(" of ") || label.contains("/") {
                scored.append("\(remaining) → \(label)")
            }
        }
        check("no label carries a fraction or a percentage (found: \(scored))",
              scored.isEmpty)

        // AND NOTHING EMPTY. A blank button is a tappable mystery.
        var blank: [Int] = []
        for remaining in -2...(six + 2)
        where InterviewInvitation.buttonLabel(remaining: remaining, total: six).isEmpty {
            blank.append(remaining)
        }
        check("no count produces a blank label (blank at: \(blank))", blank.isEmpty)

        print("")
        print("What she holds, when the interview is untouched")

        // ------------------------------------------------------- the holdings line

        // The one case the shipped sentence was true of, kept verbatim.
        equal("holding nothing keeps the shipped sentence",
              InterviewInvitation.nothingAnswered(
                name: false, number: false, calendar: false, contacts: false),
              "You haven't told me anything about your life yet. Six questions, all skippable.")

        equal("a name alone",
              InterviewInvitation.nothingAnswered(
                name: true, number: false, calendar: false, contacts: false),
              "I know your name. Six questions would tell me the rest, all skippable.")

        equal("a number alone",
              InterviewInvitation.nothingAnswered(
                name: false, number: true, calendar: false, contacts: false),
              "I know your number. Six questions would tell me the rest, all skippable.")

        equal("a calendar alone",
              InterviewInvitation.nothingAnswered(
                name: false, number: false, calendar: true, contacts: false),
              "I know what's on your calendar. Six questions would tell me the rest, all skippable.")

        equal("two of them join with 'and', no comma",
              InterviewInvitation.nothingAnswered(
                name: true, number: true, calendar: false, contacts: false),
              "I know your name and your number. Six questions would tell me the rest, all skippable.")

        // The audit's own example sentence, word for word.
        equal("three of them, the audit's sentence",
              InterviewInvitation.nothingAnswered(
                name: true, number: true, calendar: true, contacts: false),
              "I know your name, your number and what's on your calendar. Six questions would tell me the rest, all skippable.")

        equal("all four",
              InterviewInvitation.nothingAnswered(
                name: true, number: true, calendar: true, contacts: true),
              "I know your name, your number, what's on your calendar and who's in your contacts. Six questions would tell me the rest, all skippable.")

        // The gap in the middle: she holds a name and a calendar but no number.
        // The clause must simply skip the number, not mark its absence.
        equal("a gap in the middle closes up rather than being named",
              InterviewInvitation.nothingAnswered(
                name: true, number: false, calendar: true, contacts: false),
              "I know your name and what's on your calendar. Six questions would tell me the rest, all skippable.")

        print("")
        print("The law legs, over every combination")

        // ------------------------------------------------------------ the sweeps

        // Every combination this type can produce, built once and asked three
        // questions. A table of expected answers cannot catch these; they are
        // properties of all sixteen at once.
        struct Held {
            let name: Bool, number: Bool, calendar: Bool, contacts: Bool
            var line: String {
                InterviewInvitation.nothingAnswered(
                    name: name, number: number, calendar: calendar, contacts: contacts)
            }
            var words: String {
                "name=\(name) number=\(number) calendar=\(calendar) contacts=\(contacts)"
            }
        }
        var every: [Held] = []
        for n in [false, true] {
            for p in [false, true] {
                for c in [false, true] {
                    for k in [false, true] {
                        every.append(Held(name: n, number: p, calendar: c, contacts: k))
                    }
                }
            }
        }
        check("sixteen combinations built", every.count == 16)

        // 1. SHE NEVER NAMES A GRANT SHE DOES NOT HOLD. This is the leg that
        //    matters most: the line is a claim about somebody's own account, and
        //    a false one on a consent screen is worse than the silence it
        //    replaced. A calendar she cannot see must not appear in this
        //    sentence in any form, including a denial of it.
        var claimedWhatItLacks: [String] = []
        for held in every {
            let line = held.line
            if !held.name && line.contains("your name") {
                claimedWhatItLacks.append("\(held.words) — named a name")
            }
            if !held.number && line.contains("your number") {
                claimedWhatItLacks.append("\(held.words) — named a number")
            }
            if !held.calendar && line.contains("calendar") {
                claimedWhatItLacks.append("\(held.words) — named the calendar")
            }
            if !held.contacts && line.contains("contacts") {
                claimedWhatItLacks.append("\(held.words) — named the contacts")
            }
        }
        check("never names a source she does not hold (\(claimedWhatItLacks))",
              claimedWhatItLacks.isEmpty)

        // 2. AND IT NEVER NAMES AN ABSENCE. The opposite failure, and the more
        //    tempting one: "I know your name, but not your number" is true, and
        //    it is also a gap with a shape on a screen about consent. She says
        //    what she has and stops.
        var namedAnAbsence: [String] = []
        for held in every {
            let line = held.line.lowercased()
            for gap in ["but not", "don't know", "do not know", "haven't got",
                        "still missing", "i'm missing", "not yet got"]
            where line.contains(gap) && !(held.line.hasPrefix("You haven't told me")) {
                namedAnAbsence.append("\(held.words) — \(gap)")
            }
        }
        check("never names what she is missing (\(namedAnAbsence))",
              namedAnAbsence.isEmpty)

        // 3. NO FRACTION, NO PERCENTAGE, NO METER, and no digit at all. The
        //    holdings clause is a separate statement of what she holds and is
        //    explicitly NOT counted toward the six: knowing a phone number is
        //    not two-sixths of an interview. A digit appearing in this sentence
        //    is the fraction growing back.
        var counted: [String] = []
        for held in every {
            let line = held.line
            if line.contains("%") || line.contains("/")
                || line.rangeOfCharacter(from: CharacterSet.decimalDigits) != nil {
                counted.append("\(held.words) → \(line)")
            }
        }
        check("no combination reports a fraction, a percentage or a digit (\(counted))",
              counted.isEmpty)

        // 4. AND EVERY ONE OF THEM IS A SENTENCE. Ends in a full stop, opens on
        //    a capital, and is never empty — a clause assembled from a list is
        //    exactly the thing that ships as "I know . Six questions…".
        var malformed: [String] = []
        for held in every {
            let line = held.line
            if line.isEmpty || !line.hasSuffix(".") || line.contains("  ")
                || line.contains(" .") || line.contains(",.") {
                malformed.append("\(held.words) → \(line)")
            }
        }
        check("every combination is a well-formed sentence (\(malformed))",
              malformed.isEmpty)

        // 5. THE OFFER SURVIVES IN ALL OF THEM. Whatever she holds, the line
        //    still has to say the questions exist and that they can be skipped —
        //    that promise is what makes the section askable at all.
        var lostThePromise: [String] = []
        for held in every where !held.line.contains("skippable") {
            lostThePromise.append(held.words)
        }
        check("every combination still promises the questions are skippable "
              + "(\(lostThePromise))",
              lostThePromise.isEmpty)

        print("")
        print("The list joiner")

        // ------------------------------------------------------------- the joiner

        equal("nothing", InterviewInvitation.sentenceList([]), "")
        equal("one", InterviewInvitation.sentenceList(["a"]), "a")
        equal("two", InterviewInvitation.sentenceList(["a", "b"]), "a and b")
        equal("three, no serial comma",
              InterviewInvitation.sentenceList(["a", "b", "c"]), "a, b and c")
        equal("four, no serial comma",
              InterviewInvitation.sentenceList(["a", "b", "c", "d"]), "a, b, c and d")
        check("never a serial comma at any length",
              !(2...8).contains { n in
                  InterviewInvitation.sentenceList((1...n).map { "x\($0)" })
                      .contains(", and ")
              })

        print("")
        if failures.isEmpty {
            print("InterviewInvitation: all \(checks) checks passed")
        } else {
            print("InterviewInvitation: \(failures.count) of \(checks) checks FAILED")
            for name in failures { print("  - \(name)") }
            exit(1)
        }
    }
}
