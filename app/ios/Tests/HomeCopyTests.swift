import Foundation

// Checks for HOME'S COUNTED SENTENCES — the browser ask, the interview ask, the
// microphone taken away, and the day-zero examples said out loud.
//
// WHY EXACT STRINGS, EVERYWHERE. Every sentence below is a claim about a number
// this phone counted, and three of them were wrong before this suite existed:
// the browser card asked for two minutes and never named what was waiting, the
// interview card told a person with three answers behind them that there were
// six questions, and the interruption line claimed an ongoing recovery in the
// present tense that read the same at four seconds as at four hours. A copy
// change that walks any of those back has to come here and be argued for.
//
// WHAT THIS SUITE WILL NOT LET BACK IN, because the audit these fixes came from
// is explicit that the loss-aversion principle applied literally would end this
// product: no percentage, no meter, no countdown, no verdict, no colour word,
// no urgency the phone did not measure. The legs at the end sweep every string
// this type can produce for those.
//
// Pure Foundation. `run_home_copy_tests.sh` lifts `HomeCopy` out of the real
// ContentView.swift between its ANCHOR markers and compiles it with this file
// and `PlainDuration.swift` — the shipping source, not a copy of it.

@main
struct HomeCopyTests {
    static func main() {
        var checks = 0
        var failures: [String] = []

        func check(_ name: String, _ ok: Bool) {
            checks += 1
            print(ok ? "  ok    \(name)" : "  FAIL  \(name)")
            if !ok { failures.append(name) }
        }

        func says(_ what: String, _ got: String, _ expected: String) {
            check(what + (got == expected ? "" : "\n          got      \"\(got)\"\n          expected \"\(expected)\""),
                  got == expected)
        }

        // ------------------------------------------------------------------
        // THE BROWSER ASK. The cost was always honest; what it never carried
        // was the other side of the trade, sitting three inches below the card.
        // ------------------------------------------------------------------
        print("the browser ask")

        says("one thing waiting: the headline is singular",
             HomeCopy.browserHeadline(waiting: 1), "This one needs your Chrome")
        says("more than one: the headline is plural",
             HomeCopy.browserHeadline(waiting: 4), "These need your Chrome")

        says("one thing waiting: cost and payoff in one sentence",
             HomeCopy.browserBody(waiting: 1),
             "I work inside your own Chrome, using the accounts you're already signed in to. "
             + "I never ask for a password. Two minutes on a computer, once — and the thing "
             + "below starts moving on its own. There's one Chrome setting to flip; the guide "
             + "shows you where.")
        says("three things waiting: the count is in the payoff",
             HomeCopy.browserBody(waiting: 3),
             "I work inside your own Chrome, using the accounts you're already signed in to. "
             + "I never ask for a password. Two minutes on a computer, once — and the 3 things "
             + "below start moving on their own. There's one Chrome setting to flip; the guide "
             + "shows you where.")

        // The count is READ, never assumed. "three" was the number in the
        // proposal for this fix and the number in the audit's example, and a
        // hardcoded one is invisible until the day somebody has two.
        check("the payoff counts what is actually there, not \"three\"",
              HomeCopy.browserBody(waiting: 7).contains("the 7 things below start")
              && !HomeCopy.browserBody(waiting: 7).lowercased().contains("three"))

        // The promise that made the old sentence worth keeping.
        for waiting in [1, 2, 9] {
            check("\(waiting) waiting: still says she never asks for a password",
                  HomeCopy.browserBody(waiting: waiting).contains("I never ask for a password."))
            check("\(waiting) waiting: still says where the one setting is",
                  HomeCopy.browserBody(waiting: waiting).contains("one Chrome setting to flip"))
        }

        // Grammar, in the branch that is easy to get wrong. One shared ending
        // gives "the thing below starts moving on their own", which does not
        // parse, and a sentence that does not parse is one nobody trusts.
        check("the singular payoff says \"its own\", never \"their own\"",
              HomeCopy.browserBody(waiting: 1).contains("on its own")
              && !HomeCopy.browserBody(waiting: 1).contains("their own"))
        check("the plural payoff says \"their own\"",
              HomeCopy.browserBody(waiting: 5).contains("on their own"))

        says("the button prices the tap: one",
             HomeCopy.browserButton(waiting: 1), "Set it up — 1 waiting")
        says("the button prices the tap: many",
             HomeCopy.browserButton(waiting: 12), "Set it up — 12 waiting")

        // ------------------------------------------------------------------
        // THE INTERVIEW ASK. Home gates on "anything left" and then used to
        // describe the whole script, so real work counted for nothing on the
        // one screen asking for more of it.
        // ------------------------------------------------------------------
        print("")
        print("the interview ask")

        // NOTHING ANSWERED YET IS TODAY'S CARD, CHARACTER FOR CHARACTER. This
        // is the pin: the fix was only ever about the person who has already
        // given something, and a first-timer must not be able to tell that
        // anything happened here.
        says("nobody has answered anything: today's title, unchanged",
             HomeCopy.interviewTitle(answered: 0), "Want me to actually know you?")
        says("nobody has answered anything: today's body, unchanged",
             HomeCopy.interviewBody(answered: 0, total: 6),
             "Six questions, in your words. I ask, you answer or skip. "
             + "I never send anything on your behalf without your yes.")
        says("nobody has answered anything: today's button, unchanged",
             HomeCopy.interviewButton(answered: 0, total: 6), "Ask me")

        says("three of six answered: the title asks for the rest",
             HomeCopy.interviewTitle(answered: 3), "Want me to know the rest?")
        says("three of six answered: the body counts what she holds",
             HomeCopy.interviewBody(answered: 3, total: 6),
             "You've answered 3 of 6. I've kept them. The rest are still open — "
             + "I ask, you answer or skip. I never send anything on your behalf without your yes.")
        says("three of six answered: the button counts what is left",
             HomeCopy.interviewButton(answered: 3, total: 6), "Ask me — 3 left")
        says("five of six answered: one left, and it says one",
             HomeCopy.interviewButton(answered: 5, total: 6), "Ask me — 1 left")

        // The promise the card is really making, on both branches.
        for answered in [0, 1, 5] {
            check("\(answered) answered: the consent sentence survives",
                  HomeCopy.interviewBody(answered: answered, total: 6)
                    .contains("I never send anything on your behalf without your yes."))
            check("\(answered) answered: it still offers the skip",
                  HomeCopy.interviewBody(answered: answered, total: 6)
                    .contains("you answer or skip"))
        }

        // THE NUMERAL FOLLOWS THE SCRIPT. "Six questions" was typed into the
        // prose, so the day a seventh question ships the card goes on saying
        // six. This is the whole reason the sentence is built rather than
        // written.
        check("a seven-question script opens \"Seven questions\"",
              HomeCopy.interviewBody(answered: 0, total: 7).hasPrefix("Seven questions,"))
        check("a five-question script opens \"Five questions\"",
              HomeCopy.interviewBody(answered: 0, total: 5).hasPrefix("Five questions,"))
        says("spelled out: six", HomeCopy.spelledOut(6), "Six")
        says("spelled out: one", HomeCopy.spelledOut(1), "One")
        says("past twelve, digits — English stops being the shorter way",
             HomeCopy.spelledOut(13), "13")

        // A count that cannot go backwards on the button, whatever it is given.
        var negatives: [String] = []
        for total in 1...12 {
            for answered in 0...total {
                let label = HomeCopy.interviewButton(answered: answered, total: total)
                if label.contains("-") { negatives.append("\(answered)/\(total): \(label)") }
            }
        }
        check("no arrangement of answered/total puts a negative on the button"
              + (negatives.isEmpty ? "" : " — \(negatives.prefix(3))"), negatives.isEmpty)

        // ------------------------------------------------------------------
        // THE MICROPHONE, TAKEN AWAY. `suspended` stays true and `isListening`
        // stays true when the watchdog never gets it back, so this line claimed
        // an ongoing recovery for the rest of the day.
        // ------------------------------------------------------------------
        print("")
        print("the microphone, taken away")

        // NOTHING MEASURED, NOTHING SAID: today's sentence verbatim. `.unknown`
        // and `.stoppedByOwner` both arrive here as nil, and a gap invented for
        // either would be a number about nothing.
        says("no measurement: today's sentence, unchanged",
             HomeCopy.micInterrupted(unheardForSeconds: nil),
             "Mic interrupted, taking it back…")
        says("a measurement of zero is not a gap either",
             HomeCopy.micInterrupted(unheardForSeconds: 0),
             "Mic interrupted, taking it back…")
        says("a negative can only be a clock that moved: still silent",
             HomeCopy.micInterrupted(unheardForSeconds: -30),
             "Mic interrupted, taking it back…")

        says("four minutes gone, named",
             HomeCopy.micInterrupted(unheardForSeconds: 260),
             "Mic interrupted 4 min ago, still trying to take it back. I've missed that stretch.")
        says("six hours and twenty minutes gone, in the same sentence",
             HomeCopy.micInterrupted(unheardForSeconds: 22_800),
             "Mic interrupted 6 hr 20 min ago, still trying to take it back. "
             + "I've missed that stretch.")
        says("forty-four seconds gone",
             HomeCopy.micInterrupted(unheardForSeconds: 44),
             "Mic interrupted 44 seconds ago, still trying to take it back. "
             + "I've missed that stretch.")

        // THE WORDS COME FROM `PlainDuration` AND NOWHERE ELSE. Three screens
        // now report this same `ListenTally.unheardForSeconds`, and the refusal
        // to give a verdict rests on the same seconds reading the same way on
        // all of them.
        var reworded: [String] = []
        for seconds in stride(from: 1, through: 200_000, by: 97) {
            if !HomeCopy.micInterrupted(unheardForSeconds: seconds)
                .contains(PlainDuration.words(seconds)) {
                reworded.append("\(seconds)")
            }
        }
        check("every gap is worded by PlainDuration"
              + (reworded.isEmpty ? "" : " — \(reworded.prefix(3))"), reworded.isEmpty)

        // The sentence never stops saying it is still trying, which is the
        // thing on the card that is actually true of the app's state.
        check("the long version still says it is trying to take the mic back",
              HomeCopy.micInterrupted(unheardForSeconds: 9_000)
                .contains("still trying to take it back"))

        // ------------------------------------------------------------------
        // THE DAY-ZERO EXAMPLES. Hidden from VoiceOver, so a first-timer using
        // it got the promise and no sample of the delivery at all.
        // ------------------------------------------------------------------
        print("")
        print("the day-zero examples")

        says("the label reads the fixtures back",
             HomeCopy.exampleCardsLabel,
             "Example. When I catch something it looks like this. "
             + "Heard: I'll get that invoice over to you tonight. "
             + "Ready: Draft the invoice email to Devon.")
        check("it says it is an example before anything else",
              HomeCopy.exampleCardsLabel.hasPrefix("Example."))
        // Built FROM the drawn strings, never beside them: a hand-written copy
        // would go stale the first time somebody edited the cards, and a
        // VoiceOver user would then be read a screen that is not on the screen.
        check("the label carries the heard line the screen actually draws",
              HomeCopy.exampleCardsLabel.contains(HomeCopy.exampleHeard))
        check("the label carries the job the screen actually draws",
              HomeCopy.exampleCardsLabel.contains(HomeCopy.exampleGoal))

        // ------------------------------------------------------------------
        // THE LAW LEGS. Everything this type can say, swept for the shapes the
        // audit forbids outright.
        // ------------------------------------------------------------------
        print("")
        print("what may never appear in any of it")

        var everything: [String] = [HomeCopy.exampleCardsLabel,
                                    HomeCopy.micInterrupted(unheardForSeconds: nil)]
        for n in 0...13 {
            everything.append(HomeCopy.browserHeadline(waiting: max(1, n)))
            everything.append(HomeCopy.browserBody(waiting: max(1, n)))
            everything.append(HomeCopy.browserButton(waiting: max(1, n)))
            everything.append(HomeCopy.interviewTitle(answered: n))
            everything.append(HomeCopy.interviewBody(answered: n, total: 6))
            everything.append(HomeCopy.interviewButton(answered: n, total: 6))
            everything.append(HomeCopy.micInterrupted(unheardForSeconds: n * 601))
        }

        check("no percentage anywhere — a count is not a score",
              everything.allSatisfy { !$0.contains("%") })

        // A verdict is the one thing `ListeningDiagnosticsView.swift:38-43`
        // refuses by name, and these sentences sit inside that argument.
        let verdicts = ["too long", "too many", "urgent", "warning", "critical",
                        "failing", "you're missing out", "don't lose", "before it's too late",
                        "hurry", "act now", "last chance", "risk it"]
        var judged: [String] = []
        for line in everything {
            for verdict in verdicts where line.lowercased().contains(verdict) {
                judged.append("\"\(verdict)\" in \"\(line.prefix(48))…\"")
            }
        }
        check("no verdict, no manufactured urgency, no guilt"
              + (judged.isEmpty ? "" : " — \(judged.prefix(3))"), judged.isEmpty)

        // A countdown is a deadline the phone did not measure. Nothing here
        // counts DOWN to anything: the only numbers are how many are waiting,
        // how many questions are answered, and how long the mic has been gone.
        let countdowns = ["remaining", "expires", "left today", "in the next",
                          "within", "deadline"]
        var clocks: [String] = []
        for line in everything {
            for word in countdowns where line.lowercased().contains(word) {
                clocks.append("\"\(word)\" in \"\(line.prefix(48))…\"")
            }
        }
        check("no countdown and no deadline"
              + (clocks.isEmpty ? "" : " — \(clocks.prefix(3))"), clocks.isEmpty)

        print("")
        if failures.isEmpty {
            print("HomeCopy: all \(checks) checks passed")
        } else {
            print("HomeCopy: \(failures.count) of \(checks) checks FAILED")
            for name in failures { print("  - \(name)") }
            exit(1)
        }
    }
}
