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
    static let fallback = "You called this off. I didn't do it."

    static func place(_ status: String, _ lane: String? = nil) -> HomeFeedPolicy.Placement {
        HomeFeedPolicy.placement(status: status, lane: lane)
    }

    static func lead(_ result: String?) -> String {
        HomeFeedPolicy.calledOffLead(result: result)
    }

    static func unreachable(_ phone: String, _ reached: Bool) -> Bool {
        HomeFeedPolicy.sayUnreachable(ownerPhone: phone, reachedTheServer: reached)
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

        // The fallback claims only what THIS APP did. It must never say the
        // errand did not happen out in the world, because on the `stopRunning`
        // path nobody knows that.
        check("the fallback never claims nothing happened out there",
              !lead(nil).lowercased().contains("nothing"))

        // Whitespace comes off the edges; the sentence inside is untouched.
        check("surrounding whitespace is trimmed",
              lead("  \(stopWarning)  ") == stopWarning)
        check("a one-word result is still the lead", lead("Stopped.") == "Stopped.")

        // ------------------------------------------------------------------
        // SAYING THERE IS NO WAY TO REACH SOMEBODY
        // ------------------------------------------------------------------

        check("no number, and we have read the account: say so",
              unreachable("", true))
        check("a number on file: say nothing", !unreachable("+16045550142", true))

        // THE GUARD THAT KEEPS THIS FROM BEING A CONFIDENT LIE. `ownerPhone` is
        // a device-local mirror, and it is empty in exactly the same way
        // whether the account has no number or this launch has not asked yet.
        // Home does not get to say "I can't reach you" from a session that has
        // never once reached its own server.
        check("no number and no read: say nothing", !unreachable("", false))
        check("a number and no read: still say nothing",
              !unreachable("+16045550142", false))

        // A field holding a space cannot be texted.
        check("a blank number is no number", unreachable("   ", true))
        check("a newline is no number", unreachable("\n", true))

        if failures > 0 {
            print("HomeFeedTests: \(failures) failed")
            exit(1)
        }
        print("HomeFeedTests: all passed")
    }
}
