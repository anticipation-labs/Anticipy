import Foundation

// Where a job lands on Home, and what a called-off card leads with.
//
// THE DEFECT THIS SUITE EXISTS FOR. `cancelled` matched none of Home's three
// filters, so every job the owner stopped rendered NOWHERE. The tap looked like
// it had worked; the row simply left the screen. And in the one case that
// matters, what left with it was the sentence "It may already have gone through
// before I stopped. Worth a check." — because the same PATCH that writes that
// sentence into `result` also writes `effect_uncertain: false`, so
// `JobReceiptPolicy.safetyLine` answers "Nothing you told me was lost."
// `result` is the ONLY surviving carrier of the warning.
//
// docs ex 36 / ex 50: the duplicate booking nobody checks for.
//
// The policy under test is lifted out of ContentView.swift between its ANCHOR
// markers by run_home_feed_tests.sh and compiled here — the real source, not a
// copy of it. That runner also holds the WIRING legs: whether Home still asks
// this policy at all, and whether `safetyLine` has crept onto the cancelled
// branch. Behaviour without wiring proves nothing.

@main
enum HomeFeedTests {

    // The exact string `stopRunning` writes. The runner greps AnticipyApp.swift
    // for this phrase, so a fixture that has drifted from the shipping sentence
    // is caught there rather than quietly measuring a string nothing produces.
    static let stopWarning =
        "You stopped this. It may already have gone through before I stopped. Worth a check."
    static let stopPlain = "You stopped this."
    // WHAT THE CARD SAYS WHEN THE SERVER WROTE NOTHING. It is a claim about
    // this app's own action AFTER the tap and about nothing else. See
    // `deniedIt` below for the sentence it replaced and why.
    static let fallback = "I did nothing further."
    // The exact sentence this card shipped with for one commit, kept as a
    // fixture so the regression has a name. "Don't do it" is offered on
    // `awaiting_confirm` AND on `needs_user` — a run that stopped partway and
    // can carry `effect_uncertain` — and `decline` clears that flag on its way
    // out, so by the time the card renders the two are indistinguishable. A
    // flat denial over the second one is ex 36's duplicate booking with a
    // denial printed on it.
    static let deniedIt = "You called this off. I didn't do it."

    static func place(_ status: String, _ lane: String? = nil) -> HomeFeedPolicy.Placement {
        HomeFeedPolicy.placement(status: status, lane: lane)
    }

    static func lead(_ result: String?) -> String {
        HomeFeedPolicy.calledOffLead(result: result)
    }

    static func settled(_ status: String, _ effectUncertain: Bool? = nil) -> Bool {
        HomeFeedPolicy.settled(status: status, effectUncertain: effectUncertain)
    }

    /// A Done section as the screen hands it over: newest terminal update
    /// first, each row reduced to the two fields the cap is allowed to read.
    static func shelved(_ rows: [(String, Bool?)], shelf: Int = 8) -> [Int] {
        HomeFeedPolicy.shelved(rows.map { (status: $0.0, effectUncertain: $0.1) },
                               shelf: shelf)
    }

    /// `n` receipts, the ordinary contents of a shelf.
    static func receipts(_ n: Int) -> [(String, Bool?)] {
        Array(repeating: ("done", Bool?.some(false)), count: n)
    }

    static func unreachable(_ state: OwnerMirror.PhoneState) -> Bool {
        HomeFeedPolicy.sayUnreachable(phoneState: state)
    }

