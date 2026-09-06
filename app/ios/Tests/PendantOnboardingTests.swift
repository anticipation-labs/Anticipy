import Foundation

// The pendant's onboarding decisions, walked. Compiled by
// run_pendant_onboarding_tests.sh against the production policy; this file is
// that suite's main.swift, so it may hold top-level code.

var failures = 0
func check(_ ok: Bool, _ name: String, _ detail: @autoclosure () -> String = "") {
    if ok { print("PASS: \(name)") } else { failures += 1; print("FAIL: \(name) \(detail())") }
}

typealias P = PendantOnboardingPolicy

// ------------------------------------------------- the branch, and its weight
// The decision the whole flow rests on: there is no shipping pendant, and the
// phone is the primary ear, so the person WITHOUT hardware is on the main road.
check(P.next(after: .offer, answer: .notYet) == nil,
      "answering 'not yet' leaves the pendant flow entirely")
check(P.next(after: .offer, answer: .hasOne) == .wake,
      "answering 'I have one' is the branch, not the default")
check(P.next(after: .offer) == nil,
      "with no answer at all the flow does not wander into the hardware")

check(P.next(after: .wake) == .looking, "wake leads to looking")
check(P.next(after: .looking) == .pairing, "looking leads to pairing")
check(P.next(after: .pairing) == .wearing, "pairing leads to wearing")
check(P.next(after: .wearing) == .done, "wearing leads to done")
check(P.next(after: .done) == nil, "and done is the end")

// The copy carries that weight or it does not hold. The primary control must be
// the one WITHOUT hardware, and nothing may frame going on as skipping.
check(P.Copy.offerPrimary == "Continue without one",
      "the primary action is the road without hardware", P.Copy.offerPrimary)
let banned = ["skip", "later", "not now", "maybe"]
for word in banned {
    check(!P.Copy.offerPrimary.lowercased().contains(word),
          "the primary action does not say '\(word)'")
}
check(P.Copy.offerSecondary == "I have a pendant",
      "and owning one is the quiet second line")
check(!P.Copy.offerBody.lowercased().contains("without it")
        && !P.Copy.offerBody.lowercased().contains("miss out"),
      "the offer never says the product is lesser without the hardware")
check(P.Copy.offerBody.lowercased().contains("nothing is missing"),
      "it says the opposite, plainly")
check(!P.Copy.offerFootnote.isEmpty,
      "and it says the door stays open in Settings")

// ------------------------------------------------------------ the radio faces
// A screen that says "Looking…" while nothing is searching is the one lie this
// flow can tell, so `searching` is checked state by state.
check(P.face(.scanning).searching, "scanning moves")
check(P.face(.warmingUp).searching, "so does waiting for the radio")
check(P.face(.nothingFound).searching, "and so does still-looking-after-a-while")
check(!P.face(.switchedOff).searching, "a switched-off radio is still")
check(!P.face(.needsPermission).searching, "so is one nobody has allowed yet")
check(!P.face(.connected(name: "x")).searching, "and so is a finished connection")

for radio: P.Radio in [.warmingUp, .scanning, .foundSomething(count: 1),
                       .connecting(name: "P"), .connected(name: "P"),
                       .needsPermission, .switchedOff, .nothingFound] {
    let f = P.face(radio)
    check(!f.title.isEmpty && !f.body.isEmpty, "\(radio) says what it is and what to do")
    check(f.offersWayOut, "\(radio) keeps a way out on screen")
}
check(P.face(.foundSomething(count: 1)).title == "Found one",
      "one device is 'one', not '1'")
check(P.face(.foundSomething(count: 3)).title == "Found 3", "several are counted")
check(P.face(.connected(name: "Pendant 7A")).title.contains("Pendant 7A"),
      "a connected device is named")

// -------------------------------------------------------------- what is shown
// RSSI IS NOT A PERCENTAGE. Dressing it as one is a number somebody believes.
check(P.Candidate(id: "a", name: "a", rssi: nil).nearness == nil,
      "an unmeasured signal draws nothing at all")
check(P.Candidate(id: "a", name: "a", rssi: -40).nearness == 3, "very near is four bars")
check(P.Candidate(id: "a", name: "a", rssi: -60).nearness == 2, "near is three")
check(P.Candidate(id: "a", name: "a", rssi: -80).nearness == 1, "far is two")
check(P.Candidate(id: "a", name: "a", rssi: -100).nearness == 0, "very far is one")

// Strongest first: the pendant in somebody's hand is the one they mean.
let found = [P.Candidate(id: "far", name: "far", rssi: -90),
             P.Candidate(id: "near", name: "near", rssi: -40),
             P.Candidate(id: "mid", name: "mid", rssi: -65)]
check(P.ordered(found).map(\.id) == ["near", "mid", "far"], "nearest first")
let tied = [P.Candidate(id: "b", name: "b", rssi: -50),
            P.Candidate(id: "a", name: "a", rssi: -50)]
check(P.ordered(tied).map(\.id) == ["a", "b"],
      "a tie breaks by id, so the list does not reshuffle under a thumb")
check(P.ordered([]).isEmpty, "nothing found, nothing listed")
let unmeasured = [P.Candidate(id: "x", name: "x", rssi: nil),
                  P.Candidate(id: "y", name: "y", rssi: -70)]
check(P.ordered(unmeasured).first?.id == "y",
      "a measured device outranks one that reported nothing")

// ------------------------------------------------------------------ the close
check(P.doneLine(deviceName: "Pendant 7A").contains("Pendant 7A"),
      "the closing line names the device when there is a name")
check(!P.doneLine(deviceName: nil).isEmpty && !P.doneLine(deviceName: "").isEmpty,
      "and says something true when there is not")
check(!P.doneLine(deviceName: nil).contains("Optional"),
      "and never leaks a Swift optional onto a screen")

// Patience: long enough not to give up in front of somebody still fetching the
// pendant from the next room.
check(P.patience >= 10, "it looks for at least ten seconds before saying nothing yet")

if failures == 0 {
    print("PendantOnboardingTests: all passed")
} else {
    print("PendantOnboardingTests: \(failures) case(s) came back wrong")
    exit(1)
}