    static func main() {
        var failures = 0
        func check(_ name: String, _ ok: Bool) {
            print("\(ok ? "PASS" : "FAIL"): \(name)")
            if !ok { failures += 1 }
        }

        // ------------------------------------------------------------------
        // PLACEMENT
        // ------------------------------------------------------------------

        // THE FIX. A stopped job reaches a section at all.
        check("a cancelled errand files as terminal", place("cancelled") == .done)
        check("a cancelled errand is not hidden", place("cancelled") != .hidden)
        check("a cancelled errand is not still handling", place("cancelled") != .handling)
        check("a cancelled errand does not claim your attention",
              place("cancelled") != .needsYou)

        // What was already true and must stay true.
        check("done is terminal", place("done") == .done)
        check("failed is terminal", place("failed") == .done)
        check("queued is handling", place("queued") == .handling)
        check("running is handling", place("running") == .handling)
        check("awaiting_confirm needs you", place("awaiting_confirm") == .needsYou)
        check("needs_user needs you", place("needs_user") == .needsYou)

        // A lane the feed knows nothing about is an ordinary errand.
        check("no lane is an errand", place("running", nil) == .handling)
        check("an empty lane is an errand", place("running", "") == .handling)
        check("the research lane is an errand", place("done", "research") == .done)

        // A SUPERVISED READ IS WATCHED, NOT QUEUED. It must never appear under
        // "Waiting for your browser" while the person sits there watching it,
        // nor file under Done as an errand nobody asked for.
        check("a watched read is not handling",
              place("running", "supervised_read") == .hidden)
        check("a watched read is not queued work",
              place("queued", "supervised_read") == .hidden)
        check("a watched read does not file under Done",
              place("done", "supervised_read") == .hidden)
        check("a watched read that failed does not file under Done",
              place("failed", "supervised_read") == .hidden)
        check("a watched read that was called off does not file under Done",
              place("cancelled", "supervised_read") == .hidden)

        // PINNED, because it is the surprising half AND it is the shipping
        // behaviour: `needsOK` never consulted `isErrand`, so a watched read
        // that stopped and asked for something has always been given a card.
        // Testing the lane first would take that card away from the two
        // statuses that cannot afford to lose it — a read stuck behind a login
        // would go silent.
        check("a watched read still gets a card when it needs you",
              place("needs_user", "supervised_read") == .needsYou)
        check("a watched read still gets a card when it awaits your word",
              place("awaiting_confirm", "supervised_read") == .needsYou)

        // A status this build has never heard of says nothing, rather than
        // filing itself under a heading that would then claim something about
        // it.
        check("an unknown status is hidden", place("archived") == .hidden)
        check("an empty status is hidden", place("") == .hidden)
        check("status is matched exactly, not loosely",
              place("cancelled_by_owner") == .hidden)
        check("case matters", place("Cancelled") == .hidden)

        // ------------------------------------------------------------------
        // WHAT THE CALLED-OFF CARD LEADS WITH
        // ------------------------------------------------------------------

        // THE WHOLE POINT. The warning reaches the screen, word for word.
        check("the warning survives to the card", lead(stopWarning) == stopWarning)
        check("the warning is not paraphrased",
              lead(stopWarning).contains("Worth a check"))
        check("the warning is not replaced by the fallback",
              lead(stopWarning) != fallback)
        check("a plain stop keeps its own words", lead(stopPlain) == stopPlain)

        // `decline` writes the cancellation fields and no result at all, so
        // this is the only branch where the phone speaks for itself.
        check("nothing written falls back", lead(nil) == fallback)
        check("an empty result falls back", lead("") == fallback)
        check("a blank result falls back", lead("   \n\t ") == fallback)

        // THE FALLBACK IS PINNED TO ITS EXACT REVIEWED WORDS, and that is the
        // assertion rather than any predicate about them. A predicate over the
        // sentence ("does it contain the word nothing") is a word list deciding
        // what the sentence MEANS, which is the one thing this repo forbids —
        // and the first version of this check was exactly that, and would have
        // gone red on the honest sentence while passing the denial.
        check("the fallback is the reviewed sentence", lead(nil) == fallback)
        // The named regression. This card cannot assert that the errand did not
        // happen: "Don't do it" is offered on `needs_user` too, where the run
        // stopped partway and `effect_uncertain` may have been true right up
        // until `decline` cleared it.
        check("the fallback is not the denial it used to be", lead(nil) != deniedIt)
        check("no result can produce the denial", lead("") != deniedIt)
        check("a blank result cannot produce the denial", lead("  ") != deniedIt)

        // ------------------------------------------------------------------
        // THE CARD SAYS WHAT IT IS, WHATEVER THE SERVER WROTE
        // ------------------------------------------------------------------
        //
        // `decline` never writes `result`, so on that path the lead is whatever
        // the engine last said — for a stuck job, an offer to try again, on a
        // row that will never be tried again. The kicker is the only thing on
        // the card that is true of every cancellation, so it is pinned here and
        // its presence on the branch is pinned by the runner.
        check("the kicker says what the card is",
              HomeFeedPolicy.calledOffKicker == "Stopped")
        check("the kicker is not the lead", HomeFeedPolicy.calledOffKicker != lead(nil))
        check("the kicker is not empty", !HomeFeedPolicy.calledOffKicker.isEmpty)

        // AND IT NAMES NO ACTOR. `cancelled` is not the owner's word: the brain
        // writes it to take a card off the desk he was NEVER TOLD ABOUT ("I
        // picked this up from the room rather than from you, so I've dropped
        // it"; "she was not allowed to raise this"), and the extension writes
        // it when a run spends its last attempt. Every one of these is the same
        // sentence with the actor filled in, and every one of them is false on
        // those rows — which is the defect this card exists to stop, printed
        // the other way round.
        check("the kicker does not tell him he cancelled it",
              HomeFeedPolicy.calledOffKicker != "You called this off")
        check("the kicker is not the old denial either",
              HomeFeedPolicy.calledOffKicker != deniedIt)
        check("the kicker does not claim he stopped it",
              HomeFeedPolicy.calledOffKicker != "You stopped this")

        // The two endings `AnswerRoutePolicy` writes into `result` are led with
        // verbatim, and the kicker must not contradict either. "You handled it
        // yourself" is not a cancellation the owner asked for, and a kicker
        // asserting one over it would be arguing with the sentence below it.
        check("the handled-it-yourself ending survives to the card",
              lead("You handled it yourself: \u{201C}I booked it\u{201D}. I did nothing further.")
                  == "You handled it yourself: \u{201C}I booked it\u{201D}. I did nothing further.")
        check("the brain's own drop survives to the card",
              lead("I picked this up from the room rather than from you, so I've dropped it.")
                  == "I picked this up from the room rather than from you, so I've dropped it.")

        // Whitespace comes off the edges; the sentence inside is untouched.
        check("surrounding whitespace is trimmed",
              lead("  \(stopWarning)  ") == stopWarning)
        check("a one-word result is still the lead", lead("Stopped.") == "Stopped.")

        // ------------------------------------------------------------------
        // WHAT DONE'S CAP MAY CUT
        // ------------------------------------------------------------------
        //
        // The section is drawn newest terminal update first and capped. A
        // warning-bearing cancellation can still age past ordinary receipts,
        // so the cap counts settled cards only rather than swallowing it.

        check("a cancellation is never settled", !settled("cancelled"))
        check("a cancellation is not settled even when the row says false",
              !settled("cancelled", false))
        check("a cancellation is not settled when the row says uncertain",
              !settled("cancelled", true))

        // A failure the row itself still marks uncertain carries the same
        // sentence out of `JobReceiptPolicy.safetyLine` — "so you don't end up
        // with two" — and was just as droppable before any of this.
        check("a failure the row marks uncertain is not settled",
              !settled("failed", true))

        // Everything else is a receipt on a shelf and may scroll away.
        check("a plain failure is settled", settled("failed", false))
        check("a failure that says nothing about the effect is settled",
              settled("failed"))
        check("a completed job is settled", settled("done", false))
        check("a completed job that says nothing is settled", settled("done"))

        // `nil` is "the row never said", which is not the same as the row
        // saying it is in doubt. Reading absence as uncertainty would exempt
        // almost every card from the cap and quietly retire it.
        check("an unspoken effect is not read as uncertainty",
              settled("done", nil) && settled("failed", nil))

        // One answer to "did the owner stop it", asked by the card and by the
        // cap. Two spellings of one question is how `cancelled` came to match
        // nothing at all.
        check("the policy names a cancellation", HomeFeedPolicy.wasCalledOff(status: "cancelled"))
        check("a failure is not a cancellation", !HomeFeedPolicy.wasCalledOff(status: "failed"))
        check("a completed job is not a cancellation", !HomeFeedPolicy.wasCalledOff(status: "done"))
        check("cancellation is matched exactly",
              !HomeFeedPolicy.wasCalledOff(status: "cancelled_by_owner"))

        // ------------------------------------------------------------------
        // THE WALK PAST THE SHELF
        // ------------------------------------------------------------------
        //
        // `settled` is a predicate about one row. The defect is about a WALK
        // over many, and the walk is where it can go wrong in one word: a scan
        // that STOPS at the shelf's edge instead of stepping past it drops the
        // very card the rule keeps, while every predicate here still answers
        // correctly. That mutation survived this suite until these cases
        // existed, so they are the reason the walk is a function at all.

        // The ordinary phone: nothing unsettled, exactly the shelf, in order.
        check("a shelf of receipts is cut at the shelf",
              shelved(receipts(20)) == Array(0..<8))
        check("fewer receipts than the shelf are all drawn",
              shelved(receipts(3)) == [0, 1, 2])
        check("an empty section draws nothing", shelved([]).isEmpty)

        // THE FIX: an errand begun this morning and stopped tonight is the
        // OLDEST row of the batch and sorts below every quick job that began
        // and finished after it.
        check("a cancellation under a full shelf is still drawn",
              shelved(receipts(8) + [("cancelled", nil)]) == Array(0..<8) + [8])
        check("a cancellation under a day of receipts is still drawn",
              shelved(receipts(30) + [("cancelled", nil)]).last == 30)
        check("a failure the row still marks uncertain is drawn from down there",
              shelved(receipts(12) + [("failed", true)]).last == 12)

        // THE ONE-WORD FAILURE, named. A settled row past the edge is stepped
        // OVER, never stopped at: the cancellation below it is down there for
        // the same reason a stop would never reach it — because it is old.
        check("a receipt past the shelf does not end the walk",
              shelved(receipts(9) + [("cancelled", nil)]) == Array(0..<8) + [9])
        check("several receipts past the shelf do not end the walk",
              shelved(receipts(20) + [("cancelled", nil)]).last == 20)

        // The shelf is spent by receipts only, so an unsettled card costs the
        // section nothing and cannot push a receipt off it.
        check("an unsettled card does not spend the shelf",
              shelved([("cancelled", nil)] + receipts(8)) == Array(0..<9))
        check("a section of nothing but unsettled cards is drawn whole",
              shelved(Array(repeating: ("cancelled", Bool?.none), count: 12)).count == 12)

        // Nothing is promoted. What survives the cut lands exactly where
        // newest-first already put it: at the bottom.
        let mixed = receipts(4) + [("cancelled", nil)] + receipts(6)
            + [("failed", true)] + receipts(3)
        check("the order given is the order drawn", shelved(mixed) == shelved(mixed).sorted())
        check("nothing is drawn twice", Set(shelved(mixed)).count == shelved(mixed).count)
        check("the shelf still spends on receipts in a mixed section",
              shelved(mixed).filter { mixed[$0].0 == "done" }.count == 8)
        check("both unsettled cards in a mixed section survive",
              shelved(mixed).contains(4) && shelved(mixed).contains(11))

        // ------------------------------------------------------------------
        // SAYING THERE IS NO WAY TO REACH SOMEBODY
        // ------------------------------------------------------------------

        check("the canonical account has no number: say so",
              unreachable(.none))

        // THE GUARD THAT KEEPS THIS FROM BEING A CONFIDENT LIE, and it is the
        // ACCOUNT that answers, never the device-local mirror. Unknown is a
        // real state after a failed read; Home must not turn it into "none".
        check("nobody has asked successfully yet: say nothing",
              !unreachable(.unknown))

        check("a canonical valid number says nothing", !unreachable(.valid))
        check("a canonical malformed number gets repair copy, not no-number copy",
              !unreachable(.invalid))

        // One completed job is one result on Home. The worker writes both the
        // terminal job and an anticipy_says receipt linked by external_event_id;
        // the visible Done card owns that result while it is on the shelf.
        let visibleTerminalIDs: Set<String> = ["job-17"]
        let matchingEventIsVisible = HomeFeedPolicy.showsDoneEvent(
            externalEventID: "job-result:job-17",
            visibleTerminalJobIDs: visibleTerminalIDs)
        check("one terminal job plus its linked result event renders once",
              1 + (matchingEventIsVisible ? 1 : 0) == 1)
        let briefingEventIsVisible = HomeFeedPolicy.showsDoneEvent(
            externalEventID: "job-result:job-17",
            visibleTerminalJobIDs: visibleTerminalIDs)
        check("Done plus both event-backed Home surfaces still renders one result",
              1 + (matchingEventIsVisible ? 1 : 0)
                + (briefingEventIsVisible ? 1 : 0) == 1)
        check("a result whose terminal card is off the shelf remains visible",
              HomeFeedPolicy.showsDoneEvent(
                externalEventID: "job-result:job-18",
                visibleTerminalJobIDs: visibleTerminalIDs))
        check("an unrelated external event namespace remains visible",
              HomeFeedPolicy.showsDoneEvent(
                externalEventID: "calendar-result:job-17",
                visibleTerminalJobIDs: visibleTerminalIDs))
        check("an empty job-result id does not swallow an event",
              HomeFeedPolicy.showsDoneEvent(
                externalEventID: "job-result:",
                visibleTerminalJobIDs: visibleTerminalIDs))

        if failures > 0 {
            print("HomeFeedTests: \(failures) failed")
            exit(1)
        }
        print("HomeFeedTests: all passed")
    }
}
